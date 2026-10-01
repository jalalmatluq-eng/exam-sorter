"""
وحدة إدارة الملفات والمجلدات لتطبيق مصنّف صور الاختبارات (Exam Sorter).
المسؤوليات:
1. تحديد مسار التخزين المناسب (على الهاتف أندرويد أو الحاسوب).
2. تنظيف أسماء المواد من الرموز الممنوعة وإنشاء المجلدات.
3. حفظ الصور وتسميتها بنظام موحد (اسم المادة + التاريخ + رقم تسلسلي).
4. استرجاع قائمة المواد وعدد الصور الموجودة في كل مادة.
5. استرجاع صور مادة معينة لعرضها في المعرض.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("FileManager")


def get_base_storage_path() -> Path:
    """تحديد المسار الأساسي لحفظ ملفات الاختبارات المنظمة"""
    try:
        base = get_media_sorter_base_path() / "صور الاختبارات"
    except OSError:
        base = get_internal_media_sorter_base_path() / "صور الاختبارات"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return base


WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}


def sanitize_folder_name(name: str) -> str:
    r"""
    تنظيف اسم المادة من أي رموز غير مسموحة في أنظمة الملفات.

    يزيل الرموز: \ / : * ? " < > | والأسماء المحجوزة في ويندوز.
    إذا كان الاسم فارغاً، يُعاد اسم افتراضي 'مادة_غير_محددة'.
    """
    if not name:
        return "مادة_غير_محددة"

    # استبدال الرموز غير المسموحة بمسافة لحفظ التباعد بين الكلمات
    clean_name = re.sub(r'[\\/*?:"<>|\r\n\t]', " ", name)
    # استبدال المسافات المتعددة بمسافة واحدة وحذف المسافات الطرفية
    clean_name = re.sub(r"\s+", " ", clean_name).strip().rstrip(". ")

    # منع الأسماء المحجوزة في أنظمة ويندوز
    if clean_name.upper() in WINDOWS_RESERVED:
        clean_name = f"{clean_name}_مادة"

    # تقليص الطول الأقصى لاسم المجلد إلى 120 حرف
    if len(clean_name) > 120:
        clean_name = clean_name[:120].strip()

    return clean_name if clean_name else "مادة_غير_محددة"


def ensure_subject_folder(base_path: Path, subject_name: str) -> Path:
    """
    إنشاء مجلد المادة إن لم يكن موجوداً، مع تنظيف الاسم من الرموز الممنوعة.

    المعاملات:
        base_path: المسار الأساسي لحفظ المجلدات.
        subject_name: اسم المادة الدراسية (مثل: 'رياضيات 1').

    العائد:
        كائن Path يمثل المجلد المنشأ أو الموجود للمادة.
    """
    clean_name = sanitize_folder_name(subject_name)
    target_dir = Path(base_path) / clean_name
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def save_image_to_subject(
    image_path: str,
    subject_name: str,
    base_path: Path | None = None
) -> str:
    """
    نسخ الصورة إلى مجلد المادة المناسب بتسمية منظمة وفريدة.

    صيغة الاسم الجديد:
        [اسم_المادة]_[YYYY-MM-DD]_[الرقم_التسلسلي].[الامتداد]
        مثال: رياضيات_2026-09-24_01.jpg

    المعاملات:
        image_path: مسار الصورة الأصلية (المصدر).
        subject_name: اسم المادة الدراسية.
        base_path: اختياري، استخدام get_base_storage_path() افتراضياً.

    العائد:
        مسار الملف الجديد النهائي كـ string.
    """
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(f"ملف الصورة غير موجود: {image_path}")

    if base_path is None:
        base_path = get_base_storage_path()

    subject_folder = ensure_subject_folder(base_path, subject_name)
    clean_name = sanitize_folder_name(subject_name)

    # استخراج الامتداد الأصلي للصورة أو افتراضي .jpg
    ext = Path(image_path).suffix.lower()
    if not ext or ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".jpg"

    today_str = datetime.now(UTC).strftime("%Y-%m-%d")

    # حساب الرقم التسلسلي اليومي للملف داخل المجلد
    index = 1
    while True:
        candidate_filename = f"{clean_name}_{today_str}_{index:02d}{ext}"
        candidate_path = subject_folder / candidate_filename
        if not candidate_path.exists():
            break
        index += 1

    # نسخ الملف إلى الوجهة النهائية
    _ = shutil.copy2(image_path, candidate_path)

    # تنظيف الملف المؤقت إذا كان مصدره من مجلد temp الخاص بالتطبيق
    try:
        src_path = Path(image_path).resolve()
        app_temp_dir = get_temp_dir().resolve()
        if src_path.parent == app_temp_dir:
            src_path.unlink(missing_ok=True)
    except OSError:
        pass

    return str(candidate_path)


def get_temp_dir() -> Path:
    """تحديد مجلد الملفات المؤقتة الموحد للتطبيق"""
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app and hasattr(app, "user_data_dir") and app.user_data_dir:
            t = Path(str(app.user_data_dir)) / "temp"
            t.mkdir(parents=True, exist_ok=True)
            return t
    except (ImportError, AttributeError, OSError):
        pass

    # على الحاسوب أو في غياب التطبيق نستخدم مجلد temp داخل مسار التخزين
    t = get_base_storage_path().parent / "temp"
    t.mkdir(parents=True, exist_ok=True)
    return t


def cleanup_temp_files(temp_dir: Path | None = None) -> int:
    """حذف جميع الملفات المؤقتة القديمة لتوفير المساحة."""
    if temp_dir is None:
        temp_dir = get_temp_dir()

    cleaned_count = 0
    if temp_dir.exists() and temp_dir.is_dir():
        for f in temp_dir.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                    cleaned_count += 1
                except OSError:
                    pass
    return cleaned_count


def list_subjects(
    base_path: Path | None = None,
    target_location: Any | None = None,
) -> list[dict[str, object]]:
    """
    إرجاع قائمة بجميع المواد والأقسام المخزنة وعدد الملفات في كل مجلد:
    - يدعم المسار الفيزيائي (Path) للذاكرة الداخلية.
    - يدعم SAF Tree URI لبطاقة الذاكرة الخارجية دون استدعاء Path.iterdir أو get_media_sorter_base_path.
    - مرتبة تنازلياً بحسب عدد الملفات ثم أبجدياً.
    """
    import storage_backend
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

    valid_extensions = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif",
        ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm", ".m4v", ".flv"
    }
    subjects_dict: dict[str, dict[str, object]] = {}

    # 1. إذا كانت الوجهة SAF Tree URI لبطاقة الذاكرة الخارجية
    if target_location and target_location.is_saf:
        tree_uri = target_location.tree_uri or target_location.saf_uri
        if tree_uri and storage_backend.is_saf_uri_valid(tree_uri):
            try:
                saf_items = storage_backend.scan_saf_tree_recursively(tree_uri, include_organized=True)
                for item in saf_items:
                    rel = getattr(item, "relative_path", "")
                    if rel:
                        parts = rel.replace("\\", "/").strip("/").split("/")
                        if parts and parts[0] == storage_backend.ORGANIZED_FOLDER_NAME:
                            parts = parts[1:]
                        if parts:
                            subj_name = parts[0]
                            if subj_name in ("صور الاختبارات", "صور اختبارات") and len(parts) > 1:
                                subj_name = parts[1]
                        else:
                            subj_name = "خارج التصنيف"
                    else:
                        raw_p = item.path or item.id
                        parts = raw_p.replace("\\", "/").strip("/").split("/")
                        subj_name = parts[-2] if len(parts) >= 2 else "خارج التصنيف"

                    if subj_name not in subjects_dict:
                        subjects_dict[subj_name] = {
                            "name": subj_name,
                            "folder_path": f"{tree_uri}/{subj_name}",
                            "count": 0,
                            "latest_modified": 0.0,
                            "is_saf": True,
                        }
                    subjects_dict[subj_name]["count"] = int(str(subjects_dict[subj_name]["count"])) + 1
                    cur_m = float(str(subjects_dict[subj_name]["latest_modified"]))
                    subjects_dict[subj_name]["latest_modified"] = max(cur_m, float(item.date_modified))
            except Exception as e:
                logger.error("خطأ أثناء استعلام مجلدات SAF في list_subjects: %s", e)

        subjects = list(subjects_dict.values())
        subjects.sort(key=lambda s: (-int(str(s["count"])), str(s["name"])))
        return subjects

    # 2. إذا كانت الوجهة مسار محلي فيزيائي (الذاكرة الداخلية)
    roots: list[Path] = []
    if target_location and target_location.path:
        roots.append(target_location.path)
        exam_p = target_location.path / "صور الاختبارات"
        if exam_p.exists() and exam_p not in roots:
            roots.append(exam_p)
    elif base_path is not None:
        roots.append(Path(base_path))
    else:
        int_base = get_internal_media_sorter_base_path()
        roots.append(int_base)
        exam_base = int_base / "صور الاختبارات"
        if exam_base.exists() and exam_base not in roots:
            roots.append(exam_base)

    for root in roots:
        try:
            if not root.exists():
                continue
            items = list(root.iterdir())
        except (OSError, PermissionError):
            continue

        for item in items:
            try:
                if not item.is_dir():
                    continue
                media_files = [
                    f for f in item.iterdir()
                    if f.is_file() and f.suffix.lower() in valid_extensions
                ]
            except (OSError, PermissionError):
                continue
            count = len(media_files)
            try:
                latest_mod = item.stat().st_mtime
                if media_files:
                    latest_mod = max(f.stat().st_mtime for f in media_files)
            except (OSError, PermissionError):
                latest_mod = 0.0

            # فحص المجلدات الفرعية للمواد داخل صور الاختبارات
            if item.name in ("صور الاختبارات", "صور اختبارات"):
                try:
                    sub_items = [sub for sub in item.iterdir() if sub.is_dir()]
                except (OSError, PermissionError):
                    sub_items = []
                for sub in sub_items:
                    try:
                        sub_files = [
                            f for f in sub.iterdir()
                            if (
                                f.is_file()
                                and f.suffix.lower() in valid_extensions
                            )
                        ]
                        s_count = len(sub_files)
                        s_mod = sub.stat().st_mtime
                        if sub_files:
                            s_mod = max(
                                f.stat().st_mtime for f in sub_files
                            )
                    except (OSError, PermissionError):
                        sub_files = []
                        s_count = 0
                        s_mod = 0.0

                    sub_name = sub.name
                    if sub_name not in subjects_dict:
                        subjects_dict[sub_name] = {
                            "name": sub_name,
                            "folder_path": str(sub),
                            "count": s_count,
                            "latest_modified": s_mod,
                        }
                    else:
                        old_c = int(str(subjects_dict[sub_name]["count"]))
                        subjects_dict[sub_name]["count"] = old_c + s_count
                        old_m = float(str(subjects_dict[sub_name]["latest_modified"]))
                        subjects_dict[sub_name]["latest_modified"] = max(old_m, float(s_mod))

                    count += s_count

                name = item.name
                if name in subjects_dict:
                    cur_c = int(str(subjects_dict[name]["count"]))
                    subjects_dict[name]["count"] = cur_c + count
                    cur_m = float(str(subjects_dict[name]["latest_modified"]))
                    subjects_dict[name]["latest_modified"] = max(cur_m, float(latest_mod))
                else:
                    subjects_dict[name] = {
                        "name": name,
                        "folder_path": str(item),
                        "count": count,
                        "latest_modified": latest_mod,
                    }
            else:
                name = item.name
                if name in subjects_dict:
                    cur_c = int(str(subjects_dict[name]["count"]))
                    subjects_dict[name]["count"] = cur_c + count
                    cur_m = float(str(subjects_dict[name]["latest_modified"]))
                    subjects_dict[name]["latest_modified"] = max(cur_m, float(latest_mod))
                else:
                    subjects_dict[name] = {
                        "name": name,
                        "folder_path": str(item),
                        "count": count,
                        "latest_modified": latest_mod,
                    }

    subjects = list(subjects_dict.values())
    subjects.sort(key=lambda s: (-int(str(s["count"])), str(s["name"])))
    return subjects


# اسم بديل موحد ومطابق لمتطلبات المعمارية
get_subjects = list_subjects


def get_subject_images(
    subject_name: str,
    base_path: Path | None = None,
    target_location: Any | None = None,
) -> list[str]:
    """
    استرجاع قائمة مسارات أو URIs الصور والفيديوهات لمادة أو قسم معين مرتبة من الأحدث إلى الأقدم:
    - إذا كانت الوجهة SAF، يستخرج ملفات المادة عبر scan_saf_tree_recursively.
    - إذا كانت الذاكرة الداخلية، يستخرج الملفات عبر المسار المحلي.
    - يمنع استخدام get_media_sorter_base_path عند اختيار SAF.
    """
    import storage_backend
    clean_name = sanitize_folder_name(subject_name)

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

    valid_extensions = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif",
        ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm", ".m4v", ".flv"
    }

    # 1. إذا كانت الوجهة SAF Tree URI
    if target_location and target_location.is_saf:
        tree_uri = target_location.tree_uri or target_location.saf_uri
        if tree_uri and storage_backend.is_saf_uri_valid(tree_uri):
            try:
                saf_items = storage_backend.scan_saf_tree_recursively(tree_uri, include_organized=True)
                matching: list[tuple[str, float]] = []
                for item in saf_items:
                    rel = getattr(item, "relative_path", "")
                    matched = False
                    if rel:
                        parts = rel.replace("\\", "/").strip("/").split("/")
                        if parts and parts[0] == storage_backend.ORGANIZED_FOLDER_NAME:
                            parts = parts[1:]
                        # تحليل الهيكل بدقة:
                        # 1) صور الاختبارات / [اسم المادة] / الملف
                        # 2) [اسم المادة] / الملف
                        if len(parts) >= 3 and parts[0] in ("صور الاختبارات", "صور اختبارات"):
                            item_subj = parts[1]
                        elif len(parts) >= 2:
                            item_subj = parts[0]
                        else:
                            item_subj = ""

                        if item_subj and (
                            sanitize_folder_name(item_subj).lower() == clean_name.lower()
                            or item_subj.lower() == clean_name.lower()
                        ):
                            matched = True
                    else:
                        raw_p = item.path or item.id
                        parts = raw_p.replace("\\", "/").strip("/").split("/")
                        if len(parts) >= 2:
                            parent_dir = parts[-2]
                            if (
                                sanitize_folder_name(parent_dir).lower() == clean_name.lower()
                                or parent_dir.lower() == clean_name.lower()
                            ):
                                matched = True
                    if matched:
                        file_uri = item.uri or item.path
                        matching.append((file_uri, float(item.date_modified)))

                matching.sort(key=lambda x: x[1], reverse=True)
                return [m[0] for m in matching]
            except Exception as e:
                logger.error("خطأ أثناء جلب ملفات المادة عبر SAF: %s", e)
        return []

    # 2. وجهة مسار محلي فيزيائي
    candidates: list[Path] = []
    if target_location and target_location.path:
        candidates.append(target_location.path / clean_name)
        candidates.append(target_location.path / "صور الاختبارات" / clean_name)
    elif base_path is not None:
        candidates.append(Path(base_path) / clean_name)
        candidates.append(Path(base_path) / "صور الاختبارات" / clean_name)
    else:
        int_base = get_internal_media_sorter_base_path()
        candidates.append(int_base / clean_name)
        candidates.append(int_base / "صور الاختبارات" / clean_name)

    images: list[str] = []
    for subject_folder in candidates:
        if subject_folder.exists() and subject_folder.is_dir():
            for root, _, files in os.walk(str(subject_folder)):
                for f in files:
                    if Path(f).suffix.lower() in valid_extensions:
                        full_img = Path(root) / f
                        if str(full_img) not in images:
                            images.append(str(full_img))

    images.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return images


def delete_image_file(image_path: str, target_location: Any | None = None) -> bool:
    """حذف صورة أو فيديو معينة بأمان من مجلد المادة سواء كانت مساراً محلياً أو SAF Document URI وتحديث السجل"""
    import storage_backend
    try:
        ok = storage_backend.delete_media_item(image_path)
        if ok:
            remove_transfer_history_records_by_dest([image_path])
        return ok
    except Exception as e:
        logger.warning("خطأ أثناء حذف الصورة/الملف %s: %s", image_path, e)
        return False


@dataclass
class DeleteFolderResult:
    """نتيجة تفصيلية لعملية حذف مجلد المادة تميز بين حذف الملفات وحذف المجلد نفسه"""
    files_deleted: bool = False
    folder_deleted: bool = False
    deleted_files_count: int = 0
    total_files_count: int = 0
    message: str = ""

    def __bool__(self) -> bool:
        # لا يعتبر الحذف كاملاً وناجحاً إلا بحذف الملفات والمجلد معاً
        return self.files_deleted and self.folder_deleted


def delete_subject_folder(
    subject_name: str,
    base_path: Path | None = None,
    target_location: Any | None = None,
) -> DeleteFolderResult:
    """
    حذف مجلد مادة بالكامل وجميع الصور بداخله بأمان عبر Path أو SAF وتحديث السجل:
    - يميز بدقة بين نجاح حذف الملفات ونجاح حذف مجلد المادة.
    - إذا بقيت الملفات أو بقي المجلد فارغاً دون حذف، يصدر تحذيراً صريحاً ورسالة توضيحية.
    """
    import storage_backend
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

    clean_name = sanitize_folder_name(subject_name)

    # 1. إذا كانت الوجهة SAF Tree URI لبطاقة الذاكرة
    if target_location and target_location.is_saf:
        tree_uri = target_location.tree_uri or target_location.saf_uri
        if not tree_uri or not storage_backend.is_saf_uri_valid(tree_uri):
            msg = "تعذر حذف مجلد المادة: إذن SAF غير صالح أو بطاقة SD مفصولة"
            logger.warning(msg)
            return DeleteFolderResult(files_deleted=False, folder_deleted=False, message=msg)

        # أ) حذف جميع الملفات الموجودة داخل المادة أولاً
        imgs = get_subject_images(clean_name, target_location=target_location)
        deleted_count = 0
        for img in imgs:
            if delete_image_file(img, target_location=target_location):
                deleted_count += 1

        files_deleted = (deleted_count == len(imgs))

        # ب) البحث عن مجلد المادة في شجرة SAF وحذفه كـ Document
        folder_uri = storage_backend.saf_find_directory(tree_uri, clean_name)
        if not folder_uri:
            folder_uri = storage_backend.saf_find_directory(tree_uri, f"صور الاختبارات/{clean_name}")

        folder_deleted = False
        if folder_uri:
            folder_deleted = storage_backend.delete_media_item(folder_uri)

        if files_deleted and folder_deleted:
            return DeleteFolderResult(
                files_deleted=True,
                folder_deleted=True,
                deleted_files_count=deleted_count,
                total_files_count=len(imgs),
                message="تم حذف جميع أوراق المادة ومجلدها بنجاح من بطاقة SD",
            )
        elif files_deleted and not folder_deleted:
            warn_msg = f"تم حذف {deleted_count} ورقة بنجاح، لكن تعذر حذف مجلد المادة وبقي فارغاً في بطاقة SD."
            logger.warning(warn_msg)
            return DeleteFolderResult(
                files_deleted=True,
                folder_deleted=False,
                deleted_files_count=deleted_count,
                total_files_count=len(imgs),
                message=warn_msg,
            )
        else:
            fail_msg = f"فشل حذف بعض ملفات المادة (تم حذف {deleted_count} من {len(imgs)})."
            logger.warning(fail_msg)
            return DeleteFolderResult(
                files_deleted=False,
                folder_deleted=folder_deleted,
                deleted_files_count=deleted_count,
                total_files_count=len(imgs),
                message=fail_msg,
            )

    # 2. إذا كانت الوجهة مسار محلي فيزيائي
    base = target_location.path if (target_location and target_location.path) else (Path(base_path) if base_path else get_internal_media_sorter_base_path())
    candidates = [
        base / "صور الاختبارات" / clean_name,
        base / clean_name,
    ]
    target_dir = None
    for c in candidates:
        if c.exists() and c.is_dir():
            target_dir = c
            break

    if target_dir:
        files_to_delete = [str(f) for f in target_dir.rglob("*") if f.is_file()]
        try:
            shutil.rmtree(target_dir)
            if target_dir.exists():
                warn_msg = "تم حذف محتويات المادة ولكن بقي المجلد فارغاً على القرص."
                logger.warning(warn_msg)
                return DeleteFolderResult(
                    files_deleted=True, folder_deleted=False, deleted_files_count=len(files_to_delete), message=warn_msg
                )
            if files_to_delete:
                remove_transfer_history_records_by_dest(files_to_delete)
            return DeleteFolderResult(
                files_deleted=True,
                folder_deleted=True,
                deleted_files_count=len(files_to_delete),
                total_files_count=len(files_to_delete),
                message="تم حذف مجلد المادة بالكامل",
            )
        except OSError as e:
            err_msg = f"خطأ أثناء حذف مجلد المادة: {e}"
            logger.warning(err_msg)
            return DeleteFolderResult(files_deleted=False, folder_deleted=False, message=err_msg)

    return DeleteFolderResult(files_deleted=True, folder_deleted=True, message="مجلد المادة غير موجود أصلاً")


def clean_empty_subject_folders(base_path: Path | None = None) -> int:
    """فحص مجلد التخزين وحذف أي مجلدات مواد فارغة بأمان دون التأثير على SAF"""
    valid_extensions = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif",
        ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm", ".m4v", ".flv"
    }
    roots: list[Path] = []
    if base_path is not None:
        roots.append(Path(base_path))
    else:
        int_base = get_internal_media_sorter_base_path()
        roots.append(int_base)
        exam_p = int_base / "صور الاختبارات"
        if exam_p.exists():
            roots.append(exam_p)

    deleted_count = 0
    for root in roots:
        if not root.exists():
            continue
        try:
            for item in list(root.iterdir()):
                if item.is_dir():
                    media_files = [
                        f for f in item.iterdir()
                        if f.is_file() and f.suffix.lower() in valid_extensions
                    ]
                    if len(media_files) == 0:
                        try:
                            shutil.rmtree(item)
                            deleted_count += 1
                        except OSError:
                            pass
        except (OSError, PermissionError):
            continue

    return deleted_count


def open_folder_native(folder_path: str) -> bool:
    """فتح المجلد في مستعرض الملفات الأصلي لنظام التشغيل"""
    try:
        from kivy.utils import platform
        if platform == "android":
            return False

        p = Path(folder_path).resolve()
        if not p.exists():
            p = get_base_storage_path()
        if os.name == "nt":
            os.startfile(str(p))
            return True
        elif sys.platform == "darwin":
            import subprocess
            _ = subprocess.Popen(["open", str(p)])
            return True
        else:
            import subprocess
            _ = subprocess.Popen(["xdg-open", str(p)])
            return True
    except (OSError, RuntimeError) as e:
        print("تعذر فتح المجلد في المستكشف:", e)
        return False


ORGANIZED_FOLDER_NAME = "الملفات المنظمة"

DEFAULT_PREFERENCES: dict[str, object] = {
    "target_storage": "internal",
    "source_storage": "both",
    "operation_mode": "copy",
    "custom_target_path": "",
    "scan_all_roots": True,
    "initial_setup_completed": False,
    "poison_files": [],
    "pending_scan": False,
    "pending_source": "both",
    "pending_target": "internal",
    "api_key": "",
    "detected_sdcard_path": "",
}


def get_app_private_storage_dir() -> Path:
    """
    تحديد مجلد التخزين الخاص بالتطبيق (App Private Storage) بشكل موحد وآمن:
    - محمي تماماً من قيود الأذونات في التخزين المشترك.
    - يحتوي ملفات النظام الداخلية: scanned_media_cache.db, sorter_prefs.json,
      last_processing.json, service_control.json.
    """
    # 1. فحص متغير البيئة المعتمد من python-for-android
    android_private = os.environ.get("ANDROID_PRIVATE")
    if android_private and os.path.exists(android_private):
        return Path(android_private)

    # 2. تطبيق Kivy النشط في الذاكرة
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app and hasattr(app, "user_data_dir") and app.user_data_dir:
            p = Path(str(app.user_data_dir))
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass

    # 3. الوصول المباشر عبر pyjnius لتطبيق أندرويد أو الخدمة الخلفية
    try:
        from kivy.utils import platform
        if platform == "android":
            from jnius import autoclass
            try:
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                if PythonActivity.mActivity:
                    return Path(PythonActivity.mActivity.getFilesDir().getAbsolutePath())
            except Exception:
                pass
            try:
                PythonService = autoclass("org.kivy.android.PythonService")
                if PythonService.mService:
                    return Path(PythonService.mService.getFilesDir().getAbsolutePath())
            except Exception:
                pass
    except Exception:
        pass

    # 4. مسارات التخزين الخاصة القياسية على نظام أندرويد
    for std_path in [
        "/data/user/0/com.cosmosort.ai.cosmosort/files",
        "/data/data/com.cosmosort.ai.cosmosort/files",
    ]:
        p = Path(std_path)
        if p.exists() and os.access(str(p), os.W_OK):
            return p

    # 5. للحاسوب وبيئة الاختبارات والتطوير
    fallback = Path(__file__).resolve().parent / ".app_private"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_prefs_file_path() -> Path:
    """مسار ملف حفظ تفضيلات المستخدم الخاصة بالفرز والتخزين في التخزين الخاص"""
    p = get_app_private_storage_dir() / "sorter_prefs.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def get_sorter_preferences() -> dict[str, object]:
    """استرجاع تفضيلات الفرز المحفوظة من المستخدم"""
    prefs_file = get_prefs_file_path()
    prefs = dict(DEFAULT_PREFERENCES)
    if prefs_file.exists():
        try:
            with open(prefs_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    prefs.update(saved)
        except (OSError, json.JSONDecodeError) as e:
            print("تنبيه: تعذر قراءة ملف تفضيلات الفرز:", e)
    return prefs


def save_sorter_preferences(prefs: dict[str, object]) -> None:
    """حفظ تفضيلات الفرز المحدثة"""
    prefs_file = get_prefs_file_path()
    current = get_sorter_preferences()
    current.update(prefs)
    try:
        with open(prefs_file, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError) as e:
        print("خطأ أثناء حفظ تفضيلات الفرز:", e)


def get_last_processing_file_path() -> Path:
    """مسار ملف تتبع الملف الجاري معالجته لاكتشاف الانهيارات غير المتوقعة (Poison Files)"""
    return get_prefs_file_path().parent / "last_processing.json"


def mark_file_processing_start(file_path: str) -> None:
    """تسجيل مسار الملف قبل بدء معالجته لاكتشاف أي انهيار أصلي مفاجئ"""
    try:
        target = get_last_processing_file_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {"file": file_path, "started_at": time.time()}
        target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def mark_file_processing_end() -> None:
    """مسح ملف التتبع بعد اكتمال معالجة الملف بنجاح"""
    try:
        target = get_last_processing_file_path()
        if target.exists():
            target.unlink(missing_ok=True)
    except Exception:
        pass


def check_and_handle_poison_file_on_boot() -> str | None:
    """
    فحص ما إذا كان التطبيق قد انهار في الجلسة السابقة أثناء معالجة ملف معين:
    إذا وُجد ملف مسجل، يتم اعتباره ملفاً ساماً (Poison File) مسبباً للانهيار الأصلي،
    ويُضاف تلقائياً إلى قائمة poison_files لتخطيه مستقبلاً مع حذف ملف التتبع.
    """
    try:
        target = get_last_processing_file_path()
        if not target.exists():
            return None
        data = json.loads(target.read_text(encoding="utf-8"))
        poison_file = str(data.get("file", "")).strip()
        target.unlink(missing_ok=True)

        if poison_file:
            prefs = get_sorter_preferences()
            raw_poisons = prefs.get("poison_files", [])
            poisons: list[str] = (
                [str(x) for x in raw_poisons]
                if isinstance(raw_poisons, (list, tuple, set))
                else []
            )
            if poison_file not in poisons:
                poisons.append(poison_file)
                save_sorter_preferences({"poison_files": poisons})
            return poison_file
    except Exception as e:
        print("خطأ أثناء فحص ملف الانهيار السابق:", e)
    return None


def get_poison_files_set() -> set[str]:
    """استرجاع مجموعة مسارات الملفات السامة المستبعدة"""
    try:
        prefs = get_sorter_preferences()
        raw_poisons = prefs.get("poison_files", [])
        if isinstance(raw_poisons, (list, tuple, set)):
            return {str(x) for x in raw_poisons}
        return set()
    except Exception:
        return set()


def set_pending_scan(
    pending: bool, source: str = "both", target: str = "internal"
) -> None:
    """حفظ نية الفحص لاستئنافها تلقائياً بعد منح الصلاحيات"""
    save_sorter_preferences({
        "pending_scan": pending,
        "pending_source": source,
        "pending_target": target,
    })


def get_pending_scan_info() -> tuple[bool, str, str]:
    """استرجاع حالة الفحص المعلق ومصدره ووجهته"""
    prefs = get_sorter_preferences()
    is_pending = bool(prefs.get("pending_scan", False))
    source = str(prefs.get("pending_source", "both"))
    target = str(prefs.get("pending_target", "internal"))
    return is_pending, source, target


def clear_pending_scan() -> None:
    """إلغاء الفحص المعلق بعد تنفيذه"""
    save_sorter_preferences({"pending_scan": False})


def get_pending_scan() -> tuple[bool, str, str]:
    """اسم بديل لدالة get_pending_scan_info لضمان التوافق الكامل"""
    return get_pending_scan_info()



def get_stored_api_key() -> str:
    """استرجاع مفتاح API المحفوظ في مسار التخزين المشترك لتتمكن الخدمة والتطبيق من قراءته"""
    try:
        prefs = get_sorter_preferences()
        k = str(prefs.get("api_key", "")).strip()
        if k:
            return k
    except Exception:
        pass

    try:
        candidates = [
            get_prefs_file_path().parent / ".api_key",
            get_media_sorter_base_path() / ".api_key",
            Path(__file__).resolve().parent / ".api_key",
        ]
        for c in candidates:
            if c.exists() and c.is_file():
                val = c.read_text(encoding="utf-8").strip()
                if val:
                    return val
    except Exception:
        pass
    return ""


def save_api_key_to_persistent_storage(new_key: str) -> None:
    """حفظ مفتاح API في مسار تخزين دائم ومشترك يصل إليه التطبيق والخدمة الخلفية"""
    clean_k = (new_key or "").strip()
    try:
        save_sorter_preferences({"api_key": clean_k})
    except Exception:
        pass

    targets = [
        get_prefs_file_path().parent / ".api_key",
        get_media_sorter_base_path() / ".api_key",
    ]
    for target in targets:
        try:
            if clean_k:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(clean_k, encoding="utf-8")
            else:
                if target.exists():
                    target.unlink(missing_ok=True)
        except Exception:
            pass


def is_all_files_access_granted() -> bool:
    """التحقق من صلاحية الوصول الشامل لكافة الملفات (أندرويد 11+)"""
    try:
        from kivy.utils import platform  # type: ignore
        if platform != "android":
            return True
        from jnius import autoclass  # type: ignore
        Environment = autoclass("android.os.Environment")
        BuildVersion = autoclass("android.os.Build$VERSION")
        if int(BuildVersion.SDK_INT) >= 30:
            return bool(Environment.isExternalStorageManager())
        return True
    except (ImportError, AttributeError, RuntimeError) as e:
        print("تنبيه: تعذر فحص صلاحية إدارة كافة الملفات:", e)
        return True


def open_all_files_permission_settings() -> bool:
    """فتح شاشة إعدادات أندرويد الخاصة بمنح صلاحية الوصول لكافة الملفات بتوافق كامل مع جميع أجهزة أندرويد"""
    try:
        from kivy.utils import platform  # type: ignore
        if platform != "android":
            return False
        from android import mActivity  # type: ignore
        from jnius import autoclass  # type: ignore
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        pkg = str(mActivity.getPackageName())
        uri = Uri.fromParts("package", pkg, None)

        # 1. المحاولة الأولى: صفحة التطبيق المباشرة
        try:
            intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
            intent.setData(uri)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            mActivity.startActivity(intent)
            return True
        except Exception:
            pass

        # 2. المحاولة الثانية: صفحة إدارة جميع الملفات العامة (خاصة بأجهزة سامسونج وشاومي)
        try:
            intent = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            mActivity.startActivity(intent)
            return True
        except Exception:
            pass

        # 3. المحاولة الثالثة: صفحة تفاصيل أذونات التطبيق
        try:
            intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
            intent.setData(uri)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            mActivity.startActivity(intent)
            return True
        except Exception:
            pass

        return False
    except Exception as e:
        print("تعذر فتح شاشة إذن الملفات:", e)
        return False


def is_directory_writable(dir_path: Path) -> bool:
    """التحقق الفعلي الصارم من إمكانية إنشاء وكتابة وحذف الملفات داخل المجلد"""
    import storage_backend
    return storage_backend.is_directory_writable(dir_path)


def find_external_sdcard_root() -> Path | None:
    """
    اكتشاف مسار بطاقة الذاكرة الخارجية MicroSD فقط عند ثبوت وجودها وإمكانية الوصول إليها.
    هام: لا يتم قبول المسار لمجرد وجوده؛ يجب أن يكون متاحاً ومقروءاً فعلياً.
    """
    import storage_backend
    locs = storage_backend.detect_storage_locations()
    sd = locs.get("sdcard")
    if sd and sd.detected and sd.path and sd.path != "غير متوفرة حالياً":
        p = Path(sd.path)
        if p.name == ORGANIZED_FOLDER_NAME:
            return p.parent
        return p
    return None


def get_available_storage_destinations() -> dict[str, dict[str, object]]:
    """
    استكشاف مسارات التخزين المتاحة على الجهاز (الداخلية والخارجية) بدقة،
    مع بيان إمكانية الكتابة وسبب الفشل وحاجة بطاقة SD لإذن SAF.
    """
    import storage_backend
    locs = storage_backend.detect_storage_locations()
    dests: dict[str, dict[str, object]] = {}
    for loc_id, loc in locs.items():
        dests[loc_id] = {
            "id": loc.id,
            "name": loc.name,
            "path": loc.path,
            "uri": loc.uri,
            "available": loc.detected and loc.mounted,
            "is_writable": loc.writable,
            "requires_saf": loc.requires_saf,
            "free_gb": loc.free_gb,
            "total_gb": loc.total_gb,
            "failure_reason": loc.failure_reason,
            "description": loc.description,
        }
    return dests


def get_internal_media_sorter_base_path() -> Path:
    """المسار الأساسي للملفات المنظمة على الذاكرة الداخلية حصراً"""
    import storage_backend
    try:
        from kivy.utils import platform
        if platform == "android":
            internal_base = Path("/storage/emulated/0") / ORGANIZED_FOLDER_NAME
            try:
                internal_base.mkdir(parents=True, exist_ok=True)
                storage_backend.migrate_legacy_folders(internal_base)
                return internal_base
            except (PermissionError, OSError) as e:
                logger.debug("تنبيه أثناء إنشاء مجلد الذاكرة الداخلية: %s", e)
                if internal_base.exists():
                    storage_backend.migrate_legacy_folders(internal_base)
                    return internal_base
    except (ImportError, OSError, RuntimeError) as e:
        logger.debug("تنبيه أثناء تهيئة مسار الملفات المنظمة الداخلي: %s", e)

    base = Path(__file__).resolve().parent / ORGANIZED_FOLDER_NAME
    try:
        base.mkdir(parents=True, exist_ok=True)
        storage_backend.migrate_legacy_folders(base)
    except OSError:
        pass
    return base


def get_media_sorter_base_path() -> Path:
    """
    تحديد المسار الأساسي الموحد لمجلدات مُنظّم الوسائط:
    - التحقق الصارم من بطاقة SD ومنع أي Fallback صامت للذاكرة الداخلية.
    - إذا تم اختيار بطاقة SD وكانت تتطلب SAF أو غير متوفرة، يطلق استثناء واضحاً (OSError)
      ويمنع إنشاء أي مجلدات في الذاكرة الداخلية.
    """
    import storage_backend
    prefs = get_sorter_preferences()
    target_pref = prefs.get("target_storage", "internal")

    if target_pref == "sdcard":
        locs = storage_backend.detect_storage_locations()
        sd = locs.get("sdcard")
        if sd and sd.detected and sd.writable and not sd.requires_saf and sd.path and sd.path != "غير متوفرة حالياً":
            sd_target = Path(sd.path)
            if sd_target.name != ORGANIZED_FOLDER_NAME:
                sd_target = sd_target / ORGANIZED_FOLDER_NAME
            try:
                sd_target.mkdir(parents=True, exist_ok=True)
                storage_backend.migrate_legacy_folders(sd_target)
                return sd_target
            except (PermissionError, OSError) as e:
                raise OSError(f"تعذر إنشاء مجلد الوجهة على بطاقة SD ({sd_target}): {e}") from e

        # بطاقة SD تتطلب SAF أو غير متوفرة: منع الرجوع الصامت نهائياً
        raise OSError("بطاقة الذاكرة الخارجية تتطلب إذن SAF للوصول ولا تملك مساراً محلياً مباشراً؛ استخدم TargetLocation.")

    return get_internal_media_sorter_base_path()


def create_initial_category_folders(
    target_location: Any | None = None,
    base_path: Path | None = None,
) -> list[Any]:
    """
    إنشاء وتجهيز شجرة المجلدات الرسمية للملفات المنظمة بدعم كامل لـ TargetLocation:
    - Path destination: إنشاء المجلدات عبر mkdir وهجرة المجلدات القديمة.
    - SAF destination: إنشاء المجلدات عبر saf_find_or_create_directory دون لمس التخزين الداخلي.
    - أي فشل في الوجهة يطلق استثناءً واضحاً ولا ينشئ مجلدات في الذاكرة الداخلية.
    """
    import storage_backend

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

    if not target_location.is_valid:
        raise OSError(f"فشل إعداد مجلدات الوجهة، التخزين غير صالح: {target_location.error_message}")

    created: list[Any] = []

    # 1. وجهة SAF Tree URI لبطاقة الذاكرة الخارجية
    if target_location.is_saf:
        tree_uri = target_location.tree_uri
        if not tree_uri:
            raise OSError("تم اختيار بطاقة الذاكرة الخارجية كوجهة لكن لم يتم تحديد URI الصالح عبر SAF.")

        for f_name in storage_backend.STANDARD_CATEGORIES:
            cat_uri = storage_backend.saf_find_or_create_directory(tree_uri, f_name)
            if not cat_uri:
                raise OSError(f"فشل إنشاء مجلد التصنيف في بطاقة SD عبر SAF: {f_name}")
            created.append(cat_uri)
        return created

    # 2. وجهة مسار محلي فيزيائي
    base = target_location.path
    if base is None:
        raise OSError("وجهة التخزين المحددة لا تملك مساراً محلياً صالحاً.")

    try:
        base.mkdir(parents=True, exist_ok=True)
        storage_backend.migrate_legacy_folders(base)
    except OSError as e:
        raise OSError(f"تعذر إنشاء المجلد الرئيسي للوجهة ({base}): {e}") from e

    for f_name in storage_backend.STANDARD_CATEGORIES:
        p = base / f_name
        try:
            p.mkdir(parents=True, exist_ok=True)
            created.append(p)
        except OSError as e:
            raise OSError(f"تعذر إنشاء مجلد التصنيف ({p}): {e}") from e

    return created


def get_transfer_log_path(base_path: Path | None = None) -> Path:
    """مسار ملف سجل عمليات النقل للتراجع والمراجعة محفوظ دائماً في app-private storage"""
    if base_path is not None:
        return Path(base_path) / "transfer_history.json"

    private_log = get_app_private_storage_dir() / "transfer_history.json"
    # هجرة تلقائية من المسار القديم إن وجد
    if not private_log.exists():
        try:
            legacy_log = get_internal_media_sorter_base_path() / "transfer_history.json"
            if legacy_log.exists():
                shutil.copy2(str(legacy_log), str(private_log))
                logger.info("تمت هجرة سجل transfer_history.json إلى التخزين الخاص بالتطبيق بنجاح")
        except Exception as e:
            logger.debug("تعذر نسخ سجل العمليات القديم: %s", e)
    return private_log


def _log_transfer_record(
    src_path: str,
    dest_path: str,
    category: str,
    file_size: int,
    base_path: Path | None = None,
    is_copy: bool = True,
    is_saf_dest: bool = False,
) -> int:
    """تسجيل عملية نسخ/فرز في سجل المعاملات JSON مع دعم المسارات وعناوين URIs"""
    log_file = get_transfer_log_path(base_path)
    records: list[dict[str, object]] = []
    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    records = [
                        item for item in loaded if isinstance(item, dict)
                    ]
        except (OSError, json.JSONDecodeError):
            records = []

    rec_id = int(datetime.now(UTC).timestamp() * 1000)
    records.append({
        "id": rec_id,
        "source": src_path,
        "destination": dest_path,
        "category": category,
        "size_bytes": file_size,
        "is_copy": is_copy,
        "is_saf_dest": bool(is_saf_dest or dest_path.startswith("content://")),
        "timestamp": datetime.now(UTC).isoformat(),
    })

    records = records[-1000:]
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError) as e:
        logger.warning("تعذر تحديث سجل العمليات: %s", e)
    return rec_id


def _update_last_transfer_record_to_copy(base_path: Path | None = None) -> None:
    """تحديث آخر عملية مسجلة لتكون is_copy=True عند تعذر حذف المصدر لضمان عدم فقدانه في Undo"""
    log_file = get_transfer_log_path(base_path)
    if not log_file.exists():
        return
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        if records and isinstance(records, list):
            records[-1]["is_copy"] = True
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug("تعذر تحديث سجل النقل إلى نسخ: %s", e)


def update_transfer_record_to_move(record_id: int, base_path: Path | None = None) -> bool:
    """تحديث سجل عملية معينة في transfer_history.json من Copy إلى Move بعد موافقة المستخدم ونجاح الحذف"""
    log_file = get_transfer_log_path(base_path)
    if not log_file.exists():
        return False
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        updated = False
        if isinstance(records, list):
            for rec in records:
                if rec.get("id") == record_id:
                    rec["is_copy"] = False
                    updated = True
                    break
        if updated:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
    except Exception as e:
        logger.warning("خطأ أثناء تحديث سجل النقل إلى Move: %s", e)
    return False


def update_transfer_record_by_src_to_move(src_path: str, base_path: Path | None = None) -> bool:
    """تحديث أحدث سجل نقل للملف المصدر المحدد إلى Move بعد نجاح الحذف"""
    log_file = get_transfer_log_path(base_path)
    if not log_file.exists():
        return False
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        updated = False
        src_lower = src_path.lower()
        if isinstance(records, list):
            for rec in reversed(records):
                if str(rec.get("source", "")).lower() == src_lower:
                    rec["is_copy"] = False
                    updated = True
                    break
        if updated:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
    except Exception as e:
        logger.warning("خطأ أثناء تحديث سجل النقل بالمسار إلى Move: %s", e)
    return False


def remove_transfer_history_records_by_dest(dest_paths: list[str], base_path: Path | None = None) -> int:
    """حذف سجلات عمليات النقل من transfer_history.json بناءً على مسارات أو URIs ملفات الوجهة المحذوفة فعلياً"""
    if not dest_paths:
        return 0
    log_file = get_transfer_log_path(base_path)
    if not log_file.exists():
        return 0
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            return 0
        norm_targets = {str(p).strip().lower() for p in dest_paths if p}
        remaining = []
        removed_count = 0
        for rec in records:
            dest = str(rec.get("destination", "")).strip().lower()
            if dest in norm_targets:
                removed_count += 1
            else:
                remaining.append(rec)
        if removed_count > 0:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(remaining, f, ensure_ascii=False, indent=2)
        return removed_count
    except Exception as e:
        logger.warning("خطأ أثناء تنظيف سجلات النقل للملفات المحذوفة: %s", e)
        return 0


def get_transfer_history(
    base_path: Path | None = None
) -> list[dict[str, object]]:
    """استرجاع سجل عمليات النقل الأخيرة مرتبة من الأحدث إلى الأقدم"""
    log_file = get_transfer_log_path(base_path)
    if not log_file.exists():
        return []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                valid_items: list[dict[str, object]] = [
                    d for d in data if isinstance(d, dict)
                ]
                return list(reversed(valid_items))
            return []
    except (OSError, json.JSONDecodeError):
        return []


def undo_transfer(record_id: int, base_path: Path | None = None) -> bool:
    """
    التراجع عن عملية تصنيف/نسخ معينة:
    - يدعم كلاً من المسارات العادية و Content URIs عبر SAF.
    - يتحقق من بقاء صلاحية SAF وتوصيل بطاقة الذاكرة الخارجية.
    - لا يحذف سجل العملية إذا فشل حذف الوجهة أو فشلت استعادة الأصل.
    - يعيد False عند أي فشل دون إفساد السجل.
    """
    import storage_backend
    log_file = get_transfer_log_path(base_path)
    if not log_file.exists():
        return False

    records: list[dict[str, object]] = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, list):
                records = [d for d in loaded if isinstance(d, dict)]
    except (OSError, json.JSONDecodeError):
        return False

    found_idx = -1
    target_record: dict[str, object] | None = None
    for idx, r in enumerate(records):
        if r.get("id") == record_id:
            found_idx = idx
            target_record = r
            break

    if target_record is None:
        return False

    dest_str = str(target_record["destination"])
    src_str = str(target_record["source"])
    is_copy = bool(target_record.get("is_copy", True))
    is_saf_dest = bool(target_record.get("is_saf_dest", False)) or dest_str.startswith("content://")

    # فحص صلاحية SAF إن كانت الوجهة على بطاقة SD عبر SAF
    if is_saf_dest and dest_str.startswith("content://") and not dest_str.startswith("mock_doc://"):
        saf_tree_uri = storage_backend.get_saf_persisted_uri()
        if not storage_backend.is_saf_uri_valid(saf_tree_uri):
            logger.warning("تعذر التراجع: تم فقدان صلاحية SAF أو تم فصل بطاقة SD للوجهة %s", dest_str)
            return False

    dest_deleted = False

    if is_copy:
        # عملية نسخ: نحذف الوجهة فقط
        dest_deleted = storage_backend.delete_media_item(dest_str)
        if not dest_deleted:
            # التحقق هل الملف غير موجود أصلاً (محذوف مسبقاً)
            if not dest_str.startswith("content://"):
                dest_deleted = not Path(dest_str).exists()
            elif dest_str.startswith("mock_doc://"):
                dest_deleted = not Path(dest_str.replace("mock_doc://", "")).exists()
            else:
                dest_deleted = (storage_backend.get_uri_file_size(dest_str) == 0)

        if not dest_deleted:
            logger.warning("فشل حذف ملف الوجهة في التراجع: %s، تم الإبقاء على السجل", dest_str)
            return False
    else:
        # عملية نقل: استعادة المصدر أولاً
        if not src_str.startswith("content://"):
            src_p = Path(src_str)
            src_p.parent.mkdir(parents=True, exist_ok=True)
            if not dest_str.startswith("content://"):
                dest_p = Path(dest_str)
                if dest_p.exists():
                    try:
                        shutil.move(str(dest_p), str(src_p))
                        dest_deleted = True
                    except OSError as e:
                        logger.error("فشل استعادة ملف المصدر %s من %s: %s", src_p, dest_p, e)
                        return False
                else:
                    dest_deleted = src_p.exists()
            else:
                # الوجهة كانت SAF
                if storage_backend.copy_uri_to_path(dest_str, src_p):
                    dest_deleted = storage_backend.delete_media_item(dest_str)
                else:
                    logger.error("فشل نسخ الوجهة SAF %s إلى المصدر %s", dest_str, src_p)
                    return False
        else:
            # المصدر كان Content URI، نحذف الوجهة فقط
            dest_deleted = storage_backend.delete_media_item(dest_str)

        if not dest_deleted:
            logger.warning("فشل إتمام التراجع لعملية النقل للوجهة: %s", dest_str)
            return False

    # نجحت العملية: نحذف السجل ونحدث الكاش
    _ = records.pop(found_idx)
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError):
        pass

    db_dirs = [get_app_private_storage_dir()]
    try:
        db_dirs.append(get_internal_media_sorter_base_path())
    except Exception:
        pass
    for db_dir in db_dirs:
        try:
            cache_db = db_dir / "scanned_media_cache.db"
            if cache_db.exists():
                conn = sqlite3.connect(str(cache_db))
                cursor = conn.cursor()
                q = (
                    "DELETE FROM scanned_files "
                    "WHERE file_path = ? OR file_path = ? OR dest_path = ?"
                )
                _ = cursor.execute(q, (src_str, dest_str, dest_str))
                conn.commit()
                conn.close()
        except (sqlite3.Error, OSError):
            pass

    return True


def undo_all_transfers(base_path: Path | None = None) -> int:
    """
    التراجع عن جميع عمليات النسخ/الفرز دفعة واحدة:
    - لا يحذف كل السجل عند فشل بعض العمليات؛ يحتفظ فقط بالعمليات التي فشل التراجع عنها.
    - يحدث كاش scanned_files للملفات المسترجعة بنجاح فقط.
    - يعيد عداداً دقيقاً بالعمليات الناجحة.
    """
    import storage_backend
    log_file = get_transfer_log_path(base_path)
    if not log_file.exists():
        return 0

    records: list[dict[str, object]] = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, list):
                records = [d for d in loaded if isinstance(d, dict)]
    except (OSError, json.JSONDecodeError):
        return 0

    undone_count = 0
    remaining_records: list[dict[str, object]] = []
    cleared_keys: list[tuple[str, str]] = []

    for r in records:
        dest_str = str(r.get("destination", ""))
        src_str = str(r.get("source", ""))
        is_copy = bool(r.get("is_copy", True))
        is_saf_dest = bool(r.get("is_saf_dest", False)) or dest_str.startswith("content://")

        # فحص إذن SAF
        if is_saf_dest and dest_str.startswith("content://") and not dest_str.startswith("mock_doc://"):
            saf_tree_uri = storage_backend.get_saf_persisted_uri()
            if not storage_backend.is_saf_uri_valid(saf_tree_uri):
                remaining_records.append(r)
                continue

        success = False
        if is_copy:
            if (
                storage_backend.delete_media_item(dest_str)
                or (not dest_str.startswith("content://") and not Path(dest_str).exists())
                or (dest_str.startswith("mock_doc://") and not Path(dest_str.replace("mock_doc://", "")).exists())
            ):
                success = True
        else:
            if not src_str.startswith("content://"):
                src_p = Path(src_str)
                src_p.parent.mkdir(parents=True, exist_ok=True)
                if not dest_str.startswith("content://"):
                    dest_p = Path(dest_str)
                    if dest_p.exists():
                        try:
                            shutil.move(str(dest_p), str(src_p))
                            success = src_p.exists()
                        except OSError:
                            success = False
                    else:
                        success = src_p.exists()
                else:
                    if storage_backend.copy_uri_to_path(dest_str, src_p):
                        success = storage_backend.delete_media_item(dest_str)
            else:
                if storage_backend.delete_media_item(dest_str):
                    success = True

        if success:
            undone_count += 1
            cleared_keys.append((src_str, dest_str))
        else:
            remaining_records.append(r)

    # حفظ السجلات المتبقية التي تعذر حذفها دون تنظيف السجل كاملاً
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(remaining_records, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError) as e:
        logger.warning("تعذر حفظ السجلات المتبقية في undo_all_transfers: %s", e)

    # تنظيف الكاش فقط للعناصر التي تم التراجع عنها بنجاح
    if cleared_keys:
        db_dirs = [get_app_private_storage_dir()]
        try:
            db_dirs.append(get_internal_media_sorter_base_path())
        except Exception:
            pass
        for db_dir in db_dirs:
            try:
                cache_db = db_dir / "scanned_media_cache.db"
                if cache_db.exists():
                    conn = sqlite3.connect(str(cache_db))
                    cursor = conn.cursor()
                    for s_k, d_k in cleared_keys:
                        cursor.execute(
                            "DELETE FROM scanned_files WHERE file_path = ? OR file_path = ? OR dest_path = ?",
                            (s_k, d_k, d_k),
                        )
                    conn.commit()
                    conn.close()
            except (sqlite3.Error, OSError):
                pass

    return undone_count


def copy_to_category(
    src_path: str | Path | Any = None,
    category_name: str = "",
    target_location: Any | None = None,
    base_path: Path | None = None,
    is_copy: bool = True,
    *,
    src_item: str | Path | Any = None,
) -> Path | str:
    """
    نسخ الملف بأمان إلى مجلد التصنيف المحدد مع دعم كامل لـ:
    1. Path source -> Path destination (الذاكرة الداخلية)
    2. Content URI source -> Path destination (الذاكرة الداخلية من MediaStore)
    3. Path source -> SAF Tree URI destination (بطاقة SD عبر DocumentFile/DocumentsContract)
    4. Content URI source -> SAF Tree URI destination (بطاقة SD من MediaStore)
    مع التحقق الصارم من الحجم بالبايت ومنع الـ fallback الصامت.
    """
    import storage_backend

    actual_item = src_path if src_path is not None else src_item
    if actual_item is None:
        raise ValueError("يجب تحديد الملف المصدر المراد نسخه (src_path)")

    # 1. تحديد الوجهة الفعلية TargetLocation
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

    if not target_location.is_valid:
        raise OSError(f"وجهة التخزين المحددة غير صالحة: {target_location.error_message}")

    clean_cat = storage_backend.normalize_category_name(category_name)

    # 2. تحليل المصدر (Path أو MediaItem أو Content URI)
    resolved_src_path: Path | None = None
    src_uri: str = ""
    filename: str = ""
    src_size: int = 0
    src_mime: str = ""
    is_uri_source: bool = False

    if isinstance(actual_item, storage_backend.MediaItem):
        filename = actual_item.name
        src_size = actual_item.size_bytes
        src_mime = getattr(actual_item, "mime_type", "")
        # فحص إمكانية القراءة المباشرة أولاً لتجنب حظر Scoped Storage
        if actual_item.path and storage_backend.is_path_readable(actual_item.path):
            resolved_src_path = Path(actual_item.path)
            is_uri_source = False
        elif actual_item.uri:
            src_uri = actual_item.uri
            is_uri_source = True
        elif actual_item.path and os.path.exists(actual_item.path):
            resolved_src_path = Path(actual_item.path)
            is_uri_source = False
        else:
            raise FileNotFoundError(f"العنصر غير متاح: {actual_item}")
    elif isinstance(actual_item, str) and actual_item.startswith("content://"):
        src_uri = actual_item
        is_uri_source = True
        details = storage_backend.query_content_uri_details(src_uri)
        filename = details.get("display_name") or f"media_{int(time.time() * 1000)}{details.get('extension', '.mp4' if 'video' in src_uri.lower() else '.jpg')}"
        src_size = details.get("size_bytes") or storage_backend.get_uri_file_size(src_uri)
        src_mime = details.get("mime_type", "")
    else:
        resolved_src_path = Path(actual_item).resolve()
        if not resolved_src_path.exists() or not resolved_src_path.is_file():
            raise FileNotFoundError(f"الملف المصدر غير موجود: {resolved_src_path}")
        filename = resolved_src_path.name
        src_size = resolved_src_path.stat().st_size
        if not storage_backend.is_path_readable(resolved_src_path):
            matched_uri = storage_backend.find_content_uri_for_path(str(resolved_src_path))
            if matched_uri:
                src_uri = matched_uri
                is_uri_source = True
            else:
                is_uri_source = False
        else:
            is_uri_source = False
        src_mime = storage_backend.resolve_media_mime_type(filename)

    # تنظيف اسم المجلد الفرعي
    clean_parts = [
        sanitize_folder_name(p)
        for p in clean_cat.replace("\\", "/").split("/")
        if p.strip()
    ]
    rel_category_str = "/".join(clean_parts) if clean_parts else "خارج التصنيف"

    # =========================================================================
    # الحالة الأولى: الوجهة بطاقة SD عبر Storage Access Framework (SAF Tree URI)
    # =========================================================================
    if target_location.is_saf:
        tree_uri = target_location.tree_uri
        if not tree_uri:
            raise OSError("تم اختيار بطاقة الذاكرة الخارجية لكن لم يتم تحديد URI الصالح عبر SAF")

        if is_uri_source:
            dest_uri = storage_backend.copy_uri_to_saf_uri(
                src_uri,
                tree_uri,
                category=rel_category_str,
                filename=filename,
                expected_size=src_size,
                mime_type=src_mime,
            )
        else:
            assert resolved_src_path is not None
            dest_uri = storage_backend.copy_path_to_saf_uri(
                resolved_src_path,
                tree_uri,
                category=rel_category_str,
                filename=filename,
                mime_type=src_mime,
            )

        if not dest_uri:
            raise OSError(f"فشل إتمام نسخ الملف إلى بطاقة SD عبر SAF: {filename}")

        # توثيق العملية في app-private storage (أو base_path إن مرر صراحة)
        _log_transfer_record(
            src_path=str(src_uri if is_uri_source else resolved_src_path),
            dest_path=dest_uri,
            category=clean_cat,
            file_size=src_size,
            base_path=base_path,
            is_copy=is_copy,
            is_saf_dest=True,
        )
        return dest_uri

    # =========================================================================
    # الحالة الثانية: الوجهة مسار محلي فيزيائي (الذاكرة الداخلية أو قرص مباشر)
    # =========================================================================
    target_base = target_location.path or get_media_sorter_base_path()
    target_folder = target_base
    for part in clean_parts:
        target_folder = target_folder / part
    target_folder.mkdir(parents=True, exist_ok=True)

    stem = Path(filename).stem
    suffix = Path(filename).suffix

    # حل تعارض الأسماء
    primary_dest = target_folder / f"{stem}{suffix}"
    if primary_dest.exists() and primary_dest.stat().st_size == src_size:
        _log_transfer_record(
            src_path=str(src_uri if is_uri_source else resolved_src_path),
            dest_path=str(primary_dest),
            category=clean_cat,
            file_size=src_size,
            base_path=base_path,
            is_copy=is_copy,
            is_saf_dest=False,
        )
        return primary_dest

    dest = primary_dest
    counter = 1
    while dest.exists():
        if dest.stat().st_size == src_size:
            _log_transfer_record(
                src_path=str(src_uri if is_uri_source else resolved_src_path),
                dest_path=str(dest),
                category=clean_cat,
                file_size=src_size,
                base_path=base_path,
                is_copy=is_copy,
                is_saf_dest=False,
            )
            return dest
        dest = target_folder / f"{stem}_{counter:02d}{suffix}"
        counter += 1

    # تنفيذ النسخ بالدفق
    if is_uri_source:
        success = storage_backend.copy_uri_to_path(src_uri, dest)
    else:
        assert resolved_src_path is not None
        success = storage_backend.copy_path_to_path(resolved_src_path, dest)

    if not success or not dest.exists():
        raise OSError(f"فشل التحقق: تعذر إتمام نسخ الملف إلى الوجهة: {dest}")

    dest_size = dest.stat().st_size
    if src_size > 0 and dest_size != src_size:
        dest.unlink(missing_ok=True)
        raise OSError(f"عدم تطابق الحجم بعد النسخ: المصدر {src_size} بايت، الوجهة {dest_size} بايت")

    # توثيق العملية في app-private storage (أو base_path إن مرر صراحة)
    _log_transfer_record(
        src_path=str(src_uri if is_uri_source else resolved_src_path),
        dest_path=str(dest),
        category=clean_cat,
        file_size=src_size or dest_size,
        base_path=base_path,
        is_copy=is_copy,
        is_saf_dest=False,
    )

    return dest


def move_to_category(
    src_path: str | Path | Any = None,
    category_name: str = "",
    target_location: Any | None = None,
    base_path: Path | None = None,
    copy_only: bool = True,
    *,
    src_item: str | Path | Any = None,
) -> Path | str:
    """
    نقل أو نسخ الملف إلى مجلد التصنيف المحدد مع ضمان:
    - نسخ الملف أولاً والتحقق التام من وجوده وتطابق حجمه.
    - عدم حذف الأصل في وضع النقل Move إلا بعد ثبوت نجاح الوجهة بالبايت.
    - في حال فشل حذف المصدر (مثل RecoverableSecurityException في أندرويد)،
      تسجيل العملية كـ Copy لحماية المصدر من الفقدان.
    """
    import storage_backend

    actual_item = src_path if src_path is not None else src_item
    if actual_item is None:
        raise ValueError("يجب تحديد الملف المصدر المراد نقله (src_path)")

    if copy_only:
        return copy_to_category(
            actual_item,
            category_name,
            target_location=target_location,
            base_path=base_path,
            is_copy=True,
        )

    # 1. تنفيذ النسخ أولاً والتحقق الكامل من الوجهة
    dest = copy_to_category(
        actual_item,
        category_name,
        target_location=target_location,
        base_path=base_path,
        is_copy=False,
    )

    # التحقق من سلامة الوجهة
    if isinstance(dest, Path):
        if not dest.exists():
            raise OSError(f"فشل التحقق من الوجهة قبل حذف الأصل: {dest}")
    elif isinstance(dest, str):
        if not dest.startswith("content://") and not dest.startswith("mock_doc://"):
            if not Path(dest).exists():
                raise OSError(f"فشل التحقق من الوجهة قبل حذف الأصل: {dest}")

    # 2. محاولة حذف المصدر بأمان
    deleted = storage_backend.delete_media_item(actual_item)
    if not deleted:
        logger.warning(
            "تعذر حذف الملف المصدر (%s) بعد نسخه بنجاح، تم اعتباره نسخاً آمناً حفاظاً على الملف",
            actual_item,
        )
        _update_last_transfer_record_to_copy(base_path)

    return dest

