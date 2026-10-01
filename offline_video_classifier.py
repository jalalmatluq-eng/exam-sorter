"""
offline_video_classifier.py
----------------------------
نظام تصنيف الفيديو الأوفلاين الحقيقي لتطبيق رتّب (Rateb AI):
- تصنيف بصري متعدد الإطارات (Temporal Multi-Frame Analysis):
  استخراج 5 إطارات موزعة زمنياً (10%, 30%, 50%, 70%, 90%).
- استخراج المؤشرات البصرية الخفيفة:
  * كشف الشرائح والنصوص الأكاديمية والسبورات (Edge & Text Density).
  * كشف الوجوه والأشخاص عبر الإطارات (Face & Person Dynamics).
  * قياس الاستقرار البصري ومعدل الحركة والقطع (Scene Stability & Motion Score).
  * الأبعاد ونسبة العرض إلى الارتفاع (Aspect Ratio: سينمائي، عمودي، قياسي).
  * المدة الزمنية والمؤشرات المساعدة.
- تصويت ترجيحي عبر الإطارات وحساب درجة الثقة (Confidence Score).
- تصنيفات واضحة:
  * فيديوهات مضحكة
  * محاضرات ودروس
  * أفلام ومسلسلات
  * أغاني وأناشيد
  * فيديوهات شخصية
  * خارج التصنيف
  * يحتاج مراجعة
- نظام كاش سريع ودائم يمنع تكرار التحليل لنفس الفيديو.
- تشغيل آمن ومضبوط للذاكرة مع دعم الإلغاء وتقدم العمل (Progress & Cancellation).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

try:
    import cv2
except (ImportError, Exception):
    cv2 = None  # type: ignore

logger = logging.getLogger("OfflineVideoClassifier")

MODEL_VERSION = "2.0.0-hybrid-vision"

# التصنيفات الرسمية المعتمدة
CATEGORY_FUNNY = "فيديوهات مضحكة"
CATEGORY_LECTURE = "محاضرات ودروس"
CATEGORY_MOVIES = "أفلام ومسلسلات"
CATEGORY_SONGS = "أغاني وأناشيد"
CATEGORY_PERSONAL = "فيديوهات شخصية"
CATEGORY_UNCLASSIFIED = "خارج التصنيف"
CATEGORY_NEEDS_REVIEW = "يحتاج مراجعة"

# الكلمات المساعدة (Auxiliary Clues)
AUX_KEYWORDS: dict[str, list[str]] = {
    CATEGORY_FUNNY: [
        "مضحك", "ضحك", "طقطقة", "نكتة", "كوميدي", "مقالب", "مقلب", "تحشيش", "فرفشة",
        "funny", "meme", "memes", "joke", "prank", "comedy", "tiktok", "reels", "shorts", "fail", "fyp",
    ],
    CATEGORY_LECTURE: [
        "محاضرة", "محاضره", "شرح", "درس", "كورس", "دورة", "تعليم", "جامعة", "أكاديمي", "دكتور", "أستاذ",
        "lecture", "tutorial", "lesson", "course", "study", "class", "udemy", "coursera", "webinar",
        "ch1", "ch2", "ch3", "ch4", "database", "python", "programming", "code", "excel", "math",
    ],
    CATEGORY_MOVIES: [
        "فيلم", "مسلسل", "حلقة", "سلسلة", "موسم", "سينما", "مترجم",
        "movie", "film", "episode", "season", "series", "cinema", "bluray", "web-dl", "x264", "x265",
        "netflix", "shahid", "s01", "s02", "e01", "e02",
    ],
    CATEGORY_SONGS: [
        "أغنية", "اغنية", "أغاني", "اغاني", "أنشودة", "انشودة", "أناشيد", "نشيد", "كليب", "موسيقى", "طرب",
        "song", "songs", "track", "music", "audio", "clip", "official video", "lyric", "lyrics", "remix",
    ],
    CATEGORY_PERSONAL: [
        "vlog", "family", "trip", "selfie", "رحلة", "عائلة", "طلعة", "حفلة", "شخصي", "عيد ميلاد",
    ],
}


@dataclass
class VideoClassificationResult:
    category: str
    confidence: float
    status: str  # 'success', 'needs_review', 'read_failed', 'model_unavailable'
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_video_cache_path() -> Path:
    """مسار ملف تخزين الكاش المحلي لتصنيفات الفيديو"""
    try:
        from android import mActivity  # type: ignore
        ctx = mActivity.getApplicationContext()
        p = Path(ctx.getFilesDir().getAbsolutePath()) / "video_classification_cache.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        pass

    try:
        from kivy.app import App
        app = App.get_running_app()
        if app and hasattr(app, "user_data_dir") and app.user_data_dir:
            p = Path(app.user_data_dir) / "video_classification_cache.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass

    p = Path(__file__).resolve().parent / "assets" / "video_classification_cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_video_cache() -> dict[str, Any]:
    p = get_video_cache_path()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_video_cache(cache_data: dict[str, Any]) -> None:
    try:
        p = get_video_cache_path()
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug("تعذر حفظ كاش الفيديو: %s", e)


def is_offline_video_model_available() -> bool:
    """التحقق مما إذا كان محرك تحليل الفيديو الأوفلاين متاحاً وقابلاً للتشغيل"""
    # يعتمد التحليل البصري على OpenCV و/أو محرك أندرويد الأصلي MediaMetadataRetriever
    try:
        from kivy.utils import platform
        if platform == "android":
            return True
    except Exception:
        pass
    return cv2 is not None


def _get_file_cache_key(file_path: str) -> str:
    """توليد مفتاح تجزئة فريد ومستقر للملف بناءً على المسار والحجم وتاريخ التعديل وإصدار المحرك"""
    try:
        st = os.stat(file_path)
        raw = f"{file_path}_{st.st_size}_{int(st.st_mtime)}_{MODEL_VERSION}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(file_path.encode("utf-8")).hexdigest()


def _read_frame_safe(video_path: str, ratio: float) -> np.ndarray | None:
    """استخراج إطار محدد بنسبة مئوية بأمان من الفيديو مع ضغط الذاكرة الفوري"""
    # 1. محاولة أندرويد الأصلي
    try:
        from kivy.utils import platform
        if platform == "android":
            from io import BytesIO
            from jnius import autoclass  # type: ignore
            from PIL import Image

            MediaMetadataRetriever = autoclass("android.media.MediaMetadataRetriever")
            ByteArrayOutputStream = autoclass("java.io.ByteArrayOutputStream")
            CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")

            retriever = MediaMetadataRetriever()
            retriever.setDataSource(video_path)
            try:
                dur_str = retriever.extractMetadata(9)
                dur_ms = float(dur_str) if dur_str else 0.0
                time_us = int(dur_ms * 1000.0 * max(0.05, min(0.95, ratio)))
                bitmap = retriever.getFrameAtTime(time_us, 2)
                if bitmap is None:
                    bitmap = retriever.getFrameAtTime(0, 2)
                if bitmap is not None:
                    bos = ByteArrayOutputStream()
                    bitmap.compress(CompressFormat.JPEG, 75, bos)
                    raw_bytes = bytes(bos.toByteArray())
                    bos.close()
                    pil_img = Image.open(BytesIO(raw_bytes))
                    pil_img.thumbnail((320, 240))
                    arr = np.array(pil_img.convert("RGB"))
                    return arr[:, :, [2, 1, 0]]  # BGR
            finally:
                retriever.release()
    except Exception:
        pass

    # 2. OpenCV fallback
    if cv2 is None:
        return None

    cap = None
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        target = int(total * max(0.05, min(0.95, ratio))) if total > 0 else 0
        if target > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ret, frame = cap.read()
        if ret and frame is not None:
            # ضغط الحجم إلى 320x240 لتوفير الذاكرة
            h, w = frame.shape[:2]
            scale = min(320.0 / max(1, w), 240.0 / max(1, h), 1.0)
            if scale < 1.0:
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            return frame
    except Exception as e:
        logger.debug("خطأ أثناء استخراج إطار OpenCV: %s", e)
    finally:
        if cap is not None:
            cap.release()

    return None


def _analyze_frame_visuals(frame: np.ndarray) -> dict[str, Any]:
    """
    تحليل الإطار بصرياً لاستخراج ميزات التعرف:
    - كثافة الحواف الأفقية والنصوص (Slide/Text score).
    - نسبة السطوع والتباين (Whiteboard/Slide detector).
    - كشف الوجوه ومواقعها.
    """
    if frame is None or frame.size == 0:
        return {"text_score": 0.0, "face_count": 0, "brightness": 0.0, "is_slide": False}

    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if cv2 is not None else frame.mean(axis=2).astype(np.uint8)

    # 1. كشف السطوع والتباين
    mean_val = float(np.mean(gray))
    std_val = float(np.std(gray))

    # 2. كشف الشرائح والمستندات (خلفيات فاتحة أو سوداء مع حواف نصية منتظمة)
    text_score = 0.0
    is_slide = False
    if cv2 is not None:
        # Sobel أفقي لكشف أسطر الكتابة
        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        edge_mag = np.sqrt(sobel_x**2 + sobel_y**2)
        edge_density = float(np.mean(edge_mag > 40))
        text_score = edge_density

        # خلفية شريحة عرض: تباين عالي مع كثافة حواف متوازنة
        if (mean_val > 180 or mean_val < 45) and 0.04 < edge_density < 0.35 and std_val > 35:
            is_slide = True

    # 3. كشف الوجوه
    face_count = 0
    face_is_central = False
    try:
        import offline_face_recognizer
        faces = offline_face_recognizer.detect_faces_fast(frame)
        face_count = len(faces)
        if face_count == 1:
            fx, fy, fw, fh = faces[0]
            cx, cy = fx + fw / 2, fy + fh / 2
            # وجه متمركز بحجم مناسب (Selfie / Talking Head)
            if 0.25 * w < cx < 0.75 * w and (fw / w) > 0.15:
                face_is_central = True
    except Exception:
        pass

    return {
        "text_score": round(text_score, 3),
        "brightness": round(mean_val, 1),
        "contrast": round(std_val, 1),
        "is_slide": is_slide,
        "face_count": face_count,
        "face_is_central": face_is_central,
    }


def classify_video_offline(
    video_path: str,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_token: Any = None,
) -> VideoClassificationResult:
    """
    التصنيف البصري الأوفلاين الحقيقي للفيديو:
    - فحص الكاش السريع أولاً.
    - استخراج 5 إطارات زمنية (10%, 30%, 50%, 70%, 90%).
    - تحليل الإطارات واستخراج الخصائص البصرية وحركة المشهد.
    - حساب النتائج عبر خوارزمية تصويت وزني دقيقة.
    """
    if not os.path.exists(video_path):
        return VideoClassificationResult(
            category=CATEGORY_UNCLASSIFIED,
            confidence=0.0,
            status="read_failed",
            error=f"ملف الفيديو غير موجود: {video_path}",
        )

    # 1. فحص الكاش
    cache_key = _get_file_cache_key(video_path)
    cache = _load_video_cache()
    if cache_key in cache:
        c_entry = cache[cache_key]
        return VideoClassificationResult(
            category=c_entry["category"],
            confidence=c_entry["confidence"],
            status="success",
            details=c_entry.get("details", {}),
        )

    # 2. استخراج البيانات الوصفية (Metadata)
    import video_classifier
    meta = video_classifier.get_video_metadata(video_path)
    dur = float(meta.get("duration_sec", 0.0))
    width = int(meta.get("width", 0))
    height = int(meta.get("height", 0))
    aspect_ratio = round(width / max(1, height), 2) if width and height else 1.0
    is_vertical = aspect_ratio < 0.85

    # الكلمات المفتاحية في المسار واسم الملف كمساعد ترجيحي فقط
    p_name = Path(video_path).name.lower()
    aux_scores: dict[str, float] = {cat: 0.0 for cat in AUX_KEYWORDS}
    for cat, kws in AUX_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in p_name:
                aux_scores[cat] += 0.35

    # 3. أخذ عينات 5 إطارات زمنية
    sample_ratios = [0.10, 0.30, 0.50, 0.70, 0.90]
    total_samples = len(sample_ratios)
    frames_data: list[dict[str, Any]] = []
    previous_frame_gray: np.ndarray | None = None
    motion_diffs: list[float] = []

    for idx, ratio in enumerate(sample_ratios):
        if cancel_token and getattr(cancel_token, "is_cancelled", False):
            return VideoClassificationResult(
                category=CATEGORY_NEEDS_REVIEW,
                confidence=0.0,
                status="cancelled",
                error="تم إلغاء فحص الفيديو بواسطة المستخدم",
            )

        if progress_cb:
            progress_cb(idx + 1, total_samples, f"تحليل الإطار {idx + 1} من {total_samples}")

        fr = _read_frame_safe(video_path, ratio)
        if fr is not None:
            analysis = _analyze_frame_visuals(fr)
            frames_data.append(analysis)

            # حساب الحركة والقطع بين الإطارات
            cur_gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY) if cv2 is not None else fr.mean(axis=2).astype(np.uint8)
            if previous_frame_gray is not None and cur_gray.shape == previous_frame_gray.shape:
                diff = float(np.mean(np.abs(cur_gray.astype(float) - previous_frame_gray.astype(float))))
                motion_diffs.append(diff)
            previous_frame_gray = cur_gray

    if not frames_data:
        # فشل قراءة أي إطار (ملف تالف أو غير مدعوم)
        return VideoClassificationResult(
            category=CATEGORY_NEEDS_REVIEW,
            confidence=0.0,
            status="read_failed",
            details={"duration": dur, "aspect_ratio": aspect_ratio},
            error="تعذر استخراج إطارات بصرية من الفيديو",
        )

    # 4. تجميع الإحصائيات البصرية
    slide_frames_count = sum(1 for f in frames_data if f["is_slide"])
    total_faces = sum(f["face_count"] for f in frames_data)
    frames_with_faces = sum(1 for f in frames_data if f["face_count"] > 0)
    central_face_frames = sum(1 for f in frames_data if f["face_is_central"])
    avg_text_score = float(np.mean([f["text_score"] for f in frames_data])) if frames_data else 0.0
    avg_motion = float(np.mean(motion_diffs)) if motion_diffs else 0.0

    # 5. خوارزمية التصويت البصري والترجيح
    scores: dict[str, float] = {
        CATEGORY_LECTURE: 0.0,
        CATEGORY_MOVIES: 0.0,
        CATEGORY_FUNNY: 0.0,
        CATEGORY_SONGS: 0.0,
        CATEGORY_PERSONAL: 0.0,
    }

    # ترجيح المحاضرات والدروس:
    # شرائح عرض، حواف نصوص، استقرار عالي في المشهد، مدة متوسطة أو طويلة
    if slide_frames_count >= 2 or avg_text_score > 0.08:
        scores[CATEGORY_LECTURE] += 0.50 + min(0.30, slide_frames_count * 0.10)
    if avg_motion < 15.0 and dur > 180:
        scores[CATEGORY_LECTURE] += 0.20
    if central_face_frames >= 2 and avg_text_score > 0.05:
        # أستاذ يشرح أمام سبورة أو شريحة
        scores[CATEGORY_LECTURE] += 0.25

    # ترجيح الأفلام والمسلسلات:
    # نسبة سينمائية عريضة (16:9 أو أكثر)، مدة طويلة (> 35 دقيقة)، تغير مشاهد ووجوه متعددة
    if aspect_ratio >= 1.6:
        scores[CATEGORY_MOVIES] += 0.25
    if dur > 2400:  # أكثر من 40 دقيقة
        scores[CATEGORY_MOVIES] += 0.45
    elif dur > 1200:  # حلقة مسلسل (أكثر من 20 دقيقة)
        scores[CATEGORY_MOVIES] += 0.30
    if total_faces >= 3 and avg_motion > 20.0 and aspect_ratio >= 1.4:
        scores[CATEGORY_MOVIES] += 0.20

    # ترجيح الفيديوهات المضحكة (Memes / Shorts):
    # مدة قصيرة جداً (أقل من 60 ثانية)، حركة سريعة أو تقلبات، شاشة عمودية
    if 0 < dur <= 60:
        scores[CATEGORY_FUNNY] += 0.30
    if is_vertical and dur <= 90:
        scores[CATEGORY_FUNNY] += 0.20
    if avg_motion > 35.0:
        scores[CATEGORY_FUNNY] += 0.15

    # ترجيح الفيديوهات الشخصية (Family / Vlogs):
    # وجه مركزي متكرر، مدة قصيرة إلى متوسطة، لا توجد نصوص أو شرائح
    if central_face_frames >= 3 and avg_text_score < 0.05 and dur < 600:
        scores[CATEGORY_PERSONAL] += 0.45
    if frames_with_faces >= 3 and 30 < dur < 300 and slide_frames_count == 0:
        scores[CATEGORY_PERSONAL] += 0.25

    # ترجيح الأغاني والأناشيد:
    # كليبات موسيقية: مدة 2 إلى 6 دقائق، تغير بصري وإضاءات
    if 110 <= dur <= 380 and aspect_ratio >= 1.5 and slide_frames_count == 0:
        scores[CATEGORY_SONGS] += 0.30

    # دمج الكلمات المساعدة (Auxiliary Clues) كعامل ترجيح إضافي
    for cat in scores:
        scores[cat] += aux_scores.get(cat, 0.0)

    # 6. تحديد الفائز وحساب الثقة
    best_cat = max(scores, key=scores.get)  # type: ignore
    best_score = scores[best_cat]
    confidence = min(0.95, round(best_score, 2))

    details = {
        "duration_sec": dur,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "is_vertical": is_vertical,
        "frames_sampled": len(frames_data),
        "slide_frames": slide_frames_count,
        "total_faces": total_faces,
        "avg_text_score": avg_text_score,
        "avg_motion": round(avg_motion, 1),
        "scores": {k: round(v, 2) for k, v in scores.items()},
    }

    if confidence >= 0.65:
        res = VideoClassificationResult(
            category=best_cat,
            confidence=confidence,
            status="success",
            details=details,
        )
    elif confidence >= 0.45:
        # ثقة متوسطة -> يحتاج مراجعة
        res = VideoClassificationResult(
            category=CATEGORY_NEEDS_REVIEW,
            confidence=confidence,
            status="needs_review",
            details=details,
        )
    else:
        # ثقة منخفضة -> خارج التصنيف
        res = VideoClassificationResult(
            category=CATEGORY_UNCLASSIFIED,
            confidence=confidence,
            status="success",
            details=details,
        )

    # 7. الحفظ في الكاش الدائم
    cache[cache_key] = {
        "category": res.category,
        "confidence": res.confidence,
        "details": res.details,
        "timestamp": int(time.time()),
    }
    _save_video_cache(cache)

    return res
