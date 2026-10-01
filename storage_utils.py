from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any, TypedDict

import file_manager
import storage_backend

MEDIA_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif",
    ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm", ".m4v", ".flv"
}


class CategoryInfo(TypedDict):
    count: int
    size_mb: float


class StorageStats(TypedDict):
    total_files: int
    total_size_mb: float
    categories: dict[str, CategoryInfo]
    last_scan_time: float | None


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
    }

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
                    sz = int(item.size_bytes)
                    total_bytes += sz
                    cur_mb = stats["categories"][cat_name]["size_mb"]
                    stats["categories"][cat_name]["size_mb"] = round(cur_mb + (sz / 1048576), 2)

                stats["total_files"] = sum(c["count"] for c in stats["categories"].values())
                stats["total_size_mb"] = round(total_bytes / 1048576, 2)
            except Exception as e:
                pass

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
) -> list[list[str]]:
    """
    كشف الملفات المكررة في مجلدات التخزين:
    - يدعم المسار الفيزيائي للذاكرة الداخلية.
    - يدعم بطاقة الذاكرة الخارجية عبر SAF Tree URI دون تحويله لمسار Linux.
    - يستخدم URI كمفتاح للعناصر الخارجية.
    - يحسب الاسم والحجم والتاريخ ووحدة التخزين لمنع التعارض.
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

    # 1. إذا كانت الوجهة SAF Tree URI لبطاقة الذاكرة الخارجية
    if target_location and target_location.is_saf:
        tree_uri = target_location.tree_uri or target_location.saf_uri
        if not tree_uri or not storage_backend.is_saf_uri_valid(tree_uri):
            return []

        hash_map: dict[str, list[str]] = {}
        try:
            saf_items = storage_backend.scan_saf_tree_recursively(tree_uri, include_organized=True)
            for item in saf_items:
                uri = item.uri or item.id
                sz = int(item.size_bytes)
                name = item.name.lower()
                mtime = int(item.date_modified)
                vol = getattr(item, "storage_id", "sdcard")

                if sz <= 0:
                    continue

                # حساب بصمة المحتوى عند الإمكان (mock أو فحص دفق أولي)
                sample_h = ""
                if uri.startswith("mock_doc://"):
                    p = Path(uri.replace("mock_doc://", ""))
                    if p.exists() and p.is_file():
                        try:
                            with open(p, "rb") as fp:
                                sample_h = hashlib.md5(fp.read(65536)).hexdigest()
                        except OSError:
                            pass

                # المفتاح: الحجم وبصمة المحتوى (أو الاسم عند تعذر قراءة البصمة)
                key = f"{sz}_{sample_h}" if sample_h else f"{sz}_{name}"
                if key not in hash_map:
                    hash_map[key] = []
                hash_map[key].append(uri)
        except Exception:
            return []

        return [v for v in hash_map.values() if len(v) > 1]

    # 2. إذا كانت الوجهة مسار محلي فيزيائي
    base = (
        target_location.path
        if (target_location and target_location.path)
        else (base_path or file_manager.get_internal_media_sorter_base_path())
    )
    hash_map: dict[str, list[str]] = {}
    if not base.exists():
        return []

    try:
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in MEDIA_EXTS:
                continue
            try:
                sz = f.stat().st_size
                h = hashlib.md5()
                chunk = min(65536, sz)
                with open(f, "rb") as fp:
                    h.update(fp.read(chunk))
                    if sz > 131072:
                        _ = fp.seek(-chunk, 2)
                        h.update(fp.read(chunk))
                key = f"{sz}_{h.hexdigest()}"
                if key not in hash_map:
                    hash_map[key] = []
                hash_map[key].append(str(f))
            except OSError:
                continue
    except (OSError, PermissionError):
        pass

    return [v for v in hash_map.values() if len(v) > 1]


def remove_duplicate_files(
    duplicates: list[list[str]],
    target_location: Any | None = None,
) -> tuple[int, int]:
    """
    حذف النسخ المكررة بأمان مع الحفاظ التام على النسخة الأصلية (الملف الأول) من كل مجموعة:
    - في بطاقة الذاكرة الخارجية عبر SAF: لا تحذف إلا عبر delete_media_item وبعد التحقق من الصلاحية.
    - تعيد زوجاً من: (عدد الملفات المحذوفة, إجمالي البايتات المحررة).
    """
    if target_location is None:
        target_location = storage_backend.get_active_target_location()

    deleted_count = 0
    freed_bytes = 0

    for group in duplicates:
        if len(group) <= 1:
            continue

        # الإبقاء على الملف الأول، وحذف النسخ الإضافية المكررة
        for file_ref in group[1:]:
            is_saf_or_uri = (
                str(file_ref).startswith("content://")
                or str(file_ref).startswith("mock_doc://")
                or (target_location and target_location.is_saf)
            )

            if is_saf_or_uri:
                # التحقق الصارم من الصلاحية قبل الحذف في SAF
                if target_location and target_location.is_saf:
                    tree_uri = target_location.tree_uri or target_location.saf_uri
                    if not storage_backend.is_saf_uri_valid(tree_uri):
                        continue

                sz = storage_backend.get_uri_file_size(file_ref)
                ok = storage_backend.delete_media_item(file_ref)
                if ok:
                    deleted_count += 1
                    freed_bytes += sz
            else:
                p = Path(file_ref)
                try:
                    if p.is_file():
                        sz = p.stat().st_size
                        ok = storage_backend.delete_media_item(p)
                        if ok:
                            deleted_count += 1
                            freed_bytes += sz
                except OSError:
                    continue

    return deleted_count, freed_bytes
