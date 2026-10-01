"""
وحدة تصنيف الفيديوهات (Video Classifier)
- تعمل بنظام هجين (Hybrid) من طبقتين:
  1. الطبقة المحلية (بدون إنترنت):
     - تحليل الكلمات المفتاحية في اسم الملف والمسار المصدر.
     - استخراج بيانات الفيديو الوصفية (المدة الزمنية، الأبعاد، معدل الإطارات).
     - استخراج وفحص إطارات تمثيلية من الفيديو بالـ OpenCV.
  2. طبقة الذكاء الاصطناعي (Claude Vision API):
     - تُستدعى عند الشك وعدم حسم التصنيف محلياً وعند توفر اتصال بالإنترنت.
     - إرسال إطار منتصف الفيديو للتحليل البصري الدقيق.

التصنيفات الناتجة:
- "فيديوهات مضحكة"
- "محاضرات ودروس"
- "أفلام ومسلسلات"
- "أغاني وأناشيد"
- "خارج التصنيف" (في حال عدم مطابقة أي صنف)
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import cv2
except Exception:
    cv2 = None  # type: ignore
import numpy as np

import classifier
import file_manager

CATEGORY_FUNNY = "فيديوهات مضحكة"
CATEGORY_LECTURE = "محاضرات ودروس"
CATEGORY_MOVIES = "أفلام ومسلسلات"
CATEGORY_SONGS = "أغاني وأناشيد"
CATEGORY_UNCLASSIFIED = "خارج التصنيف"

# قواميس الكلمات المفتاحية الذكية
KEYWORDS_MAP = {
    CATEGORY_FUNNY: [
        "مضحك",
        "ضحك",
        "طقطقة",
        "نكتة",
        "كوميدي",
        "مقالب",
        "مقلب",
        "funny",
        "meme",
        "memes",
        "joke",
        "jokes",
        "prank",
        "comedy",
        "tiktok",
        "reels",
        "short",
        "shorts",
        "whatsapp animated gifs",
        "vine",
        "fail",
        "fails",
        "fyp",
        "viral",
        "تحشيش",
        "هسترة",
        "فرفشة",
    ],
    CATEGORY_SONGS: [
        "أغنية",
        "اغنية",
        "أغاني",
        "اغاني",
        "أنشودة",
        "انشودة",
        "أناشيد",
        "نشيد",
        "كليب",
        "شيلة",
        "شيلات",
        "موسيقى",
        "عزف",
        "طرب",
        "song",
        "songs",
        "track",
        "music",
        "audio",
        "clip",
        "official video",
        "lyric",
        "lyrics",
        "remix",
        "nasheed",
        "melody",
        "soundtrack",
        "علي الموسوي",
        "الموسوي",
        "moussawi",
        "علي بوحمد",
        "بوحمد",
        "bouhamad",
        "لطمية",
        "لطميات",
        "رادود",
        "قصيدة",
        "قصائد",
        "عفاسي",
        "منشد",
    ],
    CATEGORY_LECTURE: [
        "محاضرة",
        "محاضره",
        "شرح",
        "درس",
        "كورس",
        "دورة",
        "تعليم",
        "جامعة",
        "أكاديمي",
        "ندوة",
        "دكتور",
        "دكتورة",
        "أستاذ",
        "أستاذة",
        "ملخص",
        "فهم",
        "lecture",
        "tutorial",
        "lesson",
        "course",
        "study",
        "class",
        "dr.",
        "prof",
        "chapter",
        "ch0",
        "ch1",
        "ch2",
        "ch3",
        "ch4",
        "ch5",
        "udemy",
        "coursera",
        "webinar",
        "explanation",
        "database",
        "java",
        "intellij",
        "python",
        "programming",
        "access",
        "sql",
        "code",
        "coding",
        "software",
        "algorithm",
        "excel",
        "computer",
        "حاسوب",
        "برمجة",
        "حلول تمارين",
        "حل مسائل",
        "حل أسئلة",
        "حل اسئلة",
    ],
    CATEGORY_MOVIES: [
        "فيلم",
        "مسلسل",
        "حلقة",
        "سلسلة",
        "موسم",
        "سينما",
        "مترجم",
        "movie",
        "film",
        "episode",
        "season",
        "series",
        "cinema",
        "bluray",
        "web-dl",
        "hdtv",
        "x264",
        "x265",
        "netflix",
        "shahid",
        "hbo",
        "disney",
        "s01",
        "s02",
        "s03",
        "s04",
        "e01",
        "e02",
        "e03",
        "e04",
        "e05",
    ],
}


def _android_get_video_metadata(video_path: str) -> dict[str, Any] | None:
    """استخراج بيانات الفيديو الوصفية بأمان كامل عبر محرك أندرويد الأصلي"""
    retriever = None
    try:
        from jnius import autoclass  # type: ignore

        MediaMetadataRetriever = autoclass("android.media.MediaMetadataRetriever")
        retriever = MediaMetadataRetriever()
        retriever.setDataSource(str(video_path))

        meta: dict[str, Any] = {
            "duration_sec": 0.0,
            "width": 0,
            "height": 0,
            "fps": 25.0,
            "frame_count": 0,
        }
        # METADATA_KEY_DURATION = 9 (in ms)
        dur_str = retriever.extractMetadata(9)
        if dur_str:
            meta["duration_sec"] = float(dur_str) / 1000.0

        # METADATA_KEY_VIDEO_WIDTH = 18, METADATA_KEY_VIDEO_HEIGHT = 19
        w_str = retriever.extractMetadata(18)
        if w_str:
            meta["width"] = int(w_str)
        h_str = retriever.extractMetadata(19)
        if h_str:
            meta["height"] = int(h_str)

        # METADATA_KEY_CAPTURE_FRAMERATE = 25
        fps_str = retriever.extractMetadata(25)
        if fps_str:
            try:
                meta["fps"] = float(fps_str)
            except ValueError:
                pass
        if meta["fps"] > 0 and meta["duration_sec"] > 0:
            meta["frame_count"] = int(meta["duration_sec"] * meta["fps"])

        return meta
    except Exception as e:
        print(f"تنبيه: تعذر قراءة بيانات الفيديو عبر أندرويد الأصلي {video_path}:", e)
        return None
    finally:
        if retriever is not None:
            try:
                retriever.release()
            except Exception:
                pass


def _android_read_frame(
    video_path: str, position_ratio: float = 0.5
) -> np.ndarray | None:
    """استخراج إطار الفيديو عبر MediaMetadataRetriever لمنع أي انهيار native في OpenCV"""
    retriever = None
    try:
        from io import BytesIO

        from jnius import autoclass  # type: ignore
        from PIL import Image

        MediaMetadataRetriever = autoclass("android.media.MediaMetadataRetriever")
        ByteArrayOutputStream = autoclass("java.io.ByteArrayOutputStream")
        CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")

        retriever = MediaMetadataRetriever()
        retriever.setDataSource(str(video_path))

        dur_str = retriever.extractMetadata(9)
        dur_ms = float(dur_str) if dur_str else 0.0
        time_us = int(dur_ms * 1000.0 * max(0.05, min(0.95, position_ratio)))

        # OPTION_CLOSEST_SYNC = 2
        bitmap = retriever.getFrameAtTime(time_us, 2)
        if bitmap is None:
            bitmap = retriever.getFrameAtTime(0, 2)
        if bitmap is None:
            return None

        bos = ByteArrayOutputStream()
        _ = bitmap.compress(CompressFormat.JPEG, 85, bos)
        raw_bytes = bytes(bos.toByteArray())
        bos.close()

        pil_img = Image.open(BytesIO(raw_bytes))
        arr = np.array(pil_img)
        # تحويل RGB إلى BGR ليتوافق مع باقي نظام التصنيف ومعالجة الوجوه
        bgr = arr[:, :, [2, 1, 0]] if arr.ndim == 3 and arr.shape[2] >= 3 else arr
        return bgr
    except Exception as e:
        print(f"تنبيه: تعذر استخراج إطار أندرويد الأصلي من {video_path}:", e)
        return None
    finally:
        if retriever is not None:
            try:
                retriever.release()
            except Exception:
                pass


def _safe_read_frame(
    video_path: str, position_ratio: float = 0.5
) -> np.ndarray | None:
    """استخراج إطار تمثيلي من الفيديو (عبر أندرويد الأصلي أولاً، أو OpenCV لسطح المكتب)"""
    try:
        from kivy.utils import platform
        if platform == "android":
            frame = _android_read_frame(video_path, position_ratio)
            if frame is not None:
                return frame
    except Exception:
        pass

    if cv2 is None:
        return None
    cap = None
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            ret, frame = cap.read()
            return frame if ret else None

        target_index = int(total_frames * max(0.05, min(0.95, position_ratio)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_index)
        ret, frame = cap.read()
        if ret and frame is not None:
            return frame

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
        return frame if ret else None
    except Exception as e:
        print(f"تعذر استخراج إطار من {video_path}:", e)
        return None
    finally:
        if cap is not None:
            cap.release()


def get_video_metadata(video_path: str) -> dict[str, Any]:
    """استخراج مدة الفيديو وأبعاده ومعدل الإطارات بأمان تام"""
    try:
        from kivy.utils import platform
        if platform == "android":
            meta = _android_get_video_metadata(video_path)
            if meta is not None and (
                meta.get("duration_sec", 0) > 0 or meta.get("width", 0) > 0
            ):
                return meta
    except Exception:
        pass

    meta = {
        "duration_sec": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "frame_count": 0,
    }
    if cv2 is None:
        return meta
    cap = None
    try:
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            duration = (frames / fps) if fps > 0 and frames > 0 else 0.0
            meta = {
                "duration_sec": float(duration),
                "width": w,
                "height": h,
                "fps": float(fps),
                "frame_count": int(frames),
            }
    except Exception as e:
        print("خطأ أثناء قراءة بيانات الفيديو:", e)
    finally:
        if cap is not None:
            cap.release()
    return meta


def classify_video_locally(
    video_path: str = "",
    duration_seconds: float = 0.0,
    width: int = 0,
    height: int = 0,
    title: str = "",
) -> str | None:
    """
    الطبقة الأولى: التصنيف المحلي الذكي بدون إنترنت:
    - فحص اسم الملف والمجلد المصدر أو العنوان الممرر.
    - فحص المدة الزمنية والأبعاد.
    - فحص محتوى الإطارات عبر OpenCV.
    """
    clean_parts: list[str] = []
    if video_path:
        path_obj = Path(video_path)
        clean_parts.extend([path_obj.name, path_obj.parent.name])
    if title:
        clean_parts.append(title)
    clean_text = " ".join(clean_parts).lower()

    # 1. فحص الكلمات المفتاحية في المسار والاسم (أعلى موثوقية)
    for category, keywords in KEYWORDS_MAP.items():
        for kw in keywords:
            if kw.lower() in clean_text:
                return category

    # 2. فحص البيانات الوصفية (المدة والأبعاد)
    duration = duration_seconds
    w = width
    h = height

    if video_path and os.path.exists(video_path):
        meta = get_video_metadata(video_path)
        if duration <= 0:
            duration = meta.get("duration_sec", 0.0)
        if w <= 0:
            w = meta.get("width", 0)
        if h <= 0:
            h = meta.get("height", 0)

    # إذا كانت المدة طويلة جداً (أكثر من 70 دقيقة = 4200 ثانية)
    if duration > 4200:
        # أفلام ومسلسلات: شاشات عريضة بنسب سينمائية (16:9 أو أكثر)
        if (w / max(1, h)) >= 1.4:
            return CATEGORY_MOVIES
        return CATEGORY_LECTURE

    # مدة بين 40 و 70 دقيقة (2400 إلى 4200 ثانية)
    if duration > 2400:
        if (w / max(1, h)) >= 1.5 and w >= 1200:
            return CATEGORY_MOVIES
        return CATEGORY_LECTURE

    # 3. مقاطع متوسطة (دقيقة ونصف إلى 6 دقائق) تحتوي على مؤشرات صوتية أو كليبات
    if 90 <= duration <= 360 and any(
        term in clean_text for term in ["vid", "audio", "track", "clip", "كليب", "لحن"]
    ):
        return CATEGORY_SONGS

    # 4. فحص محتوى متعدد الإطارات للفيديو محلياً (البداية، الوسط، النهاية)
    if video_path and os.path.exists(video_path):
        try:
            import face_classifier

            # فحص عينات متعددة الإطارات لتجنب الحكم من لقطة واحدة مضللة
            frames_to_check = [
                _safe_read_frame(video_path, position_ratio=pos)
                for pos in (0.15, 0.5, 0.85)
            ]
            valid_frames = [fr for fr in frames_to_check if fr is not None]

            if valid_frames:
                total_faces = 0
                for fr in valid_frames:
                    faces = face_classifier.detect_faces_in_image(fr)
                    total_faces += len(faces)

                # أفلام ومسلسلات: مقاطع طويلة وشاشات سينمائية بوجوه متعددة
                if duration >= 1200 and total_faces > 0 and (w / max(1, h)) >= 1.3:
                    return CATEGORY_MOVIES

                # مقاطع قصيرة جداً لا تصنف مضحكة إلا بوجود كلمات مفتاحية داعمة
                # لتجنب تصنيف فيديوهات العائلة أو المحاضرات كفيديوهات مضحكة
                funny_cues = ["meme", "funny", "tiktok", "reels", "مضحك", "ضحك", "طقطقة", "نكتة", "كوميدي"]
                if 0 < duration <= 45 and any(cue in clean_text for cue in funny_cues):
                    return CATEGORY_FUNNY
        except Exception:
            pass

    # لم نصل لقرار حاسم محلياً
    return None


def classify_video_with_claude(
    video_path: str, api_key: str | None = None
) -> str:
    """
    الطبقة الثانية: استشارة Claude Vision API عبر إرسال إطار منتصف الفيديو
    """
    key = classifier.get_api_key(api_key)
    if not key:
        return CATEGORY_UNCLASSIFIED

    frame = _safe_read_frame(video_path, position_ratio=0.5)
    if frame is None:
        return CATEGORY_UNCLASSIFIED

    temp_frame_path = str(file_manager.get_temp_dir() / "_vid_classify_frame.jpg")

    if cv2 is not None:
        cv2.imwrite(temp_frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    else:
        from PIL import Image
        pil_f = Image.fromarray(frame[:, :, ::-1] if frame.ndim == 3 else frame)
        pil_f.save(temp_frame_path, quality=85)

    try:
        base64_data, media_type = classifier.encode_and_resize_image(
            temp_frame_path, max_dimension=1000
        )

        prompt_instruction = (
            "هذا إطار ملتقط من مقطع فيديو."
            " صنّف هذا الفيديو إلى واحد فقط"
            " من هذه التصنيفات بدقة:\n"
            "- فيديوهات مضحكة\n"
            "- محاضرات ودروس\n"
            "- أفلام ومسلسلات\n"
            "- أغاني وأناشيد\n"
            "- غير ذلك\n"
            "أجب باسم التصنيف فقط دون أي شرح."
        )

        payload: dict[str, Any] = {
            "model": classifier.DEFAULT_MODEL,
            "max_tokens": 60,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt_instruction,
                        },
                    ],
                }
            ],
        }

        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            classifier.ANTHROPIC_API_URL,
            data=req_data,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=15) as response:
            raw_response = response.read().decode("utf-8")
            result = json.loads(raw_response)
            content_blocks = result.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    reply = str(block.get("text", "")).strip().lower()
                    if "مضحك" in reply:
                        return CATEGORY_FUNNY
                    elif (
                        "محاضر" in reply or "تعلم" in reply or "تعليم" in reply or "درس" in reply or "دروس" in reply
                    ):
                        return CATEGORY_LECTURE
                    elif (
                        "فيلم" in reply or "مسلسل" in reply or "سينما" in reply
                    ):
                        return CATEGORY_MOVIES
                    elif (
                        "أغاني" in reply
                        or "اغاني" in reply
                        or "نشيد" in reply
                        or "أغنية" in reply
                    ):
                        return CATEGORY_SONGS

    except Exception as e:
        print("خطأ أثناء استشارة Claude لتصنيف الفيديو:", e)
    finally:
        if os.path.exists(temp_frame_path):
            try:
                os.remove(temp_frame_path)
            except Exception:
                pass

    return CATEGORY_UNCLASSIFIED


_VIDEO_CACHE: dict[tuple[str, int, int], str] = {}


def classify_video(
    video_path: str = "",
    api_key: str | None = None,
    duration_seconds: float = 0.0,
    width: int = 0,
    height: int = 0,
    title: str = "",
) -> str:
    """
    الدالة الرئيسية لتصنيف الفيديو مع دعم كامل لنظام Offline-First:
    1. فحص كاش التصنيف المسبق لتجنب إعادة استخراج الإطارات.
    2. محاولة التصنيف محلياً دون اتصال بالإنترنت.
    3. إذا لم يُحسم محلياً: فحص قاطع الدائرة وتوافر مفتاح API قبل استشارة Claude.
    4. حفظ النتيجة في الكاش لمنع استهلاك الموارد.
    """
    cache_key: tuple[str, int, int] | None = None
    if video_path and os.path.exists(video_path):
        try:
            st = os.stat(video_path)
            cache_key = (Path(video_path).name, st.st_size, int(st.st_mtime))
            if cache_key in _VIDEO_CACHE:
                return _VIDEO_CACHE[cache_key]
        except OSError:
            pass

    local_result = classify_video_locally(
        video_path=video_path,
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        title=title,
    )
    if local_result is not None:
        if cache_key:
            _VIDEO_CACHE[cache_key] = local_result
        return local_result

    # اللجوء للذكاء الاصطناعي فقط عند توفر مفتاح API وعدم فتح قاطع الدائرة
    if video_path and os.path.exists(video_path):
        key = classifier.get_api_key(api_key)
        if key:
            try:
                import offline_classifier
                if not offline_classifier.is_circuit_breaker_open():
                    res = classify_video_with_claude(video_path, api_key=key)
                    if res and res != CATEGORY_UNCLASSIFIED:
                        offline_classifier.record_cloud_api_success()
                        if cache_key:
                            _VIDEO_CACHE[cache_key] = res
                        return res
            except Exception as e_cloud:
                print("تنبيه أثناء استدعاء ذكاء الفيديو السحابي:", e_cloud)
                try:
                    import offline_classifier
                    offline_classifier.record_cloud_api_failure()
                except Exception:
                    pass

    final_cat = CATEGORY_UNCLASSIFIED
    if cache_key:
        _VIDEO_CACHE[cache_key] = final_cat
    return final_cat
