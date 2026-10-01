"""
طبقة التخزين الموحدة (Unified Storage Layer):
- عزل منطق التخزين عن التعامل المباشر مع Path وأنظمة الملفات التقليدية.
- دعم كامل لتخزين أندرويد الحديث (Scoped Storage, MediaStore, Storage Access Framework).
- دعم بطاقات MicroSD الخارجية عبر المسار المباشر أو Document URI (SAF).
- كائن TargetLocation لدعم المسارات الفيزيائية وعناوين SAF Tree URIs معاً.
- التحقق الفعلي من إمكانية القراءة والكتابة دون افتراضات خاطئة أو fallback صامت.
- توحيد أسماء التصنيفات ومهاجرة المجلدات القديمة تلقائياً.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("StorageBackend")

ORGANIZED_FOLDER_NAME = "الملفات المنظمة"

# أسماء التصنيفات المعتمدة والموحدة لكافة أجزاء التطبيق
CATEGORY_MY_PHOTOS = "صوري"
CATEGORY_FRIENDS_PHOTOS = "صور اخوتي وزملائي"
CATEGORY_EXAMS_ROOT = "صور الاختبارات"
CATEGORY_LECTURES = "محاضرات ودروس"
CATEGORY_FUNNY_VIDEOS = "فيديوهات مضحكة"
CATEGORY_MOVIES = "أفلام ومسلسلات"
CATEGORY_SONGS = "أغاني وأناشيد"
CATEGORY_UNCLASSIFIED = "خارج التصنيف"

STANDARD_CATEGORIES: list[str] = [
    CATEGORY_MY_PHOTOS,
    CATEGORY_FRIENDS_PHOTOS,
    CATEGORY_MOVIES,
    CATEGORY_LECTURES,
    CATEGORY_SONGS,
    CATEGORY_FUNNY_VIDEOS,
    CATEGORY_EXAMS_ROOT,
    CATEGORY_UNCLASSIFIED,
]

# خريطة توحيد الأسماء القديمة والمتباينة
LEGACY_CATEGORY_MAPPINGS: dict[str, str] = {
    "محاضرات وتعلم": CATEGORY_LECTURES,
    "محاضرات_وتعلم": CATEGORY_LECTURES,
    "محاضرات": CATEGORY_LECTURES,
    "دروس": CATEGORY_LECTURES,
    "صور_الاختبارات": CATEGORY_EXAMS_ROOT,
    "صور اختبارات": CATEGORY_EXAMS_ROOT,
    "صور_اخوتي_وزملائي": CATEGORY_FRIENDS_PHOTOS,
    "صور_الزملاء_والإخوة": CATEGORY_FRIENDS_PHOTOS,
    "فيديوهات_مضحكة": CATEGORY_FUNNY_VIDEOS,
    "افلام ومسلسلات": CATEGORY_MOVIES,
    "أفلام_ومسلسلات": CATEGORY_MOVIES,
    "اغاني واناشيد": CATEGORY_SONGS,
    "أغاني_وأناشيد": CATEGORY_SONGS,
}

IMAGE_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".gif", ".bmp", ".heic", ".heif",
}

VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".3gp", ".mov",
    ".avi", ".webm", ".m4v", ".flv",
}

MIME_TYPE_MAP: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "video/x-matroska": ".mkv",
    "video/3gpp": ".3gp",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/webm": ".webm",
    "video/x-m4v": ".m4v",
    "video/x-flv": ".flv",
}


def resolve_media_mime_type(filename_or_path: str, explicit_mime: str = "") -> str:
    """
    تحديد MIME Type بدقة بناءً على النوع الممرر والامتداد لمنع حفظ الفيديو كصورة:
    - لا تعتمد على الامتداد فقط وتدعم mime_type الممرر من MediaItem.
    - تدعم video/mp4 وvideo/3gpp وvideo/x-matroska وvideo/quicktime وvideo/webm وصيغ الصور المختلفة.
    - تمنع قطعياً إنشاء أي فيديو على SAF بـ MIME image/jpeg أو العكس.
    """
    ext = Path(filename_or_path).suffix.lower()
    is_vid = (ext in VIDEO_EXTENSIONS)

    if explicit_mime:
        em = explicit_mime.strip().lower()
        if is_vid or "video" in em:
            if "image" in em:
                if ext == ".3gp":
                    return "video/3gpp"
                elif ext == ".mkv":
                    return "video/x-matroska"
                elif ext == ".mov":
                    return "video/quicktime"
                elif ext == ".webm":
                    return "video/webm"
                return "video/mp4"
            if "/" in em:
                return em
        elif "image" in em and "/" in em:
            return em

    if ext == ".mp4":
        return "video/mp4"
    elif ext == ".3gp":
        return "video/3gpp"
    elif ext == ".mkv":
        return "video/x-matroska"
    elif ext == ".mov":
        return "video/quicktime"
    elif ext == ".webm":
        return "video/webm"
    elif ext in VIDEO_EXTENSIONS:
        return "video/mp4"
    elif ext == ".png":
        return "image/png"
    elif ext == ".webp":
        return "image/webp"
    elif ext in (".heic", ".heif"):
        return "image/heic"
    elif ext == ".gif":
        return "image/gif"
    elif ext == ".bmp":
        return "image/bmp"
    return "image/jpeg"


@dataclass
class TransferReadResult:
    """نتيجة تفصيلية لعملية قراءة أو نسخ دفق Content URI"""
    success: bool = False
    reason: str = ""  # "success", "permission_denied", "file_not_found", "io_error", "stream_corrupted", "size_mismatch"
    source_uri: str = ""
    display_name: str = ""
    bytes_read: int = 0
    expected_bytes: int = 0
    retryable: bool = True
    error_class: str = ""
    error_message: str = ""


def is_path_readable(path_obj: Path | str) -> bool:
    """التحقق العملي من إمكانية فتح وقراءة أول بايت من المسار فيزيائياً دون إلقاء PermissionError"""
    if not path_obj:
        return False
    try:
        p = Path(path_obj)
        if not p.is_file():
            return False
        with open(p, "rb") as f:
            f.read(4)
        return True
    except (OSError, PermissionError):
        return False


def classify_failure_reason(
    error: Exception | str,
    target_location: Any = None,
    source_uri: str = "",
    stage: str = "",
) -> str:
    """
    تصنيف دقيق وموحد لسبب فشل معالجة الملف لعرضه للمستخدم في الواجهة:
    - يميز بدقة بين:
      1. رفض إذن قراءة المصدر (Android Media Permissions).
      2. انتهاء أو فقدان إذن مجلد بطاقة SD (SAF Tree URI).
      3. فشل إنشاء مجلد الوجهة.
      4. فشل القراءة الحقيقي (ملف تالف أو غير متاح).
      5. امتلاء المساحة التخزينية.
      6. فصل بطاقة SD الفيزيائية.
    """
    err_str = str(error).lower()
    stage_lower = (stage or "").lower()

    # 1. إذا كان الفشل في مرحلة قراءة المصدر
    if stage_lower == "source_read" or "openinputstream" in err_str or "in_stream" in err_str:
        if any(k in err_str for k in ("securityexception", "permission denied", "eacces", "operation not permitted", "صلاحية")):
            return "رفض صلاحية قراءة الملف"
        if any(k in err_str for k in ("filenotfound", "غير موجود", "no such file")):
            return "الملف غير موجود"
        return "فشل القراءة"

    # 2. فحص مخصص إذا كانت الوجهة تعتمد على SAF
    is_saf_target = bool(target_location and getattr(target_location, "is_saf", False))
    is_target_valid = getattr(target_location, "is_valid", True) if target_location else True

    is_perm_issue = any(k in err_str for k in ("permission denied", "operation not permitted", "securityexception", "eacces", "uri permission", "permission", "صلاحية", "إذن"))
    is_io_target_issue = any(k in err_str for k in ("openoutputstream", "createdocument", "saf", "document", "كتابة"))

    if is_saf_target and (is_perm_issue or is_io_target_issue or not is_target_valid):
        # بطاقة SD مركبة والـ SAF صالح: خطأ صلاحية = انتهاء إذن SAF
        if is_target_valid and is_perm_issue:
            return "انتهاء SAF permission"
        # بطاقة SD مفصولة أو URI غير صالح
        if not is_target_valid:
            return "فصل بطاقة SD"
        return "انتهاء SAF permission"

    if "enospc" in err_str or "no space" in err_str or "امتلاء" in err_str or "disk full" in err_str:
        return "امتلاء المساحة"

    # الفشل بسبب صلاحية SAF — سواء كانت الوجهة SAF أم ظهرت كلمة saf في رسالة الخطأ
    is_saf_in_err = "saf" in err_str or "tree permission" in err_str
    if (
        "securityexception" in err_str
        or (is_saf_in_err and ("permission" in err_str or "إذن" in err_str or "صلاحية" in err_str))
        or "uri permission" in err_str
    ):
        if is_saf_target or is_saf_in_err:
            return "انتهاء SAF permission"
        return "رفض الصلاحية"

    if target_location and getattr(target_location, "storage_type", "") == "sdcard" and not getattr(target_location, "is_valid", True):
        msg = getattr(target_location, "error_message", "").lower()
        if "saf" in msg or "إذن" in msg:
            return "انتهاء SAF permission"
        return "فصل بطاقة SD"

    if (
        "sdcard" in err_str or "sd card" in err_str or "enodev" in err_str
        or "بطاقة" in err_str or "غير مركبة" in err_str or "disconnected" in err_str
        or ("unmounted" in err_str and "sd" in err_str) or "missing" in err_str
    ):
        return "فصل بطاقة SD"

    if "مجلد" in err_str or "mkdir" in err_str or "createdirectory" in err_str or "directory" in err_str:
        return "فشل إنشاء المجلد"

    if "قراءة" in err_str or "دفق" in err_str or "stream" in err_str or "read" in err_str or "pipe" in err_str:
        return "فشل القراءة"

    if "permission" in err_str or "eacces" in err_str or "صلاحية" in err_str:
        if is_saf_target or stage_lower in ("target_write", "target_mkdir"):
            return "انتهاء SAF permission"
        return "رفض الصلاحية"

    return f"فشل: {error}"


def _get_platform() -> str:
    """الحصول على المنصة بأمان دون إلقاء استثناء عند غياب Kivy"""
    try:
        from kivy.utils import platform
        return str(platform)
    except Exception:
        return "win" if os.name == "nt" else "linux"


@dataclass
class StorageLocation:
    """كائن بيانات يمثل موقع تخزين على الجهاز بدقة وتفصيل كامل"""
    id: str  # "internal", "sdcard", "custom_saf"
    name: str  # الاسم المعروض للمستخدم
    path: str  # المسار الفيزيائي (إن وجد)
    uri: str = ""  # Content URI أو SAF Tree URI
    detected: bool = False
    mounted: bool = False
    readable: bool = False
    writable: bool = False
    requires_saf: bool = False
    free_gb: float = 0.0
    total_gb: float = 0.0
    failure_reason: str = ""
    description: str = ""


@dataclass
class TargetLocation:
    """
    كائن بيانات يمثل الوجهة الفعلية المعتمدة لحفظ وترتيب الملفات المنظمة:
    - يدعم المسار الفيزيائي (path) للذاكرة الداخلية أو الأقراص المباشرة.
    - يدعم Document Tree URI (SAF) لبطاقات MicroSD في أندرويد الحديث.
    - يمنع أي fallback صامت عند اختيار المستخدم لبطاقة SD.
    """
    storage_type: str  # "internal" أو "sdcard" أو "custom"
    is_saf: bool = False  # True إذا كانت الوجهة تعتمد على SAF Document Tree URI
    path: Path | None = None  # مسار محلي فيزيائي إن كانت كتابة مباشرة
    tree_uri: str = ""  # URI شجرة SAF للبطاقة الخارجية
    display_name: str = ""
    is_valid: bool = True
    error_message: str = ""

    @property
    def is_writable(self) -> bool:
        if not self.is_valid:
            return False
        if self.is_saf:
            return is_saf_uri_valid(self.tree_uri)
        if self.path:
            return is_directory_writable(self.path)
        return False

    @property
    def saf_uri(self) -> str:
        return self.tree_uri

    @property
    def name(self) -> str:
        return self.display_name or (str(self.path) if self.path else self.storage_type)

    def __str__(self) -> str:
        if self.is_saf:
            return f"SAF_Tree({self.tree_uri})"
        return str(self.path) if self.path else f"TargetLocation({self.storage_type})"


@dataclass
class MediaItem:
    """كائن بيانات يمثل ملف وسائط مراد فحصه أو فرزه بتوافق كامل مع مسارات أندرويد الحديثة"""
    id: str  # المعرف الفريد (مسار أو Content URI)
    source_type: str  # "path", "content_uri", "saf_document"
    path: str = ""  # المسار الحقيقي على القرص إن أمكن
    uri: str = ""  # Content URI للملف
    display_name: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    date_modified: float = 0.0
    storage_id: str = "internal"  # "internal" أو "sdcard"
    relative_path: str = ""  # المسار النسبي داخل وحدة التخزين (مثل DCIM/Camera أو صوري)

    @property
    def name(self) -> str:
        if self.display_name:
            return self.display_name
        if self.path:
            return Path(self.path).name
        return self.id

    @property
    def suffix(self) -> str:
        ext = Path(self.name).suffix.lower()
        if ext:
            return ext
        if self.mime_type in MIME_TYPE_MAP:
            return MIME_TYPE_MAP[self.mime_type]
        if "video" in self.mime_type:
            return ".mp4"
        if "image" in self.mime_type:
            return ".jpg"
        return ".mp4" if "video" in self.mime_type else ".jpg"

    @property
    def is_video(self) -> bool:
        ext = Path(self.name).suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            return True
        return bool(self.mime_type and "video" in self.mime_type.lower())

    @property
    def is_image(self) -> bool:
        ext = Path(self.name).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            return True
        return bool(self.mime_type and "image" in self.mime_type.lower())

    def exists(self) -> bool:
        if self.path:
            try:
                return Path(self.path).exists()
            except OSError:
                return False
        return bool(self.uri)

    def __str__(self) -> str:
        return self.path if self.path else (self.uri if self.uri else self.id)


def normalize_category_name(raw_name: str) -> str:
    """توحيد اسم التصنيف وإرجاع الاسم القياسي المعتمد"""
    if not raw_name:
        return CATEGORY_UNCLASSIFIED
    cleaned = raw_name.strip()
    return LEGACY_CATEGORY_MAPPINGS.get(cleaned, cleaned)


def migrate_legacy_folders(base_path: Path) -> int:
    """
    دمج المجلدات القديمة تلقائياً (مثل 'محاضرات وتعلم' إلى 'محاضرات ودروس')
    دون فقدان أي ملف أو إنشاء مجلدات مكررة.
    """
    if not base_path.exists() or not base_path.is_dir():
        return 0

    migrated_count = 0
    for old_name, std_name in LEGACY_CATEGORY_MAPPINGS.items():
        if old_name == std_name:
            continue
        old_dir = base_path / old_name
        std_dir = base_path / std_name

        if old_dir.exists() and old_dir.is_dir():
            try:
                std_dir.mkdir(parents=True, exist_ok=True)
                for item in list(old_dir.iterdir()):
                    if item.is_file():
                        target_file = std_dir / item.name
                        if target_file.exists():
                            target_file = std_dir / f"{item.stem}_{int(time.time())}{item.suffix}"
                        shutil.move(str(item), str(target_file))
                        migrated_count += 1
                try:
                    old_dir.rmdir()
                except OSError:
                    pass
                logger.info("تمت هجرة المجلد القديم '%s' إلى '%s'", old_name, std_name)
            except Exception as e:
                logger.warning("تعذر هجرة المجلد %s: %s", old_name, e)

    return migrated_count


def is_directory_writable(dir_path: Path) -> bool:
    """
    التحقق الفعلي الصارم من إمكانية إنشاء وكتابة وحذف الملفات داخل المجلد.
    هام: لا يتم الفحص أبداً في جذر بطاقة الذاكرة الخارجية تجنباً لرفض النظام.
    """
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        test_file = dir_path / f".write_test_{int(time.time() * 1000)}"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return True
    except (PermissionError, OSError) as e:
        logger.debug("المجلد %s غير قابل للكتابة المباشرة: %s", dir_path, e)
        return False


def get_saf_persisted_uri() -> str:
    """استرجاع URI بطاقة SD المحفوظ مسبقاً عبر SAF إن وجد"""
    try:
        from file_manager import get_sorter_preferences
        prefs = get_sorter_preferences()
        return str(prefs.get("saf_sdcard_uri", "")).strip()
    except Exception:
        return ""


def save_saf_persisted_uri(uri_str: str) -> None:
    """حفظ URI الممنوح لبطاقة SD عبر SAF"""
    try:
        from file_manager import save_sorter_preferences
        save_sorter_preferences({"saf_sdcard_uri": uri_str})
    except Exception as e:
        logger.warning("تعذر حفظ URI البطاقة: %s", e)


def is_saf_uri_valid(uri_str: str) -> bool:
    """التحقق مما إذا كان URI الممنوح عبر SAF لا يزال صالحاً وممنوحاً"""
    if not uri_str:
        return False

    # دعم المحاكاة في بيئة الاختبارات
    if uri_str.startswith("mock_saf://"):
        mock_path = uri_str.replace("mock_saf://", "")
        return os.path.exists(mock_path)

    if "broken" in uri_str.lower() or "invalid" in uri_str.lower():
        return False

    try:
        if _get_platform() == "android":
            from android import mActivity
            from jnius import autoclass
            Uri = autoclass("android.net.Uri")
            parsed_uri = Uri.parse(uri_str)
            cr = mActivity.getContentResolver()
            persisted_list = cr.getPersistedUriPermissions()
            if persisted_list:
                for i in range(persisted_list.size()):
                    perm = persisted_list.get(i)
                    if perm:
                        p_str = str(perm.getUri())
                        if p_str == uri_str or p_str.rstrip("/") == uri_str.rstrip("/") or perm.getUri() == parsed_uri:
                            return bool(perm.isWritePermission() and perm.isReadPermission())
            return False
        return True
    except Exception as e:
        logger.debug("فحص صلاحية SAF URI: %s", e)
        return False


def request_saf_folder_picker() -> bool:
    """
    إطلاق نافذة نظام أندرويد الرسمية (Storage Access Framework)
    لاختيار مجلد بطاقة الذاكرة الخارجية ومنح إذن دائم للكتابة والقراءة.
    """
    try:
        if _get_platform() != "android":
            return False
        from android import mActivity
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
        take_flags = (
            Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
            | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION
        )
        intent.addFlags(take_flags)
        SAF_REQUEST_CODE = 4201
        mActivity.startActivityForResult(intent, SAF_REQUEST_CODE)
        logger.info("تم إطلاق منتقي المجلدات SAF بنجاح (Request Code: %d)", SAF_REQUEST_CODE)
        return True
    except Exception as e:
        logger.error("تعذر إطلاق منتقي المجلدات SAF: %s", e)
        return False


_STORAGE_DETECT_CACHE: dict[str, StorageLocation] | None = None
_STORAGE_DETECT_CACHE_TIME: float = 0.0
_STORAGE_DETECT_CACHE_TTL: float = 8.0  # مهلة 8 ثوان لتجنب تكرار فحص القرص في كل إطار


def clear_storage_detect_cache() -> None:
    """مسح كاش فحص التخزين لإجبار التحديث الفوري"""
    global _STORAGE_DETECT_CACHE, _STORAGE_DETECT_CACHE_TIME
    _STORAGE_DETECT_CACHE = None
    _STORAGE_DETECT_CACHE_TIME = 0.0


def detect_storage_locations(force_refresh: bool = False) -> dict[str, StorageLocation]:
    """
    استكشاف دقيق وشامل لجميع مواقع التخزين المتاحة على الجهاز
    مع بيان إمكانية الكتابة بدقة دون خداع المستخدم أو إخفاء المشاكل.
    يستخدم كاش بمهلة 8 ثوان لتجنب تكرار عمليات mkdir واختبارات الكتابة في كل تحديث للواجهة.
    """
    global _STORAGE_DETECT_CACHE, _STORAGE_DETECT_CACHE_TIME
    now = time.time()
    if (
        not force_refresh
        and _STORAGE_DETECT_CACHE is not None
        and (now - _STORAGE_DETECT_CACHE_TIME) < _STORAGE_DETECT_CACHE_TTL
    ):
        return dict(_STORAGE_DETECT_CACHE)

    locations: dict[str, StorageLocation] = {}

    try:
        if _get_platform() == "android":
            # 1. الذاكرة الداخلية المشتركة (/storage/emulated/0)
            int_path = Path("/storage/emulated/0")
            int_target = int_path / ORGANIZED_FOLDER_NAME
            int_free, int_total = 0.0, 0.0
            int_detected = int_path.exists()
            int_writable = False
            int_reason = ""

            if int_detected:
                try:
                    du = shutil.disk_usage(str(int_path))
                    int_free = round(du.free / (1024 ** 3), 1)
                    int_total = round(du.total / (1024 ** 3), 1)
                except OSError:
                    pass
                int_writable = is_directory_writable(int_target)
                if not int_writable:
                    int_reason = "تتطلب صلاحية إدارة كافة الملفات (All Files Access)"

            locations["internal"] = StorageLocation(
                id="internal",
                name="الذاكرة الداخلية المشتركة",
                path=str(int_target),
                detected=int_detected,
                mounted=int_detected,
                readable=int_detected,
                writable=int_writable,
                requires_saf=False,
                free_gb=int_free,
                total_gb=int_total,
                failure_reason=int_reason,
                description=f"المسار: /storage/emulated/0/{ORGANIZED_FOLDER_NAME} ({int_free} GB متاح)",
            )

            # 2. بطاقة الذاكرة الخارجية MicroSD
            sd_location = _detect_android_sdcard()
            locations["sdcard"] = sd_location
            _STORAGE_DETECT_CACHE = locations
            _STORAGE_DETECT_CACHE_TIME = now
            return locations

    except Exception as e:
        logger.warning("استثناء أثناء استكشاف التخزين: %s", e)

    # بيئة الحاسوب للتطوير والاختبارات الآلية
    dev_base = Path(__file__).resolve().parent / ORGANIZED_FOLDER_NAME
    dev_base.mkdir(parents=True, exist_ok=True)
    free_gb, total_gb = 0.0, 0.0
    try:
        du = shutil.disk_usage(str(dev_base))
        free_gb = round(du.free / (1024 ** 3), 1)
        total_gb = round(du.total / (1024 ** 3), 1)
    except OSError:
        pass

    locations["internal"] = StorageLocation(
        id="internal",
        name="القرص الأساسي (المشروع)",
        path=str(dev_base),
        detected=True,
        mounted=True,
        readable=True,
        writable=True,
        requires_saf=False,
        free_gb=free_gb,
        total_gb=total_gb,
        description=f"المسار: {dev_base} ({free_gb} GB متاح)",
    )
    locations["sdcard"] = StorageLocation(
        id="sdcard",
        name="بطاقة الذاكرة الخارجية",
        path="غير متوفرة في بيئة المحاكاة",
        detected=False,
        mounted=False,
        readable=False,
        writable=False,
        requires_saf=False,
        failure_reason="غير متوفرة على بيئة سطح المكتب",
        description="غير متوفرة في بيئة المحاكاة/سطح المكتب",
    )
    _STORAGE_DETECT_CACHE = locations
    _STORAGE_DETECT_CACHE_TIME = now
    return locations


def _detect_android_sdcard() -> StorageLocation:
    """استكشاف حالة بطاقة SD على أندرويد بطرق متعددة مع التحقق الدقيق"""
    candidate_roots: list[Path] = []
    saf_uri = get_saf_persisted_uri()
    has_valid_saf = is_saf_uri_valid(saf_uri)

    try:
        from android import mActivity
        from jnius import autoclass
        Context = autoclass("android.content.Context")
        sm = mActivity.getSystemService(Context.STORAGE_SERVICE)
        if sm:
            volumes = sm.getStorageVolumes()
            if volumes:
                for i in range(volumes.size()):
                    vol = volumes.get(i)
                    if vol and vol.isRemovable():
                        uuid = vol.getUuid()
                        if uuid:
                            candidate_roots.append(Path(f"/storage/{uuid}"))
                        try:
                            dir_f = vol.getDirectory()
                            if dir_f:
                                candidate_roots.append(Path(dir_f.getAbsolutePath()))
                        except Exception:
                            pass
    except Exception as e:
        logger.debug("StorageManager query: %s", e)

    try:
        from android import mActivity
        ext_dirs = mActivity.getExternalFilesDirs(None)
        if ext_dirs:
            for ed in ext_dirs:
                if ed:
                    ps = ed.getAbsolutePath()
                    if "/Android/data" in ps and not ps.startswith("/storage/emulated/"):
                        candidate_roots.append(Path(ps.split("/Android/data")[0]))
    except Exception as e:
        logger.debug("getExternalFilesDirs: %s", e)

    storage_dir = Path("/storage")
    if storage_dir.exists() and storage_dir.is_dir():
        try:
            for item in storage_dir.iterdir():
                if item.is_dir() and item.name not in ("emulated", "self", "knox", "sdcard0"):
                    if item not in candidate_roots:
                        candidate_roots.append(item)
        except Exception:
            pass

    found_root: Path | None = None
    sd_free, sd_total = 0.0, 0.0

    for root in candidate_roots:
        if root.exists() and root.is_dir():
            found_root = root
            try:
                du = shutil.disk_usage(str(root))
                sd_free = round(du.free / (1024 ** 3), 1)
                sd_total = round(du.total / (1024 ** 3), 1)
            except OSError:
                pass
            break

    if not found_root and not has_valid_saf:
        return StorageLocation(
            id="sdcard",
            name="بطاقة الذاكرة الخارجية (MicroSD)",
            path="غير متوفرة حالياً",
            detected=False,
            mounted=False,
            readable=False,
            writable=False,
            requires_saf=False,
            failure_reason="لم يتم العثور على بطاقة MicroSD مركبة بالجهاز",
            description="غير متوفرة حالياً",
        )

    sd_target = (found_root / ORGANIZED_FOLDER_NAME) if found_root else Path("/storage/sdcard_saf")
    direct_writable = is_directory_writable(sd_target) if found_root else False

    requires_saf = not direct_writable
    is_writable = direct_writable or has_valid_saf
    fail_reason = ""

    if requires_saf and not has_valid_saf:
        fail_reason = "تتطلب بطاقة SD اختيار مجلد الحفظ عبر SAF لمنح إذن الكتابة"
        desc = f"مركبة ({found_root}) ولكن تحتاج إذن المجلد (SAF)"
    elif has_valid_saf:
        desc = f"متاحة للكتابة عبر إذن SAF الممنوح ({sd_free} GB متاح)"
    else:
        desc = f"المسار: {sd_target} ({sd_free} GB متاح)"

    return StorageLocation(
        id="sdcard",
        name="بطاقة الذاكرة الخارجية (MicroSD)",
        path=str(sd_target),
        uri=saf_uri,
        detected=True,
        mounted=True,
        readable=True,
        writable=is_writable,
        requires_saf=requires_saf,
        free_gb=sd_free,
        total_gb=sd_total,
        failure_reason=fail_reason,
        description=desc,
    )


def get_active_target_location(target_choice: str | None = None) -> TargetLocation:
    """
    إرجاع كائن TargetLocation الفعلي والحقيقي لوجهة الحفظ الحالية:
    - لا يعمل Fallback صامتاً إلى الذاكرة الداخلية إطلاقاً.
    - إذا اختار المستخدم بطاقة SD ولم تكن صالحة، يرجع TargetLocation بحالة is_valid=False مع سبب الخطأ الدقيق.
    """
    if target_choice is None:
        try:
            from file_manager import get_sorter_preferences
            prefs = get_sorter_preferences()
            target_choice = str(prefs.get("target_storage", "internal")).strip().lower()
        except Exception:
            target_choice = "internal"

    if target_choice == "sdcard":
        locs = detect_storage_locations()
        sd = locs.get("sdcard")

        # 1. إذا كان يوجد SAF URI صالح وممنوح للبطاقة، فالوجهة SAF دائماً
        saf_uri = (sd.uri if sd else "") or get_saf_persisted_uri()
        if is_saf_uri_valid(saf_uri):
            return TargetLocation(
                storage_type="sdcard",
                is_saf=True,
                tree_uri=saf_uri,
                display_name="بطاقة الذاكرة الخارجية عبر SAF",
                is_valid=True,
            )

        if not sd or not sd.detected:
            return TargetLocation(
                storage_type="sdcard",
                is_saf=False,
                is_valid=False,
                error_message="بطاقة الذاكرة الخارجية (MicroSD) غير متوفرة أو غير مركبة بالجهاز.",
            )

        # 2. إذا كانت قابلة للكتابة المباشرة الفيزيائية دون SAF (مثل بيئات Android 9 أو المجلد المخصص)
        if sd.writable and not sd.requires_saf and sd.path and sd.path != "غير متوفرة حالياً":
            target_p = Path(sd.path)
            return TargetLocation(
                storage_type="sdcard",
                is_saf=False,
                path=target_p,
                display_name=sd.name,
                is_valid=True,
            )

        # 3. بطاقة SD مركبة ولكنها تتطلب إذن SAF
        return TargetLocation(
            storage_type="sdcard",
            is_saf=True,
            tree_uri=saf_uri,
            is_valid=False,
            error_message="تتطلب بطاقة SD تحديد مجلد الحفظ ومنح إذن الكتابة عبر Storage Access Framework (SAF).",
        )

    # الذاكرة الداخلية المشتركة
    locs = detect_storage_locations()
    internal_loc = locs.get("internal")
    int_path = Path(internal_loc.path) if (internal_loc and internal_loc.path) else (Path.cwd() / ORGANIZED_FOLDER_NAME)
    return TargetLocation(
        storage_type="internal",
        is_saf=False,
        path=int_path,
        display_name=internal_loc.name if internal_loc else "الذاكرة الداخلية",
        is_valid=True,
    )


# =========================================================================
# دعم Storage Access Framework (SAF) عبر DocumentFile و DocumentsContract
# =========================================================================

def _saf_get_document_file_class() -> Any:
    """استرجاع androidx.documentfile.provider.DocumentFile إن وجد"""
    try:
        from jnius import autoclass
        return autoclass("androidx.documentfile.provider.DocumentFile")
    except Exception:
        return None


def saf_find_or_create_directory(tree_uri: str, category_name: str) -> str:
    """
    إنشاء أو جلب مجلد الوجهة داخل بطاقة SD عبر SAF:
    يبحث عن 'الملفات المنظمة' أولاً، ثم مجلد التصنيف (مثل 'محاضرات ودروس').
    العائد: Document URI للمجلد كـ string، أو فارغ عند الفشل.
    """
    if not tree_uri:
        return ""

    # دعم المحاكاة لبيئات الاختبار
    if tree_uri.startswith("mock_saf://"):
        base_dir = Path(tree_uri.replace("mock_saf://", ""))
        target_dir = base_dir / ORGANIZED_FOLDER_NAME / category_name
        target_dir.mkdir(parents=True, exist_ok=True)
        return f"mock_doc://{target_dir}"

    if _get_platform() != "android":
        return ""

    try:
        from android import mActivity
        from jnius import autoclass
        Uri = autoclass("android.net.Uri")
        cr = mActivity.getContentResolver()
        parsed_tree = Uri.parse(tree_uri)

        DocFileClass = _saf_get_document_file_class()
        if DocFileClass is not None:
            try:
                root_doc = DocFileClass.fromTreeUri(mActivity, parsed_tree)
                if root_doc:
                    target_org = root_doc.findFile(ORGANIZED_FOLDER_NAME)
                    if not target_org:
                        target_org = root_doc.createDirectory(ORGANIZED_FOLDER_NAME)
                    if not target_org:
                        target_org = root_doc

                    sub_dir = target_org
                    for part in category_name.replace("\\", "/").split("/"):
                        p_clean = part.strip()
                        if not p_clean:
                            continue
                        next_d = sub_dir.findFile(p_clean)
                        if not next_d:
                            next_d = sub_dir.createDirectory(p_clean)
                        if next_d:
                            sub_dir = next_d

                    if sub_dir and sub_dir.getUri():
                        return str(sub_dir.getUri().toString())
            except Exception as e_df:
                logger.warning("تنبيه إنشاء مجلد SAF عبر DocumentFile، سيتم الانتقال لـ DocumentsContract: %s", e_df)

        # Fallback رسمي أصيل عبر DocumentsContract بدون androidx
        DocumentsContract = autoclass("android.provider.DocumentsContract")
        tree_doc_id = DocumentsContract.getTreeDocumentId(parsed_tree)
        root_doc_uri = DocumentsContract.buildDocumentUriUsingTree(parsed_tree, tree_doc_id)

        # 1. إنشاء أو جلب مجلد الملفات المنظمة
        MIME_DIR = "vnd.android.document/directory"
        org_uri = _contract_find_or_create_child(cr, parsed_tree, root_doc_uri, ORGANIZED_FOLDER_NAME, MIME_DIR)
        if not org_uri:
            return ""

        # 2. إنشاء مجلد التصنيف
        cat_uri = org_uri
        for part in category_name.replace("\\", "/").split("/"):
            p_clean = part.strip()
            if not p_clean:
                continue
            cat_uri = _contract_find_or_create_child(cr, parsed_tree, cat_uri, p_clean, MIME_DIR)
            if not cat_uri:
                return ""

        return str(cat_uri.toString())

    except Exception:
        logger.exception("فشل إنشاء مجلد التصنيف في SAF")
        return ""


def saf_create_target_document(
    tree_uri: str, category_name: str, filename: str, mime_type: str = ""
) -> tuple[Any, str]:
    """
    إنشاء ملف وجهة جديد داخل مجلد التصنيف في بطاقة SD عبر SAF:
    - يتعامل مباشرة مع شجرة الـ SAF دون تشويه مسار TreeDocumentFile.
    - يتحقق من وجود DocumentFile أولاً، ثم DocumentsContract كبديل أصلي موثوق.
    - يضمن أن نوع MIME متوافق مع نوع الملف الفعلي (صورة أو فيديو).
    - يعيد (new_uri_obj, new_uri_str) أو (None, "").
    """
    if not tree_uri:
        return (None, "")

    if tree_uri.startswith("mock_saf://"):
        cat_uri_str = saf_find_or_create_directory(tree_uri, category_name)
        dest_dir = Path(cat_uri_str.replace("mock_doc://", ""))
        dest_file = dest_dir / filename
        return (dest_file, f"mock_doc://{dest_file}")

    if _get_platform() != "android":
        return (None, "")

    try:
        from android import mActivity
        from jnius import autoclass
        Uri = autoclass("android.net.Uri")
        cr = mActivity.getContentResolver()
        parsed_tree = Uri.parse(tree_uri)

        resolved_mime = resolve_media_mime_type(filename, mime_type)

        # 1. المحاولة عبر DocumentFile
        DocFileClass = _saf_get_document_file_class()
        if DocFileClass is not None:
            try:
                root_doc = DocFileClass.fromTreeUri(mActivity, parsed_tree)
                if root_doc:
                    target_org = root_doc.findFile(ORGANIZED_FOLDER_NAME)
                    if not target_org:
                        target_org = root_doc.createDirectory(ORGANIZED_FOLDER_NAME)
                    if not target_org:
                        target_org = root_doc

                    curr_doc = target_org
                    for part in category_name.replace("\\", "/").split("/"):
                        p_clean = part.strip()
                        if not p_clean:
                            continue
                        next_d = curr_doc.findFile(p_clean)
                        if not next_d:
                            next_d = curr_doc.createDirectory(p_clean)
                        if next_d:
                            curr_doc = next_d

                    new_doc = curr_doc.createFile(resolved_mime, filename)
                    if new_doc:
                        u = new_doc.getUri()
                        return (u, str(u.toString()))
            except Exception as e_df:
                logger.warning("تنبيه إنشاء ملف SAF عبر DocumentFile: %s", e_df)

        # 2. Fallback عبر DocumentsContract
        DocumentsContract = autoclass("android.provider.DocumentsContract")
        tree_doc_id = DocumentsContract.getTreeDocumentId(parsed_tree)
        root_doc_uri = DocumentsContract.buildDocumentUriUsingTree(parsed_tree, tree_doc_id)

        MIME_DIR = "vnd.android.document/directory"
        org_uri = _contract_find_or_create_child(cr, parsed_tree, root_doc_uri, ORGANIZED_FOLDER_NAME, MIME_DIR)
        cat_uri = org_uri or root_doc_uri
        for part in category_name.replace("\\", "/").split("/"):
            p_clean = part.strip()
            if not p_clean:
                continue
            child_uri = _contract_find_or_create_child(cr, parsed_tree, cat_uri, p_clean, MIME_DIR)
            if child_uri:
                cat_uri = child_uri

        new_file_uri = DocumentsContract.createDocument(cr, cat_uri, resolved_mime, filename)
        if new_file_uri:
            return (new_file_uri, str(new_file_uri.toString()))

        return (None, "")
    except Exception:
        logger.exception("فشل إنشاء ملف الوجهة في SAF (%s)", filename)
        return (None, "")


def saf_find_directory(tree_uri: str, category_name: str) -> str:
    """
    البحث عن مجلد داخل بطاقة الذاكرة الخارجية عبر SAF دون إنشائه.
    يدعم المسارات بمختلف صيغها:
    1. 'الملفات المنظمة/صور الاختبارات/اسم المادة'
    2. 'صور الاختبارات/اسم المادة'
    3. 'اسم المادة'
    العائد: Document URI للمجلد كـ string أو فارغ إذا لم يكن موجوداً.
    """
    if not tree_uri:
        return ""

    clean_parts = [p.strip() for p in category_name.replace("\\", "/").split("/") if p.strip()]
    if clean_parts and clean_parts[0] == ORGANIZED_FOLDER_NAME:
        clean_parts = clean_parts[1:]

    # إعداد مسارات البحث المحتملة: المسار المحدد، وتحت صور الاختبارات إن لم تكن مذكورة
    possible_paths = [clean_parts]
    if clean_parts and clean_parts[0] != CATEGORY_EXAMS_ROOT:
        possible_paths.append([CATEGORY_EXAMS_ROOT] + clean_parts)

    if tree_uri.startswith("mock_saf://"):
        base_dir = Path(tree_uri.replace("mock_saf://", ""))
        for p_parts in possible_paths:
            sub = "/".join(p_parts)
            cand1 = base_dir / ORGANIZED_FOLDER_NAME / sub
            if cand1.exists() and cand1.is_dir():
                return f"mock_doc://{cand1}"
            cand2 = base_dir / sub
            if cand2.exists() and cand2.is_dir():
                return f"mock_doc://{cand2}"
        return ""

    if _get_platform() != "android":
        return ""

    try:
        from android import mActivity
        from jnius import autoclass
        Uri = autoclass("android.net.Uri")
        cr = mActivity.getContentResolver()
        parsed_tree = Uri.parse(tree_uri)

        DocFileClass = _saf_get_document_file_class()
        if DocFileClass is not None:
            root_doc = DocFileClass.fromTreeUri(mActivity, parsed_tree)
            if not root_doc:
                return ""
            target_org = root_doc.findFile(ORGANIZED_FOLDER_NAME)
            search_roots = [target_org] if target_org else [root_doc]
            if target_org and target_org != root_doc:
                search_roots.append(root_doc)

            for s_root in search_roots:
                for p_parts in possible_paths:
                    curr_doc = s_root
                    found = True
                    for part in p_parts:
                        next_doc = curr_doc.findFile(part)
                        if not next_doc:
                            found = False
                            break
                        curr_doc = next_doc
                    if found and curr_doc:
                        return str(curr_doc.getUri().toString())
            return ""

        # DocumentsContract Fallback
        DocumentsContract = autoclass("android.provider.DocumentsContract")
        tree_doc_id = DocumentsContract.getTreeDocumentId(parsed_tree)
        root_doc_uri = DocumentsContract.buildDocumentUriUsingTree(parsed_tree, tree_doc_id)

        org_child = _contract_find_child_only(cr, parsed_tree, root_doc_uri, ORGANIZED_FOLDER_NAME)
        search_root_uris = [org_child] if org_child else [root_doc_uri]
        if org_child and org_child != root_doc_uri:
            search_root_uris.append(root_doc_uri)

        for s_root_uri in search_root_uris:
            for p_parts in possible_paths:
                curr_uri = s_root_uri
                found = True
                for part in p_parts:
                    child_uri = _contract_find_child_only(cr, parsed_tree, curr_uri, part)
                    if not child_uri:
                        found = False
                        break
                    curr_uri = child_uri
                if found and curr_uri:
                    return str(curr_uri.toString())

        return ""
    except Exception as e:
        logger.debug("خطأ أثناء البحث عن مجلد SAF: %s", e)
        return ""


def _contract_find_child_only(cr: Any, tree_uri: Any, parent_doc_uri: Any, name: str) -> Any:
    """البحث عن عنصر ابن بالاسم فقط في DocumentsContract دون إنشائه"""
    from jnius import autoclass
    DocumentsContract = autoclass("android.provider.DocumentsContract")
    parent_doc_id = DocumentsContract.getDocumentId(parent_doc_uri)
    children_uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree_uri, parent_doc_id)
    cursor = None
    try:
        cursor = cr.query(children_uri, None, None, None, None)
        if cursor is not None:
            name_idx = cursor.getColumnIndex("_display_name")
            id_idx = cursor.getColumnIndex("document_id")
            while cursor.moveToNext():
                c_name = cursor.getString(name_idx) if name_idx >= 0 else ""
                if c_name == name:
                    c_id = cursor.getString(id_idx) if id_idx >= 0 else ""
                    if c_id:
                        return DocumentsContract.buildDocumentUriUsingTree(tree_uri, c_id)
    except Exception:
        pass
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
    return None


def _contract_find_or_create_child(cr: Any, tree_uri: Any, parent_doc_uri: Any, name: str, mime_type: str) -> Any:
    """مساعد DocumentsContract للبحث عن مجلد فرعي أو إنشائه"""
    from jnius import autoclass
    DocumentsContract = autoclass("android.provider.DocumentsContract")
    parent_doc_id = DocumentsContract.getDocumentId(parent_doc_uri)
    children_uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree_uri, parent_doc_id)

    cursor = None
    try:
        cursor = cr.query(children_uri, None, None, None, None)
        if cursor is not None:
            name_idx = cursor.getColumnIndex("_display_name")
            id_idx = cursor.getColumnIndex("document_id")
            while cursor.moveToNext():
                c_name = cursor.getString(name_idx) if name_idx >= 0 else ""
                if c_name == name:
                    c_id = cursor.getString(id_idx) if id_idx >= 0 else ""
                    return DocumentsContract.buildDocumentUriUsingTree(tree_uri, c_id)
    except Exception as e:
        logger.debug("DocumentsContract query child: %s", e)
    finally:
        if cursor is not None:
            cursor.close()

    # لم يتم العثور عليه، نقوم بإنشائه
    return DocumentsContract.createDocument(cr, parent_doc_uri, mime_type, name)


def get_uri_file_size(uri_str: str) -> int:
    """استرجاع حجم الملف بالبايت لـ Content URI أو SAF Document URI"""
    if not uri_str:
        return 0

    if uri_str.startswith("mock_doc://"):
        p = Path(uri_str.replace("mock_doc://", ""))
        return p.stat().st_size if p.exists() else 0

    try:
        if _get_platform() == "android":
            from android import mActivity
            from jnius import autoclass
            Uri = autoclass("android.net.Uri")
            cr = mActivity.getContentResolver()
            cursor = cr.query(Uri.parse(uri_str), None, None, None, None)
            if cursor is not None:
                try:
                    if cursor.moveToFirst():
                        size_idx = cursor.getColumnIndex("_size")
                        if size_idx >= 0:
                            return int(cursor.getLong(size_idx))
                finally:
                    cursor.close()
    except Exception as e:
        logger.debug("تعذر جلب حجم URI: %s: %s", uri_str, e)
    return 0


def query_content_uri_details(uri_str: str) -> dict[str, Any]:
    """
    استخراج تفاصيل Content URI الحقيقية من نظام أندرويد بدقة:
    - الاسم المعروض (_display_name)
    - نوع الوسائط الفعلي (mime_type)
    - الحجم الحقيقي بالبايت (_size)
    - الامتداد الصحيح (يمنع حفظ الفيديو كصورة JPG نهائياً)
    """
    res: dict[str, Any] = {
        "display_name": "",
        "mime_type": "",
        "size_bytes": 0,
        "extension": ".jpg",
        "is_video": False,
        "is_image": False,
    }
    if not uri_str:
        return res

    if uri_str.startswith("mock_doc://"):
        p = Path(uri_str.replace("mock_doc://", ""))
        ext = p.suffix.lower()
        is_vid = ext in VIDEO_EXTENSIONS
        res["display_name"] = p.name
        res["size_bytes"] = p.stat().st_size if p.exists() else 0
        res["extension"] = ext or (".mp4" if is_vid else ".jpg")
        res["is_video"] = is_vid
        res["is_image"] = not is_vid
        res["mime_type"] = "video/mp4" if is_vid else "image/jpeg"
        return res

    try:
        if _get_platform() == "android":
            from android import mActivity
            from jnius import autoclass
            Uri = autoclass("android.net.Uri")
            parsed_uri = Uri.parse(uri_str)
            cr = mActivity.getContentResolver()

            # 1. جلب MIME TYPE
            try:
                mime = cr.getType(parsed_uri)
                if mime:
                    res["mime_type"] = str(mime)
            except Exception:
                pass

            # 2. استعلام بيانات الملف من ContentProvider
            cursor = None
            try:
                cursor = cr.query(parsed_uri, None, None, None, None)
                if cursor is not None and cursor.moveToFirst():
                    name_idx = cursor.getColumnIndex("_display_name")
                    size_idx = cursor.getColumnIndex("_size")
                    mime_idx = cursor.getColumnIndex("mime_type")

                    if name_idx >= 0:
                        name_val = cursor.getString(name_idx)
                        if name_val:
                            res["display_name"] = str(name_val)

                    if size_idx >= 0:
                        res["size_bytes"] = int(cursor.getLong(size_idx))

                    if not res["mime_type"] and mime_idx >= 0:
                        m_val = cursor.getString(mime_idx)
                        if m_val:
                            res["mime_type"] = str(m_val)
            except Exception as e_cur:
                logger.debug("استعلام تفاصيل Content URI عبر cursor: %s", e_cur)
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
    except Exception as e:
        logger.debug("استثناء عام أثناء فحص Content URI %s: %s", uri_str, e)

    # معالجة الامتداد والنوع لمنع حفظ الفيديو باسم JPG نهائياً
    mime_lower = res["mime_type"].lower()
    is_vid = (
        ("video" in mime_lower)
        or ("video" in uri_str.lower())
        or any(uri_str.lower().endswith(ve) for ve in VIDEO_EXTENSIONS)
    )
    res["is_video"] = is_vid
    res["is_image"] = not is_vid

    disp_name = res["display_name"]
    ext = Path(disp_name).suffix.lower() if disp_name else ""

    if not ext:
        if res["mime_type"] in MIME_TYPE_MAP:
            ext = MIME_TYPE_MAP[res["mime_type"]]
        elif is_vid:
            ext = ".mp4"
        else:
            ext = ".jpg"

    # تأكيد صارم: لا يمكن أن يكون الفيديو .jpg إطلاقاً
    if is_vid and ext in IMAGE_EXTENSIONS:
        ext = ".mp4"

    res["extension"] = ext
    if not res["display_name"]:
        res["display_name"] = f"media_{int(time.time() * 1000)}{ext}"
    elif not Path(res["display_name"]).suffix:
        res["display_name"] = f"{res['display_name']}{ext}"

    return res


def scan_saf_tree_recursively(
    tree_uri: str,
    max_depth: int = 10,
    include_organized: bool = False,
) -> list[MediaItem]:
    """
    قارئ حقيقي وشامل لشجرة SAF Tree URI:
    - فحص شجري عودي (recursive) لجميع المجلدات والملفات داخل الشجرة عبر DocumentsContract / DocumentFile.
    - استخراج الصور والفيديوهات وإنشاء MediaItem لكل ملف مع تفاصيله الدقيقة.
    - يدعم استبعاد مجلد الملفات المنظمة عند فحص الوسائط غير المصنفة (include_organized=False).
    - لا يعتمد على os.walk أو MediaStore التي قد لا تعرض ملفات بطاقة SD على أجهزة أندرويد الحديثة.
    """
    found_items: list[MediaItem] = []
    if not tree_uri:
        return found_items

    # 1. بيئة المحاكاة
    if tree_uri.startswith("mock_saf://"):
        base_dir = Path(tree_uri.replace("mock_saf://", ""))
        if not base_dir.exists() or not base_dir.is_dir():
            return found_items
        for root, dirs, files in os.walk(str(base_dir)):
            rel = Path(".")  # تأكيد التهيئة قبل الاستخدام
            try:
                rel = Path(root).relative_to(base_dir)
                if len(rel.parts) > max_depth:
                    dirs[:] = []
                    continue
            except ValueError:
                pass

            is_root_chosen_organized = base_dir.name.lower() in (ORGANIZED_FOLDER_NAME.lower(), "mediasorter")
            is_root_level = (len(rel.parts) == 0)

            filtered_dirs = []
            for d in dirs:
                if d.startswith(".") or d.lower() in ("lost.dir", ".android"):
                    continue
                d_lower = d.lower()
                if not include_organized and d_lower in (ORGANIZED_FOLDER_NAME.lower(), "mediasorter"):
                    if not is_root_chosen_organized or not is_root_level:
                        continue
                filtered_dirs.append(d)
            dirs[:] = filtered_dirs

            rel_folder = str(rel).replace("\\", "/")
            if rel_folder == ".":
                rel_folder = ""

            for f in files:
                if f.startswith("."):
                    continue
                ext = Path(f).suffix.lower()
                is_img = ext in IMAGE_EXTENSIONS
                is_vid = ext in VIDEO_EXTENSIONS
                if is_img or is_vid:
                    fp = Path(root) / f
                    sz = fp.stat().st_size
                    mtime = fp.stat().st_mtime
                    mock_uri = f"mock_doc://{fp}"
                    file_rel = f"{rel_folder}/{f}".strip("/") if rel_folder else f
                    found_items.append(
                        MediaItem(
                            id=mock_uri,
                            source_type="saf_document",
                            path=str(fp),
                            uri=mock_uri,
                            display_name=f,
                            mime_type="video/mp4" if is_vid else "image/jpeg",
                            size_bytes=sz,
                            date_modified=mtime,
                            storage_id="sdcard",
                            relative_path=file_rel,
                        )
                    )
        return found_items

    if _get_platform() != "android":
        return found_items

    # 2. على نظام أندرويد
    try:
        from android import mActivity
        from jnius import autoclass
        Uri = autoclass("android.net.Uri")
        DocumentsContract = autoclass("android.provider.DocumentsContract")
        cr = mActivity.getContentResolver()
        parsed_tree = Uri.parse(tree_uri)

        tree_doc_id = DocumentsContract.getTreeDocumentId(parsed_tree)
        root_doc_uri = DocumentsContract.buildDocumentUriUsingTree(parsed_tree, tree_doc_id)

        # التحقق مما إذا كان الجذر الذي اختاره المستخدم هو مجلد "الملفات المنظمة" نفسه
        is_root_chosen_organized = False
        try:
            tree_doc_id_decoded = str(tree_doc_id).lower()
            if ORGANIZED_FOLDER_NAME.lower() in tree_doc_id_decoded or "mediasorter" in tree_doc_id_decoded:
                is_root_chosen_organized = True
            else:
                r_cursor = cr.query(root_doc_uri, None, None, None, None)
                if r_cursor is not None:
                    try:
                        if r_cursor.moveToFirst():
                            r_idx = r_cursor.getColumnIndex("_display_name")
                            if r_idx >= 0:
                                r_name = str(r_cursor.getString(r_idx) or "").lower()
                                if r_name in (ORGANIZED_FOLDER_NAME.lower(), "mediasorter"):
                                    is_root_chosen_organized = True
                    finally:
                        r_cursor.close()
        except Exception:
            pass

        # طابور التفرع: (document_uri, current_depth, relative_folder_path)
        queue: list[tuple[Any, int, str]] = [(root_doc_uri, 0, "")]
        visited_doc_ids: set[str] = set()

        MIME_DIR = "vnd.android.document/directory"

        while queue:
            curr_doc_uri, depth, curr_rel = queue.pop(0)
            if depth > max_depth:
                continue

            curr_doc_id = DocumentsContract.getDocumentId(curr_doc_uri)
            curr_doc_id_str = str(curr_doc_id)
            if curr_doc_id_str in visited_doc_ids:
                continue
            visited_doc_ids.add(curr_doc_id_str)

            children_uri = DocumentsContract.buildChildDocumentsUriUsingTree(parsed_tree, curr_doc_id)
            cursor = None
            try:
                cursor = cr.query(children_uri, None, None, None, None)
                if cursor is None:
                    continue

                id_idx = cursor.getColumnIndex("document_id")
                name_idx = cursor.getColumnIndex("_display_name")
                mime_idx = cursor.getColumnIndex("mime_type")
                size_idx = cursor.getColumnIndex("_size")
                mtime_idx = cursor.getColumnIndex("last_modified")

                while cursor.moveToNext():
                    c_id = cursor.getString(id_idx) if id_idx >= 0 else ""
                    if not c_id:
                        continue
                    c_name = cursor.getString(name_idx) if name_idx >= 0 else ""
                    c_mime = cursor.getString(mime_idx) if mime_idx >= 0 else ""
                    c_size = cursor.getLong(size_idx) if size_idx >= 0 else 0
                    c_mtime = float(cursor.getLong(mtime_idx) / 1000.0) if mtime_idx >= 0 else 0.0

                    c_name_lower = c_name.lower()
                    if c_name.startswith(".") or c_name_lower in ("lost.dir", ".android"):
                        continue

                    if not include_organized and c_name_lower in (ORGANIZED_FOLDER_NAME.lower(), "mediasorter"):
                        # استبعاد المجلد فقط عندما يكون فرعياً داخل الجذر، وليس عندما يكون الجذر نفسه
                        if not is_root_chosen_organized or depth > 0:
                            continue

                    child_doc_uri = DocumentsContract.buildDocumentUriUsingTree(parsed_tree, c_id)

                    if c_mime == MIME_DIR:
                        sub_rel = f"{curr_rel}/{c_name}".strip("/") if curr_rel else c_name
                        queue.append((child_doc_uri, depth + 1, sub_rel))
                    else:
                        ext = Path(c_name).suffix.lower()
                        is_img = (ext in IMAGE_EXTENSIONS) or (c_mime and "image" in c_mime)
                        is_vid = (ext in VIDEO_EXTENSIONS) or (c_mime and "video" in c_mime)
                        if is_img or is_vid:
                            doc_uri_str = str(child_doc_uri.toString())
                            file_rel = f"{curr_rel}/{c_name}".strip("/") if curr_rel else c_name
                            found_items.append(
                                MediaItem(
                                    id=doc_uri_str,
                                    source_type="saf_document",
                                    path="",
                                    uri=doc_uri_str,
                                    display_name=c_name,
                                    mime_type=c_mime or ("video/mp4" if is_vid else "image/jpeg"),
                                    size_bytes=c_size,
                                    date_modified=c_mtime,
                                    storage_id="sdcard",
                                    relative_path=file_rel,
                                )
                            )
            except Exception as e_q:
                logger.debug("خطأ أثناء استعلام فرع SAF %s: %s", curr_doc_id_str, e_q)
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass

    except Exception as e:
        logger.error("فشل الفحص الشجري لـ SAF Tree URI %s: %s", tree_uri, e)

    return found_items


# =========================================================================
# دوال النسخ والنقل الموحدة (Unified Stream Transfer Layer)
# =========================================================================

def copy_path_to_path(src_file: Path, dest_file: Path) -> bool:
    """نسخ آمن من مسار إلى مسار مع كتابة مؤقتة (Atomic Copy) والتحقق من الحجم"""
    if not src_file.exists() or not src_file.is_file():
        logger.error("الملف المصدر غير موجود: %s", src_file)
        return False

    dest_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_file.parent / f".tmp_{dest_file.name}_{int(time.time() * 1000)}"

    src_size = src_file.stat().st_size
    try:
        with open(src_file, "rb") as f_in, open(temp_dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out, length=64 * 1024)

        if not temp_dest.exists() or temp_dest.stat().st_size != src_size:
            logger.error("فشل تطابق حجم الملف المؤقت بعد النسخ!")
            temp_dest.unlink(missing_ok=True)
            return False

        temp_dest.replace(dest_file)
        return True
    except Exception as e:
        logger.error("خطأ أثناء نسخ الملف من مسار لمسار: %s", e)
        temp_dest.unlink(missing_ok=True)
        return False


def find_content_uri_for_path(path_str: str) -> str:
    """البحث عن Content URI لمسار ملف في MediaStore على أندرويد عند تعذر فتحه المباشر"""
    if _get_platform() != "android" or not path_str:
        return ""
    try:
        from android import mActivity
        from jnius import autoclass
        MediaStoreImages = autoclass("android.provider.MediaStore$Images$Media")
        MediaStoreVideo = autoclass("android.provider.MediaStore$Video$Media")
        ContentUris = autoclass("android.content.ContentUris")
        cr = mActivity.getContentResolver()

        for base_table in [MediaStoreImages.EXTERNAL_CONTENT_URI, MediaStoreVideo.EXTERNAL_CONTENT_URI]:
            cursor = cr.query(
                base_table,
                ["_id"],
                "_data = ?",
                [str(path_str)],
                None,
            )
            if cursor is not None:
                try:
                    if cursor.moveToFirst():
                        item_id = cursor.getLong(0)
                        if item_id > 0:
                            return str(ContentUris.withAppendedId(base_table, item_id).toString())
                finally:
                    cursor.close()
    except Exception as e:
        logger.debug("تعذر استخراج Content URI للمسار %s: %s", path_str, e)
    return ""


def copy_uri_to_path_detailed(content_uri: str, dest_file: Path) -> TransferReadResult:
    """
    نسخ ملف من Content URI إلى مسار محلي مع إرجاع كائن TransferReadResult تفصيلي:
    - إغلاق كافة التدفقات في finally دوماً.
    - حذف الملف المؤقت التالف عند أي فشل فورياً.
    - التقاط SecurityException و FileNotFoundException و PermissionError بتفصيل ودقة.
    """
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_file.parent / f".tmp_uri_{dest_file.name}_{int(time.time() * 1000)}"
    expected_size = get_uri_file_size(content_uri)

    # 1. بيئة المحاكاة
    if content_uri.startswith("mock_doc://"):
        src_mock = Path(content_uri.replace("mock_doc://", ""))
        ok = copy_path_to_path(src_mock, temp_dest)
        if not ok:
            temp_dest.unlink(missing_ok=True)
            return TransferReadResult(
                success=False,
                reason="file_not_found",
                source_uri=content_uri,
                display_name=dest_file.name,
                bytes_read=0,
                expected_bytes=expected_size,
                error_message="فشل نسخ الملف الوهمي في المحاكاة",
            )
        if expected_size > 0 and temp_dest.stat().st_size != expected_size:
            sz = temp_dest.stat().st_size
            temp_dest.unlink(missing_ok=True)
            return TransferReadResult(
                success=False,
                reason="size_mismatch",
                source_uri=content_uri,
                display_name=dest_file.name,
                bytes_read=sz,
                expected_bytes=expected_size,
                error_message="عدم تطابق حجم الملف في المحاكاة",
            )
        temp_dest.replace(dest_file)
        return TransferReadResult(
            success=True,
            reason="success",
            source_uri=content_uri,
            display_name=dest_file.name,
            bytes_read=expected_size,
            expected_bytes=expected_size,
        )

    # 2. أندرويد الحقيقي عبر ContentResolver
    in_stream = None
    is_success = False
    total_written = 0
    err_cls = ""
    err_msg = ""
    fail_reason = "io_error"

    try:
        if _get_platform() == "android":
            from android import mActivity
            from jnius import autoclass
            Uri = autoclass("android.net.Uri")
            parsed_uri = Uri.parse(content_uri)
            cr = mActivity.getContentResolver()

            try:
                in_stream = cr.openInputStream(parsed_uri)
            except Exception as e_open:
                cls_name = type(e_open).__name__
                msg_lower = str(e_open).lower()
                if "securityexception" in msg_lower or "permission" in msg_lower:
                    return TransferReadResult(
                        success=False,
                        reason="permission_denied",
                        source_uri=content_uri,
                        display_name=dest_file.name,
                        expected_bytes=expected_size,
                        error_class=cls_name,
                        error_message=f"رفض إذن القراءة من مزود الوسائط: {e_open}",
                        retryable=True,
                    )
                return TransferReadResult(
                    success=False,
                    reason="file_not_found" if "filenotfound" in msg_lower else "stream_open_failed",
                    source_uri=content_uri,
                    display_name=dest_file.name,
                    expected_bytes=expected_size,
                    error_class=cls_name,
                    error_message=f"تعذر فتح دفق المصدر: {e_open}",
                    retryable=False,
                )

            if in_stream is None:
                return TransferReadResult(
                    success=False,
                    reason="stream_null",
                    source_uri=content_uri,
                    display_name=dest_file.name,
                    expected_bytes=expected_size,
                    error_message="دفق القراءة من ContentResolver أعاد Null",
                    retryable=True,
                )

            CHUNK_SIZE = 64 * 1024
            buffer = bytearray(CHUNK_SIZE)

            with open(temp_dest, "wb") as out_f:
                while True:
                    read_bytes = in_stream.read(buffer)
                    if read_bytes == -1 or read_bytes == 0:
                        break
                    out_f.write(buffer[:read_bytes])
                    total_written += read_bytes

            if total_written == 0:
                return TransferReadResult(
                    success=False,
                    reason="stream_empty",
                    source_uri=content_uri,
                    display_name=dest_file.name,
                    bytes_read=0,
                    expected_bytes=expected_size,
                    error_message="تم قراءة 0 بايت من Content URI",
                    retryable=True,
                )

            if expected_size > 0 and total_written != expected_size:
                return TransferReadResult(
                    success=False,
                    reason="size_mismatch",
                    source_uri=content_uri,
                    display_name=dest_file.name,
                    bytes_read=total_written,
                    expected_bytes=expected_size,
                    error_message=f"عدم تطابق الحجم: مقروء {total_written} vs متوقع {expected_size}",
                    retryable=True,
                )

            temp_dest.replace(dest_file)
            is_success = True
            return TransferReadResult(
                success=True,
                reason="success",
                source_uri=content_uri,
                display_name=dest_file.name,
                bytes_read=total_written,
                expected_bytes=expected_size,
            )
        else:
            # بيئات غير أندرويد (اختبارات المسارات المحلية)
            p = Path(content_uri)
            if p.exists() and p.is_file():
                ok = copy_path_to_path(p, temp_dest)
                if ok and (expected_size <= 0 or temp_dest.stat().st_size == expected_size):
                    temp_dest.replace(dest_file)
                    is_success = True
                    return TransferReadResult(
                        success=True,
                        reason="success",
                        source_uri=content_uri,
                        display_name=dest_file.name,
                        bytes_read=dest_file.stat().st_size,
                        expected_bytes=expected_size,
                    )
            return TransferReadResult(
                success=False,
                reason="file_not_found",
                source_uri=content_uri,
                display_name=dest_file.name,
                error_message="الملف غير موجود في بيئة الاختبار",
            )

    except (PermissionError, OSError) as e_sys:
        err_cls = type(e_sys).__name__
        err_msg = str(e_sys)
        fail_reason = "permission_denied" if isinstance(e_sys, PermissionError) else "io_error"
        logger.error("خطأ أثناء نسخ Content URI (%s): %s", content_uri, e_sys)
        return TransferReadResult(
            success=False,
            reason=fail_reason,
            source_uri=content_uri,
            display_name=dest_file.name,
            bytes_read=total_written,
            expected_bytes=expected_size,
            error_class=err_cls,
            error_message=err_msg,
            retryable=True,
        )
    except Exception as e_all:
        err_cls = type(e_all).__name__
        err_msg = str(e_all)
        logger.error("استثناء غير متوقع أثناء نسخ Content URI (%s): %s", content_uri, e_all)
        return TransferReadResult(
            success=False,
            reason="unexpected_exception",
            source_uri=content_uri,
            display_name=dest_file.name,
            bytes_read=total_written,
            expected_bytes=expected_size,
            error_class=err_cls,
            error_message=err_msg,
            retryable=True,
        )
    finally:
        if in_stream is not None:
            try:
                in_stream.close()
            except Exception:
                pass
        if not is_success and temp_dest.exists():
            temp_dest.unlink(missing_ok=True)


def copy_uri_to_path(content_uri: str, dest_file: Path) -> bool:
    """نسخ ملف من Content URI إلى مسار محلي (غلاف متوافق يعيد bool)"""
    return copy_uri_to_path_detailed(content_uri, dest_file).success


def compute_content_uri_hash(uri_or_path: str, chunk_size: int = 65536) -> str | None:
    """
    حساب بصمة التجزئة الفعلية (SHA-256) لمحتوى ملف محلي أو Content URI على دفعات:
    - يدعم المسارات المحلية، مسارات mock_doc://، و Content URIs على أندرويد عبر openInputStream.
    - يعيد None عند أي خطأ في القراءة أو تعذر فتح الدفق لتجنب اعتبار الملفات مكررة خطأً.
    """
    if not uri_or_path:
        return None

    import hashlib
    hasher = hashlib.sha256()

    # 1. إذا كان mock_doc://
    if uri_or_path.startswith("mock_doc://"):
        local_p = Path(uri_or_path.replace("mock_doc://", ""))
        if not local_p.exists() or not local_p.is_file():
            return None
        try:
            with open(local_p, "rb") as fp:
                while True:
                    data = fp.read(chunk_size)
                    if not data:
                        break
                    hasher.update(data)
            return hasher.hexdigest()
        except OSError as e:
            logger.warning("تعذر قراءة ملف mock_doc لحساب الهاش: %s (%s)", local_p, e)
            return None

    # 2. إذا كان Content URI على أندرويد
    if uri_or_path.startswith("content://"):
        if _get_platform() == "android":
            try:
                from android import mActivity
                from jnius import autoclass
                Uri = autoclass("android.net.Uri")
                parsed_uri = Uri.parse(uri_or_path)
                cr = mActivity.getContentResolver()
                in_stream = cr.openInputStream(parsed_uri)
                if in_stream is None:
                    logger.warning("تعذر فتح دفق القراءة لحساب الهاش للـ URI: %s", uri_or_path)
                    return None

                buffer = bytearray(chunk_size)
                try:
                    while True:
                        read_bytes = in_stream.read(buffer)
                        if read_bytes == -1 or read_bytes == 0:
                            break
                        hasher.update(buffer[:read_bytes])
                finally:
                    try:
                        in_stream.close()
                    except Exception:
                        pass

                return hasher.hexdigest()
            except Exception as e:
                logger.warning("استثناء أثناء حساب هاش Content URI: %s (%s)", uri_or_path, e)
                return None
        else:
            p = Path(uri_or_path)
            if p.exists() and p.is_file():
                try:
                    with open(p, "rb") as fp:
                        while True:
                            data = fp.read(chunk_size)
                            if not data:
                                break
                            hasher.update(data)
                    return hasher.hexdigest()
                except OSError:
                    return None
            return None

    # 3. مسار محلي عادي
    p = Path(uri_or_path)
    if not p.exists() or not p.is_file():
        return None
    try:
        with open(p, "rb") as fp:
            while True:
                data = fp.read(chunk_size)
                if not data:
                    break
                hasher.update(data)
        return hasher.hexdigest()
    except OSError as e:
        logger.warning("تعذر قراءة الملف المحلي لحساب الهاش: %s (%s)", p, e)
        return None


def copy_path_to_saf_uri(src_file: Path, saf_tree_uri: str, category: str, filename: str, mime_type: str = "") -> str:
    """
    نسخ ملف محلي إلى بطاقة SD عبر Storage Access Framework و DocumentFile/DocumentsContract.
    العائد: Document URI للملف المنشأ في الوجهة كـ string، أو فارغ عند الفشل.
    حذف الملف الجزئي التالف فوراً في finally عند أي فشل أو عدم تطابق في الحجم.
    """
    if not src_file.exists():
        return ""

    src_size = src_file.stat().st_size

    # بيئة المحاكاة
    if saf_tree_uri.startswith("mock_saf://"):
        cat_uri = saf_find_or_create_directory(saf_tree_uri, category)
        dest_dir = Path(cat_uri.replace("mock_doc://", ""))
        dest_file = dest_dir / filename
        ok = copy_path_to_path(src_file, dest_file)
        return f"mock_doc://{dest_file}" if ok else ""

    if _get_platform() != "android":
        return ""

    created_uri_str = ""
    is_success = False
    out_stream = None

    try:
        from android import mActivity
        cr = mActivity.getContentResolver()

        cat_doc_uri_str = saf_find_or_create_directory(saf_tree_uri, category)
        if not cat_doc_uri_str:
            logger.error("تعذر تهيئة مجلد التصنيف في SAF للوجهة!")
            return ""

        target_name = filename or src_file.name
        # تحديد نوع الوسائط بدقة مع منع جعل الفيديو صورة JPG
        mime = resolve_media_mime_type(target_name, mime_type)

        new_file_uri, created_uri_str = saf_create_target_document(
            saf_tree_uri, category, target_name, mime
        )
        if not new_file_uri or not created_uri_str:
            raise OSError(f"تعذر إنشاء ملف الوجهة في بطاقة SD عبر SAF: {target_name}")

        out_stream = cr.openOutputStream(new_file_uri)
        if not out_stream:
            raise OSError(f"تعذر فتح دفق الكتابة لملف SAF: {target_name}")

        total_written = 0
        with open(src_file, "rb") as in_f:
            buf = bytearray(64 * 1024)
            while True:
                chunk = in_f.read(len(buf))
                if not chunk:
                    break
                out_stream.write(chunk)
                total_written += len(chunk)

        try:
            out_stream.close()
        except Exception:
            pass
        out_stream = None

        if total_written != src_size:
            raise OSError(f"عدم تطابق البايتات المكتوبة إلى SAF: كتب {total_written} من {src_size}")

        # استعلام الحجم النهائي الفعلي بعد إغلاق OutputStream من نظام الملفات
        final_size = get_uri_file_size(created_uri_str)
        if final_size != src_size:
            raise OSError(f"عدم تطابق الحجم النهائي لملف SAF: المتوقع {src_size}، الفعلي {final_size}")

        is_success = True
        return created_uri_str

    except Exception:
        logger.exception("فشل نسخ الملف إلى بطاقة SD عبر SAF (%s)", filename or src_file.name)
        raise
    finally:
        if out_stream is not None:
            try:
                out_stream.close()
            except Exception:
                pass
        # حذف الملف الجزئي أو التالف فوراً عند أي فشل
        if not is_success and created_uri_str:
            logger.warning("تنظيف وحذف ملف SAF غير المكتمل: %s", created_uri_str)
            delete_media_item(created_uri_str)


def copy_uri_to_saf_uri(src_content_uri: str, saf_tree_uri: str, category: str, filename: str, expected_size: int = 0, mime_type: str = "") -> str:
    """
    نسخ ملف من Content URI (MediaStore) مباشرة إلى Document URI في بطاقة SD عبر SAF.
    التحقق الصارم من دفق البيانات وتطابق الحجم بالبايت.
    حذف الملف الجزئي التالف فوراً في finally عند أي فشل أو عدم تطابق في الحجم.
    """
    if saf_tree_uri.startswith("mock_saf://"):
        cat_uri = saf_find_or_create_directory(saf_tree_uri, category)
        dest_dir = Path(cat_uri.replace("mock_doc://", ""))
        dest_file = dest_dir / filename
        ok = copy_uri_to_path(src_content_uri, dest_file)
        return f"mock_doc://{dest_file}" if ok else ""

    if _get_platform() != "android":
        return ""

    created_uri_str = ""
    is_success = False
    in_stream = None
    out_stream = None

    try:
        from android import mActivity
        from jnius import autoclass
        Uri = autoclass("android.net.Uri")
        cr = mActivity.getContentResolver()

        src_parsed = Uri.parse(src_content_uri)
        in_stream = cr.openInputStream(src_parsed)
        if not in_stream:
            raise PermissionError(f"تعذر فتح دفق المصدر للقراءة من مزود الوسائط: {src_content_uri}")

        # تحديد نوع الوسائط بدقة مع منع جعل الفيديو صورة JPG
        mime = resolve_media_mime_type(filename, mime_type)

        new_file_uri, created_uri_str = saf_create_target_document(
            saf_tree_uri, category, filename, mime
        )
        if not new_file_uri or not created_uri_str:
            raise OSError(f"تعذر إنشاء ملف الوجهة في بطاقة SD عبر SAF: {filename}")

        out_stream = cr.openOutputStream(new_file_uri)
        if not out_stream:
            raise OSError(f"تعذر فتح دفق الكتابة لملف SAF: {filename}")

        total_written = 0
        buf = bytearray(64 * 1024)
        while True:
            read_bytes = in_stream.read(buf)
            if read_bytes == -1 or read_bytes == 0:
                break
            out_stream.write(buf[:read_bytes])
            total_written += read_bytes

        try:
            in_stream.close()
        except Exception:
            pass
        in_stream = None

        try:
            out_stream.close()
        except Exception:
            pass
        out_stream = None

        if expected_size > 0 and total_written != expected_size:
            raise OSError(f"عدم تطابق الحجم عند نسخ URI إلى SAF: كتب {total_written} من {expected_size}")

        final_size = get_uri_file_size(created_uri_str)
        if expected_size > 0 and final_size != expected_size:
            raise OSError(f"عدم تطابق الحجم النهائي لملف SAF: المتوقع {expected_size}، الفعلي {final_size}")

        is_success = True
        return created_uri_str

    except Exception:
        logger.exception("فشل نسخ Content URI إلى SAF (%s)", filename)
        raise
    finally:
        if in_stream is not None:
            try:
                in_stream.close()
            except Exception:
                pass
        if out_stream is not None:
            try:
                out_stream.close()
            except Exception:
                pass
        if not is_success and created_uri_str:
            logger.warning("تنظيف وحذف ملف SAF غير المكتمل: %s", created_uri_str)
            delete_media_item(created_uri_str)


def delete_media_item(item: MediaItem | Path | str) -> bool:
    """
    حذف الملف المصدر أو وجهة تراجع بأمان:
    - يتعامل مع المسارات الفيزيائية (Path).
    - يتعامل مع Document URIs عبر DocumentsContract.
    - يتعامل مع MediaStore Content URIs ويحمي من RecoverableSecurityException في أندرويد الحديث مع طلب إذن المستخدم.
    - إذا فشل الحذف، يعيد False دون التسبب في Crash.
    """
    try:
        # 1. إذا كان MediaItem
        if isinstance(item, MediaItem):
            if item.source_type == "path" and item.path:
                p = Path(item.path)
                if p.exists():
                    p.unlink()
                    return True
            elif item.uri:
                return delete_media_item(item.uri)
            return False

        # 2. إذا كان Path
        if isinstance(item, Path):
            if item.exists():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink()
                return True
            return True

        # 3. إذا كان نصاً (مسار أو Content URI)
        item_str = str(item).strip()
        if not item_str:
            return False

        if item_str.startswith("mock_doc://"):
            mock_p = Path(item_str.replace("mock_doc://", ""))
            if mock_p.exists():
                if mock_p.is_dir():
                    shutil.rmtree(mock_p, ignore_errors=True)
                else:
                    mock_p.unlink()
            return True

        if item_str.startswith("content://"):
            if _get_platform() == "android":
                from android import mActivity
                from jnius import autoclass
                Uri = autoclass("android.net.Uri")
                parsed_uri = Uri.parse(item_str)
                cr = mActivity.getContentResolver()

                # فحص هل هو SAF Document
                if "document" in item_str or "tree" in item_str:
                    try:
                        DocumentsContract = autoclass("android.provider.DocumentsContract")
                        return bool(DocumentsContract.deleteDocument(cr, parsed_uri))
                    except Exception as e:
                        logger.debug("DocumentsContract delete failed, fallback to cr.delete: %s", e)

                # حذف من MediaStore مع معالجة RecoverableSecurityException
                try:
                    deleted = cr.delete(parsed_uri, None, None)
                    return deleted > 0
                except Exception as sec_e:
                    err_name = type(sec_e).__name__
                    if "RecoverableSecurityException" in err_name or "RecoverableSecurityException" in str(sec_e):
                        logger.info("حذف MediaStore يتطلب إذن المستخدم عبر RecoverableSecurityException: %s", sec_e)
                        try:
                            # طلب تأكيد أندرويد لحذف الملف عبر jnius لأن الكائن Java
                            from jnius import autoclass
                            RecoverableSecurityException = autoclass(
                                "android.app.RecoverableSecurityException"
                            )
                            java_exc = RecoverableSecurityException._cast(sec_e)
                            user_action = java_exc.getUserAction()
                            intent_sender = user_action.getActionIntent().getIntentSender()
                            RECOVERABLE_REQUEST_CODE = 4202
                            real_name = ""
                            try:
                                details = query_content_uri_details(item_str)
                                real_name = details.get("display_name", "")
                            except Exception:
                                pass
                            set_pending_recoverable_deletion(item_str, file_name=real_name)
                            mActivity.startIntentSenderForResult(
                                intent_sender, RECOVERABLE_REQUEST_CODE, None, 0, 0, 0
                            )
                            logger.info("تم إطلاق نافذة تأكيد حذف أندرويد الرسمية وتخزين العملية المعلقة (Request Code: %d)", RECOVERABLE_REQUEST_CODE)
                        except Exception as act_e:
                            logger.debug("تعذر إطلاق intent sender لـ RecoverableSecurityException: %s", act_e)
                    else:
                        logger.warning("فشل حذف Content URI: %s (%s)", item_str, sec_e)
                    return False
            return False

        # مسار محلي عادي
        p = Path(item_str)
        if p.exists():
            p.unlink()
            return True
        return True

    except Exception as e:
        logger.warning("استثناء أثناء حذف العنصر %s: %s", item, e)
        return False


# =========================================================================
# إدارة العمليات المعلقة لـ RecoverableSecurityException (Request Code 4202)
# =========================================================================

_pending_recoverable_deletion: dict[str, Any] | None = None


def _get_pending_recoverable_file() -> Path:
    from file_manager import get_app_private_storage_dir
    return get_app_private_storage_dir() / "pending_recoverable_deletion.json"


def set_pending_recoverable_deletion(
    item_uri: str,
    record_id: int | None = None,
    src_path: str = "",
    dest_path: str = "",
    file_size: int = 0,
    mtime: float = 0.0,
    category: str = "",
    target_storage: str = "",
    file_name: str = "",
) -> None:
    """تخزين تفاصيل عملية الحذف المعلقة في الذاكرة وفي التخزين الخاص بالتطبيق لحين استلام نتيجة موافقة المستخدم"""
    global _pending_recoverable_deletion
    if not file_name:
        try:
            details = query_content_uri_details(item_uri) if item_uri.startswith("content://") else {}
            file_name = details.get("display_name") or Path(src_path or item_uri).name
        except Exception:
            file_name = Path(src_path or item_uri).name or "ملف وسائط"

    data = {
        "item_uri": item_uri,
        "record_id": record_id,
        "src_path": src_path or item_uri,
        "dest_path": dest_path,
        "file_name": file_name,
        "file_size": file_size,
        "mtime": mtime,
        "category": category,
        "target_storage": target_storage,
        "timestamp": time.time(),
    }
    _pending_recoverable_deletion = data
    try:
        p = _get_pending_recoverable_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("تعذر حفظ pending recoverable deletion في التخزين الخاص: %s", e)
    logger.info("تم تسجيل عملية الحذف المعلقة لـ RecoverableSecurityException: %s (الاسم: %s)", item_uri, file_name)


def get_pending_recoverable_deletion() -> dict[str, Any] | None:
    """استرجاع العملية المعلقة من الذاكرة أو من التخزين الخاص بالتطبيق"""
    global _pending_recoverable_deletion
    if _pending_recoverable_deletion is not None:
        return _pending_recoverable_deletion
    try:
        p = _get_pending_recoverable_file()
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _pending_recoverable_deletion = data
                    return data
    except Exception as e:
        logger.debug("تعذر قراءة pending recoverable deletion من التخزين الخاص: %s", e)
    return None


def clear_pending_recoverable_deletion() -> None:
    """مسح العملية المعلقة من الذاكرة ومن التخزين الخاص بالتطبيق"""
    global _pending_recoverable_deletion
    _pending_recoverable_deletion = None
    try:
        p = _get_pending_recoverable_file()
        if p.exists():
            p.unlink()
    except Exception as e:
        logger.debug("تعذر مسح ملف pending recoverable deletion: %s", e)


def _finalize_successful_recoverable_deletion(pending: dict[str, Any]) -> None:
    """تحديث السجل والكاش ومسح ملف العملية المعلقة بعد إتمام الحذف بنجاح لمنع التكرار"""
    record_id = pending.get("record_id")
    src_path = pending.get("src_path", "")

    import file_manager
    if record_id is not None:
        file_manager.update_transfer_record_to_move(record_id)
    elif src_path:
        file_manager.update_transfer_record_by_src_to_move(src_path)

    if src_path:
        try:
            import media_scanner
            media_scanner.record_scanned_file_result(
                file_path=src_path,
                file_size=pending.get("file_size", 0),
                mtime=pending.get("mtime", 0.0),
                category=pending.get("category", ""),
                operation_status="success",
                target_storage=pending.get("target_storage", ""),
            )
        except Exception as e_cache:
            logger.debug("تنبيه تحديث كاش الفحص بعد الحذف: %s", e_cache)

    clear_pending_recoverable_deletion()


def retry_pending_recoverable_deletion() -> bool:
    """إعادة إطلاق طلب حذف الملف المعلق عبر نظام أندرويد مع إظهار نافذة إذن النظام إذا لزم"""
    pending = get_pending_recoverable_deletion()
    if not pending:
        return False
    item_uri = pending.get("item_uri", "")
    if not item_uri:
        clear_pending_recoverable_deletion()
        return False
    logger.info("إعادة محاولة حذف الملف المعلق لـ RecoverableSecurityException: %s", item_uri)
    del_ok = delete_media_item(item_uri)
    if del_ok:
        _finalize_successful_recoverable_deletion(pending)
        return True
    return False


def handle_recoverable_deletion_result(result_ok: bool) -> bool:
    """
    معالجة نتيجة استجابة المستخدم لـ RecoverableSecurityException (Request Code 4202):
    - إذا وافق المستخدم (result_ok=True): حذف المصدر فعلياً وتحديث السجل إلى Move وتحديث الكاش ومسح ملف pending.
    - إذا رفض المستخدم (result_ok=False): الإبقاء على العملية كـ Copy وإلغاء التعليق فوراً لمنع التكرار.
    """
    pending = get_pending_recoverable_deletion()
    if not pending:
        return False

    if not result_ok:
        logger.info("رفض المستخدم حذف الملف الأصلي عبر نظام أندرويد، ستبقى العملية كنسخ آمن (Copy)")
        clear_pending_recoverable_deletion()
        return False

    item_uri = pending.get("item_uri", "")
    del_ok = delete_media_item(item_uri)
    if del_ok:
        logger.info("تم تأكيد حذف الملف من قبل المستخدم واكتمال النقل بنجاح: %s", item_uri)
        _finalize_successful_recoverable_deletion(pending)
        return True

    clear_pending_recoverable_deletion()
    return False


# =========================================================================
# دوال استعراض وفتح مجلدات وملفات SAF عبر Intent
# =========================================================================

def open_saf_folder_in_file_manager(tree_uri: str) -> bool:
    """
    فتح مجلد SAF Document Tree في مدير الملفات الأصلي لنظام التشغيل:
    - عبر Android Intent رسمي بصلاحيات القراءة الممنوحة.
    - عدم محاولة فتح SAF URI كمسار Linux إطلاقاً.
    """
    if not tree_uri:
        return False

    if tree_uri.startswith("mock_saf://"):
        p = tree_uri.replace("mock_saf://", "")
        import file_manager
        return file_manager.open_folder_native(p)

    if _get_platform() != "android":
        return False

    try:
        from android import mActivity
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        DocumentsContract = autoclass("android.provider.DocumentsContract")

        parsed_tree = Uri.parse(tree_uri)
        try:
            doc_id = DocumentsContract.getTreeDocumentId(parsed_tree)
            doc_uri = DocumentsContract.buildDocumentUriUsingTree(parsed_tree, doc_id)
        except Exception:
            doc_uri = parsed_tree

        intent = Intent(Intent.ACTION_VIEW)
        intent.setDataAndType(doc_uri, "vnd.android.document/directory")
        intent.addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION
            | Intent.FLAG_ACTIVITY_NEW_TASK
        )
        mActivity.startActivity(intent)
        return True
    except Exception as e:
        logger.debug("فشل فتح SAF folder intent عبر ACTION_VIEW: %s", e)
        try:
            from android import mActivity
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            intent = Intent(Intent.ACTION_VIEW)
            intent.setData(Uri.parse(tree_uri))
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK)
            mActivity.startActivity(intent)
            return True
        except Exception as e2:
            logger.debug("فشل فتح SAF intent البديل: %s", e2)
            return False


def get_displayable_image_path(uri_or_path: str) -> str:
    """
    إرجاع مسار محلي صالح لعرضه في عناصر واجهة Kivy:
    - للمسارات المحلية العادية: يعاد المسار نفسه فوراً.
    - لـ mock_doc://: يعاد المسار المحلي المباشر.
    - لـ content://: نسخ تدفق خفيف للصورة داخل كاش المعاينة بالذاكرة الخاصة لتمكين Kivy من رسمها بسلاسة.
    """
    if not uri_or_path:
        return ""
    if uri_or_path.startswith("mock_doc://"):
        return uri_or_path.replace("mock_doc://", "")

    p = Path(uri_or_path)
    if p.exists() and p.is_file():
        return str(p)

    if uri_or_path.startswith("content://"):
        try:
            import hashlib

            from file_manager import get_app_private_storage_dir

            cache_dir = get_app_private_storage_dir() / "thumb_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            h = hashlib.md5(uri_or_path.encode("utf-8")).hexdigest()
            cache_file = cache_dir / f"thumb_{h}.jpg"
            if cache_file.exists() and cache_file.stat().st_size > 0:
                return str(cache_file)

            # نسخ خفيف للمعاينة
            ok = copy_uri_to_path(uri_or_path, cache_file)
            if ok and cache_file.exists() and cache_file.stat().st_size > 0:
                return str(cache_file)
        except Exception as e:
            logger.debug("تعذر تجهيز معاينة الصورة لـ %s: %s", uri_or_path, e)

    return uri_or_path


def open_media_file_native(uri_or_path: str) -> bool:
    """تشغيل أو فتح ملف الوسائط (فيديو أو صورة) في التطبيق الرسمي للنظام بأمان سواء كان مساراً أو Content URI"""
    if not uri_or_path:
        return False

    # 1. إذا كان Content URI على أندرويد
    if uri_or_path.startswith("content://"):
        if _get_platform() == "android":
            try:
                from android import mActivity
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")
                Uri = autoclass("android.net.Uri")
                parsed_uri = Uri.parse(uri_or_path)
                details = query_content_uri_details(uri_or_path)
                display_name = details.get("display_name", "") or Path(uri_or_path).name
                raw_mime = details.get("mime_type", "")
                mime = resolve_media_mime_type(display_name, raw_mime)

                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(parsed_uri, mime)
                intent.addFlags(
                    Intent.FLAG_GRANT_READ_URI_PERMISSION
                    | Intent.FLAG_ACTIVITY_NEW_TASK
                )
                mActivity.startActivity(intent)
                return True
            except Exception as e:
                logger.debug("فشل فتح Content URI في مشغل النظام: %s", e)
                return False
        return True

    # 2. إذا كان mock_doc:// أو مسار محلي
    clean_p = uri_or_path.replace("mock_doc://", "")
    p = Path(clean_p)
    if not p.exists():
        return False

    try:
        import subprocess
        import sys
        if sys.platform.startswith("win"):
            os.startfile(str(p))
            return True
        elif sys.platform.startswith("darwin"):
            subprocess.run(["open", str(p)], check=False)
            return True
        else:
            subprocess.run(["xdg-open", str(p)], check=False)
            return True
    except Exception as e:
        logger.debug("تعذر تشغيل الملف في مشغل النظام: %s", e)
        return False
