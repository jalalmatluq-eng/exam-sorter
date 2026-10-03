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
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import cv2
except Exception:
    cv2 = None  # type: ignore

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

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


@contextmanager
def _get_cache_db_conn(timeout: float = 5.0):
    """إدارة اتصال قاعدة البيانات وإغلاق المقبض حتمياً لمنع تسريب المقابض أو قفل الملفات"""
    db_path = get_cache_db_path()
    conn = sqlite3.connect(str(db_path), timeout=timeout)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def init_cache_db() -> bool:
    """تهيئة جدول تتبع الملفات المفحوصة في SQLite بشكل غير حاجب للفرز مع دعم حالة العملية والوجهة"""
    try:
        db_path = get_cache_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with _get_cache_db_conn(timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scanned_files (
                    file_path TEXT PRIMARY KEY,
                    file_size INTEGER,
                    mtime REAL,
                    category TEXT,
                    dest_path TEXT,
                    dest_size INTEGER,
                    operation_status TEXT DEFAULT 'success',
                    target_storage TEXT DEFAULT '',
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
            try:
                cursor.execute("ALTER TABLE scanned_files ADD COLUMN operation_status TEXT DEFAULT 'success'")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE scanned_files ADD COLUMN target_storage TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value INTEGER DEFAULT 0
                )
            """)
            cursor.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('cumulative_classified', 0)"
            )
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
    إذا كانت الحالة success أو copied_not_deleted، والنسخة موجودة ومطابقة بالحجم، يعتبر معالجاً لتفادي تكرار النسخ!
    """
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return False
        with _get_cache_db_conn(timeout=5.0) as conn:
            cursor = conn.cursor()
            query = (
                "SELECT file_size, mtime, dest_path, dest_size, operation_status, target_storage FROM scanned_files WHERE file_path = ?"
            )
            cursor.execute(query, (file_path,))
            row = cursor.fetchone()
            if row and len(row) >= 2:
                saved_size = int(str(row[0]))
                saved_mtime = float(str(row[1]))
                status = str(row[4]) if len(row) > 4 and row[4] else "success"
                if status == "failed":
                    return False

                if saved_size == file_size and abs(saved_mtime - mtime) < 1.0:
                    if len(row) >= 3 and row[2]:
                        dest_str = str(row[2])
                        if dest_str.startswith("content://"):
                            final_sz = storage_backend.get_uri_file_size(dest_str)
                            return final_sz == file_size
                        else:
                            dest_p = Path(dest_str)
                            return dest_p.exists() and dest_p.is_file() and dest_p.stat().st_size == file_size
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
        with _get_cache_db_conn(timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM scanned_files WHERE operation_status != 'failed'")
            for row in cursor.fetchall():
                if row and row[0]:
                    scanned.add(str(row[0]))
    except Exception as e:
        logger.debug("خطأ أثناء قراءة كاش الملفات: %s", e)
    return scanned


def get_scanned_files_details() -> dict[str, dict[str, object]]:
    """تحميل تفاصيل الملفات المفحوصة مسبقاً بما فيها مسارات الوجهة وحالة العملية"""
    details: dict[str, dict[str, object]] = {}
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return details
        with _get_cache_db_conn(timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_path, file_size, dest_path, dest_size, operation_status, target_storage FROM scanned_files"
            )
            for row in cursor.fetchall():
                if row and row[0]:
                    details[str(row[0])] = {
                        "size": row[1],
                        "dest_path": row[2] if len(row) > 2 else "",
                        "dest_size": row[3] if len(row) > 3 else 0,
                        "operation_status": row[4] if len(row) > 4 else "success",
                        "target_storage": row[5] if len(row) > 5 else "",
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
    dest_size: int = 0,
    operation_status: str = "success",
    target_storage: str = "",
) -> bool:
    """تسجيل الملف في كاش التتبع مع حالة العملية ونوع التخزين لمنع تكرار النسخ بعد تعذر حذف المصدر"""
    try:
        init_cache_db()
        with _get_cache_db_conn(timeout=5.0) as conn:
            cursor = conn.cursor()
            sql = """
                INSERT OR REPLACE INTO scanned_files
                (file_path, file_size, mtime, category, dest_path, dest_size, operation_status, target_storage, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    operation_status,
                    target_storage,
                    time.time(),
                ),
            )
            conn.commit()
            cursor.execute(
                "UPDATE meta SET value = value + 1 WHERE key = 'cumulative_classified'"
            )
            conn.commit()
        return True
    except (sqlite3.Error, OSError) as e:
        logger.warning(
            "تنبيه: تعذر تسجيل الملف المفحوص في الكاش: %s (الفرز مستمر)", e
        )
        return False


def get_cumulative_classified() -> int:
    """إجمالي عمليات التصنيف الناجحة تراكمياً منذ أول تشغيل (لا يتصفر مع مسح الكاش)."""
    try:
        init_cache_db()
        with _get_cache_db_conn(timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM meta WHERE key = 'cumulative_classified'")
            row = cursor.fetchone()
            if row and row[0] is not None:
                return int(row[0])
    except (sqlite3.Error, OSError, ValueError, TypeError) as e:
        logger.debug("تعذر قراءة العداد التراكمي: %s", e)
    return 0


# اسم بديل موحد ومريح
record_scanned_file_result = record_processed_file


def unrecord_processed_file(
    file_path: str, dest_path: str | None = None
) -> None:
    """إزالة الملف من قاعدة بيانات التتبع لإتاحة فحصه مجدداً"""
    try:
        db_path = get_cache_db_path()
        if not db_path.exists():
            return
        with _get_cache_db_conn(timeout=5.0) as conn:
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
            with _get_cache_db_conn(timeout=5.0) as conn:
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

        targets = []
        try:
            BuildVersion = autoclass("android.os.Build$VERSION")
            sdk_int = int(BuildVersion.SDK_INT)
        except Exception:
            sdk_int = 0

        # في أندرويد 10+ (API 29+)، يمكن استعلام كل وحدة تخزين (Volume) بشكل محدد ومنفصل
        if sdk_int >= 29:
            try:
                MediaStore = autoclass("android.provider.MediaStore")
                vol_set = MediaStore.getExternalVolumeNames(mActivity)
                if vol_set is not None:
                    vol_iter = vol_set.iterator()
                    while vol_iter.hasNext():
                        v_name = str(vol_iter.next())
                        is_primary = (v_name == "external_primary")
                        if source_storage == "internal" and not is_primary:
                            continue
                        if source_storage == "sdcard" and is_primary:
                            continue
                        img_uri = MediaStoreImages.getContentUri(v_name)
                        vid_uri = MediaStoreVideo.getContentUri(v_name)
                        targets.append((img_uri, "image", v_name))
                        targets.append((vid_uri, "video", v_name))
            except Exception as e_vol:
                logger.warning("فشل استعلام أسماء مجلدات التخزين (Volume Names) عبر MediaStore: %s", e_vol)

        if not targets:
            if source_storage == "sdcard":
                logger.warning("لم يُعثر على وحدة تخزين خارجية لبطاقة SD في MediaStore؛ سيتم الاعتماد على قارئ SAF Tree المباشر")
            else:
                targets = [
                    (MediaStoreImages.EXTERNAL_CONTENT_URI, "image", ""),
                    (MediaStoreVideo.EXTERNAL_CONTENT_URI, "video", ""),
                ]

        cr = mActivity.getContentResolver()
        # تحديد الأعمدة المطلوبة صراحة لتسريع الاستعلام ومنع أخطاء الأعمدة غير المعروفة
        proj_list = ["_id", "_display_name", "mime_type", "_size", "date_modified", "_data"]
        if sdk_int >= 29:
            proj_list.extend(["relative_path", "volume_name"])
        projection_arr = list(proj_list)

        for target_info in targets:
            base_table_uri = target_info[0]
            target_vol_name = target_info[2] if len(target_info) > 2 else ""

            cursor = None
            try:
                try:
                    cursor = cr.query(base_table_uri, projection_arr, None, None, None)
                except Exception:
                    # في حال تعذر بعض الأعمدة، الاستعلام الاحتياطي
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
                vol_idx = cursor.getColumnIndex("volume_name")

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
                    vol_name = cursor.getString(vol_idx) if vol_idx >= 0 else target_vol_name

                    display_name = name_val or (Path(data_path).name if data_path else f"media_{item_id}")
                    ext = Path(display_name).suffix.lower()
                    if not ext and mime_val in storage_backend.MIME_TYPE_MAP:
                        ext = storage_backend.MIME_TYPE_MAP[mime_val]
                        display_name = f"{display_name}{ext}"

                    is_img = (ext in storage_backend.IMAGE_EXTENSIONS) or (mime_val and "image" in mime_val)
                    is_vid = (ext in storage_backend.VIDEO_EXTENSIONS) or (mime_val and "video" in mime_val)
                    if not is_img and not is_vid:
                        continue

                    # استبعاد المجلدات المحمية ومجلدات النظام والتطبيقات والملفات المنظمة
                    full_check_str = f"{rel_path or ''}/{data_path or ''}/{display_name}".lower()
                    excluded_markers = [
                        "android/data", "android/obb", ".thumbnails", ".trashed",
                        "lost.dir", "الملفات المنظمة", "mediasorter", "examsorter",
                    ]
                    if any(m in full_check_str for m in excluded_markers):
                        continue

                    # تصنيف التخزين بدقة عبر VOLUME_NAME والمسار (internal أو sdcard)
                    if vol_name:
                        is_sdcard = (vol_name != "external_primary")
                    elif data_path:
                        is_sdcard = not data_path.startswith("/storage/emulated/")
                    elif rel_path:
                        is_sdcard = not rel_path.startswith("/storage/emulated/")
                    else:
                        is_sdcard = False

                    storage_id = "sdcard" if is_sdcard else "internal"

                    if source_storage == "internal" and is_sdcard:
                        continue
                    if source_storage == "sdcard" and not is_sdcard:
                        continue

                    cache_key = data_path if (data_path and storage_backend.is_path_readable(data_path)) else item_uri_str
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

                    # التحقق الاستباقي الخفيف من قابلية قراءة الملف
                    is_directly_readable = bool(data_path and storage_backend.is_path_readable(data_path))
                    if not is_directly_readable:
                        # لا نتخطى الملف هنا — نتركه في القائمة لمعالجته فعلياً عبر ContentResolver
                        # الفشل الحقيقي سيُسجَّل لاحقاً في process_one_file بتفصيل كامل
                        logger.debug(
                            "الملف غير مقروء مباشرة، سيُعالج عبر Content URI: %s",
                            item_uri_str[:80],
                        )

                    item = storage_backend.MediaItem(
                        id=item_uri_str,
                        source_type="path" if is_directly_readable else "content_uri",
                        path=data_path if is_directly_readable else "",
                        uri=item_uri_str,
                        display_name=display_name,
                        mime_type=mime_val or ("image/jpeg" if is_img else "video/mp4"),
                        size_bytes=size_val,
                        date_modified=date_val,
                        storage_id=storage_id,
                        relative_path=rel_path or "",
                    )
                    found.append(item)
            finally:
                if cursor is not None:
                    cursor.close()
    except Exception as e:
        logger.warning("استثناء أثناء استعلام MediaStore: %s", e)

    return found


def _extract_media_dedup_keys(item: Any) -> dict[str, Any]:
    """
    استخراج مفاتيح إزالة التكرار بدقة وفقاً للمستويات الأربعة المعتمدة:
    1. URI: Content URI أو SAF Tree Document URI.
    2. Path: المسار المحلي على نظام الملفات.
    3. relative_key: (volume, relative_path.lower(), name.lower()).
    4. fallback_key: (name.lower(), size, mtime, volume).
    """
    uri = ""
    path = ""
    name = ""
    size = 0
    mtime = 0
    volume = "internal"
    rel_path = ""

    if isinstance(item, storage_backend.MediaItem):
        if item.uri:
            uri = item.uri
        elif item.id.startswith("content://"):
            uri = item.id
        if item.path:
            path = item.path
        elif not item.id.startswith("content://"):
            path = item.id

        name = item.name.lower()
        size = item.size_bytes
        mtime = int(item.date_modified)
        volume = getattr(item, "storage_id", "") or ""
        rel_path = getattr(item, "relative_path", "")

        if not volume:
            path_str = path or uri
            if "/emulated/" in path_str:
                volume = "internal"
            elif "documents" in uri or "sdcard" in path_str.lower():
                volume = "sdcard"
            else:
                volume = "internal"

    elif isinstance(item, Path):
        resolved = item.resolve()
        path = str(resolved)
        name = item.name.lower()
        try:
            st = item.stat()
            size = st.st_size
            mtime = int(st.st_mtime)
        except OSError:
            pass
        path_lower = path.lower()
        volume = "internal" if ("/emulated/" in path_lower or "c:" in path_lower) else "sdcard"

    else:
        item_str = str(item)
        if item_str.startswith("content://"):
            uri = item_str
            details = storage_backend.query_content_uri_details(uri)
            name = (details.get("display_name") or Path(uri).name).lower()
            size = int(details.get("size_bytes") or 0)
            mtime = int(details.get("date_modified") or 0)
            volume = "sdcard" if ("externalstorage" in uri or "document" in uri) else "internal"
            rel_path = details.get("relative_path", "")
            path = details.get("file_path", "")
        else:
            p = Path(item_str)
            path = str(p.resolve())
            name = p.name.lower()
            try:
                st = p.stat()
                size = st.st_size
                mtime = int(st.st_mtime)
            except OSError:
                pass
            volume = "internal" if "/emulated/" in item_str.lower() else "sdcard"

    vol_norm = "sdcard" if volume in ("sdcard", "external", "secondary") else "internal"
    norm_rel = rel_path.replace("\\", "/").strip("/").lower()
    if norm_rel and name:
        if norm_rel.endswith("/" + name):
            norm_rel = norm_rel[: -len(name) - 1].strip("/")
        elif norm_rel == name:
            norm_rel = ""
    if not norm_rel and path:
        # استخراج المجلد النسبي القياسي
        parts = Path(path).parts
        for std_dir in ("dcim", "pictures", "movies", "download", "whatsapp", "telegram", "documents"):
            lower_parts = [p.lower() for p in parts]
            if std_dir in lower_parts:
                idx = lower_parts.index(std_dir)
                norm_rel = "/".join(lower_parts[idx:-1])
                break

    return {
        "uri": uri,
        "path": path,
        "name": name,
        "size": size,
        "mtime": mtime,
        "volume": vol_norm,
        "relative_path": norm_rel,
    }


def find_unsorted_media(
    roots: list[Path] | None = None,
    max_depth: int = 10,
    source_storage: str | None = None,
    force_rescan: bool = False,
) -> list[Any]:
    """
    البحث الشجري الموحد والشامل عن جميع الصور والفيديوهات غير المصنفة:
    - دمج نتائج فحص نظام الملفات (os.walk) مع نتائج MediaStore و SAF دون تكرار.
    - منع تكرار الملفات عند دمج MediaStore مع SAF وفق هرمية إزالة التكرار الصارمة (4 مستويات):
        1. URI متطابق.
        2. المسار المتطابق.
        3. volume + relative_path + name.
        4. name + size + mtime كحل احتياطي (لا يتم الاعتماد على name + size فقط).
    - احترام اختيار الذاكرة (internal / sdcard / both) بشكل صارم وفعلي.
    - عدم استبعاد WhatsApp / Telegram في Android/media مع استبعاد Android/data و Android/obb.
    - استبعاد مجلد الملفات المنظمة والملفات المفحوصة مسبقاً بعد التحقق من وجود نسختها في الوجهة.
    """
    if source_storage is None:
        prefs = file_manager.get_sorter_preferences()
        source_storage = str(prefs.get("source_storage", "both"))

    scanned_details = get_scanned_files_details()
    combined_items: list[Any] = []
    seen_uris: set[str] = set()
    seen_paths: set[str] = set()
    seen_rel_keys: set[tuple[str, str, str]] = set()  # (volume, relative_path, name)
    seen_fallback_sigs: set[tuple[str, int, int, str]] = set()  # (name, size, mtime, volume)

    def try_add_item(candidate: Any) -> bool:
        keys = _extract_media_dedup_keys(candidate)
        uri = keys["uri"]
        path = keys["path"]
        vol = keys["volume"]
        rel = keys["relative_path"]
        name = keys["name"]
        size = keys["size"]
        mtime = keys["mtime"]

        # Level 1: Matching URI
        if uri and uri.lower() in seen_uris:
            return False

        # Level 2: Matching Path
        if path and path.lower() in seen_paths:
            return False

        # Level 3: (volume + relative_path + name)
        if rel and (vol, rel, name) in seen_rel_keys:
            logger.info("تخطي ملف مكرر بالمجلد النسبي (المستوى 3): %s/%s (%s)", rel, name, vol)
            return False

        # Level 4: (name + size + mtime) as fallback - never name + size only!
        if size > 0 and mtime > 0 and (name, size, mtime, vol) in seen_fallback_sigs:
            logger.info("تخطي ملف مكرر بالبصمة الاحتياطية (المستوى 4): %s (%s, %d bytes)", name, vol, size)
            return False

        # تسجيل الملف غير المكرر
        if uri:
            seen_uris.add(uri.lower())
        if path:
            seen_paths.add(path.lower())
        if rel:
            seen_rel_keys.add((vol, rel, name))
        if size > 0 and mtime > 0:
            seen_fallback_sigs.add((name, size, mtime, vol))

        combined_items.append(candidate)
        return True

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
                try_add_item(item)
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
        active_target_loc = storage_backend.get_active_target_location()
        active_target_base = active_target_loc.path.resolve() if (active_target_loc and active_target_loc.path) else None
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

                        try_add_item(full_path)
        except (OSError, RuntimeError) as e:
            logger.warning("خطأ أثناء فحص المجلد %s: %s", root_dir, e)

    # 3. فحص بطاقة الذاكرة الخارجية عودياً عبر SAF Tree URI
    if source_storage in ("sdcard", "both"):
        saf_tree_uri = storage_backend.get_saf_persisted_uri()
        if saf_tree_uri and storage_backend.is_saf_uri_valid(saf_tree_uri):
            try:
                saf_items = storage_backend.scan_saf_tree_recursively(
                    saf_tree_uri, max_depth=max_depth, include_organized=False
                )
                logger.info("تم العثور على %d ملف وسائط عبر قارئ SAF Tree الشجري", len(saf_items))
                for s_item in saf_items:
                    k = s_item.uri
                    if not force_rescan and k in scanned_details:
                        info = scanned_details[k]
                        dest_path_str = str(info.get("dest_path", ""))
                        if dest_path_str:
                            dest_sz = storage_backend.get_uri_file_size(dest_path_str) if dest_path_str.startswith("content://") else (Path(dest_path_str).stat().st_size if Path(dest_path_str).exists() else 0)
                            if dest_sz == s_item.size_bytes:
                                continue
                    try_add_item(s_item)
            except Exception as e_saf:
                logger.error("خطأ أثناء قراءة شجرة SAF للبطاقة الخارجية: %s", e_saf)
        elif source_storage == "sdcard":
            logger.warning("تنبيه: تم اختيار فحص بطاقة SD ولكن لا يوجد إذن SAF صالح ومحفوظ للبطاقة!")

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
        if np is None:
            return False
        small = face_classifier.safe_read_image(image_path, max_size=500)
        if small is None:
            return False
        assert np is not None
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
        logger.exception("استثناء غير متوقع أثناء معالجة الملف %s", item_id)
        active_target = None
        try:
            active_target = storage_backend.get_active_target_location()
        except Exception:
            pass
        fail_reason = storage_backend.classify_failure_reason(e, target_location=active_target)
        return {
            "success": False,
            "source": item_id,
            "category": CATEGORY_UNCLASSIFIED,
            "error": str(e),
            "failure_reason": fail_reason,
        }
    finally:
        file_manager.mark_file_processing_end()


def classify_media_access_status(file_item: Any) -> tuple[str, str, str]:
    """
    فحص وتصنيف عملي استباقي لحالة كل عنصر وسائط قبل محاولة معالجته وفرزه:
    العائد: (status: 'readable' | 'permission_denied' | 'file_not_found' | 'corrupt' | 'needs_saf',
             error_message: str,
             failure_reason_arabic: str)
    """
    import android_permissions

    source_key = ""
    uri_check = ""
    path_check = ""

    if isinstance(file_item, storage_backend.MediaItem):
        source_key = file_item.uri or file_item.path or file_item.id
        uri_check = file_item.uri or ""
        path_check = file_item.path or ""
    elif isinstance(file_item, Path):
        source_key = str(file_item)
        path_check = str(file_item)
    else:
        source_key = str(file_item)
        if source_key.startswith("content://"):
            uri_check = source_key
        else:
            path_check = source_key

    # 1. فحص إذن SAF لبطاقة الذاكرة الخارجية
    if uri_check and ("tree" in uri_check or "document" in uri_check):
        if not storage_backend.is_saf_uri_valid(uri_check):
            return "needs_saf", "انتهت صلاحية إذن الوصول لمجلد بطاقة الذاكرة الخارجية (SAF)", "يحتاج إعادة اختيار SAF"

    # 2. فحص الوجود المادي للمسار الفيزيائي
    if path_check:
        p = Path(path_check)
        if not p.exists():
            return "file_not_found", f"الملف غير موجود في المسار: {p.name}", "الملف غير موجود"
        try:
            st = p.stat()
            if st.st_size == 0:
                return "corrupt", "الملف فارغ بحجم 0 بايت (ملف تالف)", "ملف تالف"
        except (OSError, PermissionError) as e:
            return "permission_denied", f"تم رفض صلاحية الوصول للمسار: {e}", "مرفوض بسبب إذن Android"

    # 3. فحص صلاحيات الوسائط لنظام أندرويد
    if not android_permissions.is_images_permission_granted() and not android_permissions.is_videos_permission_granted():
        return "permission_denied", "صلاحيات الوصول للصور والفيديوهات غير ممنوحة من قبل النظام", "مرفوض بسبب إذن Android"

    # 4. الفحص العملي لقابلية القراءة عبر فتح الدفق الفعلي (is_source_path_readable)
    target_to_test = uri_check or path_check or source_key
    if not android_permissions.is_source_path_readable(target_to_test):
        if uri_check:
            return "permission_denied", "تعذر فتح دفق القراءة من مزود الوسائط (تم رفض الإذن)", "مرفوض بسبب إذن Android"
        return "permission_denied", "تعذر قراءة بايتات الملف من وحدة التخزين (حظر أمني)", "مرفوض بسبب إذن Android"

    return "readable", "", "جاهز"


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
    elif isinstance(file_item, Path):
        source_key = str(file_item.resolve())
    else:
        source_key = str(file_item)

    # 1. فحص وتصنيف صلاحية القراءة والتوافر قبل البدء
    access_status, access_err, access_reason = classify_media_access_status(file_item)
    if access_status != "readable":
        return {
            "success": False,
            "source": source_key,
            "error": access_err,
            "failure_reason": access_reason,
            "access_status": access_status,
            "stage": "source_read",
        }

    if isinstance(file_item, storage_backend.MediaItem):

        if file_item.path and storage_backend.is_path_readable(file_item.path):
            p = Path(file_item.path).resolve()
        else:
            # نسخ Content URI إلى temp خاص بالتطبيق بطريقة streaming
            is_uri_source = True
            temp_dir = file_manager.get_temp_dir()
            safe_name = file_item.name or f"media_{int(time.time() * 1000)}.jpg"
            temp_stream_file = temp_dir / f"stream_{int(time.time() * 1000)}_{safe_name}"
            read_res = storage_backend.copy_uri_to_path_detailed(file_item.uri, temp_stream_file)
            if not read_res.success or not temp_stream_file.exists():
                fail_reason = storage_backend.classify_failure_reason(
                    read_res.error_message or "فشل قراءة الملف من مزود وسائط الجهاز",
                    stage="source_read",
                    source_uri=file_item.uri,
                )
                return {
                    "success": False,
                    "source": source_key,
                    "error": read_res.error_message or "تعذر قراءة دفق Content URI أو اكتماله",
                    "failure_reason": fail_reason,
                }
            p = temp_stream_file
    elif isinstance(file_item, Path):
        p = file_item.resolve()
        source_key = str(p)
        import android_permissions
        if not android_permissions.is_source_path_readable(source_key):
            return {
                "success": False,
                "source": source_key,
                "error": "تعذر قراءة المسار المحلي (الملف تالف أو محظور)",
                "failure_reason": "فشل القراءة" if not p.exists() else "مرفوض بسبب إذن Android",
                "stage": "source_read",
            }
    else:
        source_str = str(file_item)
        if source_str.startswith("content://"):
            is_uri_source = True
            source_key = source_str
            import android_permissions
            if not android_permissions.is_source_path_readable(source_key):
                return {
                    "success": False,
                    "source": source_key,
                    "error": "تعذر فتح دفق Content URI",
                    "failure_reason": "فشل القراءة",
                    "stage": "source_read",
                }
            uri_info = storage_backend.query_content_uri_details(source_str)
            safe_name = uri_info.get("display_name") or f"media_{int(time.time() * 1000)}{uri_info.get('extension', '.mp4' if 'video' in source_str.lower() else '.jpg')}"
            temp_dir = file_manager.get_temp_dir()
            temp_stream_file = temp_dir / f"stream_{int(time.time() * 1000)}_{safe_name}"
            copied = storage_backend.copy_uri_to_path(source_str, temp_stream_file)
            if not copied or not temp_stream_file.exists():
                return {
                    "success": False,
                    "source": source_key,
                    "error": "تعذر قراءة دفق Content URI أو اكتماله",
                    "failure_reason": "فشل القراءة",
                }
            p = temp_stream_file
        else:
            p = Path(source_str).resolve()
            source_key = str(p)

    try:
        if not p.exists() or not p.is_file():
            return {
                "success": False,
                "source": source_key,
                "error": "الملف غير موجود",
                "failure_reason": "فشل القراءة",
            }

        ext = p.suffix.lower()
        file_mime = getattr(file_item, "mime_type", "") if isinstance(file_item, storage_backend.MediaItem) else ""
        if not ext and file_mime:
            resolved_mime = storage_backend.resolve_media_mime_type(p.name, file_mime)
            ext = storage_backend.MIME_TYPE_MAP.get(resolved_mime, ".mp4" if "video" in resolved_mime else ".jpg")

        is_video = (ext in VIDEO_EXTENSIONS) or (file_mime and "video" in file_mime.lower())
        is_image = (ext in IMAGE_EXTENSIONS) or (file_mime and "image" in file_mime.lower())

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
        # 1. إذا كان الملف صورة (Image Routing عبر offline_classifier الموضعي)
        # =====================================================================
        if is_image and not is_video:
            import offline_classifier
            # استدعاء هرمية التصنيف الأوفلاين الصارمة
            off_res = offline_classifier.classify_media_offline(
                file_path=str(p),
                filename=p.name,
                mime_type=file_mime,
                size_bytes=orig_size,
                mtime=int(orig_mtime),
            )
            target_category = str(off_res.get("category", CATEGORY_UNCLASSIFIED))
            detected_details = str(off_res.get("details", ""))

            # في حال توفر مفتاح API واستدعاء السحابة لترقية الورقة العامة أو عند الحاجة لمراجعة
            if api_key and (off_res.get("needs_review") or target_category == "اختبارات/اختبارات عامة"):
                if not offline_classifier.is_circuit_breaker_open():
                    try:
                        subject_name = classifier.classify_exam_image(
                            str(p), api_key=api_key, fallback_to_ocr=False
                        )
                        if subject_name and subject_name.strip():
                            clean_sub = subject_name.strip()
                            target_category = f"{CATEGORY_EXAMS_ROOT}/{clean_sub}"
                            detected_details = f"ورقة اختبار مادة: {clean_sub} (عبر الذكاء الاصطناعي)"
                            offline_classifier.record_cloud_api_success()
                    except Exception as e_cloud:
                        offline_classifier.record_cloud_api_failure()
                        logger.debug("تجاوز استدعاء السحابة بسبب استثناء: %s", e_cloud)

        # =====================================================================
        # 2. إذا كان الملف مقطع فيديو (Video Routing)
        # =====================================================================
        elif is_video:
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
        target_location = storage_backend.get_active_target_location()
        if not target_location.is_valid:
            fail_reason = storage_backend.classify_failure_reason(
                target_location.error_message,
                target_location=target_location,
                stage="target_write",
            )
            return {
                "success": False,
                "source": source_key,
                "error": target_location.error_message,
                "failure_reason": fail_reason,
            }

        item_to_process = (
            file_item
            if isinstance(file_item, storage_backend.MediaItem)
            else (file_item if is_uri_source else p)
        )
        try:
            dest_res = file_manager.copy_to_category(
                item_to_process,
                target_category,
                target_location=target_location,
                is_copy=is_copy,
            )
        except Exception as e_trans:
            fail_reason = storage_backend.classify_failure_reason(
                e_trans,
                target_location=target_location,
                stage="target_write",
            )
            return {
                "success": False,
                "source": source_key,
                "error": str(e_trans),
                "failure_reason": fail_reason,
                "stage": "target_write",
            }

        dest_str = str(dest_res)
        dest_size = orig_size
        if isinstance(dest_res, Path):
            if not dest_res.exists():
                raise OSError(f"الملف الوجهة غير موجود بعد النقل/النسخ: {dest_res}")
            if orig_size > 0 and dest_res.stat().st_size != orig_size:
                raise OSError(
                    f"حجم الملف في الوجهة لا يطابق الأصل: {dest_res.stat().st_size} vs {orig_size}"
                )
            dest_size = dest_res.stat().st_size
        else:
            if not dest_str.startswith("content://") and not dest_str.startswith("mock_doc://"):
                if not Path(dest_str).exists():
                    raise OSError(f"الملف الوجهة غير موجود بعد النقل/النسخ: {dest_str}")

        # إذا كنا في وضع النقل Move: نحذف الأصل فقط بعد التحقق التام
        actual_mode = "copy" if is_copy else "move"
        op_status = "success"
        if not is_copy:
            deleted = storage_backend.delete_media_item(item_to_process)
            if not deleted:
                op_status = "copied_not_deleted"
                logger.warning(
                    "تعذر حذف الأصل بعد النقل (%s)، تم الاحتفاظ به كنسخة آمنة",
                    source_key,
                )
                file_manager._update_last_transfer_record_to_copy()
                actual_mode = "copy"

        # تسجيل الملف في كاش التتبع بعد التأكد التام
        chosen_target = getattr(target_location, "storage_type", "internal")
        record_processed_file(
            source_key,
            orig_size,
            orig_mtime,
            target_category,
            dest_path=dest_str,
            dest_size=dest_size,
            operation_status=op_status,
            target_storage=chosen_target,
        )

        return {
            "success": True,
            "source": source_key,
            "destination": dest_str,
            "category": target_category,
            "details": detected_details,
            "mode": actual_mode,
            "is_copy": is_copy,
            "stage": "done",
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
    failed_count = 0
    failures_by_reason: dict[str, int] = {}
    results: list[dict[str, object]] = []

    for idx, f in enumerate(batch):
        if progress_callback:
            progress_callback(idx + 1, len(batch), f.name)

        res = process_one_file(f, api_key=api_key)
        results.append(res)
        if res.get("success"):
            processed_count += 1
        else:
            failed_count += 1
            reason = str(res.get("failure_reason") or "فشل غير محدد")
            failures_by_reason[reason] = failures_by_reason.get(reason, 0) + 1

        time.sleep(0.03)

    return {
        "total_unprocessed_found": total_found,
        "batch_size": len(batch),
        "processed_count": processed_count,
        "success_count": processed_count,
        "failed_count": failed_count,
        "failures_by_reason": failures_by_reason,
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

    import android_permissions

    target_loc = storage_backend.get_active_target_location()
    tgt_name = target_loc.storage_type if target_loc else "internal"
    can_proceed, issue_code, issue_msg, action_req = android_permissions.preflight_scan_access(
        source_storage or "both", tgt_name
    )
    if not can_proceed:
        logger.warning("تم إيقاف الفحص المستمر قبل البدء بسبب عدم اكتمال الصلاحيات: %s (%s)", issue_code, issue_msg)
        return {
            "total_found": 0,
            "total_processed": 0,
            "success_count": 0,
            "failed_count": 0,
            "preflight_failed": True,
            "failure_reason": "رفض الصلاحية" if "permission" in issue_code or "media" in issue_code else "يحتاج إعادة اختيار SAF",
            "error": issue_msg,
            "action_required": action_req,
        }

    try:
        init_cache_db()
    except Exception as e:
        logger.warning("Cache DB init failed: %s (continuing scan)", e)

    total_processed = 0
    total_failed = 0
    readable_count = 0
    classified_count = 0
    copied_count = 0
    moved_count = 0
    read_failed_count = 0
    classification_failed_count = 0
    write_failed_count = 0
    permission_rejected_count = 0
    saf_reselect_count = 0

    failures_by_reason: dict[str, int] = {}
    all_results: list[dict[str, object]] = []

    # استكشاف الملفات دفعة واحدة في البداية بدلاً من إعادة المسح البطيء
    media_files = find_unsorted_media(
        source_storage=source_storage, force_rescan=force_rescan
    )
    total_files = len(media_files)
    if total_files == 0:
        return {
            "total_processed": 0,
            "success_count": 0,
            "failed_count": 0,
            "total_found": 0,
            "readable_count": 0,
            "classified_count": 0,
            "copied_count": 0,
            "moved_count": 0,
            "read_failed_count": 0,
            "classification_failed_count": 0,
            "write_failed_count": 0,
            "permission_rejected_count": 0,
            "saf_reselect_count": 0,
            "failures_by_reason": {},
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
            active_target = None
            try:
                active_target = storage_backend.get_active_target_location()
            except Exception:
                pass
            fail_reason = storage_backend.classify_failure_reason(e, target_location=active_target)
            res = {
                "success": False,
                "error": str(e),
                "original_path": str(f),
                "failure_reason": fail_reason,
                "stage": "unknown",
            }

        is_succ = bool(res.get("success"))
        stg = str(res.get("stage") or "")
        reason = str(res.get("failure_reason") or "فشل غير محدد")

        if is_succ:
            total_processed += 1
            readable_count += 1
            cat = str(res.get("category") or "")
            if cat and cat != CATEGORY_UNCLASSIFIED:
                classified_count += 1
            if res.get("is_copy") is False:
                moved_count += 1
            else:
                copied_count += 1
        else:
            total_failed += 1
            if stg == "source_read":
                read_failed_count += 1
                if any(k in reason for k in ("صلاحية", "permission", "إذن")):
                    permission_rejected_count += 1
            elif stg == "target_write":
                readable_count += 1
                classified_count += 1
                write_failed_count += 1
                if any(k in reason.lower() for k in ("saf", "إذن", "بطاقة")):
                    saf_reselect_count += 1
            elif stg == "classification":
                readable_count += 1
                classification_failed_count += 1
            else:
                if any(k in reason for k in ("صلاحية", "permission")):
                    permission_rejected_count += 1
                elif any(k in reason.lower() for k in ("saf", "إذن")):
                    saf_reselect_count += 1

            failures_by_reason[reason] = failures_by_reason.get(reason, 0) + 1

        # الاحتفاظ بآخر 50 نتيجة فقط لتجنب استهلاك ذاكرة RAM عند معالجة آلاف الملفات
        if len(all_results) < 50:
            all_results.append(res)

        if progress_callback:
            progress_callback({
                "current_file": getattr(f, "name", None) or getattr(f, "display_name", None) or str(f)[:60],
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
        "discovered": total_files,
        "readable": readable_count,
        "classified": classified_count,
        "copied": copied_count,
        "moved": moved_count,
        "read_failed": read_failed_count,
        "permission_denied": permission_rejected_count,
        "target_write_failed": write_failed_count,
        "total_processed": total_processed,
        "success_count": total_processed,
        "failed_count": total_failed,
        "total_found": total_files,
        "readable_count": readable_count,
        "classified_count": classified_count,
        "copied_count": copied_count,
        "moved_count": moved_count,
        "read_failed_count": read_failed_count,
        "classification_failed_count": classification_failed_count,
        "write_failed_count": write_failed_count,
        "permission_rejected_count": permission_rejected_count,
        "saf_reselect_count": saf_reselect_count,
        "failures_by_reason": failures_by_reason,
        "batches_completed": (total_processed // batch_size) + 1,
        "results": all_results,
    }
