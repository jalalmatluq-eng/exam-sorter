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

import logging
import os
import re
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
        return ".jpg" if "image" in self.mime_type else ".mp4"

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
        save_sorter_preferences({"saf_sdcard_uri": str(uri_str)})
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
                    if perm and str(perm.getUri()) == uri_str:
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

    is_writable = direct_writable or has_valid_saf
    requires_saf = not direct_writable and not has_valid_saf
    fail_reason = ""

    if requires_saf:
        fail_reason = "تتطلب بطاقة SD اختيار مجلد الحفظ عبر SAF لمنح إذن الكتابة"
        desc = f"مركبة ({found_root}) ولكن تحتاج إذن المجلد (SAF)"
    elif has_valid_saf and not direct_writable:
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

        if not sd or not sd.detected:
            # التحقق هل يوجد إذن SAF صالح مسبقاً حتى لو فشل كشف الروت الفيزيائي
            saf_uri = get_saf_persisted_uri()
            if is_saf_uri_valid(saf_uri):
                return TargetLocation(
                    storage_type="sdcard",
                    is_saf=True,
                    tree_uri=saf_uri,
                    display_name="بطاقة الذاكرة الخارجية (SAF)",
                    is_valid=True,
                )
            return TargetLocation(
                storage_type="sdcard",
                is_saf=False,
                is_valid=False,
                error_message="بطاقة الذاكرة الخارجية (MicroSD) غير متوفرة أو غير مركبة بالجهاز.",
            )

        # إذا كانت قابلة للكتابة المباشرة (مثل بيئات Android 9 أو مجلد التطبيق المخصص)
        if sd.writable and not sd.requires_saf and sd.path and sd.path != "غير متوفرة حالياً":
            target_p = Path(sd.path)
            return TargetLocation(
                storage_type="sdcard",
                is_saf=False,
                path=target_p,
                display_name=sd.name,
                is_valid=True,
            )

        # بطاقة SD تتطلب SAF
        saf_uri = sd.uri or get_saf_persisted_uri()
        if is_saf_uri_valid(saf_uri):
            return TargetLocation(
                storage_type="sdcard",
                is_saf=True,
                tree_uri=saf_uri,
                display_name="بطاقة الذاكرة الخارجية عبر SAF",
                is_valid=True,
            )

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
            root_doc = DocFileClass.fromTreeUri(mActivity, parsed_tree)
            if not root_doc or not root_doc.canWrite():
                logger.error("مجلد SAF غير قابل للكتابة عبر DocumentFile!")
                return ""

            target_org = root_doc.findFile(ORGANIZED_FOLDER_NAME)
            if not target_org:
                target_org = root_doc.createDirectory(ORGANIZED_FOLDER_NAME)

            sub_dir = target_org
            for part in category_name.replace("\\", "/").split("/"):
                p_clean = part.strip()
                if not p_clean:
                    continue
                next_d = sub_dir.findFile(p_clean)
                if not next_d:
                    next_d = sub_dir.createDirectory(p_clean)
                sub_dir = next_d

            return str(sub_dir.getUri().toString())

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

    except Exception as e:
        logger.error("فشل إنشاء مجلد التصنيف في SAF: %s", e, exc_info=True)
        return ""


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


def scan_saf_tree_recursively(tree_uri: str, max_depth: int = 10) -> list[MediaItem]:
    """
    قارئ حقيقي وشامل لشجرة SAF Tree URI:
    - فحص شجري عودي (recursive) لجميع المجلدات والملفات داخل الشجرة عبر DocumentsContract / DocumentFile.
    - استخراج الصور والفيديوهات وإنشاء MediaItem لكل ملف مع تفاصيله الدقيقة.
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
            try:
                rel = Path(root).relative_to(base_dir)
                if len(rel.parts) > max_depth:
                    dirs[:] = []
                    continue
            except ValueError:
                pass

            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d.lower() not in (ORGANIZED_FOLDER_NAME.lower(), "mediasorter", "lost.dir", ".android")
            ]

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

        # طابور التفرع: (document_uri, current_depth)
        queue: list[tuple[Any, int]] = [(root_doc_uri, 0)]
        visited_doc_ids: set[str] = set()

        MIME_DIR = "vnd.android.document/directory"

        while queue:
            curr_doc_uri, depth = queue.pop(0)
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
                    if c_name.startswith(".") or c_name_lower in (ORGANIZED_FOLDER_NAME.lower(), "mediasorter", "lost.dir", ".android"):
                        continue

                    child_doc_uri = DocumentsContract.buildDocumentUriUsingTree(parsed_tree, c_id)

                    if c_mime == MIME_DIR:
                        queue.append((child_doc_uri, depth + 1))
                    else:
                        ext = Path(c_name).suffix.lower()
                        is_img = (ext in IMAGE_EXTENSIONS) or (c_mime and "image" in c_mime)
                        is_vid = (ext in VIDEO_EXTENSIONS) or (c_mime and "video" in c_mime)
                        if is_img or is_vid:
                            doc_uri_str = str(child_doc_uri.toString())
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


def copy_uri_to_path(content_uri: str, dest_file: Path) -> bool:
    """نسخ ملف من Content URI (MediaStore / SAF) إلى مسار محلي عبر دفق آمن"""
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_file.parent / f".tmp_uri_{dest_file.name}_{int(time.time() * 1000)}"

    # دعم المحاكاة لبيئات الاختبار
    if content_uri.startswith("mock_doc://"):
        src_mock = Path(content_uri.replace("mock_doc://", ""))
        return copy_path_to_path(src_mock, dest_file)

    try:
        if _get_platform() == "android":
            from android import mActivity
            from jnius import autoclass
            Uri = autoclass("android.net.Uri")
            parsed_uri = Uri.parse(content_uri)
            cr = mActivity.getContentResolver()
            in_stream = cr.openInputStream(parsed_uri)
            if in_stream is None:
                logger.error("تعذر فتح دفق القراءة للـ URI: %s", content_uri)
                return False

            total_written = 0
            CHUNK_SIZE = 64 * 1024
            buffer = bytearray(CHUNK_SIZE)

            with open(temp_dest, "wb") as out_f:
                while True:
                    read_bytes = in_stream.read(buffer)
                    if read_bytes == -1 or read_bytes == 0:
                        break
                    out_f.write(buffer[:read_bytes])
                    total_written += read_bytes

            in_stream.close()

            if total_written == 0:
                logger.error("تم قراءة 0 بايت من URI: %s", content_uri)
                temp_dest.unlink(missing_ok=True)
                return False

            temp_dest.replace(dest_file)
            return True
        else:
            p = Path(content_uri)
            if p.exists():
                return copy_path_to_path(p, dest_file)
            return False
    except Exception as e:
        logger.error("فشل نسخ Content URI إلى مسار محلي: %s", e)
        temp_dest.unlink(missing_ok=True)
        return False


def copy_path_to_saf_uri(src_file: Path, saf_tree_uri: str, category: str, filename: str) -> str:
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
        from jnius import autoclass
        Uri = autoclass("android.net.Uri")
        cr = mActivity.getContentResolver()

        cat_doc_uri_str = saf_find_or_create_directory(saf_tree_uri, category)
        if not cat_doc_uri_str:
            logger.error("تعذر تهيئة مجلد التصنيف في SAF للوجهة!")
            return ""

        parsed_cat_uri = Uri.parse(cat_doc_uri_str)

        # تخمين نوع الوسائط
        ext = src_file.suffix.lower()
        mime = "video/mp4" if ext in VIDEO_EXTENSIONS else "image/jpeg"

        # إنشاء الملف
        new_file_uri = None
        DocFileClass = _saf_get_document_file_class()
        if DocFileClass is not None:
            cat_doc = DocFileClass.fromTreeUri(mActivity, parsed_cat_uri)
            if cat_doc:
                existing = cat_doc.findFile(filename)
                if existing and existing.exists():
                    if existing.length() == src_size:
                        return str(existing.getUri().toString())
                new_doc = cat_doc.createFile(mime, filename)
                if new_doc:
                    new_file_uri = new_doc.getUri()

        if new_file_uri is None:
            DocumentsContract = autoclass("android.provider.DocumentsContract")
            new_file_uri = DocumentsContract.createDocument(cr, parsed_cat_uri, mime, filename)

        if not new_file_uri:
            logger.error("فشل إنشاء ملف الوجهة في SAF!")
            return ""

        created_uri_str = str(new_file_uri.toString())

        out_stream = cr.openOutputStream(new_file_uri)
        if not out_stream:
            logger.error("تعذر فتح دفق الكتابة لملف SAF!")
            return ""

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
            logger.error("عدم تطابق البايتات المكتوبة إلى SAF: كتب %d من %d", total_written, src_size)
            return ""

        # استعلام الحجم النهائي الفعلي بعد إغلاق OutputStream من نظام الملفات
        final_size = get_uri_file_size(created_uri_str)
        if final_size != src_size:
            logger.error("عدم تطابق الحجم النهائي لملف SAF: المتوقع %d، الفعلي %d", src_size, final_size)
            return ""

        is_success = True
        return created_uri_str

    except Exception as e:
        logger.error("فشل نسخ الملف إلى SAF: %s", e, exc_info=True)
        return ""
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


def copy_uri_to_saf_uri(src_content_uri: str, saf_tree_uri: str, category: str, filename: str, expected_size: int = 0) -> str:
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

        cat_doc_uri_str = saf_find_or_create_directory(saf_tree_uri, category)
        if not cat_doc_uri_str:
            return ""

        parsed_cat_uri = Uri.parse(cat_doc_uri_str)
        src_parsed = Uri.parse(src_content_uri)

        in_stream = cr.openInputStream(src_parsed)
        if not in_stream:
            logger.error("تعذر فتح دفق المصدر للـ URI: %s", src_content_uri)
            return ""

        ext = Path(filename).suffix.lower()
        mime = "video/mp4" if ext in VIDEO_EXTENSIONS else "image/jpeg"

        DocFileClass = _saf_get_document_file_class()
        new_file_uri = None
        if DocFileClass is not None:
            cat_doc = DocFileClass.fromTreeUri(mActivity, parsed_cat_uri)
            if cat_doc:
                new_doc = cat_doc.createFile(mime, filename)
                if new_doc:
                    new_file_uri = new_doc.getUri()

        if new_file_uri is None:
            DocumentsContract = autoclass("android.provider.DocumentsContract")
            new_file_uri = DocumentsContract.createDocument(cr, parsed_cat_uri, mime, filename)

        if not new_file_uri:
            return ""

        created_uri_str = str(new_file_uri.toString())

        out_stream = cr.openOutputStream(new_file_uri)
        if not out_stream:
            return ""

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
            logger.error("عدم تطابق الحجم عند نسخ URI إلى SAF: كتب %d من %d", total_written, expected_size)
            return ""

        final_size = get_uri_file_size(created_uri_str)
        if expected_size > 0 and final_size != expected_size:
            logger.error("عدم تطابق الحجم النهائي لملف SAF: المتوقع %d، الفعلي %d", expected_size, final_size)
            return ""

        is_success = True
        return created_uri_str

    except Exception as e:
        logger.error("فشل نسخ Content URI إلى SAF: %s", e, exc_info=True)
        return ""
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
                            # طلب تأكيد أندرويد لحذف الملف
                            user_action = sec_e.getUserAction()
                            intent_sender = user_action.getActionIntent().getIntentSender()
                            RECOVERABLE_REQUEST_CODE = 4202
                            mActivity.startIntentSenderForResult(
                                intent_sender, RECOVERABLE_REQUEST_CODE, None, 0, 0, 0
                            )
                            logger.info("تم إطلاق نافذة تأكيد حذف أندرويد الرسمية (Request Code: %d)", RECOVERABLE_REQUEST_CODE)
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

