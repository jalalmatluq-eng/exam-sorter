# -*- coding: utf-8 -*-
"""
وحدة الفحص والفرز الشامل للوسائط (Media Scanner):
- فحص وسائط الذاكرة الداخلية والخارجية تلقائياً.
- استثناء المجلدات المحمية ومجلد MediaSorter وقاعدة بيانات الملفات المفحوصة مسبقاً.
- توجيه كل ملف للمصنف المناسب حسب الأولويات:
    1. صور اختبارات جامعية -> مجلد المادة الدراسية.
    2. صوري أنا -> مجلد "صوري".
    3. صور فيها أشخاص آخرون -> مجلد "صور الزملاء والإخوة".
    4. فيديوهات مضحكة -> مجلد "فيديوهات مضحكة".
    5. فيديوهات محاضرات/تعليمية -> مجلد "محاضرات وتعلم".
    6. أفلام ومسلسلات -> مجلد "أفلام ومسلسلات".
    7. أغاني وأناشيد -> مجلد "أغاني وأناشيد".
    8. أي وسائط أخرى -> مجلد "خارج التصنيف".
- تشغيل الفحص على دفعات (Batches) لتفادي تجميد النظام واستهلاك الطاقة.
"""

import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable

import classifier
import face_classifier
import file_manager
import video_classifier

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm"}

CATEGORY_MY_PHOTOS = "صوري"
CATEGORY_FRIENDS_PHOTOS = "صور اصدقاء"
CATEGORY_EXAMS_ROOT = "صور اختبارات"
CATEGORY_UNCLASSIFIED = "خارج التصنيف"


def get_cache_db_path() -> Path:
    """مسار قاعدة بيانات التتبع لمنع إعادة فحص الملفات المكررة"""
    base = file_manager.get_media_sorter_base_path()
    return base / "scanned_media_cache.db"


def init_cache_db() -> None:
    """تهيئة جدول تتبع الملفات المفحوصة في SQLite"""
    db_path = get_cache_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scanned_files (
            file_path TEXT PRIMARY KEY,
            file_size INTEGER,
            mtime REAL,
            category TEXT,
            processed_at REAL
        )
    """)
    conn.commit()
    conn.close()


def is_file_already_processed(file_path: str, file_size: int, mtime: float) -> bool:
    """التحقق مما إذا كان الملف قد تمت معالجته مسبقاً ولم يتغير حجمه أو تاريخه"""
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return False
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT file_size, mtime FROM scanned_files WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        conn.close()
        if row:
            saved_size, saved_mtime = row
            if saved_size == file_size and abs(saved_mtime - mtime) < 1.0:
                return True
    except Exception:
        pass
    return False


def record_processed_file(file_path: str, file_size: int, mtime: float, category: str) -> None:
    """تسجيل الملف في قاعدة بيانات الملفات المعالجة"""
    try:
        init_cache_db()
        db_path = get_cache_db_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO scanned_files (file_path, file_size, mtime, category, processed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (file_path, file_size, mtime, category, time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        print("خطأ أثناء تسجيل الملف المفحوص:", e)


def scan_storage_roots() -> list[Path]:
    """
    استكشاف جميع جذور التخزين القابلة للفحص:
    - على أندرويد: الذاكرة الداخلية المشتركة (/storage/emulated/0) وبطاقات الذاكرة الخارجية SD.
    - على الحاسوب: مجلدات المستخدم الافتراضية للوسائط ومجلد اختباري للمشروع.
    """
    roots: list[Path] = []
    try:
        from kivy.utils import platform
        if platform == "android":
            # 1. الذاكرة الداخلية المشتركة
            internal_root = Path("/storage/emulated/0")
            if internal_root.exists():
                roots.append(internal_root)

            # 2. فحص بطاقات الذاكرة الخارجية في /storage
            storage_dir = Path("/storage")
            if storage_dir.exists():
                for item in storage_dir.iterdir():
                    if item.is_dir() and item.name not in ("emulated", "self", "knox"):
                        roots.append(item)
            return roots
    except Exception:
        pass

    # على بيئة سطح المكتب للتطوير والتجربة
    project_dir = Path(__file__).resolve().parent
    project_test_dir = project_dir / "test_media_input"
    project_test_dir.mkdir(parents=True, exist_ok=True)
    roots.append(project_test_dir)

    # فحص أي مجلدات أمثلة تجريبية وضعها المستخدم في المشروع (باستثناء النسخ الاحتياطية)
    for item in project_dir.iterdir():
        if item.is_dir() and "امثلة" in item.name and "نسخة" not in item.name and "backup" not in item.name.lower():
            roots.append(item)

    return roots


def find_unsorted_media(roots: list[Path] | None = None, max_depth: int = 8) -> list[Path]:
    """
    البحث الشجري عن جميع الصور والفيديوهات غير المصنفة:
    - استثناء مجلد MediaSorter و ExamSorter ومجلدات أندرويد المحمية Android/data و Android/obb.
    - استثناء الملفات المعالجة مسبقاً.
    """
    if roots is None:
        roots = scan_storage_roots()

    found_files: list[Path] = []
    excluded_dir_names = {
        "mediasorter", "examsorter", ".git", ".venv", "venv",
        "__pycache__", "temp", "node_modules", ".buildozer",
        "امثلة_نسخة_احتياطية", "backup", "backups"
    }

    for root_dir in roots:
        if not root_dir.exists() or not root_dir.is_dir():
            continue

        try:
            for root, dirs, files in os.walk(str(root_dir)):
                # استبعاد المجلدات الممنوعة وتعديل dirs في المكان لتفادي النزول فيها
                kept_dirs = []
                for d in dirs:
                    if d.startswith(".") or d.lower() in excluded_dir_names:
                        continue
                    full_sub = (Path(root) / d).as_posix().lower()
                    if "/android/data" in full_sub or "/android/obb" in full_sub:
                        continue
                    kept_dirs.append(d)
                dirs[:] = kept_dirs

                # فحص عمق التفرع
                depth = len(Path(root).relative_to(root_dir).parts)
                if depth > max_depth:
                    continue

                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                        full_path = Path(root) / f
                        try:
                            st = full_path.stat()
                            if is_file_already_processed(str(full_path), st.st_size, st.st_mtime):
                                continue
                            found_files.append(full_path)
                        except Exception:
                            continue
        except Exception as e:
            print(f"خطأ أثناء فحص المجلد {root_dir}:", e)

    return found_files


def is_visual_document_or_paper(image_path: str) -> bool:
    """
    فحص بصري بالرؤية الحاسوبية (OpenCV) لمعرفة ما إذا كانت الصورة ورقة مستند أو اختبار:
    - فحص تشبع الألوان (HSV Saturation): الأوراق والمستندات ذات تشبع لوني شبه منعدم (< 48).
    - فحص السطوع (HSV Value): خلفية الورقة فاتحة وبيضاء/رمادية (سطوع > 130).
    - فحص نسبة الحبر للنصوص عبر Otsu Threshold: كثافة النصوص بين 1.2% و 38%.
    - فحص التوزيع الأفقي للأسطر (Horizontal projection variance): وجود سطور كتابة.
    """
    try:
        import cv2
        import numpy as np

        img = face_classifier._safe_read_image(image_path)
        if img is None:
            return False
        h, w = img.shape[:2]
        if h < 100 or w < 100:
            return False

        # تصغير سريع لتقليل استهلاك المعالج والذاكرة
        max_dim = max(h, w)
        if max_dim > 600:
            scale = 600.0 / max_dim
            small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        else:
            small = img

        # استثناء الصور التي تحتوي على وجوه بشرية (صور شخصية وليست مستندات)
        import face_classifier
        faces = face_classifier.detect_faces_in_image(small)
        if len(faces) > 0:
            return False

        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        mean_s = float(np.mean(hsv[:, :, 1]))
        mean_v = float(np.mean(hsv[:, :, 2]))

        # الأوراق والمستندات تتميز بخلفية بيضاء/فاتحة وتشبع لوني منخفض
        if mean_s > 58.0 or mean_v < 118.0:
            return False

        # استخراج عتبة الحبر والنصوص باستخدام Otsu Threshold
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink_ratio = float(np.count_nonzero(thresh) / thresh.size)

        # نسبة الحبر في أوراق الاختبارات والمستندات عادة بين 1% و 60%
        if not (0.01 <= ink_ratio <= 0.60):
            return False

        # التحقق من وجود توزيع أفقي لسطور النصوص (Horizontal projection standard deviation)
        horiz_hist = np.sum(thresh, axis=1)
        if float(np.std(horiz_hist)) < 5.0:
            return False

        return True
    except Exception:
        return False


def is_likely_exam_paper(image_path: str) -> bool:
    """
    فحص أولي سريع عالي الكفاءة لمعرفة ما إذا كانت الصورة ورقة اختبار:
    1. فحص اسم الملف (exam, test, quiz, midterm, final, اختبار, امتحان, مقرر...).
    2. فحص الرؤية الحاسوبية المستنداتي (ورقة بيضاء + تشبع منخفض + كثافة حبر وتوزيع سطور).
    3. فحص الترويسة عبر OCR إن كان متاحاً.
    """
    name_lower = Path(image_path).name.lower()
    exam_terms = [
        "exam", "test", "quiz", "midterm", "final", "sheet", "paper",
        "اختبار", "امتحان", "كويز", "شهري", "نهائي", "ورقة", "مقرر", "اسئلة", "أسئلة"
    ]
    if any(term in name_lower for term in exam_terms):
        return True

    # فحص الرؤية الحاسوبية لمستندات الأوراق والاختبارات المصورة بالكاميرا مثل IMG_*.jpg
    if is_visual_document_or_paper(image_path):
        return True

    # محاولة فحص الترويسة عبر OCR إن كانت المكتبة متوفرة
    try:
        subject = classifier.classify_with_local_ocr(image_path)
        if subject:
            return True
    except Exception:
        pass

    return False


def process_one_file(file_path: str | Path, api_key: str | None = None) -> dict[str, Any]:
    """
    تطبيق قواعد التصنيف بدقة وتسلسل الأولويات المعتمد، ونقل الملف بأمان:
    1. صور اختبارات جامعية -> مجلد المادة.
    2. صوري أنا -> مجلد "صوري".
    3. صور فيها أشخاص آخرون -> مجلد "صور الزملاء والإخوة".
    4. فيديوهات مضحكة / محاضرات / أفلام / أغاني.
    5. خارج التصنيف.
    """
    p = Path(file_path).resolve()
    if not p.exists() or not p.is_file():
        return {"success": False, "error": "الملف غير موجود"}

    ext = p.suffix.lower()
    target_category = CATEGORY_UNCLASSIFIED
    detected_details = ""
    orig_size = p.stat().st_size
    orig_mtime = p.stat().st_mtime

    # =========================================================================
    # 1. إذا كان الملف صورة (Image Routing)
    # =========================================================================
    if ext in IMAGE_EXTENSIONS:
        # أولوية 1: صور الاختبارات والمقررات بالاسم أو الرؤية المستنداتية أو OCR
        if is_likely_exam_paper(str(p)):
            try:
                subject_name = classifier.classify_exam_image(str(p), api_key=api_key, fallback_to_ocr=True)
                if subject_name and subject_name.strip():
                    clean_sub = subject_name.strip()
                    target_category = f"{CATEGORY_EXAMS_ROOT}/{clean_sub}"
                    detected_details = f"ورقة اختبار مادة: {clean_sub}"
            except Exception:
                # إذا حُسمت الورقة كمستند/اختبار لكن تعذر استخراج المادة أوفلاين
                target_category = f"{CATEGORY_EXAMS_ROOT}/اختبارات عامة"
                detected_details = "ورقة اختبار ومستند دراسي (بانتظار تحديد المادة)"

        # إذا لم تحسم كاختبار بالاسم أو الرؤية، نفحص الوجوه
        if target_category == CATEGORY_UNCLASSIFIED:
            face_result = face_classifier.detect_and_match_face(str(p))
            if face_result == "me":
                target_category = CATEGORY_MY_PHOTOS
                detected_details = "مطابقة بصمة وجه صاحب الجهاز"
            elif face_result == "other":
                target_category = CATEGORY_FRIENDS_PHOTOS
                detected_details = "اكتشاف وجوه أصدقاء وإخوة"
            else:
                # إذا كانت الصورة خالية من الوجوه (None): نفحص ما إذا كانت ورقة اختبار
                if is_likely_exam_paper(str(p)):
                    try:
                        subject_name = classifier.classify_exam_image(str(p), api_key=api_key, fallback_to_ocr=True)
                        if subject_name and subject_name.strip():
                            clean_sub = subject_name.strip()
                            target_category = f"{CATEGORY_EXAMS_ROOT}/{clean_sub}"
                            detected_details = f"ورقة اختبار مادة مصنفة: {clean_sub}"
                    except Exception:
                        target_category = f"{CATEGORY_EXAMS_ROOT}/اختبارات عامة"
                        detected_details = "ورقة اختبار ومستند دراسي"
                elif api_key or os.getenv("ANTHROPIC_API_KEY"):
                    try:
                        subject_name = classifier.classify_exam_image(str(p), api_key=api_key, fallback_to_ocr=True)
                        if subject_name and subject_name.strip():
                            clean_sub = subject_name.strip()
                            target_category = f"{CATEGORY_EXAMS_ROOT}/{clean_sub}"
                            detected_details = f"ورقة اختبار مادة مصنفة بالذكاء الاصطناعي: {clean_sub}"
                    except Exception:
                        pass

                if target_category == CATEGORY_UNCLASSIFIED:
                    target_category = CATEGORY_UNCLASSIFIED
                    detected_details = "لا يوجد وجه بشري أو ترويسة اختبار"

    # =========================================================================
    # 2. إذا كان الملف مقطع فيديو (Video Routing)
    # =========================================================================
    elif ext in VIDEO_EXTENSIONS:
        v_cat = video_classifier.classify_video(str(p), api_key=api_key)
        target_category = v_cat
        detected_details = f"تصنيف فيديو: {v_cat}"

    # =========================================================================
    # تنفيذ النقل الفعلي المحمي مع التحقق الصارم من الحجم
    # =========================================================================
    try:
        dest_path = file_manager.move_to_category(p, target_category)
        record_processed_file(str(dest_path), orig_size, orig_mtime, target_category)
        return {
            "success": True,
            "source": str(p),
            "destination": str(dest_path),
            "category": target_category,
            "details": detected_details
        }
    except Exception as e:
        print(f"فشل نقل الملف {p}:", e)
        return {
            "success": False,
            "source": str(p),
            "category": target_category,
            "error": str(e)
        }


def run_batch_scan(
    max_files: int = 30,
    api_key: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None
) -> dict[str, Any]:
    """
    تشغيل فحص دفعي متحكم به لتجنب استهلاك البطارية أو تجميد الواجهة.
    """
    init_cache_db()
    media_files = find_unsorted_media()
    total_found = len(media_files)
    batch = media_files[:max_files]

    processed_count = 0
    results: list[dict[str, Any]] = []

    for idx, f in enumerate(batch):
        if progress_callback:
            progress_callback(idx + 1, len(batch), f.name)

        res = process_one_file(f, api_key=api_key)
        results.append(res)
        if res.get("success"):
            processed_count += 1

        # فترة راحة قصيرة جداً (30ms) بين الملفات لمنع رفع حرارة المعالج و ANR
        time.sleep(0.03)

    return {
        "total_unprocessed_found": total_found,
        "batch_size": len(batch),
        "processed_count": processed_count,
        "results": results
    }
