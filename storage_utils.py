import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import file_manager
import storage_backend

logger = logging.getLogger(__name__)

MEDIA_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif",
    ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm", ".m4v", ".flv"
}


@dataclass
class DeduplicationResult:
    """نتيجة تفصيلية لعملية كشف وإزالة الملفات المكررة تميز بين النجاح والفشل والانتظار"""
    detected_count: int = 0
    deleted_count: int = 0
    failed_count: int = 0
    pending_approval_count: int = 0
    freed_bytes: int = 0

    def __iter__(self):
        # التوافق الكامل مع الكود القديم الذي يعتمد على استخراج (del_count, freed)
        return iter((self.deleted_count, self.freed_bytes))


class CategoryInfo(TypedDict):
    count: int
    size_mb: float


class StorageStats(TypedDict):
    total_files: int
    total_size_mb: float
    categories: dict[str, CategoryInfo]
    last_scan_time: float | None
    cumulative_classified: int


def get_storage_stats(
    base_path: Path | None = None,
    target_location: Any | None = None,
) -> StorageStats:
    """
    حساب إحصائيات التخزين بدقة:
    - يدعم المسار الفيزيائي للذاكرة الداخلية.
    - يدعم SAF Tree URI لبطاقة الذاكرة الخارجية دون استدعاء Path.iterdir أو get_media_sorter_base_path.
    """
    if target_location is None:
        if base_path is not None:
            target_location = storage_backend.TargetLocation(
                storage_type="custom",
                is_saf=False,
                path=Path(base_path),
                display_name=str(base_path),
                is_valid=True,
            )
        else:
            target_location = storage_backend.get_active_target_location()

    stats: StorageStats = {
        "total_files": 0,
        "total_size_mb": 0.0,
        "categories": {},
        "last_scan_time": None,
        "cumulative_classified": 0,
    }
    try:
        import media_scanner

        stats["cumulative_classified"] = media_scanner.get_cumulative_classified()
    except Exception:
        pass

    # 1. إذا كانت الوجهة SAF Tree URI لبطاقة الذاكرة الخارجية
    if target_location and target_location.is_saf:
        tree_uri = target_location.tree_uri or target_location.saf_uri
        if tree_uri and storage_backend.is_saf_uri_valid(tree_uri):
            try:
                saf_items = storage_backend.scan_saf_tree_recursively(tree_uri, include_organized=True)
                total_bytes = 0
                for item in saf_items:
                    rel = getattr(item, "relative_path", "")
                    if rel:
                        parts = rel.replace("\\", "/").strip("/").split("/")
                        if parts and parts[0] == storage_backend.ORGANIZED_FOLDER_NAME:
                            parts = parts[1:]
                        cat_name = parts[0] if parts else "خارج التصنيف"
                    else:
                        raw_p = item.path or item.id
                        parts = raw_p.replace("\\", "/").strip("/").split("/")
                        cat_name = parts[-2] if len(parts) >= 2 else "خارج التصنيف"

                    if cat_name not in stats["categories"]:
                        stats["categories"][cat_name] = {"count": 0, "size_mb": 0.0}
                    stats["categories"][cat_name]["count"] += 1
                    sz = item.size_bytes
                    total_bytes += sz
                    cur_mb = stats["categories"][cat_name]["size_mb"]
                    stats["categories"][cat_name]["size_mb"] = round(cur_mb + (sz / 1048576), 2)

                stats["total_files"] = sum(c["count"] for c in stats["categories"].values())
                stats["total_size_mb"] = round(total_bytes / 1048576, 2)
            except Exception as e:
                logger.debug("خطأ في احتساب إحصائيات التخزين: %s", e)

        # استعلام وقت آخر فحص من كاش التطبيق الخاص
        try:
            db_path = file_manager.get_app_private_storage_dir() / "scanned_media_cache.db"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                row = conn.execute("SELECT MAX(processed_at) FROM scanned_files").fetchone()
                conn.close()
                if row and row[0]:
                    stats["last_scan_time"] = float(row[0])
        except (sqlite3.Error, OSError, ValueError):
            pass

        return stats

    # 2. إذا كانت الوجهة مسار محلي فيزيائي
    base = (
        target_location.path
        if (target_location and target_location.path)
        else (base_path or file_manager.get_internal_media_sorter_base_path())
    )
    if not base.exists():
        return stats

    total_bytes = 0
    try:
        for cat_dir in base.iterdir():
            if not cat_dir.is_dir():
                continue
            cat_count, cat_bytes = 0, 0
            for f in cat_dir.rglob("*"):
                if f.is_file() and f.suffix.lower() in MEDIA_EXTS:
                    try:
                        sz = f.stat().st_size
                        cat_count += 1
                        cat_bytes += sz
                        total_bytes += sz
                    except OSError:
                        continue
            if cat_count > 0:
                stats["categories"][cat_dir.name] = {
                    "count": cat_count,
                    "size_mb": round(cat_bytes / 1048576, 2),
                }
    except (OSError, PermissionError):
        pass

    stats["total_files"] = sum(
        c["count"] for c in stats["categories"].values()
    )
    stats["total_size_mb"] = round(total_bytes / 1048576, 2)

    for test_dir in [file_manager.get_app_private_storage_dir(), base]:
        try:
            db_path = test_dir / "scanned_media_cache.db"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                row = conn.execute(
                    "SELECT MAX(processed_at) FROM scanned_files"
                ).fetchone()
                conn.close()
                if row and row[0]:
                    stats["last_scan_time"] = float(row[0])
                    break
        except (sqlite3.Error, OSError, ValueError):
            pass

    return stats


def find_duplicate_files(
    base_path: Path | None = None,
    target_location: Any | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    stop_check: Callable[[], bool] | None = None,
) -> list[list[str]]:
    """
    كشف الملفات المكررة في مجلدات التخزين مع دعم شريط التقدم والإلغاء الآمن:
    - يدعم المسار الفيزيائي للذاكرة الداخلية.
    - يدعم بطاقة الذاكرة الخارجية عبر SAF Tree URI دون تحويله لمسار Linux.
    - تصفية سريعة بالأحجام لتجنب حساب SHA-256 للملفات ذات الأحجام الفريدة.
    - يدعم stop_check لإيقاف الفحص عند مغادرة الشاشة أو فصل بطاقة SD دون انهيار.
    """
    if stop_check and stop_check():
        return []

    if target_location is None:
        if base_path is not None:
            target_location = storage_backend.TargetLocation(
                storage_type="custom",
                is_saf=False,
                path=Path(base_path),
                display_name=str(base_path),
                is_valid=True,
            )
        else:
            target_location = storage_backend.get_active_target_location()

    # 1. إذا كانت الوجهة SAF Tree URI لبطاقة الذاكرة الخارجية
    if target_location and target_location.is_saf:
        tree_uri = target_location.tree_uri or target_location.saf_uri
        if not tree_uri or not storage_backend.is_saf_uri_valid(tree_uri):
            logger.warning("فحص المكررات: بطاقة SD غير متصلة أو إذن SAF غير متاح")
            return []

        # المرحلة 1: تجميع سريع حسب الحجم دون فحص دفق المحتوى لاستبعاد الملفات الفريدة
        size_groups: dict[int, list[str]] = {}
        try:
            saf_items = storage_backend.scan_saf_tree_recursively(tree_uri, include_organized=True)
            for item in saf_items:
                if stop_check and stop_check():
                    return []
                uri = item.uri or item.id
                sz = item.size_bytes
                if sz <= 0:
                    continue
                size_groups.setdefault(sz, []).append(uri)

            # المرحلة 2: فحص الهاش (SHA-256) للملفات التي لها نفس الحجم فقط
            candidates = {sz: uris for sz, uris in size_groups.items() if len(uris) > 1}
            total_candidates = sum(len(uris) for uris in candidates.values())
            processed_count = 0

            hash_map: dict[str, list[str]] = {}
            for sz, uris in candidates.items():
                for uri in uris:
                    if stop_check and stop_check():
                        logger.info("تم إيقاف فحص SHA-256 للمكررات بناءً على طلب الإلغاء")
                        return []
                    if not storage_backend.is_saf_uri_valid(tree_uri):
                        logger.warning("تم فصل بطاقة الذاكرة الخارجية أثناء فحص الهاش")
                        return []

                    processed_count += 1
                    if progress_callback:
                        try:
                            progress_callback(processed_count, total_candidates, uri)
                        except Exception:
                            pass

                    content_hash = storage_backend.compute_content_uri_hash(uri)
                    if not content_hash:
                        logger.warning(
                            "تعذر قراءة دفق المحتوى لحساب الهاش للملف: %s. تم استبعاده من كشف المكررات لضمان سلامة البيانات.",
                            uri,
                        )
                        continue
                    key = f"{sz}_{content_hash}"
                    hash_map.setdefault(key, []).append(uri)
        except Exception as e:
            logger.error("خطأ أثناء فحص مكررات SAF: %s", e)
            return []

        return [v for v in hash_map.values() if len(v) > 1]

    # 2. إذا كانت الوجهة مسار محلي فيزيائي
    base = (
        target_location.path
        if (target_location and target_location.path)
        else (base_path or file_manager.get_internal_media_sorter_base_path())
    )
    if not base.exists():
        return []

    # المرحلة 1: تجميع محلي سريع حسب الحجم
    size_groups_local: dict[int, list[str]] = {}
    hash_map_local: dict[str, list[str]] = {}
    try:
        for f in base.rglob("*"):
            if stop_check and stop_check():
                return []
            if not f.is_file() or f.suffix.lower() not in MEDIA_EXTS:
                continue
            try:
                sz = f.stat().st_size
                if sz <= 0:
                    continue
                size_groups_local.setdefault(sz, []).append(str(f))
            except OSError:
                continue

        # المرحلة 2: حساب الهاش الفعلي على دفعات للعينات المشتركة في الحجم فقط
        candidates_local = {sz: paths for sz, paths in size_groups_local.items() if len(paths) > 1}
        total_candidates_local = sum(len(paths) for paths in candidates_local.values())
        processed_local = 0

        for sz, paths in candidates_local.items():
            for p_str in paths:
                if stop_check and stop_check():
                    logger.info("تم إيقاف فحص SHA-256 للمكررات محلياً")
                    return []

                processed_local += 1
                if progress_callback:
                    try:
                        progress_callback(processed_local, total_candidates_local, p_str)
                    except Exception:
                        pass

                content_hash = storage_backend.compute_content_uri_hash(p_str)
                if not content_hash:
                    continue
                key = f"{sz}_{content_hash}"
                hash_map_local.setdefault(key, []).append(p_str)
    except (OSError, PermissionError) as e_loc:
        logger.warning("تنبيه فحص المكررات محلياً: %s", e_loc)

    return [v for v in hash_map_local.values() if len(v) > 1]


def remove_duplicate_files(
    duplicates: list[list[str]],
    target_location: Any | None = None,
) -> DeduplicationResult:
    """
    حذف النسخ المكررة بأمان مع الحفاظ التام على النسخة الأصلية (الملف الأول) من كل مجموعة:
    - يميز بين المحذوف بنجاح، والفاشل، وبانتظار موافقة أندرويد (RecoverableSecurityException).
    - تعيد كائن DeduplicationResult متوافق مع الاستخراج الثنائي (del_count, freed).
    """
    if target_location is None:
        target_location = storage_backend.get_active_target_location()

    res = DeduplicationResult()
    res.detected_count = sum(len(g) - 1 for g in duplicates if len(g) > 1)

    for group in duplicates:
        if len(group) <= 1:
            continue

        # الإبقاء على الملف الأول، وحذف النسخ الإضافية المكررة
        for file_ref in group[1:]:
            is_saf_or_uri = (
                file_ref.startswith(("content://", "mock_doc://"))
                or (target_location and target_location.is_saf)
            )

            if is_saf_or_uri:
                # التحقق الصارم من الصلاحية قبل الحذف في SAF
                if target_location and target_location.is_saf:
                    tree_uri = target_location.tree_uri or target_location.saf_uri
                    if not storage_backend.is_saf_uri_valid(tree_uri):
                        res.failed_count += 1
                        continue

                sz = storage_backend.get_uri_file_size(file_ref)
                ok = storage_backend.delete_media_item(file_ref)
                if ok:
                    res.deleted_count += 1
                    res.freed_bytes += sz
                else:
                    pending = storage_backend.get_pending_recoverable_deletion()
                    if pending and pending.get("item_uri") == file_ref:
                        res.pending_approval_count += 1
                    else:
                        res.failed_count += 1
            else:
                p = Path(file_ref)
                try:
                    if p.is_file():
                        sz = p.stat().st_size
                        ok = storage_backend.delete_media_item(p)
                        if ok:
                            res.deleted_count += 1
                            res.freed_bytes += sz
                        else:
                            res.failed_count += 1
                    else:
                        res.failed_count += 1
                except OSError:
                    res.failed_count += 1

    return res
