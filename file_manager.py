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
import logging
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("FileManager")


def get_base_storage_path() -> Path:
    """تحديد المسار الأساسي لحفظ ملفات الاختبارات المنظمة"""
    base = get_media_sorter_base_path() / "صور الاختبارات"
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


def list_subjects(base_path: Path | None = None) -> list[dict[str, object]]:
    """
    إرجاع قائمة بجميع المواد والأقسام المخزنة وعدد الملفات في كل مجلد.
    مرتبة تنازلياً بحسب عدد الملفات ثم أبجدياً.
    """
    valid_extensions = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif",
        ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm", ".m4v", ".flv"
    }
    roots: list[Path] = []
    if base_path is not None:
        roots.append(Path(base_path))
    else:
        media_root = get_media_sorter_base_path()
        roots.append(media_root)
        exam_root = media_root / "صور الاختبارات"
        if exam_root.exists() and exam_root not in roots:
            roots.append(exam_root)

    subjects_dict: dict[str, dict[str, object]] = {}

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
                sub_exam_count = 0
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
                        old_c = int(
                            str(subjects_dict[sub_name]["count"])
                        )
                        subjects_dict[sub_name]["count"] = (
                            old_c + s_count
                        )
                        old_m = float(
                            str(
                                subjects_dict[sub_name][
                                    "latest_modified"
                                ]
                            )
                        )
                        subjects_dict[sub_name][
                            "latest_modified"
                        ] = max(old_m, float(s_mod))

                    count += sub_exam_count

                name = item.name
                if name in subjects_dict:
                    cur_c = int(str(subjects_dict[name]["count"]))
                    subjects_dict[name]["count"] = cur_c + count
                    cur_m = float(
                        str(subjects_dict[name]["latest_modified"])
                    )
                    subjects_dict[name]["latest_modified"] = max(
                        cur_m, float(latest_mod)
                    )
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


def get_subject_images(
    subject_name: str, base_path: Path | None = None
) -> list[str]:
    """استرجاع قائمة مسارات الصور لمادة معينة مرتبة من الأحدث إلى الأقدم"""
    clean_name = sanitize_folder_name(subject_name)
    candidates: list[Path] = []
    if base_path is not None:
        candidates.append(Path(base_path) / clean_name)
        candidates.append(Path(base_path) / "صور الاختبارات" / clean_name)
    else:
        candidates.append(get_base_storage_path() / clean_name)
        media_root = get_media_sorter_base_path()
        candidates.append(media_root / clean_name)
        candidates.append(media_root / "صور الاختبارات" / clean_name)
        candidates.append(media_root / "صور اختبارات" / clean_name)

    valid_extensions = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif",
        ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm", ".m4v", ".flv"
    }
    images: list[str] = []

    for subject_folder in candidates:
        if subject_folder.exists() and subject_folder.is_dir():
            if clean_name in ("صور الاختبارات", "صور اختبارات"):
                for root, _, files in os.walk(str(subject_folder)):
                    for f in files:
                        if Path(f).suffix.lower() in valid_extensions:
                            full_img = Path(root) / f
                            if str(full_img) not in images:
                                images.append(str(full_img))
            else:
                for img in subject_folder.iterdir():
                    is_valid = (
                        img.is_file()
                        and img.suffix.lower() in valid_extensions
                        and str(img) not in images
                    )
                    if is_valid:
                        images.append(str(img))

    images.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return images


def delete_image_file(image_path: str) -> bool:
    """حذف صورة معينة بأمان من مجلد المادة."""
    try:
        p = Path(image_path)
        if p.exists() and p.is_file():
            p.unlink()
            return True
    except OSError as e:
        print("خطأ أثناء حذف الصورة:", e)
    return False


def delete_subject_folder(
    subject_name: str, base_path: Path | None = None
) -> bool:
    """حذف مجلد مادة بالكامل وجميع الصور بداخله."""
    if base_path is None:
        base_path = get_base_storage_path()

    clean_name = sanitize_folder_name(subject_name)
    subject_folder = Path(base_path) / clean_name

    try:
        if subject_folder.exists() and subject_folder.is_dir():
            shutil.rmtree(subject_folder)
            return True
    except OSError as e:
        print("خطأ أثناء حذف مجلد المادة:", e)
    return False


def clean_empty_subject_folders(base_path: Path | None = None) -> int:
    """فحص مجلد التخزين وحذف أي مجلدات مواد فارغة."""
    valid_extensions = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif",
        ".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm", ".m4v", ".flv"
    }
    roots: list[Path] = []
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
                    except OSError:
                        pass

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
        data = {"file": str(file_path), "started_at": time.time()}
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
            poisons = list(prefs.get("poison_files", []))
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
        return set(str(x) for x in prefs.get("poison_files", []))
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
    """
    التحقق الفعلي من إمكانية إنشاء وكتابة وحذف الملفات داخل المجلد المحدد.
    هام: لا نختبر في جذر بطاقة SD مباشرة لأن نظام أندرويد يحظر إنشاء ملفات نقطية في الجذر.
    """
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        test_file = dir_path / f".write_test_{int(time.time() * 1000)}"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return True
    except (PermissionError, OSError) as e:
        logger.debug("المجلد غير قابل للكتابة %s: %s", dir_path, e)
        return False


def find_external_sdcard_root() -> Path | None:
    """
    اكتشاف مسار بطاقة الذاكرة الخارجية MicroSD بطرق Android الرسمية:
    1. StorageManager.getStorageVolumes() عبر Pyjnius.
    2. Context.getExternalFilesDirs(None) عبر Pyjnius.
    3. فحص مجلد /storage عن أي معرف بطاقة غير emulated.
    4. استرجاع المسار المحفوظ مسبقاً إذا كان متاحاً.
    مع التأكد من إمكانية الكتابة داخل [مسار البطاقة]/الملفات المنظمة/ بدلاً من فحص جذر البطاقة.
    """
    try:
        from kivy.utils import platform
        if platform == "android":
            candidate_roots: list[Path] = []

            # 1. الطريقة الأولى: StorageManager / StorageVolume
            try:
                from android import mActivity
                from jnius import autoclass
                Context = autoclass("android.content.Context")
                storage_manager = mActivity.getSystemService(Context.STORAGE_SERVICE)
                if storage_manager is not None:
                    volumes = storage_manager.getStorageVolumes()
                    if volumes is not None:
                        for i in range(volumes.size()):
                            vol = volumes.get(i)
                            if vol is not None and vol.isRemovable():
                                uuid = vol.getUuid()
                                if uuid:
                                    p = Path(f"/storage/{uuid}")
                                    if p not in candidate_roots:
                                        candidate_roots.append(p)
                                try:
                                    dir_file = vol.getDirectory()
                                    if dir_file is not None:
                                        dir_path = Path(dir_file.getAbsolutePath())
                                        if dir_path not in candidate_roots:
                                            candidate_roots.append(dir_path)
                                except Exception:
                                    pass
            except Exception as e:
                logger.debug("StorageManager check: %s", e)

            # 2. الطريقة الثانية: getExternalFilesDirs(None)
            try:
                from android import mActivity
                ext_dirs = mActivity.getExternalFilesDirs(None)
                if ext_dirs:
                    for ed in ext_dirs:
                        if ed is not None:
                            p_str = ed.getAbsolutePath()
                            if "/Android/data" in p_str and not p_str.startswith("/storage/emulated/"):
                                root_part = p_str.split("/Android/data")[0]
                                p = Path(root_part)
                                if p not in candidate_roots:
                                    candidate_roots.append(p)
            except Exception as e:
                logger.debug("getExternalFilesDirs check: %s", e)

            # 3. الطريقة الثالثة: فحص محتويات /storage المباشرة
            storage_dir = Path("/storage")
            if storage_dir.exists() and storage_dir.is_dir():
                try:
                    for item in storage_dir.iterdir():
                        is_sys = item.name in ("emulated", "self", "knox", "sdcard0")
                        if item.is_dir() and not is_sys:
                            if item not in candidate_roots:
                                candidate_roots.append(item)
                except Exception:
                    pass

            # 4. الطريقة الرابعة: التحقق من المسار المحفوظ في التفضيلات
            try:
                saved_sd = str(get_sorter_preferences().get("detected_sdcard_path", "")).strip()
                if saved_sd:
                    p = Path(saved_sd)
                    if p not in candidate_roots:
                        candidate_roots.append(p)
            except Exception:
                pass

            # فحص كل مسار مرشح: التحقق من وجوده وإمكانية إنشاء مجلد الملفات المنظمة داخله
            for root_candidate in candidate_roots:
                if not root_candidate.exists() or not root_candidate.is_dir():
                    continue
                # لا نختبر في جذر البطاقة مباشرة! نختبر مجلد [root]/الملفات المنظمة/
                target_folder = root_candidate / ORGANIZED_FOLDER_NAME
                writable = is_directory_writable(target_folder)
                if writable:
                    try:
                        save_sorter_preferences({"detected_sdcard_path": str(root_candidate)})
                    except Exception:
                        pass
                    return root_candidate
                elif root_candidate.exists():
                    try:
                        save_sorter_preferences({"detected_sdcard_path": str(root_candidate)})
                    except Exception:
                        pass
                    return root_candidate

    except (ImportError, OSError, RuntimeError) as e:
        logger.debug("find_external_sdcard_root error: %s", e)

    return None


def get_available_storage_destinations() -> dict[str, dict[str, object]]:
    """
    استكشاف مسارات التخزين المتاحة على الجهاز (الداخلية والخارجية)
    مع إحصائيات المساحة المتوفرة في كل منهما لتسهيل الاختيار على المستخدم.
    """
    destinations: dict[str, dict[str, object]] = {}
    try:
        from kivy.utils import platform
        if platform == "android":
            # 1. الذاكرة الداخلية
            internal_root = Path("/storage/emulated/0")
            internal_target = internal_root / ORGANIZED_FOLDER_NAME
            int_free_gb, int_total_gb = 0.0, 0.0
            try:
                du = shutil.disk_usage(str(internal_root))
                int_free_gb = round(du.free / (1024 ** 3), 1)
                int_total_gb = round(du.total / (1024 ** 3), 1)
            except OSError:
                pass

            destinations["internal"] = {
                "id": "internal",
                "name": "الذاكرة الداخلية المشتركة",
                "path": str(internal_target),
                "available": True,
                "is_writable": is_directory_writable(internal_target),
                "free_gb": int_free_gb,
                "total_gb": int_total_gb,
                "description": (
                    f"المسار: /storage/emulated/0/{ORGANIZED_FOLDER_NAME} "
                    f"({int_free_gb} GB متاح)"
                ),
            }

            # 2. بطاقة الذاكرة الخارجية (MicroSD Card)
            sd_root = find_external_sdcard_root()
            if sd_root and sd_root.exists():
                sd_target = sd_root / ORGANIZED_FOLDER_NAME
                sd_free_gb, sd_total_gb = 0.0, 0.0
                try:
                    du = shutil.disk_usage(str(sd_root))
                    sd_free_gb = round(du.free / (1024 ** 3), 1)
                    sd_total_gb = round(du.total / (1024 ** 3), 1)
                except OSError:
                    pass

                is_writable = is_directory_writable(sd_target)
                destinations["sdcard"] = {
                    "id": "sdcard",
                    "name": "بطاقة الذاكرة الخارجية (MicroSD)",
                    "path": str(sd_target),
                    "available": True,
                    "is_writable": is_writable,
                    "free_gb": sd_free_gb,
                    "total_gb": sd_total_gb,
                    "description": (
                        f"المسار: {sd_target} ({sd_free_gb} GB متاح)"
                    ),
                }
            else:
                destinations["sdcard"] = {
                    "id": "sdcard",
                    "name": "بطاقة الذاكرة الخارجية (MicroSD)",
                    "path": "غير متوفرة حالياً",
                    "available": False,
                    "is_writable": False,
                    "free_gb": 0.0,
                    "total_gb": 0.0,
                    "description": (
                        "لم يتم العثور على كرت MicroSD مركب في الجهاز"
                    ),
                }
            return destinations
    except (ImportError, OSError, RuntimeError):
        pass

    # على بيئة سطح المكتب للتطوير
    project_base = Path(__file__).resolve().parent / ORGANIZED_FOLDER_NAME
    project_base.mkdir(parents=True, exist_ok=True)
    free_gb, total_gb = 0.0, 0.0
    try:
        du = shutil.disk_usage(str(project_base))
        free_gb = round(du.free / (1024 ** 3), 1)
        total_gb = round(du.total / (1024 ** 3), 1)
    except OSError:
        pass

    destinations["internal"] = {
        "id": "internal",
        "name": "القرص الأساسي (المشروع)",
        "path": str(project_base),
        "available": True,
        "free_gb": free_gb,
        "total_gb": total_gb,
        "description": f"المسار: {project_base} ({free_gb} GB متاح)",
    }
    destinations["sdcard"] = {
        "id": "sdcard",
        "name": "بطاقة الذاكرة الخارجية",
        "path": "غير متوفرة في بيئة المحاكاة",
        "available": False,
        "free_gb": 0.0,
        "total_gb": 0.0,
        "description": "غير متوفرة في بيئة المحاكاة/سطح المكتب",
    }
    return destinations


def get_media_sorter_base_path() -> Path:
    """تحديد المسار الأساسي الموحد لمجلدات مُنظّم الوسائط"""
    prefs = get_sorter_preferences()
    target_pref = prefs.get("target_storage", "internal")

    try:
        from kivy.utils import platform
        if platform == "android":
            if target_pref == "sdcard":
                sd_root = find_external_sdcard_root()
                if sd_root:
                    sd_target = sd_root / ORGANIZED_FOLDER_NAME
                    sd_target.mkdir(parents=True, exist_ok=True)
                    return sd_target
                else:
                    print(
                        "تنبيه: تم اختيار الذاكرة الخارجية لكن لم يتم "
                        "العثور على كرت MicroSD، الرجوع للداخلية."
                    )

            internal_base = (
                Path("/storage/emulated/0") / ORGANIZED_FOLDER_NAME
            )
            try:
                internal_base.mkdir(parents=True, exist_ok=True)
                return internal_base
            except OSError:
                if internal_base.exists():
                    return internal_base
    except (ImportError, OSError, RuntimeError) as e:
        print("تنبيه أثناء تهيئة مسار الملفات المنظمة:", e)

    base = Path(__file__).resolve().parent / ORGANIZED_FOLDER_NAME
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return base


def create_initial_category_folders(
    base_path: Path | None = None
) -> list[Path]:
    """إنشاء وتجهيز شجرة المجلدات الرسمية للملفات المنظمة"""
    base = (
        base_path if base_path is not None
        else get_media_sorter_base_path()
    )
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    folder_names = [
        "صوري",
        "صور اخوتي وزملائي",
        "أفلام ومسلسلات",
        "محاضرات ودروس",
        "أغاني وأناشيد",
        "فيديوهات مضحكة",
        "صور الاختبارات",
        "خارج التصنيف",
    ]
    created: list[Path] = []
    for f_name in folder_names:
        p = base / f_name
        try:
            p.mkdir(parents=True, exist_ok=True)
            created.append(p)
        except OSError:
            pass
    return created


def get_transfer_log_path(base_path: Path | None = None) -> Path:
    """مسار ملف سجل عمليات النقل للتراجع والمراجعة"""
    base = (
        base_path if base_path is not None
        else get_media_sorter_base_path()
    )
    return base / "transfer_history.json"


def _log_transfer_record(
    src_path: str,
    dest_path: str,
    category: str,
    file_size: int,
    base_path: Path | None = None,
    is_copy: bool = True
) -> None:
    """تسجيل عملية نسخ/فرز في سجل المعاملات JSON"""
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

    records.append({
        "id": int(datetime.now(UTC).timestamp() * 1000),
        "source": src_path,
        "destination": dest_path,
        "category": category,
        "size_bytes": file_size,
        "is_copy": is_copy,
        "timestamp": datetime.now(UTC).isoformat(),
    })

    records = records[-1000:]
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError) as e:
        print("تعذر تحديث سجل العمليات:", e)


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
    1. حذف النسخة من مجلد MediaSorter مع بقاء الأصل دون مساس.
    2. حذف السجل من transfer_history.json.
    3. إزالة الملف من scanned_media_cache.db لإتاحة فحصه مجدداً.
    """
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

    dest = Path(str(target_record["destination"]))
    src = Path(str(target_record["source"]))
    is_copy = bool(target_record.get("is_copy", True))

    if is_copy or src.exists():
        if dest.exists():
            try:
                dest.unlink()
            except OSError as e:
                print(f"تعذر حذف النسخة {dest}:", e)
                return False
    else:
        if dest.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            _ = shutil.move(str(dest), str(src))

    _ = records.pop(found_idx)
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError):
        pass

    for db_dir in [get_app_private_storage_dir(), get_media_sorter_base_path()]:
        try:
            cache_db = db_dir / "scanned_media_cache.db"
            if cache_db.exists():
                conn = sqlite3.connect(str(cache_db))
                cursor = conn.cursor()
                q = (
                    "DELETE FROM scanned_files "
                    "WHERE file_path = ? OR file_path = ?"
                )
                _ = cursor.execute(q, (str(src), str(dest)))
                conn.commit()
                conn.close()
        except (sqlite3.Error, OSError):
            pass

    return True


def undo_all_transfers(base_path: Path | None = None) -> int:
    """التراجع عن جميع عمليات النسخ/الفرز دفعة واحدة"""
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
    for r in records:
        dest = Path(str(r["destination"]))
        src = Path(str(r["source"]))
        is_copy = bool(r.get("is_copy", True))

        if is_copy or src.exists():
            if dest.exists():
                try:
                    dest.unlink()
                    undone_count += 1
                except OSError:
                    pass
        else:
            if dest.exists():
                try:
                    src.parent.mkdir(parents=True, exist_ok=True)
                    _ = shutil.move(str(dest), str(src))
                    undone_count += 1
                except OSError:
                    pass

    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    except (OSError, TypeError):
        pass

    for db_dir in [get_app_private_storage_dir(), get_media_sorter_base_path()]:
        try:
            cache_db = db_dir / "scanned_media_cache.db"
            if cache_db.exists():
                conn = sqlite3.connect(str(cache_db))
                cursor = conn.cursor()
                _ = cursor.execute("DELETE FROM scanned_files")
                conn.commit()
                conn.close()
        except (sqlite3.Error, OSError):
            pass

    return undone_count


def copy_to_category(
    src_path: str | Path,
    category_name: str,
    base_path: Path | None = None,
    is_copy: bool = True
) -> Path:
    """
    نسخ الملف بأمان إلى مجلد التصنيف المحدد مع الحفاظ التام على الملف الأصلي:
    1. إنشاء مجلد التصنيف إن لم يكن موجوداً.
    2. حل تعارض الأسماء تلقائياً.
    3. التحقق الحاسم من اكتمال النسخ وتطابق الحجم بالبايت.
    4. الحفاظ على الملف المصدر دون حذفه.
    5. توثيق العملية في transfer_history.json.
    """
    src = Path(src_path).resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"الملف المصدر غير موجود: {src}")

    target_base = (
        base_path if base_path is not None
        else get_media_sorter_base_path()
    )

    clean_parts = [
        sanitize_folder_name(p)
        for p in category_name.replace("\\", "/").split("/")
        if p.strip()
    ]
    target_folder = target_base
    for part in clean_parts:
        target_folder = target_folder / part
    target_folder.mkdir(parents=True, exist_ok=True)

    stem = src.stem
    suffix = src.suffix
    src_size = src.stat().st_size

    # إذا كان الملف موجوداً مسبقاً بنفس الحجم، لا داعي لتكرار نسخه
    primary_dest = target_folder / f"{stem}{suffix}"
    if primary_dest.exists() and primary_dest.stat().st_size == src_size:
        _log_transfer_record(
            str(src),
            str(primary_dest),
            category_name,
            src_size,
            base_path=target_base,
            is_copy=is_copy,
        )
        return primary_dest

    # حل تعارض الأسماء
    dest = primary_dest
    counter = 1
    while dest.exists():
        if dest.stat().st_size == src_size:
            _log_transfer_record(
                str(src),
                str(dest),
                category_name,
                src_size,
                base_path=target_base,
                is_copy=is_copy,
            )
            return dest
        dest = target_folder / f"{stem}_{counter:02d}{suffix}"
        counter += 1

    # نسخ مطابق مع الحفاظ التام على الأصل
    _ = shutil.copy2(src, dest)

    # التحقق الحاسم: التأكد من اكتمال النسخ وتطابق الحجم
    if not dest.exists():
        raise OSError(f"فشل التحقق: الملف غير موجود بعد النسخ: {dest}")

    dest_size = dest.stat().st_size
    if dest_size != src_size:
        dest.unlink(missing_ok=True)
        err_msg = (
            f"عدم تطابق الحجم: المصدر {src_size} بايت، الوجهة {dest_size} بايت"
        )
        raise OSError(err_msg)

    # توثيق العملية
    _log_transfer_record(
        str(src),
        str(dest),
        category_name,
        src_size,
        base_path=target_base,
        is_copy=is_copy,
    )

    return dest


def move_to_category(
    src_path: str | Path,
    category_name: str,
    base_path: Path | None = None,
    copy_only: bool = True
) -> Path:
    """نقل أو نسخ الملف إلى مجلد التصنيف المحدد"""
    if copy_only:
        return copy_to_category(
            src_path, category_name, base_path=base_path, is_copy=True
        )

    src = Path(src_path).resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"الملف المصدر غير موجود: {src}")

    dest = copy_to_category(
        src, category_name, base_path=base_path, is_copy=False
    )
    src.unlink()
    return dest
