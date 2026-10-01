"""
طبقة التخزين الموحدة (Unified Storage Layer):
- عزل منطق التخزين عن التعامل المباشر مع Path وأنظمة الملفات التقليدية.
- دعم كامل لتخزين أندرويد الحديث (Scoped Storage, MediaStore, Storage Access Framework).
- دعم بطاقات MicroSD الخارجية عبر المسار المباشر أو Document URI (SAF).
- التحقق الفعلي من إمكانية القراءة والكتابة دون افتراضات خاطئة.
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
                        # حل تعارض الأسماء
                        if target_file.exists():
                            target_file = std_dir / f"{item.stem}_{int(time.time())}{item.suffix}"
                        shutil.move(str(item), str(target_file))
                        migrated_count += 1
                # حذف المجلد القديم الفارغ
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
    try:
        from kivy.utils import platform
        if platform == "android":
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
        from kivy.utils import platform
        if platform != "android":
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
        # كود الطلب المخصص لـ SAF
        SAF_REQUEST_CODE = 4201
        mActivity.startActivityForResult(intent, SAF_REQUEST_CODE)
        logger.info("تم إطلاق منتقي المجلدات SAF بنجاح (Request Code: %d)", SAF_REQUEST_CODE)
        return True
    except Exception as e:
        logger.error("تعذر إطلاق منتقي المجلدات SAF: %s", e)
        return False


def detect_storage_locations() -> dict[str, StorageLocation]:
    """
    استكشاف دقيق وشامل لجميع مواقع التخزين المتاحة على الجهاز
    مع بيان إمكانية الكتابة بدقة دون خداع المستخدم أو إخفاء المشاكل.
    """
    locations: dict[str, StorageLocation] = {}

    try:
        from kivy.utils import platform
        if platform == "android":
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

    # فحص مسارات /storage
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

    if not found_root:
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

    # فحص الكتابة المباشرة في مجلد الملفات المنظمة
    sd_target = found_root / ORGANIZED_FOLDER_NAME
    direct_writable = is_directory_writable(sd_target)

    # هل تتوفر كتابة مباشرة أم يلزم SAF؟
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


# =========================================================================
# دوال النسخ والنقل الموحدة (Unified Stream Transfer Layer)
# =========================================================================

def copy_path_to_path(src_file: Path, dest_file: Path) -> bool:
    """
    نسخ آمن من مسار إلى مسار مع كتابة مؤقتة (Atomic Copy) والتحقق من الحجم.
    """
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

        # استبدال ذري بالملف النهائي
        temp_dest.replace(dest_file)
        return True
    except Exception as e:
        logger.error("خطأ أثناء نسخ الملف من مسار لمسار: %s", e)
        temp_dest.unlink(missing_ok=True)
        return False


def copy_uri_to_path(content_uri: str, dest_file: Path) -> bool:
    """
    نسخ ملف من Content URI (أندرويد MediaStore / SAF) إلى مسار محلي
    عبر تدفق آمن ContentResolver.openInputStream.
    """
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_file.parent / f".tmp_uri_{dest_file.name}_{int(time.time() * 1000)}"

    try:
        from kivy.utils import platform
        if platform == "android":
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
            # محاكاة لسطح المكتب
            p = Path(content_uri)
            if p.exists():
                return copy_path_to_path(p, dest_file)
            return False
    except Exception as e:
        logger.error("فشل نسخ Content URI إلى مسار محلي: %s", e)
        temp_dest.unlink(missing_ok=True)
        return False


def copy_path_to_saf_uri(src_file: Path, saf_tree_uri: str, subfolder: str, filename: str) -> str:
    """
    نسخ ملف محلي إلى بطاقة SD عبر إذن Storage Access Framework و DocumentFile.
    العائد: URI الملف المنشأ في الوجهة كـ string، أو فارغ عند الفشل.
    """
    if not src_file.exists():
        return ""
    try:
        from kivy.utils import platform
        if platform == "android":
            from android import mActivity
            from jnius import autoclass
            Uri = autoclass("android.net.Uri")
            DocumentFile = autoclass("androidx.documentfile.provider.DocumentFile")

            parsed_tree = Uri.parse(saf_tree_uri)
            root_doc = DocumentFile.fromTreeUri(mActivity, parsed_tree)
            if not root_doc or not root_doc.canWrite():
                logger.error("مجلد SAF غير قابل للكتابة!")
                return ""

            # البحث عن المجلد المنظم أو إنشاؤه
            target_dir = root_doc.findFile(ORGANIZED_FOLDER_NAME)
            if not target_dir:
                target_dir = root_doc.createDirectory(ORGANIZED_FOLDER_NAME)

            # المجلد الفرعي للتصنيف
            sub_dir = target_dir
            for part in subfolder.replace("\\", "/").split("/"):
                part_clean = part.strip()
                if not part_clean:
                    continue
                next_d = sub_dir.findFile(part_clean)
                if not next_d:
                    next_d = sub_dir.createDirectory(part_clean)
                sub_dir = next_d

            # تخمين نوع الوسائط
            ext = src_file.suffix.lower()
            mime = "image/jpeg"
            if ext in VIDEO_EXTENSIONS:
                mime = "video/mp4"

            # إنشاء الملف الهدف
            new_file_doc = sub_dir.createFile(mime, filename)
            if not new_file_doc:
                logger.error("فشل إنشاء ملف الوجهة في SAF Document!")
                return ""

            dest_uri = new_file_doc.getUri()
            cr = mActivity.getContentResolver()
            out_stream = cr.openOutputStream(dest_uri)
            if not out_stream:
                logger.error("تعذر فتح دفق الكتابة للـ DocumentFile!")
                return ""

            with open(src_file, "rb") as in_f:
                buf = bytearray(64 * 1024)
                while True:
                    chunk = in_f.read(len(buf))
                    if not chunk:
                        break
                    out_stream.write(chunk)

            out_stream.close()
            return str(dest_uri.toString())
        return ""
    except Exception as e:
        logger.error("فشل نسخ الملف إلى SAF Document: %s", e)
        return ""


def delete_media_item(item: MediaItem | Path | str) -> bool:
    """حذف الملف المصدر بأمان (لنمط النقل Move) سواء كان مساراً فيزيائياً أو Content URI"""
    try:
        if isinstance(item, MediaItem):
            if item.source_type == "path" and item.path:
                p = Path(item.path)
                if p.exists():
                    p.unlink()
                    return True
            elif item.source_type == "content_uri" and item.uri:
                from kivy.utils import platform
                if platform == "android":
                    from android import mActivity
                    from jnius import autoclass
                    Uri = autoclass("android.net.Uri")
                    cr = mActivity.getContentResolver()
                    deleted = cr.delete(Uri.parse(item.uri), None, None)
                    return deleted > 0
                return False

        elif isinstance(item, Path):
            if item.exists():
                item.unlink()
                return True

        elif isinstance(item, str):
            if item.startswith("content://"):
                from kivy.utils import platform
                if platform == "android":
                    from android import mActivity
                    from jnius import autoclass
                    Uri = autoclass("android.net.Uri")
                    cr = mActivity.getContentResolver()
                    deleted = cr.delete(Uri.parse(item), None, None)
                    return deleted > 0
                return False
            else:
                p = Path(item)
                if p.exists():
                    p.unlink()
                    return True

        return False
    except Exception as e:
        logger.warning("تعذر حذف الملف المصدر %s: %s", item, e)
        return False
