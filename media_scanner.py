"""
وحدة الفحص والفرز الشامل للوسائط (Media Scanner):
- فحص وسائط الذاكرة الداخلية والخارجية تلقائياً.
- استثناء المجلدات المحمية ومجلد MediaSorter وقاعدة بيانات التتبع.
- توجيه كل ملف للمصنف المناسب حسب الأولويات:
    1. صور اختبارات جامعية -> مجلد المادة الدراسية.
    2. صوري أنا -> مجلد "صوري".
    3. صور فيها أشخاص آخرون -> مجلد "صور الزملاء والإخوة".
    4. فيديوهات مضحكة -> مجلد "فيديوهات مضحكة".
    5. فيديوهات محاضرات/تعليمية -> مجلد "محاضرات وتعلم".
    6. أفلام ومسلسلات -> مجلد "أفلام ومسلسلات".
    7. أغاني وأناشيد -> مجلد "أغاني وأناشيد".
    8. أي وسائط أخرى -> مجلد "خارج التصنيف".
- تشغيل الفحص على دفعات (Batches) لتفادي تجميد النظام.
"""

import logging
import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

try:
    import cv2
except Exception:
    cv2 = None  # type: ignore
import numpy as np

import classifier
import face_classifier
import file_manager
import video_classifier

logger = logging.getLogger("MediaScanner")

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".gif", ".bmp", ".heic", ".heif",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".3gp", ".mov",
    ".avi", ".webm", ".m4v", ".flv",
}

CATEGORY_MY_PHOTOS = "صوري"
CATEGORY_FRIENDS_PHOTOS = "صور اخوتي وزملائي"
CATEGORY_EXAMS_ROOT = "صور الاختبارات"
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
    _ = cursor.execute("""
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


def is_file_already_processed(
    file_path: str, file_size: int, mtime: float
) -> bool:
    """التحقق مما إذا كان الملف قد تمت معالجته مسبقاً دون تغيير"""
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return False
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        query = (
            "SELECT file_size, mtime FROM scanned_files WHERE file_path = ?"
        )
        _ = cursor.execute(query, (file_path,))
        row: object = cursor.fetchone()
        conn.close()
        if isinstance(row, (tuple, list)) and len(row) >= 2:
            saved_size = int(str(row[0]))
            saved_mtime = float(str(row[1]))
            if saved_size == file_size and abs(saved_mtime - mtime) < 1.0:
                return True
    except (sqlite3.Error, OSError, ValueError) as e:
        logger.debug("خطأ أثناء قراءة سجل الملف المفحوص: %s", e)
    return False


def get_all_scanned_files_set() -> set[str]:
    """تحميل مسارات كافة الملفات المفحوصة مسبقاً في الذاكرة دفعة واحدة لسرعة فائقة"""
    scanned: set[str] = set()
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return scanned
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM scanned_files")
        for row in cursor.fetchall():
            if row and row[0]:
                scanned.add(str(row[0]))
        conn.close()
    except Exception as e:
        logger.debug("خطأ أثناء قراءة كاش الملفات: %s", e)
    return scanned


def record_processed_file(
    file_path: str, file_size: int, mtime: float, category: str
) -> None:
    """تسجيل الملف في قاعدة بيانات الملفات المعالجة"""
    try:
        init_cache_db()
        db_path = get_cache_db_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        sql = """
            INSERT OR REPLACE INTO scanned_files
            (file_path, file_size, mtime, category, processed_at)
            VALUES (?, ?, ?, ?, ?)
        """
        _ = cursor.execute(
            sql, (file_path, file_size, mtime, category, time.time())
        )
        conn.commit()
        conn.close()
    except (sqlite3.Error, OSError) as e:
        print("خطأ أثناء تسجيل الملف المفحوص:", e)


def unrecord_processed_file(
    file_path: str, dest_path: str | None = None
) -> None:
    """إزالة الملف من قاعدة بيانات التتبع لإتاحة فحصه مجدداً"""
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        del_sql = "DELETE FROM scanned_files WHERE file_path = ?"
        _ = cursor.execute(del_sql, (file_path,))
        if dest_path:
            _ = cursor.execute(del_sql, (dest_path,))
        conn.commit()
        conn.close()
    except (sqlite3.Error, OSError) as e:
        logger.debug("خطأ أثناء إزالة الملف من قاعدة البيانات: %s", e)


def clear_all_cache() -> None:
    """مسح كامل سجل التتبع المؤقت لتمكين إعادة الفحص الشامل"""
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        _ = cursor.execute("DELETE FROM scanned_files")
        conn.commit()
        conn.close()
    except (sqlite3.Error, OSError) as e:
        logger.debug("خطأ أثناء مسح قاعدة البيانات: %s", e)


def scan_storage_roots(source_storage: str | None = None) -> list[Path]:
    """
    استكشاف جذور التخزين القابلة للفحص بحسب المصدر المحدد:
    - 'internal': فحص الذاكرة الداخلية المشتركة فقط
    - 'sdcard': فحص بطاقة الذاكرة الخارجية SD Card فقط
    - 'both' أو None: فحص الذاكرة الداخلية والذاكرة الخارجية معاً
    """
    if source_storage is None:
        prefs = file_manager.get_sorter_preferences()
        source_storage = str(prefs.get("source_storage", "both"))

    roots: list[Path] = []
    try:
        from kivy.utils import platform
        if platform == "android":
            internal_root = Path("/storage/emulated/0")
            sd_root = file_manager.find_external_sdcard_root()

            has_internal = source_storage in ("internal", "both")
            if has_internal and internal_root.exists():
                roots.append(internal_root)

            if source_storage in ("sdcard", "both"):
                try:
                    if sd_root and sd_root.exists() and sd_root not in roots:
                        roots.append(sd_root)
                except (OSError, RuntimeError) as e:
                    logger.debug("تعذر الوصول لبطاقة SD: %s", e)

            return roots
    except (ImportError, OSError, RuntimeError) as e:
        logger.debug("تنبيه أثناء استكشاف جذور التخزين: %s", e)

    # على بيئة سطح المكتب للتطوير والتجربة
    project_dir = Path(__file__).resolve().parent
    project_test_dir = project_dir / "test_media_input"
    project_test_dir.mkdir(parents=True, exist_ok=True)
    roots.append(project_test_dir)

    # فحص أي مجلدات أمثلة تجريبية وضعها المستخدم في المشروع
    for item in project_dir.iterdir():
        is_ex = "امثلة" in item.name
        is_bk = "نسخة" in item.name or "backup" in item.name.lower()
        if item.is_dir() and is_ex and not is_bk:
            roots.append(item)

    return roots


def find_unsorted_media(
    roots: list[Path] | None = None,
    max_depth: int = 8,
    source_storage: str | None = None
) -> list[Path]:
    """
    البحث الشجري عن جميع الصور والفيديوهات غير المصنفة:
    - استثناء مجلد الملفات المنظمة ومجلدات أندرويد المحمية.
    - استثناء مجلد الحفظ المعتمد أياً كان مساره لمنع التكرار.
    - استثناء الملفات المعالجة مسبقاً.
    """
    if roots is None:
        roots = scan_storage_roots(source_storage=source_storage)

    found_files: list[Path] = []
    scanned_set = get_all_scanned_files_set()
    excluded_dir_names = {
        "الملفات المنظمة", "الملفات_المنظمة", "mediasorter",
        "examsorter", ".git", ".venv", "venv",
        "__pycache__", "temp", "node_modules", ".buildozer",
        "امثلة_نسخة_احتياطية", "backup", "backups",
        "android", ".android", "data", "obb", "cache", ".thumbnails",
        "lost.dir", "alms",
    }

    try:
        active_target_base = (
            file_manager.get_media_sorter_base_path().resolve()
        )
    except (OSError, RuntimeError):
        active_target_base = None

    for root_dir in roots:
        if not root_dir.exists() or not root_dir.is_dir():
            continue

        try:
            for root, dirs, files in os.walk(str(root_dir)):
                curr_root_path = Path(root).resolve()
                is_sub_of_target = (
                    active_target_base is not None
                    and (
                        curr_root_path == active_target_base
                        or active_target_base in curr_root_path.parents
                    )
                )
                if is_sub_of_target:
                    dirs[:] = []
                    continue

                # استبعاد المجلدات الممنوعة وتعديل dirs في المكان
                kept_dirs: list[str] = []
                for d in dirs:
                    d_lower = d.lower()
                    if d.startswith(".") or d_lower in excluded_dir_names:
                        continue
                    full_sub_path = curr_root_path / d
                    if (
                        active_target_base is not None
                        and full_sub_path == active_target_base
                    ):
                        continue
                    full_sub = full_sub_path.as_posix().lower()
                    if (
                        "/android" in full_sub
                        or "/data" in full_sub
                        or "/obb" in full_sub
                        or "/cache" in full_sub
                    ):
                        continue
                    kept_dirs.append(d)
                dirs[:] = kept_dirs

                # فحص عمق التفرع
                depth = len(Path(root).relative_to(root_dir).parts)
                if depth > max_depth:
                    continue

                for f in files:
                    if f.startswith("."):
                        continue
                    ext = Path(f).suffix.lower()
                    if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                        full_path = Path(root) / f
                        str_full = str(full_path)
                        if str_full in scanned_set:
                            continue
                        found_files.append(full_path)
        except (OSError, RuntimeError) as e:
            print(f"خطأ أثناء فحص المجلد {root_dir}:", e)

    return found_files


def is_visual_document_or_paper(image_path: str) -> bool:
    """
    فحص بصري بالرؤية الحاسوبية لمعرفة ما إذا كانت الصورة مستنداً أو ورقة:
    - فحص تشبع الألوان (HSV Saturation): تشبع شبه منعدم (< 58).
    - فحص السطوع (HSV Value): خلفية الورقة فاتحة (> 118).
    - فحص نسبة الحبر للنصوص عبر Otsu Threshold بين 1% و 60%.
    - فحص التوزيع الأفقي للأسطر.
    """
    try:
        small = face_classifier.safe_read_image(image_path, max_size=500)
        if small is None:
            return False
        h = int(str(small.shape[0]))
        w = int(str(small.shape[1]))
        if h < 80 or w < 80:
            return False

        if cv2 is not None:
            # استثناء الصور التي تحتوي على وجوه بشرية
            faces = face_classifier.detect_faces_in_image(small)
            if len(faces) > 0:
                return False

            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            mean_s = float(str(np.mean(hsv[:, :, 1])))
            mean_v = float(str(np.mean(hsv[:, :, 2])))

            # الأوراق والمستندات تتميز بخلفية بيضاء/فاتحة وتشبع لوني منخفض
            if mean_s > 58.0 or mean_v < 118.0:
                return False

            # استخراج عتبة الحبر والنصوص باستخدام Otsu Threshold
            otsu_flag = cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            _, thresh = cv2.threshold(gray, 0, 255, otsu_flag)
            ink_ratio = float(np.count_nonzero(thresh) / thresh.size)

            # نسبة الحبر في أوراق الاختبارات والمستندات عادة بين 1% و 60%
            if not (0.01 <= ink_ratio <= 0.60):
                return False

            # التحقق من وجود توزيع أفقي لسطور النصوص
            horiz_hist = np.sum(thresh, axis=1)
            return float(np.std(horiz_hist)) >= 5.0
        else:
            # بديل نقي معتمد على NumPy
            faces = face_classifier.detect_faces_in_image(small)
            if len(faces) > 0:
                return False
            b = small[:, :, 0].astype(np.float32)
            g = small[:, :, 1].astype(np.float32)
            r = small[:, :, 2].astype(np.float32)
            v = np.maximum(np.maximum(r, g), b)
            m = np.minimum(np.minimum(r, g), b)
            delta = v - m
            s = np.where(v == 0, 0, (delta / np.maximum(v, 1.0)) * 255.0)
            if float(np.mean(s)) > 58.0 or float(np.mean(v)) < 118.0:
                return False
            gray = 0.299 * r + 0.587 * g + 0.114 * b
            ink_mask = gray < 180.0
            ink_ratio = float(np.count_nonzero(ink_mask) / ink_mask.size)
            if not (0.01 <= ink_ratio <= 0.60):
                return False
            horiz_hist = np.sum(ink_mask, axis=1)
            return float(np.std(horiz_hist)) >= 5.0
    except Exception as e:
        logger.debug("خطأ أثناء فحص الرؤية الحاسوبية للورقة: %s", e)
        return False


def is_likely_exam_paper(image_path: str) -> bool:
    """
    فحص أولي سريع عالي الكفاءة لمعرفة ما إذا كانت الصورة ورقة اختبار:
    1. فحص اسم الملف (exam, test, quiz, midterm, final, اختبار...).
    2. فحص الرؤية الحاسوبية المستنداتي (ورقة بيضاء + تشبع منخفض + سطور).
    3. فحص الترويسة عبر OCR إن كان متاحاً.
    """
    name_lower = Path(image_path).name.lower()
    exam_terms = [
        "exam", "test", "quiz", "midterm", "final", "sheet", "paper",
        "اختبار", "امتحان", "كويز", "شهري", "نهائي", "ورقة", "مقرر",
        "اسئلة", "أسئلة",
    ]
    if any(term in name_lower for term in exam_terms):
        return True

    # فحص الرؤية الحاسوبية لمستندات الأوراق والاختبارات
    if is_visual_document_or_paper(image_path):
        return True

    # محاولة فحص الترويسة عبر OCR إن كانت المكتبة متوفرة
    try:
        subject = classifier.classify_with_local_ocr(image_path)
        if subject:
            return True
    except Exception as e:
        logger.debug("فشل فحص OCR المحلي للورقة: %s", e)

    return False


def _guess_exam_subject(filename: str) -> str:
    """تخمين اسم المادة الدراسية بذكاء من اسم الملف في حال غياب مفتاح API أو الإنترنت"""
    name_clean = Path(filename).stem.lower().replace("_", " ").replace("-", " ")
    subject_keywords: dict[str, list[str]] = {
        "رياضيات": ["رياضيات", "math", "calculus", "جبر", "تفاضل", "هندسة"],
        "فيزياء": ["فيزياء", "physic", "physics"],
        "كيمياء": ["كيمياء", "chem", "chemistry"],
        "أحياء": ["أحياء", "احياء", "bio", "biology"],
        "برمجة": ["برمجة", "programming", "code", "python", "java", "حاسوب"],
        "لغة إنجليزية": ["english", "إنجليزي", "انجليزي"],
        "لغة عربية": ["عربي", "نحو", "بلاغة", "arabic"],
        "علوم": ["علوم", "science"],
        "تاريخ": ["تاريخ", "history"],
        "جغرافيا": ["جغرافيا", "geography"],
        "إسلامية": ["إسلامية", "اسلامية", "قرآن", "حديث", "فقه", "توحيد"],
    }
    for subj, kws in subject_keywords.items():
        if any(kw in name_clean for kw in kws):
            return subj
    return "اختبارات عامة"


def process_one_file(
    file_path: str | Path,
    api_key: str | None = None,
    copy_only: bool | None = None
) -> dict[str, object]:
    """
    تطبيق قواعد التصنيف بدقة وتسلسل الأولويات المعتمد، ونقل أو نسخ الملف بأمان:
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

    # تحديد نمط العملية (نسخ آمن أم نقل مع حذف الأصل)
    if copy_only is None:
        prefs = file_manager.get_sorter_preferences()
        is_copy: bool = (prefs.get("operation_mode", "copy") == "copy")
    else:
        is_copy = copy_only

    # =========================================================================
    # 1. إذا كان الملف صورة (Image Routing)
    # =========================================================================
    if ext in IMAGE_EXTENSIONS:
        # أولوية 1: صور الاختبارات والمقررات بالاسم أو الرؤية أو OCR
        if is_likely_exam_paper(str(p)):
            try:
                subject_name = classifier.classify_exam_image(
                    str(p), api_key=api_key, fallback_to_ocr=True
                )
                if subject_name and subject_name.strip():
                    clean_sub = subject_name.strip()
                    target_category = f"{CATEGORY_EXAMS_ROOT}/{clean_sub}"
                    detected_details = f"ورقة اختبار مادة: {clean_sub}"
            except Exception:
                guessed = _guess_exam_subject(p.name)
                target_category = f"{CATEGORY_EXAMS_ROOT}/{guessed}"
                detected_details = f"ورقة اختبار مادة: {guessed}"

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
                # إذا كانت الصورة خالية من الوجوه: نفحص إن كانت ورقة اختبار
                if is_likely_exam_paper(str(p)):
                    try:
                        subject_name = classifier.classify_exam_image(
                            str(p), api_key=api_key, fallback_to_ocr=True
                        )
                        if subject_name and subject_name.strip():
                            clean_sub = subject_name.strip()
                            target_category = (
                                f"{CATEGORY_EXAMS_ROOT}/{clean_sub}"
                            )
                            detected_details = (
                                f"ورقة اختبار مادة مصنفة: {clean_sub}"
                            )
                    except Exception:
                        guessed = _guess_exam_subject(p.name)
                        target_category = (
                            f"{CATEGORY_EXAMS_ROOT}/{guessed}"
                        )
                        detected_details = f"ورقة اختبار مادة: {guessed}"
                elif api_key or os.getenv("ANTHROPIC_API_KEY"):
                    try:
                        subject_name = classifier.classify_exam_image(
                            str(p), api_key=api_key, fallback_to_ocr=True
                        )
                        if subject_name and subject_name.strip():
                            clean_sub = subject_name.strip()
                            target_category = (
                                f"{CATEGORY_EXAMS_ROOT}/{clean_sub}"
                            )
                            detected_details = (
                                f"ورقة اختبار مادة مصنفة: {clean_sub}"
                            )
                    except Exception as e:
                        logger.debug("فشل تصنيف الورقة بالذكاء: %s", e)

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

    # تنفيذ العملية (نسخ آمن أو نقل) مع الحفاظ على التوثيق
    # =========================================================================
    try:
        dest_path = file_manager.move_to_category(
            p, target_category, copy_only=is_copy
        )
        record_processed_file(
            str(p), orig_size, orig_mtime, target_category
        )
        record_processed_file(
            str(dest_path), orig_size, orig_mtime, target_category
        )
        return {
            "success": True,
            "source": str(p),
            "destination": str(dest_path),
            "category": target_category,
            "details": detected_details,
            "mode": "copy" if is_copy else "move",
        }
    except (OSError, ValueError, RuntimeError) as e:
        print(f"فشل معالجة الملف {p}:", e)
        return {
            "success": False,
            "source": str(p),
            "category": target_category,
            "error": str(e),
        }


def run_batch_scan(
    max_files: int = 30,
    api_key: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    source_storage: str | None = None
) -> dict[str, object]:
    """
    تشغيل فحص دفعي متحكم به لتجنب استهلاك البطارية أو تجميد الواجهة.
    """
    init_cache_db()
    media_files = find_unsorted_media(source_storage=source_storage)
    total_found = len(media_files)
    batch = media_files[:max_files]

    processed_count = 0
    results: list[dict[str, object]] = []

    for idx, f in enumerate(batch):
        if progress_callback:
            progress_callback(idx + 1, len(batch), f.name)

        res = process_one_file(f, api_key=api_key)
        results.append(res)
        if res.get("success"):
            processed_count += 1

        # فترة راحة قصيرة جداً (30ms) بين الملفات لمنع رفع حرارة المعالج
        time.sleep(0.03)

    return {
        "total_unprocessed_found": total_found,
        "batch_size": len(batch),
        "processed_count": processed_count,
        "results": results,
    }


def run_continuous_scan(
    batch_size: int = 25,
    api_key: str | None = None,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
    stop_check: Callable[[], bool] | None = None,
    source_storage: str | None = None
) -> dict[str, object]:
    """
    تشغيل فرز متواصل مستمر حتى الانتهاء من جميع الملفات المتاحة على الجهاز
    مع حماية متقدمة من نفاد الذاكرة وتحمل ضغط آلاف الملفات والصور الكبيرة.
    """
    import gc
    init_cache_db()
    total_processed = 0
    all_results: list[dict[str, object]] = []

    # استكشاف الملفات دفعة واحدة في البداية بدلاً من إعادة المسح البطيء
    media_files = find_unsorted_media(source_storage=source_storage)
    total_files = len(media_files)
    if total_files == 0:
        return {
            "total_processed": 0,
            "batches_completed": 0,
            "results": [],
        }

    for idx, f in enumerate(media_files):
        if stop_check and stop_check():
            break

        try:
            res: dict[str, object] = process_one_file(f, api_key=api_key)
        except Exception as e:
            logger.error("خطأ أثناء معالجة الملف %s: %s", f, e)
            res = {"success": False, "error": str(e), "original_path": str(f)}

        if res.get("success"):
            total_processed += 1

        # الاحتفاظ بآخر 50 نتيجة فقط لتجنب استهلاك ذاكرة RAM عند معالجة آلاف الملفات
        if len(all_results) < 50:
            all_results.append(res)

        if progress_callback:
            progress_callback({
                "current_file": f.name,
                "batch_index": idx + 1,
                "batch_total": total_files,
                "total_processed": total_processed,
                "remaining_count": max(0, total_files - (idx + 1)),
                "is_finished": False,
            })

        # تنظيف الذاكرة دورياً كل 20 ملفاً لمنع انهيار التطبيق تحت الضغط العالي
        if (idx + 1) % 20 == 0:
            gc.collect()
            time.sleep(0.03)
        else:
            time.sleep(0.01)

    gc.collect()

    if progress_callback:
        progress_callback({
            "current_file": "",
            "batch_index": total_files,
            "batch_total": total_files,
            "total_processed": total_processed,
            "remaining_count": 0,
            "is_finished": True,
        })

    return {
        "total_processed": total_processed,
        "batches_completed": (total_processed // batch_size) + 1,
        "results": all_results,
    }
