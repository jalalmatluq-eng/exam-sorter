# -*- coding: utf-8 -*-
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
- "محاضرات وتعلم"
- "أفلام ومسلسلات"
- "أغاني وأناشيد"
- "خارج التصنيف" (في حال عدم مطابقة أي صنف)
"""

import json
import os
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

import cv2
import numpy as np

import classifier
import file_manager

CATEGORY_FUNNY = "فيديوهات مضحكة"
CATEGORY_LECTURE = "محاضرات وتعلم"
CATEGORY_MOVIES = "أفلام ومسلسلات"
CATEGORY_SONGS = "أغاني وأناشيد"
CATEGORY_UNCLASSIFIED = "خارج التصنيف"

# قواميس الكلمات المفتاحية الذكية
KEYWORDS_MAP = {
    CATEGORY_FUNNY: [
        "مضحك", "ضحك", "طقطقة", "نكتة", "كوميدي", "مقالب", "مقلب",
        "funny", "meme", "memes", "joke", "jokes", "prank", "comedy",
        "tiktok", "reels", "short", "shorts", "whatsapp animated gifs",
        "vine", "fail", "fails", "fyp", "viral", "تحشيش", "هسترة", "فرفشة"
    ],
    CATEGORY_SONGS: [
        "أغنية", "اغنية", "أغاني", "اغاني", "أنشودة", "انشودة", "أناشيد",
        "نشيد", "كليب", "شيلة", "شيلات", "موسيقى", "عزف", "طرب",
        "song", "songs", "track", "music", "audio", "clip", "official video",
        "lyric", "lyrics", "remix", "nasheed", "melody", "soundtrack",
        "علي الموسوي", "الموسوي", "moussawi", "علي بوحمد", "بوحمد", "bouhamad",
        "لطمية", "لطميات", "رادود", "قصيدة", "قصائد", "عفاسي", "منشد"
    ],
    CATEGORY_LECTURE: [
        "محاضرة", "محاضره", "شرح", "درس", "كورس", "دورة", "تعليم", "جامعة",
        "أكاديمي", "ندوة", "دكتور", "دكتورة", "أستاذ", "أستاذة", "ملخص", "فهم",
        "lecture", "tutorial", "lesson", "course", "study", "class",
        "dr.", "prof", "chapter", "ch0", "ch1", "ch2", "ch3", "ch4", "ch5",
        "udemy", "coursera", "webinar", "explanation", "database", "java",
        "intellij", "python", "programming", "access", "sql", "code", "coding",
        "software", "algorithm", "excel", "computer", "حاسوب", "برمجة", "حل"
    ],
    CATEGORY_MOVIES: [
        "فيلم", "مسلسل", "حلقة", "سلسلة", "موسم", "سينما", "مترجم",
        "movie", "film", "episode", "season", "series", "cinema",
        "bluray", "web-dl", "hdtv", "x264", "x265",
        "netflix", "shahid", "hbo", "disney", "s01", "s02", "s03", "s04",
        "e01", "e02", "e03", "e04", "e05"
    ]
}


def _safe_read_frame(video_path: str, position_ratio: float = 0.5) -> np.ndarray | None:
    """استخراج إطار تمثيلي محدد من الفيديو عبر OpenCV"""
    cap = None
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            # محاولة قراءة أول إطار إن كان طول الفيديو غير محدد
            ret, frame = cap.read()
            return frame if ret else None

        target_index = int(total_frames * max(0.05, min(0.95, position_ratio)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_index)
        ret, frame = cap.read()
        if ret and frame is not None:
            return frame

        # محاولة بديلة لقراءة أول إطار
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
    """استخراج مدة الفيديو وأبعاده ومعدل الإطارات"""
    meta = {
        "duration_sec": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "frame_count": 0
    }
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
                "frame_count": int(frames)
            }
    except Exception as e:
        print("خطأ أثناء قراءة بيانات الفيديو:", e)
    finally:
        if cap is not None:
            cap.release()
    return meta


def classify_video_locally(video_path: str) -> str | None:
    """
    الطبقة الأولى: التصنيف المحلي الذكي بدون إنترنت:
    - فحص اسم الملف والمجلد المصدر.
    - فحص المدة الزمنية والأبعاد.
    - فحص محتوى الإطارات.
    """
    path_obj = Path(video_path)
    clean_text = f"{path_obj.name} {path_obj.parent.name}".lower()

    # 1. فحص الكلمات المفتاحية في المسار والاسم (أعلى موثوقية)
    for category, keywords in KEYWORDS_MAP.items():
        for kw in keywords:
            if kw.lower() in clean_text:
                return category

    # 2. فحص البيانات الوصفية (المدة والأبعاد)
    meta = get_video_metadata(video_path)
    duration = meta.get("duration_sec", 0.0)
    w = meta.get("width", 0)
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

    # مقاطع قصيرة جداً (أقل من 35 ثانية) من تطبيقات المراسلة أو بنسب طولية (9:16)
    if 0 < duration < 35 and h > w:
        return CATEGORY_FUNNY

    # مقاطع متوسطة (دقيقة ونصف إلى 6 دقائق)
    if 90 <= duration <= 360:
        if any(term in clean_text for term in ["vid", "audio", "track", "clip"]):
            return CATEGORY_SONGS

    # 3. فحص الوجوه ومحتوى الإطار الأوسط للفيديو محلياً
    try:
        import face_classifier
        frame = _safe_read_frame(video_path, position_ratio=0.5)
        if frame is not None:
            faces = face_classifier.detect_faces_in_image(frame)
            if len(faces) > 0:
                # أفلام ومسلسلات: مقاطع طويلة بوجوه بشرية وشاشات عرض سينمائي
                if duration >= 1200:
                    return CATEGORY_MOVIES
                # مقاطع قصيرة بوجوه بشرية (ريلز أو تيك توك مضحك)
                elif 0 < duration <= 45 and h >= w:
                    return CATEGORY_FUNNY
    except Exception:
        pass

    # لم نصل لقرار حاسم محلياً
    return None


def classify_video_with_claude(video_path: str, api_key: str | None = None) -> str:
    """
    الطبقة الثانية: استشارة Claude Vision API عبر إرسال إطار منتصف الفيديو
    """
    key = classifier.get_api_key(api_key)
    if not key:
        return CATEGORY_UNCLASSIFIED

    frame = _safe_read_frame(video_path, position_ratio=0.5)
    if frame is None:
        return CATEGORY_UNCLASSIFIED

    # حفظ الإطار في ملف مؤقت لتجهيزه وتصغيره
    temp_dir = file_manager.get_temp_dir()
    temp_frame_path = str(temp_dir / f"vframe_{os.urandom(4).hex()}.jpg")
    cv2.imwrite(temp_frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

    try:
        base64_data, media_type = classifier.encode_and_resize_image(temp_frame_path, max_dimension=1000)

        prompt_instruction = (
            "هذا إطار ملتقط من مقطع فيديو. صنّف هذا الفيديو إلى واحد فقط من هذه التصنيفات بدقة:\n"
            "- فيديوهات مضحكة\n"
            "- محاضرات وتعلم\n"
            "- أفلام ومسلسلات\n"
            "- أغاني وأناشيد\n"
            "- غير ذلك\n"
            "أجب باسم التصنيف فقط بكلمات معدودة دون أي شرح."
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
        req = urllib.request.Request(classifier.ANTHROPIC_API_URL, data=req_data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=15) as response:
            raw_response = response.read().decode("utf-8")
            result = json.loads(raw_response)
            content_blocks = result.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    reply = str(block.get("text", "")).strip().lower()
                    if "مضحك" in reply:
                        return CATEGORY_FUNNY
                    elif "محاضر" in reply or "تعلم" in reply or "تعليم" in reply:
                        return CATEGORY_LECTURE
                    elif "فيلم" in reply or "مسلسل" in reply or "سينما" in reply:
                        return CATEGORY_MOVIES
                    elif "أغاني" in reply or "اغاني" in reply or "نشيد" in reply or "أغنية" in reply:
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


def classify_video(video_path: str, api_key: str | None = None) -> str:
    """
    الدالة الرئيسية المطلوبة في البرومبت:
    classify_video(video_path) -> category
    
    1. تحاول أولاً التصنيف محلياً دون الحاجة لإنترنت.
    2. في حال عدم الحسم محلياً، تستشير Claude Vision API إن توفر إنترنت ومفتاح API.
    3. إذا تعذر ذلك، ترجع 'خارج التصنيف'.
    """
    if not os.path.exists(video_path):
        return CATEGORY_UNCLASSIFIED

    local_result = classify_video_locally(video_path)
    if local_result is not None:
        return local_result

    # اللجوء للذكاء الاصطناعي عند الشك
    return classify_video_with_claude(video_path, api_key=api_key)
