# -*- coding: utf-8 -*-
import hashlib
import sqlite3
from pathlib import Path
import file_manager

MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm"}


def get_storage_stats(base_path=None):
    base = base_path or file_manager.get_media_sorter_base_path()
    stats = {"total_files": 0, "total_size_mb": 0.0, "categories": {}, "last_scan_time": None}
    if not base.exists():
        return stats
    total_bytes = 0
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
            stats["categories"][cat_dir.name] = {"count": cat_count, "size_mb": round(cat_bytes / 1048576, 2)}
    stats["total_files"] = sum(c["count"] for c in stats["categories"].values())
    stats["total_size_mb"] = round(total_bytes / 1048576, 2)
    try:
        db_path = base / "scanned_media_cache.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            row = conn.execute("SELECT MAX(processed_at) FROM scanned_files").fetchone()
            conn.close()
            if row and row[0]:
                stats["last_scan_time"] = float(row[0])
    except Exception:
        pass
    return stats


def find_duplicate_files(base_path=None):
    base = base_path or file_manager.get_media_sorter_base_path()
    hash_map = {}
    if not base.exists():
        return []
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
                    fp.seek(-chunk, 2)
                    h.update(fp.read(chunk))
            key = str(sz) + "_" + h.hexdigest()
            if key not in hash_map:
                hash_map[key] = []
            hash_map[key].append(str(f))
        except OSError:
            continue
    return [v for v in hash_map.values() if len(v) > 1]
