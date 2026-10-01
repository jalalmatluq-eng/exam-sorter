"""
offline_classifier.py
---------------------
نظام التصنيف المحلي الذكي المبني على هرمية Offline-First لتطبيق رتّب / CosmoSort:
- الطبقة 1: فحص الكلمات المفتاحية في اسم الملف والمسار النسبي.
- الطبقة 2: التحقق من نوع MIME والامتداد.
- الطبقة 3: خوارزميات الرؤية الحاسوبية الخفيفة (كشف الأوراق، كشف الوجوه التقريبي).
- الطبقة 4: الـ OCR المحلي (إن كان مثبت ومتاح فعلياً في النظام فقط دون ادعاء وهمي).
- قاطع الدائرة الذكي (Circuit Breaker) للـ API السحابي لتفادي تجميد الواجهة عند انقطاع الإنترنت.
- ذاكرة تخزين مؤقت (Cache) تمنع إعادة تحليل نفس الملف أكثر من مرة.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("OfflineClassifier")

# تصنيفات الاختبارات والمقررات الدراسية
CATEGORY_EXAMS_ROOT = "اختبارات"
CATEGORY_EXAMS_GENERAL = "اختبارات/اختبارات عامة"
CATEGORY_MY_PHOTOS = "صوري الشخصية"
CATEGORY_FRIENDS_PHOTOS = "صور الأصدقاء والعائلة"
CATEGORY_UNCLASSIFIED = "خارج التصنيف"

# تصنيفات الفيديو
CATEGORY_FUNNY_VIDEOS = "فيديوهات مضحكة"
CATEGORY_LECTURES = "محاضرات ودروس"
CATEGORY_MOVIES = "أفلام ومسلسلات"
CATEGORY_SONGS = "أغاني وأناشيد"

# قواميس المواد الدراسية الذكية
SUBJECT_KEYWORDS: dict[str, list[str]] = {
    "رياضيات": [
        "رياضيات", "math", "calculus", "جبر", "تفاضل", "تكامل", "هندسة",
        "linear algebra", "discrete", "إحصاء", "احتمالات", "algebra",
    ],
    "فيزياء": ["فيزياء", "physic", "physics", "كهرباء", "ميكانيكا", "ديناميكا"],
    "كيمياء": ["كيمياء", "chem", "chemistry", "عضوية", "تحليلية"],
    "أحياء": ["أحياء", "احياء", "bio", "biology", "وراثة", "خلية", "تشريح"],
    "برمجة": [
        "برمجة", "programming", "code", "python", "java", "حاسوب", "خوارزميات",
        "algorithms", "data structures", "تراكيب", "c++", "database", "قواعد بيانات",
    ],
    "ذكاء اصطناعي": ["ذكاء اصطناعي", "ai", "machine learning", "تعلم آلة", "deep learning"],
    "شبكات": ["شبكات", "network", "networking", "سيسكو", "cisco", "بروتوكول"],
    "لغة إنجليزية": ["english", "إنجليزي", "انجليزي", "grammar", "vocab", "قواعد انجليزي"],
    "لغة عربية": ["عربي", "نحو", "بلاغة", "arabic", "إملاء", "صرف", "أدب"],
    "علوم": ["علوم", "science"],
    "تاريخ": ["تاريخ", "history", "حضارة", "معركة"],
    "جغرافيا": ["جغرافيا", "geography", "تضاريس", "خرائط"],
    "إسلامية": ["إسلامية", "اسلامية", "قرآن", "قران", "حديث", "فقه", "توحيد", "تفسير", "عقيدة"],
    "طب وصيدلة": ["طب", "صيدلة", "تمريض", "ادوية", "أدوية", "pharma", "medicine"],
    "إدارة واقتصاد": ["إدارة", "ادارة", "محاسبة", "اقتصاد", "accounting", "management", "finance"],
}

EXAM_PAPER_INDICATORS = [
    "exam", "test", "quiz", "midterm", "final", "sheet", "paper",
    "اختبار", "امتحان", "كويز", "شهري", "نهائي", "ورقة", "مقرر",
    "اسئلة", "أسئلة", "نموذج", "إجابة", "حلول", "واجب", "homework",
]

# كاش نتائج التصنيف في الذاكرة لتفادي إعادة الحساب
_CLASSIFICATION_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}

# قاطع الدائرة للـ API السحابي (Circuit Breaker)
_CIRCUIT_BREAKER_FAILS = 0
_CIRCUIT_BREAKER_TRIPPED_UNTIL = 0.0
_CIRCUIT_BREAKER_THRESHOLD = 2
_CIRCUIT_BREAKER_COOLDOWN = 60.0  # 60 ثانية استراحة عند انقطاع الإنترنت


def is_circuit_breaker_open() -> bool:
    """التحقق مما إذا كان قاطع الدائرة مفتوحاً (أي أن الإنترنت غير متاح أو الخدمة معطلة)"""
    return time.time() < _CIRCUIT_BREAKER_TRIPPED_UNTIL


def record_cloud_api_success() -> None:
    """تسجيل نجاح استدعاء سحابي لإعادة ضبط قاطع الدائرة"""
    global _CIRCUIT_BREAKER_FAILS, _CIRCUIT_BREAKER_TRIPPED_UNTIL
    _CIRCUIT_BREAKER_FAILS = 0
    _CIRCUIT_BREAKER_TRIPPED_UNTIL = 0.0


def record_cloud_api_failure() -> None:
    """تسجيل فشل استدعاء سحابي لفتح قاطع الدائرة وتفادي الانتظار المتكرر"""
    global _CIRCUIT_BREAKER_FAILS, _CIRCUIT_BREAKER_TRIPPED_UNTIL
    _CIRCUIT_BREAKER_FAILS += 1
    if _CIRCUIT_BREAKER_FAILS >= _CIRCUIT_BREAKER_THRESHOLD:
        _CIRCUIT_BREAKER_TRIPPED_UNTIL = time.time() + _CIRCUIT_BREAKER_COOLDOWN
        logger.warning(
            "تم تفعيل قاطع الدائرة السحابي لمدة %d ثانية بعد %d إخفاقات متتالية",
            int(_CIRCUIT_BREAKER_COOLDOWN),
            _CIRCUIT_BREAKER_FAILS,
        )


def is_offline_ocr_runtime_available() -> bool:
    """
    فحص حقيقي وصارم لمدى توفر محرك Tesseract والملفات اللغوية في البيئة الفعلية.
    لا يدعي توفر الـ OCR إلا إذا كان محرك التشغيل موجوداً ومثبتاً بالفعل.
    """
    try:
        import importlib
        import shutil
        _ = importlib.import_module("pytesseract")
        tess_bin = shutil.which("tesseract")
        return bool(tess_bin)
    except Exception:
        return False


def classify_by_filename(filename: str, rel_path: str = "") -> dict[str, Any] | None:
    """
    الطبقة الأولى: التحليل اللفظي واللغوي فائق السرعة لاسم الملف والمسار
    """
    clean_text = f"{rel_path} {Path(filename).stem}".lower().replace("_", " ").replace("-", " ")

    # 1. فحص كلمات الاختبارات والمواد الدراسية
    has_exam_term = any(t in clean_text for t in EXAM_PAPER_INDICATORS)
    for subject, kws in SUBJECT_KEYWORDS.items():
        if any(kw in clean_text for kw in kws):
            return {
                "category": f"{CATEGORY_EXAMS_ROOT}/{subject}",
                "confidence": 0.95 if has_exam_term else 0.80,
                "details": f"مطابقة مادة '{subject}' في اسم الملف",
                "needs_review": False,
                "method": "filename_keyword",
            }

    if has_exam_term:
        return {
            "category": CATEGORY_EXAMS_GENERAL,
            "confidence": 0.75,
            "details": "اكتشاف ورقة اختبار بدون تحديد المادة",
            "needs_review": True,
            "method": "filename_exam_generic",
        }

    # 2. فحص كلمات الفيديوهات الشائعة
    funny_kws = ["funny", "meme", "jokes", "مضحك", "ضحك", "مقالب", "تحشيش", "طقطقة", "tiktok", "reels"]
    if any(k in clean_text for k in funny_kws):
        return {
            "category": CATEGORY_FUNNY_VIDEOS,
            "confidence": 0.85,
            "details": "مطابقة وسم فيديو مضحك بالاسم",
            "needs_review": False,
            "method": "filename_video",
        }

    lecture_kws = ["lecture", "tutorial", "شرح", "محاضرة", "درس", "كورس", "session"]
    if any(k in clean_text for k in lecture_kws):
        return {
            "category": CATEGORY_LECTURES,
            "confidence": 0.85,
            "details": "مطابقة محاضرة دراسية بالاسم",
            "needs_review": False,
            "method": "filename_lecture",
        }

    movie_kws = ["movie", "film", "series", "season", "episode", "حلقة", "مسلسل", "فيلم"]
    if any(k in clean_text for k in movie_kws):
        return {
            "category": CATEGORY_MOVIES,
            "confidence": 0.85,
            "details": "مطابقة فيلم أو مسلسل بالاسم",
            "needs_review": False,
            "method": "filename_movie",
        }

    song_kws = ["song", "music", "audio", "اغنية", "أغنية", "نشيد", "انشودة", "شيلة", "قصيدة"]
    if any(k in clean_text for k in song_kws):
        return {
            "category": CATEGORY_SONGS,
            "confidence": 0.85,
            "details": "مطابقة عمل صوتي/غنائي بالاسم",
            "needs_review": False,
            "method": "filename_song",
        }

    return None


def classify_media_offline(
    file_path: str | Path,
    filename: str = "",
    mime_type: str = "",
    size_bytes: int = 0,
    mtime: int = 0,
    relative_path: str = "",
) -> dict[str, Any]:
    """
    التصنيف الموضعي المتكامل بنظام هرمي صارم بدون إنترنت:
    - فحص الكاش أولاً.
    - فحص اسم الملف.
    - فحص الرؤية الحاسوبية (ورقة / وجوه تقريبية).
    - حفظ النتيجة في الكاش.
    """
    fname = filename or Path(str(file_path)).name
    cache_key = (fname, size_bytes, mtime)
    if cache_key in _CLASSIFICATION_CACHE:
        return _CLASSIFICATION_CACHE[cache_key]

    # 1. الطبقة الأولى: اسم الملف
    by_name = classify_by_filename(fname, rel_path=relative_path)
    if by_name and by_name["confidence"] >= 0.80:
        _CLASSIFICATION_CACHE[cache_key] = by_name
        return by_name

    ext = Path(fname).suffix.lower()
    is_video = "video" in mime_type.lower() or ext in [".mp4", ".mkv", ".avi", ".mov", ".3gp", ".webm"]
    is_image = "image" in mime_type.lower() or ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic"]

    p_str = str(file_path)

    # 2. الطبقة الثانية: للصور (الرؤية الحاسوبية الخفيفة)
    if is_image and not is_video:
        try:
            import media_scanner
            # التحقق مما إذا كانت الصورة ورقة مستند / اختبار
            if media_scanner.is_visual_document_or_paper(p_str):
                # فحص OCR إن كان متوفراً ومثبتاً فعلياً داخل النظام
                if is_offline_ocr_runtime_available():
                    try:
                        import classifier
                        subj = classifier.classify_with_local_ocr(p_str)
                        if subj and subj.strip():
                            clean_subj = subj.strip()
                            res = {
                                "category": f"{CATEGORY_EXAMS_ROOT}/{clean_subj}",
                                "confidence": 0.85,
                                "details": f"ورقة اختبار مادة: {clean_subj} (عبر OCR المحلي)",
                                "needs_review": False,
                                "method": "local_ocr",
                            }
                            _CLASSIFICATION_CACHE[cache_key] = res
                            return res
                    except Exception as e_ocr:
                        logger.debug("تجاوز تشغيل OCR المحلي: %s", e_ocr)

                res = {
                    "category": (by_name["category"] if by_name else CATEGORY_EXAMS_GENERAL),
                    "confidence": 0.70,
                    "details": "اكتشاف ورقة اختبار عبر الرؤية الحاسوبية (تحليل السطوع والتشبع)",
                    "needs_review": True,
                    "method": "cv_document_detector",
                }
                _CLASSIFICATION_CACHE[cache_key] = res
                return res
        except Exception as e_cv:
            logger.debug("تجاوز فحص الرؤية الحاسوبية للورقة: %s", e_cv)

        # فحص الكشف التقريبي للوجوه (بدون ادعاء نموذج AI عميق غير موجود)
        try:
            import face_classifier
            match_res = face_classifier.detect_and_match_face(p_str)
            if match_res == "me":
                res = {
                    "category": CATEGORY_MY_PHOTOS,
                    "confidence": 0.65,
                    "details": "كشف تقريبي: تطابق بصمة وجه صاحب الجهاز",
                    "needs_review": False,
                    "method": "approximate_face_detection",
                }
                _CLASSIFICATION_CACHE[cache_key] = res
                return res
            elif match_res == "other":
                res = {
                    "category": CATEGORY_FRIENDS_PHOTOS,
                    "confidence": 0.60,
                    "details": "كشف تقريبي: اكتشاف وجوه أخرى (أصدقاء / عائلة)",
                    "needs_review": False,
                    "method": "approximate_face_detection",
                }
                _CLASSIFICATION_CACHE[cache_key] = res
                return res
        except Exception as e_face:
            logger.debug("تجاوز كشف الوجوه: %s", e_face)

    # 3. الطبقة الثالثة: للفيديوهات
    if is_video:
        try:
            import video_classifier
            v_cat = video_classifier.classify_video(p_str, api_key=None)
            res = {
                "category": v_cat,
                "confidence": 0.70,
                "details": f"تصنيف فيديو محلي: {v_cat}",
                "needs_review": (v_cat == CATEGORY_UNCLASSIFIED),
                "method": "video_local_rules",
            }
            _CLASSIFICATION_CACHE[cache_key] = res
            return res
        except Exception as e_vid:
            logger.debug("تجاوز تصنيف الفيديو المحلي: %s", e_vid)

    # النتيجة الافتراضية الآمنة
    default_res = by_name or {
        "category": CATEGORY_UNCLASSIFIED,
        "confidence": 0.50,
        "details": "خارج التصنيف (يحتاج مراجعة أو تسمية يدوية)",
        "needs_review": True,
        "method": "unclassified_fallback",
    }
    _CLASSIFICATION_CACHE[cache_key] = default_res
    return default_res
