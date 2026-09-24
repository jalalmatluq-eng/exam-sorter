"""
وحدة إدارة الملفات والمجلدات لتطبيق مصنّف صور الاختبارات (Exam Sorter).
المسؤوليات:
1. تحديد مسار التخزين المناسب (على الهاتف أندرويد أو الحاسوب).
2. تنظيف أسماء المواد من الرموز الممنوعة وإنشاء المجلدات.
3. حفظ الصور وتسميتها بنظام موحد (اسم المادة + التاريخ + رقم تسلسلي).
4. استرجاع قائمة المواد وعدد الصور الموجودة في كل مادة.
5. استرجاع صور مادة معينة لعرضها في المعرض.
"""

import json
import os
import sys
from pathlib import Path
import re
import shutil
from datetime import datetime
from typing import Any


def get_base_storage_path() -> Path:
    """
    تحديد المسار الأساسي لحفظ ملفات الاختبارات.
    
    المنطق:
    - على أجهزة Android: يُفضل استخدام مجلد الصور أو المستندات عبر plyer إن توفرت الصلاحيات،
      أو المجلد الداخلي للتطبيق لضمان الأمان وعدم فقدان البيانات.
    - على الحاسوب (Desktop / بيئة التطوير): ينشئ مجلد 'ExamSorter' داخل مسار المشروع الحالي
      أو في مسار مجلد المستخدم لسهولة المعاينة والتجربة.
    """
    try:
        # فحص إذا كان التطبيق يعمل داخل بيئة أندرويد
        from kivy.utils import platform
        if platform == "android":
            try:
                from plyer import storagepath
                # استخدام مجلد الصور المخصص
                pictures_dir = storagepath.get_pictures_dir()
                if pictures_dir and os.path.exists(pictures_dir):
                    base = Path(pictures_dir) / "ExamSorter"
                    base.mkdir(parents=True, exist_ok=True)
                    return base
            except Exception:
                pass
            
            # بديل آمن على أندرويد: مسار مجلد التطبيق الداخلي
            from kivy.app import App
            running_app = App.get_running_app()
            if running_app and hasattr(running_app, "user_data_dir"):
                base = Path(running_app.user_data_dir) / "ExamSorter"
                base.mkdir(parents=True, exist_ok=True)
                return base
    except ImportError:
        pass

    # على أنظمة سطح المكتب (Windows / Linux / macOS)
    # ننشئ مجلد ExamSorter محلياً في مجلد المشروع لسهولة الاختبار
    current_dir = Path(__file__).resolve().parent
    base = current_dir / "ExamSorter"
    base.mkdir(parents=True, exist_ok=True)
    return base


WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}


def sanitize_folder_name(name: str) -> str:
    r"""
    تنظيف اسم المادة من أي رموز غير مسموحة في أنظمة الملفات.
    
    يزيل الرموز: \ / : * ? " < > | والأسماء المحجوزة في ويندوز والنقاط الختامية.
    إذا كان الاسم فارغاً بعد التنظيف، يُعاد اسم افتراضي 'مادة_غير_محددة'.
    """
    if not name or not isinstance(name, str):
        return "مادة_غير_محددة"
    
    # استبدال الرموز غير المسموحة بمسافة لحفظ التباعد بين الكلمات
    clean_name = re.sub(r'[\\/*?:"<>|\r\n\t]', " ", name)
    # استبدال المسافات المتعددة بمسافة واحدة وحذف المسافات الطرفية والنقاط في النهاية
    clean_name = re.sub(r'\s+', " ", clean_name).strip().rstrip(". ")
    
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


def save_image_to_subject(image_path: str, subject_name: str, base_path: Path | None = None) -> str:
    """
    نسخ الصورة إلى مجلد المادة المناسب بتسمية منظمة وفريدة.
    
    صيغة الاسم الجديد:
        [اسم_المادة]_[YYYY-MM-DD]_[الرقم_التسلسلي].[الامتداد]
        مثال: رياضيات_2026-09-24_01.jpg
        
    المعاملات:
        image_path: مسار الصورة الأصلية (المصدر).
        subject_name: اسم المادة الدراسية.
        base_path: اختياري، إذا لم يُمرر سيتم استخدام get_base_storage_path().
        
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

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # حساب الرقم التسلسلي اليومي للملف داخل المجلد
    index = 1
    while True:
        candidate_filename = f"{clean_name}_{today_str}_{index:02d}{ext}"
        candidate_path = subject_folder / candidate_filename
        if not candidate_path.exists():
            break
        index += 1

    # نسخ الملف إلى الوجهة النهائية
    shutil.copy2(image_path, candidate_path)

    # تنظيف الملف المؤقت إذا كان مصدره من مجلد temp الخاص بالتطبيق حصراً
    try:
        src_path = Path(image_path).resolve()
        app_temp_dir = get_temp_dir().resolve()
        if src_path.parent == app_temp_dir:
            src_path.unlink(missing_ok=True)
    except Exception:
        pass

    return str(candidate_path)


def get_temp_dir() -> Path:
    """
    تحديد مجلد الملفات المؤقتة الموحد للتطبيق سواء على الحاسوب أو أندرويد.
    """
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app and hasattr(app, "user_data_dir") and app.user_data_dir:
            t = Path(app.user_data_dir) / "temp"
            t.mkdir(parents=True, exist_ok=True)
            return t
    except Exception:
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
                except Exception:
                    pass
    return cleaned_count


def list_subjects(base_path: Path | None = None) -> list[dict[str, Any]]:
    """
    إرجاع قائمة بجميع المواد والأقسام المخزنة وعدد الملفات (صور وفيديوهات) في كل مجلد.
    
    المعاملات:
        base_path: المسار الأساسي (اختياري، يدمج ExamSorter و MediaSorter تلقائياً إذا لم يُمرر).
        
    العائد:
        قائمة قواميس مرتبة تنازلياً بحسب عدد الملفات:
        [
            {
                'name': 'رياضيات',
                'folder_path': '...',
                'count': 5,
                'latest_modified': 1727138000.0
            },
            ...
        ]
    """
    valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm"}
    roots = []
    if base_path is not None:
        roots.append(Path(base_path))
    else:
        roots.append(get_base_storage_path())
        media_root = get_media_sorter_base_path()
        if media_root.resolve() != get_base_storage_path().resolve():
            roots.append(media_root)

    subjects_dict: dict[str, dict[str, Any]] = {}

    for root in roots:
        if not root.exists():
            continue
        for item in root.iterdir():
            if item.is_dir():
                media_files = [
                    f for f in item.iterdir()
                    if f.is_file() and f.suffix.lower() in valid_extensions
                ]
                count = len(media_files)
                latest_mod = item.stat().st_mtime
                if media_files:
                    latest_mod = max(f.stat().st_mtime for f in media_files)

                name = item.name
                if name in subjects_dict:
                    subjects_dict[name]["count"] += count
                    subjects_dict[name]["latest_modified"] = max(subjects_dict[name]["latest_modified"], latest_mod)
                else:
                    subjects_dict[name] = {
                        "name": name,
                        "folder_path": str(item),
                        "count": count,
                        "latest_modified": latest_mod,
                    }

    subjects = list(subjects_dict.values())
    # ترتيب الأقسام: الأقسام التي بها ملفات أولاً ثم الأبجدي
    subjects.sort(key=lambda s: (-s["count"], s["name"]))
    return subjects


def get_subject_images(subject_name: str, base_path: Path | None = None) -> list[str]:
    """
    استرجاع قائمة مسارات الصور لمادة معينة لعرضها في شبكة الصور.
    
    المعاملات:
        subject_name: اسم المادة.
        base_path: المسار الأساسي.
        
    العائد:
        قائمة بمسارات الصور مرتبة من الأحدث إلى الأقدم.
    """
    clean_name = sanitize_folder_name(subject_name)
    candidates: list[Path] = []
    if base_path is not None:
        candidates.append(Path(base_path) / clean_name)
    else:
        candidates.append(get_base_storage_path() / clean_name)
        candidates.append(get_media_sorter_base_path() / clean_name)

    valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm"}
    images: list[str] = []

    for subject_folder in candidates:
        if subject_folder.exists() and subject_folder.is_dir():
            for img in subject_folder.iterdir():
                if img.is_file() and img.suffix.lower() in valid_extensions:
                    images.append(str(img))

    # فرز الوسائط حسب تاريخ التعديل (الأحدث أولاً)
    images.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return images


def delete_image_file(image_path: str) -> bool:
    """
    حذف صورة معينة بأمان من مجلد المادة.
    """
    try:
        p = Path(image_path)
        if p.exists() and p.is_file():
            p.unlink()
            return True
    except Exception as e:
        print("خطأ أثناء حذف الصورة:", e)
    return False


def delete_subject_folder(subject_name: str, base_path: Path | None = None) -> bool:
    """
    حذف مجلد مادة بالكامل وجميع الصور بداخله.
    """
    if base_path is None:
        base_path = get_base_storage_path()

    clean_name = sanitize_folder_name(subject_name)
    subject_folder = Path(base_path) / clean_name

    try:
        if subject_folder.exists() and subject_folder.is_dir():
            shutil.rmtree(subject_folder)
            return True
    except Exception as e:
        print("خطأ أثناء حذف مجلد المادة:", e)
    return False


def clean_empty_subject_folders(base_path: Path | None = None) -> int:
    """
    فحص مجلد التخزين وحذف أي مجلدات مواد فارغة لا تحتوي على صور أو فيديوهات.
    """
    valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm"}
    roots = []
    if base_path is not None:
        roots.append(Path(base_path))
    else:
        roots.append(get_base_storage_path())
        media_root = get_media_sorter_base_path()
        if media_root.resolve() != get_base_storage_path().resolve():
            roots.append(media_root)

    deleted_count = 0
    for root in roots:
        if not root.exists():
            continue
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
                    except Exception:
                        pass

    return deleted_count


def open_folder_native(folder_path: str) -> bool:
    """
    فتح المجلد في مستعرض الملفات الأصلي لنظام التشغيل (Windows Explorer / Finder / Linux).
    على أندرويد يتم التحقق وإرجاع False مع توفير المسار للواجهة لإظهار تنبيه.
    """
    try:
        from kivy.utils import platform
        if platform == "android":
            return False

        p = Path(folder_path).resolve()
        if not p.exists():
            p = get_base_storage_path()
        if os.name == 'nt':
            os.startfile(str(p))
            return True
        elif sys.platform == 'darwin':
            import subprocess
            subprocess.Popen(['open', str(p)])
            return True
        else:
            import subprocess
            subprocess.Popen(['xdg-open', str(p)])
            return True
    except Exception as e:
        print("تعذر فتح المجلد في المستكشف:", e)
        return False


# =========================================================================
# وظائف منظّم الوسائط الشامل (Media Sorter Expansion)
# =========================================================================

def get_media_sorter_base_path() -> Path:
    """تحديد المسار الأساسي الموحد لجميع مجلدات مُنظّم الوسائط (MediaSorter)"""
    try:
        from kivy.utils import platform
        if platform == "android":
            return Path("/storage/emulated/0/MediaSorter")
    except Exception:
        pass

    # على الحاسوب: مجلد MediaSorter في مسار المشروع
    base = Path(__file__).resolve().parent / "MediaSorter"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_transfer_log_path() -> Path:
    """مسار ملف سجل عمليات النقل للتراجع والمراجعة"""
    base = get_media_sorter_base_path()
    return base / "transfer_history.json"


def _log_transfer_record(src_path: str, dest_path: str, category: str, file_size: int) -> None:
    """تسجيل عملية نقل في سجل المعاملات JSON"""
    log_file = get_transfer_log_path()
    records: list[dict[str, Any]] = []
    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            records = []

    records.append({
        "id": int(datetime.now().timestamp() * 1000),
        "source": src_path,
        "destination": dest_path,
        "category": category,
        "size_bytes": file_size,
        "timestamp": datetime.now().isoformat(),
    })

    # الاحتفاظ بآخر 1000 عملية نقل
    records = records[-1000:]
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("تعذر تحديث سجل النقل:", e)


def get_transfer_history() -> list[dict[str, Any]]:
    """استرجاع سجل عمليات النقل الأخيرة مرتبة من الأحدث إلى الأقدم"""
    log_file = get_transfer_log_path()
    if not log_file.exists():
        return []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return list(reversed(data))
    except Exception:
        return []


def undo_transfer(record_id: int) -> bool:
    """التراجع عن عملية نقل معينة وإعادة الملف إلى مكانه الأصلي"""
    log_file = get_transfer_log_path()
    if not log_file.exists():
        return False

    records: list[dict[str, Any]] = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            records = json.load(f)
    except Exception:
        return False

    found_idx = -1
    target_record = None
    for idx, r in enumerate(records):
        if r.get("id") == record_id:
            found_idx = idx
            target_record = r
            break

    if target_record is None:
        return False

    dest = Path(target_record["destination"])
    src = Path(target_record["source"])

    if not dest.exists():
        return False

    # إعادة الملف إلى مجلده الأصلي
    src.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(dest), str(src))

    # حذف السجل بعد التراجع عنه بنجاح
    records.pop(found_idx)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    return True


def move_to_category(src_path: str | Path, category_name: str, base_path: Path | None = None) -> Path:
    """
    نقل الملف فعلياً (Move) إلى مجلد التصنيف المحدد مع أعلى معايير الأمان:
    1. إنشاء مجلد التصنيف إن لم يكن موجوداً.
    2. حل أي تعارض في الأسماء تلقائياً عبر إضافة ترقيم تسلسلي.
    3. التحقق الحاسم: التأكد من نسخ الملف بالكامل وتطابق الحجم بالبايت قبل حذف الأصل.
    4. توثيق العملية في سجل transfer_history.json لتمكين التراجع.
    """
    src = Path(src_path).resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"الملف المصدر غير موجود: {src}")

    if base_path is None:
        base_path = get_media_sorter_base_path()

    clean_cat = sanitize_folder_name(category_name)
    target_folder = base_path / clean_cat
    target_folder.mkdir(parents=True, exist_ok=True)

    stem = src.stem
    suffix = src.suffix

    # حل تعارض الأسماء
    dest = target_folder / f"{stem}{suffix}"
    counter = 1
    while dest.exists():
        dest = target_folder / f"{stem}_{counter:02d}{suffix}"
        counter += 1

    src_size = src.stat().st_size

    # خطوة النقل الآمن: نسخ مطابق للأصل أولاً
    shutil.copy2(src, dest)

    # فحص السلامة الصارم قبل أي حذف
    if not dest.exists():
        raise IOError(f"فشل التحقق: الملف الوجهة غير موجود بعد النقل: {dest}")

    dest_size = dest.stat().st_size
    if dest_size != src_size:
        # خلل في اكتمال النقل - نحذف الملف الناقص ونحافظ على الأصل دون مساس
        dest.unlink(missing_ok=True)
        raise IOError(f"فشل التحقق: عدم تطابق الحجم (المصدر: {src_size} بايت، الوجهة: {dest_size} بايت). لم يتم حذف الأصل.")

    # تم التحقق بنجاح 100%: حذف الملف المصدر
    src.unlink()

    # توثيق العملية في السجل
    _log_transfer_record(str(src), str(dest), category_name, src_size)

    return dest


