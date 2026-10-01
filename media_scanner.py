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

from __future__ import annotations

import logging
import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    import cv2
except Exception:
    cv2 = None  # type: ignore
import numpy as np

import classifier
import face_classifier
import file_manager
import storage_backend
import video_classifier

logger = logging.getLogger("MediaScanner")

IMAGE_EXTENSIONS = storage_backend.IMAGE_EXTENSIONS
VIDEO_EXTENSIONS = storage_backend.VIDEO_EXTENSIONS

CATEGORY_MY_PHOTOS = storage_backend.CATEGORY_MY_PHOTOS
CATEGORY_FRIENDS_PHOTOS = storage_backend.CATEGORY_FRIENDS_PHOTOS
CATEGORY_EXAMS_ROOT = storage_backend.CATEGORY_EXAMS_ROOT
CATEGORY_UNCLASSIFIED = storage_backend.CATEGORY_UNCLASSIFIED
CATEGORY_LECTURES = storage_backend.CATEGORY_LECTURES


def get_cache_db_path() -> Path:
    """مسار قاعدة بيانات التتبع لمنع إعادة فحص الملفات المكررة في التخزين الخاص بالتطبيق"""
    p = file_manager.get_app_private_storage_dir() / "scanned_media_cache.db"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def init_cache_db() -> bool:
    """تهيئة جدول تتبع الملفات المفحوصة في SQLite بشكل غير حاجب للفرز"""
    try:
        db_path = get_cache_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scanned_files (
                    file_path TEXT PRIMARY KEY,
                    file_size INTEGER,
                    mtime REAL,
                    category TEXT,
                    dest_path TEXT,
                    dest_size INTEGER,
                    processed_at REAL
                )
            """)
            try:
                cursor.execute("ALTER TABLE scanned_files ADD COLUMN dest_path TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE scanned_files ADD COLUMN dest_size INTEGER")
            except sqlite3.OperationalError:
                pass
            conn.commit()
        return True
    except Exception as e:
        logger.warning("تنبيه: قاعدة بيانات الكاش غير متاحة (سيستمر الفرز بدون كاش): %s", e)
        return False


def is_file_already_processed(
    file_path: str, file_size: int, mtime: float
) -> bool:
    """
    التحقق مما إذا كان الملف قد تمت معالجته مسبقاً وتأكيد وجود النسخة المنظمة في الوجهة:
    إذا كان الملف مسجلاً لكن نسخته في الوجهة مفقودة أو غير مطابقة، يعتبر غير مكتمل ليعاد فرزه!
    """
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return False
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            query = (
                "SELECT file_size, mtime, dest_path, dest_size FROM scanned_files WHERE file_path = ?"
            )
            cursor.execute(query, (file_path,))
            row = cursor.fetchone()
            if row and len(row) >= 2:
                saved_size = int(str(row[0]))
                saved_mtime = float(str(row[1]))
                if saved_size == file_size and abs(saved_mtime - mtime) < 1.0:
                    if len(row) >= 4 and row[2]:
                        dest_str = str(row[2])
                        dest_p = Path(dest_str)
                        if dest_p.exists() and dest_p.is_file():
                            if dest_p.stat().st_size == file_size:
                                return True
                            else:
                                return False
                        else:
                            return False
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
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM scanned_files")
            for row in cursor.fetchall():
                if row and row[0]:
                    scanned.add(str(row[0]))
    except Exception as e:
        logger.debug("خطأ أثناء قراءة كاش الملفات: %s", e)
    return scanned


def get_scanned_files_details() -> dict[str, dict[str, object]]:
    """تحميل تفاصيل الملفات المفحوصة مسبقاً بما فيها مسارات الوجهة وأحجامها"""
    details: dict[str, dict[str, object]] = {}
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return details
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_path, file_size, dest_path, dest_size FROM scanned_files"
            )
            for row in cursor.fetchall():
                if row and row[0]:
                    details[str(row[0])] = {
                        "size": row[1],
                        "dest_path": row[2] if len(row) > 2 else "",
                        "dest_size": row[3] if len(row) > 3 else 0,
                    }
    except Exception as e:
        logger.debug("خطأ أثناء قراءة تفاصيل كاش الملفات: %s", e)
    return details


def record_processed_file(
    file_path: str,
    file_size: int,
    mtime: float,
    category: str,
    dest_path: str = "",
    dest_size: int = 0
) -> bool:
    """تسجيل الملف في كاش التتبع بعد نجاح العملية فعلياً دون تعطيل الفرز عند الفشل"""
    try:
        init_cache_db()
        db_path = get_cache_db_path()
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            sql = """
                INSERT OR REPLACE INTO scanned_files
                (file_path, file_size, mtime, category, dest_path, dest_size, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(
                sql,
                (
                    file_path,
                    file_size,
                    mtime,
                    category,
                    dest_path,
                    dest_size,
                    time.time(),
                ),
            )
            conn.commit()
        return True
    except (sqlite3.Error, OSError) as e:
        logger.warning(
            "تنبيه: تعذر تسجيل الملف المفحوص في الكاش: %s (الفرز مستمر)", e
        )
        return False


def unrecord_processed_file(
    file_path: str, dest_path: str | None = None
) -> None:
    """إزالة الملف من قاعدة بيانات التتبع لإتاحة فحصه مجدداً"""
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            del_sql = "DELETE FROM scanned_files WHERE file_path = ?"
            cursor.execute(del_sql, (file_path,))
            if dest_path:
                cursor.execute(del_sql, (dest_path,))
            conn.commit()
    except (sqlite3.Error, OSError) as e:
        logger.debug("خطأ أثناء إزالة الملف من قاعدة البيانات: %s", e)


def clear_all_cache() -> bool:
    """مسح كامل سجل التتبع المؤقت لتمكين إعادة الفحص الشامل"""
    try:
        db_path = get_cache_db_path()
        if db_path.exists():
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM scanned_files")
                conn.commit()
        return True
    except (sqlite3.Error, OSError) as e:
        logger.warning("خطأ أثناء مسح قاعدة البيانات: %s", e)
        return False


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


def _scan_android_mediastore(
    source_storage: str | None = None,
    scanned_details: dict[str, dict[str, object]] | None = None,
    force_rescan: bool = False,
) -> list[storage_backend.MediaItem]:
    """
    استعلام آمن وشامل لصور وفيديوهات الجهاز عبر Android MediaStore:
    - استخدام الأعمدة القياسية: _ID, DISPLAY_NAME, MIME_TYPE, SIZE, DATE_MODIFIED.
    - دعم RELATIVE_PATH و _DATA (إن توفرا دون اعتماد قسري على _DATA).
    - بناء Content URIs رسمية صالحة للفتح عبر ContentResolver.
    - احترام اختيار الذاكرة (source_storage): internal فقط، sdcard فقط، أو both.
    """
    found: list[storage_backend.MediaItem] = []
    scanned_map = scanned_details or {}
    try:
        from kivy.utils import platform
        if platform != "android":
            return found

        from android import mActivity
        from jnius import autoclass

        MediaStoreImages = autoclass("android.provider.MediaStore$Images$Media")
        MediaStoreVideo = autoclass("android.provider.MediaStore$Video$Media")
        ContentUris = autoclass("android.content.ContentUris")

        targets = [
            (MediaStoreImages.EXTERNAL_CONTENT_URI, "image"),
            (MediaStoreVideo.EXTERNAL_CONTENT_URI, "video"),
        ]

        cr = mActivity.getContentResolver()
        for base_table_uri, _media_kind in targets:
            cursor = None
            try:
                # استعلام بأعمدة آمنة لا ترمي استثناء getColumnIndexOrThrow
                cursor = cr.query(base_table_uri, None, None, None, None)
                if cursor is None:
                    continue

                id_idx = cursor.getColumnIndex("_id")
                name_idx = cursor.getColumnIndex("_display_name")
                mime_idx = cursor.getColumnIndex("mime_type")
                size_idx = cursor.getColumnIndex("_size")
                date_idx = cursor.getColumnIndex("date_modified")
                rel_idx = cursor.getColumnIndex("relative_path")
                data_idx = cursor.getColumnIndex("_data")

                while cursor.moveToNext():
                    item_id = cursor.getLong(id_idx) if id_idx >= 0 else 0
                    if item_id <= 0:
                        continue

                    item_uri_obj = ContentUris.withAppendedId(base_table_uri, item_id)
                    item_uri_str = str(item_uri_obj.toString())

                    name_val = cursor.getString(name_idx) if name_idx >= 0 else ""
                    mime_val = cursor.getString(mime_idx) if mime_idx >= 0 else ""
                    size_val = cursor.getLong(size_idx) if size_idx >= 0 else 0
                    date_val = float(cursor.getLong(date_idx)) if date_idx >= 0 else 0.0

                    rel_path = cursor.getString(rel_idx) if rel_idx >= 0 else ""
                    data_path = cursor.getString(data_idx) if data_idx >= 0 else ""

                    display_name = name_val or (Path(data_path).name if data_path else f"media_{item_id}")
                    ext = Path(display_name).suffix.lower()
                    if not ext and mime_val in storage_backend.MIME_TYPE_MAP:
                        ext = storage_backend.MIME_TYPE_MAP[mime_val]
                        display_name = f"{display_name}{ext}"

                    is_img = (ext in storage_backend.IMAGE_EXTENSIONS) or (mime_val and "image" in mime_val)
                    is_vid = (ext in storage_backend.VIDEO_EXTENSIONS) or (mime_val and "video" in mime_val)
                    if not is_img and not is_vid:
                        continue

                    full_check_str = f"{rel_path or ''}/{data_path or ''}/{display_name}".lower()
                    if "الملفات المنظمة" in full_check_str or "mediasorter" in full_check_str:
                        continue

                    # تصنيف التخزين (internal أو sdcard)
                    is_sdcard = False
                    if data_path:
                        is_sdcard = not data_path.startswith("/storage/emulated/")
                    elif rel_path:
                        is_sdcard = not rel_path.startswith("/storage/emulated/")

                    storage_id = "sdcard" if is_sdcard else "internal"

                    if source_storage == "internal" and is_sdcard:
                        continue
                    if source_storage == "sdcard" and not is_sdcard:
                        continue

                    cache_key = data_path if (data_path and os.path.exists(data_path)) else item_uri_str
                    if not force_rescan and cache_key in scanned_map:
                        info = scanned_map[cache_key]
                        dest_str = str(info.get("dest_path", ""))
                        if dest_str:
                            dest_p = Path(dest_str)
                            try:
                                if dest_p.exists() and dest_p.stat().st_size == size_val:
                                    continue
                            except OSError:
                                pass

                    item = storage_backend.MediaItem(
                        id=item_uri_str,
                        source_type="content_uri" if not (data_path and os.path.exists(data_path)) else "path",
                        path=data_path if (data_path and os.path.exists(data_path)) else "",
                        uri=item_uri_str,
                        display_name=display_name,
                        mime_type=mime_val or ("image/jpeg" if is_img else "video/mp4"),
                        size_bytes=size_val,
                        date_modified=date_val,
                        storage_id=storage_id,
                    )
                    found.append(item)
            finally:
                if cursor is not None:
                    cursor.close()
    except Exception as e:
        logger.warning("استثناء أثناء استعلام MediaStore: %s", e)

    return found


def find_unsorted_media(
    roots: list[Path] | None = None,
    max_depth: int = 10,
    source_storage: str | None = None,
    force_rescan: bool = False,
) -> list[Any]:
    """
    البحث الشجري الموحد والشامل عن جميع الصور والفيديوهات غير المصنفة:
    - دمج نتائج فحص نظام الملفات (os.walk) مع نتائج MediaStore دون استبعاد أي منهما.
    - احترام اختيار الذاكرة (internal / sdcard / both) بشكل صارم وفعلي.
    - عدم استبعاد WhatsApp / Telegram في Android/media مع استبعاد Android/data و Android/obb.
    - استبعاد مجلد الملفات المنظمة والملفات المفحوصة مسبقاً بعد التحقق من وجود نسختها في الوجهة.
    """
    if source_storage is None:
        prefs = file_manager.get_sorter_preferences()
        source_storage = str(prefs.get("source_storage", "both"))

    scanned_details = get_scanned_files_details()
    combined_items: list[Any] = []
    seen_identifiers: set[str] = set()

    # 1. استعلام MediaStore الرسمي على أندرويد
    try:
        from kivy.utils import platform
        if platform == "android":
            ms_items = _scan_android_mediastore(
                source_storage=source_storage,
                scanned_details=scanned_details,
                force_rescan=force_rescan,
            )
            for item in ms_items:
                key = item.path.lower() if item.path else item.uri
                if key not in seen_identifiers:
                    seen_identifiers.add(key)
                    combined_items.append(item)
            logger.info("تم العثور على %d ملف وسائط عبر MediaStore", len(ms_items))
    except Exception as e:
        logger.debug("تنبيه استعلام MediaStore: %s", e)

    # 2. فحص نظام الملفات عبر الجذور (os.walk)
    if roots is None:
        roots = scan_storage_roots(source_storage=source_storage)

    excluded_dir_names = {
        "الملفات المنظمة", "الملفات_المنظمة", "mediasorter",
        "examsorter", ".git", ".venv", "venv",
        "__pycache__", "temp", "node_modules", ".buildozer",
        "امثلة_نسخة_احتياطية", "backup", "backups",
        ".android", ".thumbnails", "lost.dir", "alms",
    }

    priority_dirs = {
        "dcim", "pictures", "movies", "download", "whatsapp",
        "telegram", "documents", "bluetooth", "snapseed", "camera",
        "screenshots", "facebook", "instagram"
    }

    try:
        active_target_base = file_manager.get_media_sorter_base_path().resolve()
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

                kept_dirs: list[str] = []
                for d in dirs:
                    d_lower = d.lower()
                    if d.startswith(".") or d_lower in excluded_dir_names:
                        continue
                    full_sub_path = curr_root_path / d
                    if active_target_base is not None and full_sub_path == active_target_base:
                        continue

                    # استبعاد Android/data و Android/obb المحمية فقط مع السماح بـ Android/media
                    try:
                        rel = full_sub_path.relative_to(root_dir).as_posix().lower()
                        if rel == "android/data" or rel.startswith("android/data/"):
                            continue
                        if rel == "android/obb" or rel.startswith("android/obb/"):
                            continue
                    except ValueError:
                        pass

                    if d_lower in ("data", "obb") and curr_root_path.name.lower() == "android":
                        continue

                    kept_dirs.append(d)

                kept_dirs.sort(
                    key=lambda x: (0 if x.lower() in priority_dirs else 1, x.lower())
                )
                dirs[:] = kept_dirs

                try:
                    depth = len(Path(root).relative_to(root_dir).parts)
                    if depth > max_depth:
                        continue
                except ValueError:
                    pass

                for f in files:
                    if f.startswith("."):
                        continue
                    ext = Path(f).suffix.lower()
                    if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                        full_path = Path(root) / f
                        str_full = str(full_path)
                        str_key = str_full.lower()

                        if str_key in seen_identifiers:
                            continue
                        seen_identifiers.add(str_key)

                        if not force_rescan and str_full in scanned_details:
                            info = scanned_details[str_full]
                            dest_path_str = str(info.get("dest_path", ""))
                            if dest_path_str:
                                dest_p = Path(dest_path_str)
                                try:
                                    if (
                                        dest_p.exists()
                                        and dest_p.is_file()
                                        and dest_p.stat().st_size == full_path.stat().st_size
                                    ):
                                        continue
                                except OSError:
                                    pass

                        combined_items.append(full_path)
        except (OSError, RuntimeError) as e:
            logger.warning("خطأ أثناء فحص المجلد %s: %s", root_dir, e)

    return combined_items


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
    file_path: str | Path | Any,
    api_key: str | None = None,
    copy_only: bool | None = None,
) -> dict[str, object]:
    """
    تطبيق قواعد التصنيف بدقة وتسلسل الأولويات المعتمد، ونقل أو نسخ الملف بأمان:
    - دعم كامل للمسارات الفيزيائية (Path) وكائنات الوسائط المحمولة (MediaItem).
    - استثناء الملفات السامة المسببة لانهيارات سابقة عبر poison_files.
    - تفادي إيقاف الدفعة بالكامل عند فشل قراءة أي ملف أو فيديو تالف.
    """
    item_id = str(file_path)
    if isinstance(file_path, storage_backend.MediaItem):
        item_id = file_path.path or file_path.uri or file_path.id

    if item_id in file_manager.get_poison_files_set():
        logger.info("تخطي ملف سام مستبعد من الفحص: %s", item_id)
        return {
            "success": False,
            "skipped": True,
            "reason": "poison_file",
            "source": item_id,
            "error": "ملف مستبعد لتسببه بانهيار سابق",
        }

    file_manager.mark_file_processing_start(item_id)
    try:
        return _process_one_file_internal(
            file_path, api_key=api_key, copy_only=copy_only
        )
    except Exception as e:
        logger.error("استثناء غير متوقع أثناء معالجة الملف %s: %s", item_id, e, exc_info=True)
        return {
            "success": False,
            "source": item_id,
            "category": CATEGORY_UNCLASSIFIED,
            "error": str(e),
        }
    finally:
        file_manager.mark_file_processing_end()


def _process_one_file_internal(
    file_item: str | Path | Any,
    api_key: str | None = None,
    copy_only: bool | None = None,
) -> dict[str, object]:
    """المعالجة الفعلية للملف مع دعم Content URI والمؤقت الذري"""
    temp_stream_file: Path | None = None
    is_uri_source = False
    source_key = ""

    if isinstance(file_item, storage_backend.MediaItem):
        source_key = file_item.uri or file_item.path or file_item.id
        if file_item.path and Path(file_item.path).exists():
            p = Path(file_item.path).resolve()
        else:
            # نسخ Content URI إلى temp خاص بالتطبيق بطريقة streaming
            is_uri_source = True
            temp_dir = file_manager.get_temp_dir()
            temp_stream_file = temp_dir / f"stream_{int(time.time() * 1000)}_{file_item.name}"
            copied = storage_backend.copy_uri_to_path(file_item.uri, temp_stream_file)
            if not copied or not temp_stream_file.exists():
                return {"success": False, "source": source_key, "error": "تعذر قراءة دفق Content URI"}
            p = temp_stream_file
    elif isinstance(file_item, Path):
        p = file_item.resolve()
        source_key = str(p)
    else:
        source_str = str(file_item)
        if source_str.startswith("content://"):
            is_uri_source = True
            source_key = source_str
            temp_dir = file_manager.get_temp_dir()
            temp_stream_file = temp_dir / f"stream_{int(time.time() * 1000)}.jpg"
            copied = storage_backend.copy_uri_to_path(source_str, temp_stream_file)
            if not copied or not temp_stream_file.exists():
                return {"success": False, "source": source_key, "error": "تعذر قراءة دفق Content URI"}
            p = temp_stream_file
        else:
            p = Path(source_str).resolve()
            source_key = str(p)

    try:
        if not p.exists() or not p.is_file():
            return {"success": False, "source": source_key, "error": "الملف غير موجود"}

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

        # =====================================================================
        # 1. إذا كان الملف صورة (Image Routing)
        # =====================================================================
        if ext in IMAGE_EXTENSIONS:
            # أولوية 1: صور الاختبارات والمقررات بالاسم أو الرؤية أو OCR
            try:
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
            except Exception as e:
                logger.debug("تنبيه فحص ورقة الاختبار: %s", e)

            # إذا لم تحسم كاختبار، نفحص الوجوه
            if target_category == CATEGORY_UNCLASSIFIED:
                try:
                    face_result = face_classifier.detect_and_match_face(str(p))
                    if face_result == "me":
                        target_category = CATEGORY_MY_PHOTOS
                        detected_details = "مطابقة بصمة وجه صاحب الجهاز"
                    elif face_result == "other":
                        target_category = CATEGORY_FRIENDS_PHOTOS
                        detected_details = "اكتشاف وجوه أصدقاء وإخوة"
                except Exception as e:
                    logger.debug("تنبيه أثناء فحص الوجوه: %s", e)

        # =====================================================================
        # 2. إذا كان الملف مقطع فيديو (Video Routing)
        # =====================================================================
        elif ext in VIDEO_EXTENSIONS:
            try:
                v_cat = video_classifier.classify_video(str(p), api_key=api_key)
                target_category = v_cat
                detected_details = f"تصنيف فيديو: {v_cat}"
            except Exception as e:
                logger.warning("تنبيه أثناء تصنيف الفيديو: %s", e)
                target_category = CATEGORY_UNCLASSIFIED
                detected_details = "فيديو غير محدد (خارج التصنيف)"

        # =====================================================================
        # 3. تنفيذ العملية (نسخ آمن أو نقل) مع الحفاظ على التوثيق
        # =====================================================================
        dest_path = file_manager.copy_to_category(
            p, target_category, is_copy=is_copy
        )
        dest_p = Path(dest_path)
        if not dest_p.exists():
            raise IOError(f"الملف الوجهة غير موجود بعد النقل/النسخ: {dest_path}")
        if dest_p.stat().st_size != orig_size:
            raise IOError(
                f"حجم الملف في الوجهة لا يطابق الأصل: {dest_p.stat().st_size} vs {orig_size}"
            )

        # إذا كنا في وضع النقل Move: نحذف الأصل فقط بعد التحقق التام
        if not is_copy:
            if is_uri_source and isinstance(file_item, storage_backend.MediaItem):
                storage_backend.delete_media_item(file_item)
            elif not is_uri_source and p.exists():
                p.unlink()

        # تسجيل الملف في كاش التتبع بعد التأكد التام
        record_processed_file(
            source_key,
            orig_size,
            orig_mtime,
            target_category,
            dest_path=str(dest_path),
            dest_size=orig_size,
        )

        return {
            "success": True,
            "source": source_key,
            "destination": str(dest_path),
            "category": target_category,
            "details": detected_details,
            "mode": "copy" if is_copy else "move",
        }
    finally:
        # حذف الملف المؤقت في حال استخدام streaming Content URI
        if temp_stream_file is not None and temp_stream_file.exists():
            try:
                temp_stream_file.unlink()
            except OSError:
                pass


def run_batch_scan(
    max_files: int = 30,
    api_key: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    source_storage: str | None = None,
    force_rescan: bool = False,
) -> dict[str, object]:
    """
    تشغيل فحص دفعي متحكم به لتجنب استهلاك البطارية أو تجميد الواجهة.
    """
    try:
        init_cache_db()
    except Exception as e:
        logger.warning("Cache DB init failed: %s (continuing scan)", e)

    media_files = find_unsorted_media(
        source_storage=source_storage, force_rescan=force_rescan
    )
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
    source_storage: str | None = None,
    force_rescan: bool = False,
) -> dict[str, object]:
    """
    تشغيل فرز متواصل مستمر حتى الانتهاء من جميع الملفات المتاحة على الجهاز
    مع حماية متقدمة من نفاد الذاكرة وتحمل ضغط آلاف الملفات والصور الكبيرة.
    """
    import gc

    try:
        init_cache_db()
    except Exception as e:
        logger.warning("Cache DB init failed: %s (continuing scan)", e)

    total_processed = 0
    all_results: list[dict[str, object]] = []

    # استكشاف الملفات دفعة واحدة في البداية بدلاً من إعادة المسح البطيء
    media_files = find_unsorted_media(
        source_storage=source_storage, force_rescan=force_rescan
    )
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
