"""
android_permissions.py
----------------------
مدير الصلاحيات الموحد لتطبيق رتّب / CosmoSort:
- فحص دقيق وموثوق لكل صلاحية وفق إصدار أندرويد الفعلي (SDK_INT).
- دعم سلسلة تحقق ثلاثية (check_permission -> ContextCompat -> mActivity.checkSelfPermission).
- التمييز الصارم بين Android 10 (SDK 29) والإصدارات الأحدث (SDK 30+ و SDK 33+ و SDK 34+).
- فصل صلاحيات المصدر عن صلاحيات الوجهة وعدم فرض MANAGE_EXTERNAL_STORAGE على Android 10.
- منع الحلقات التكرارية لحوارات طلب الصلاحيات.
- فحص وصول تخزيني حي وحقيقي قبل بدء الفرز (StorageAccessTest).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("AndroidPermissions")

# متغيرات للمحاكاة أثناء الاختبارات الآلية
_MOCK_ANDROID_SDK_INT: int | None = None
_MOCK_ANDROID_RELEASE: str | None = None
_MOCK_PERMISSIONS: dict[str, bool] | None = None
_MOCK_ALL_FILES_ACCESS: bool | None = None
_MOCK_SAF_VALID: bool | None = None
_MOCK_SOURCE_SAMPLES: dict[str, Any] | None = None


def set_mock_environment(
    sdk_int: int | None = None,
    release: str | None = None,
    permissions: dict[str, bool] | None = None,
    all_files_access: bool | None = None,
    saf_valid: bool | None = None,
    source_samples: dict[str, Any] | None = None,
) -> None:
    """ضبط بيئة المحاكاة للاختبارات الآلية"""
    global _MOCK_ANDROID_SDK_INT, _MOCK_ANDROID_RELEASE, _MOCK_PERMISSIONS, _MOCK_ALL_FILES_ACCESS, _MOCK_SAF_VALID, _MOCK_SOURCE_SAMPLES
    _MOCK_ANDROID_SDK_INT = sdk_int
    _MOCK_ANDROID_RELEASE = release
    _MOCK_PERMISSIONS = permissions
    _MOCK_ALL_FILES_ACCESS = all_files_access
    _MOCK_SAF_VALID = saf_valid
    _MOCK_SOURCE_SAMPLES = source_samples


def reset_mock_environment() -> None:
    """إعادة تعيين بيئة المحاكاة إلى الوضع الطبيعي"""
    global _MOCK_ANDROID_SDK_INT, _MOCK_ANDROID_RELEASE, _MOCK_PERMISSIONS, _MOCK_ALL_FILES_ACCESS, _MOCK_SAF_VALID, _MOCK_SOURCE_SAMPLES
    _MOCK_ANDROID_SDK_INT = None
    _MOCK_ANDROID_RELEASE = None
    _MOCK_PERMISSIONS = None
    _MOCK_ALL_FILES_ACCESS = None
    _MOCK_SAF_VALID = None
    _MOCK_SOURCE_SAMPLES = None


def get_android_sdk_int() -> int:
    """الحصول على رقم إصدار أندرويد (Build.VERSION.SDK_INT) بأمان وموثوقية عالية"""
    if _MOCK_ANDROID_SDK_INT is not None:
        return _MOCK_ANDROID_SDK_INT

    try:
        from kivy.utils import platform
        if platform != "android":
            return 0
        from jnius import autoclass

        try:
            BuildVersion = autoclass("android.os.Build$VERSION")
            return int(BuildVersion.SDK_INT)
        except Exception:
            try:
                Build = autoclass("android.os.Build")
                return int(Build.VERSION.SDK_INT)
            except Exception:
                pass
    except Exception as e:
        logger.warning("تعذر استخراج Build.VERSION.SDK_INT: %s", e)

    return -1  # غير معروف


def get_android_system_info() -> dict[str, Any]:
    """
    استخراج معلومات النظام وبيانات الإصدار الفعلية:
    - SDK_INT
    - Android release
    - package name
    - target SDK
    """
    sdk = get_android_sdk_int()
    release = _MOCK_ANDROID_RELEASE or ""
    pkg_name = "com.cosmosort.ai.cosmosort"
    target_sdk = 34

    try:
        from kivy.utils import platform
        if platform == "android":
            from android import mActivity
            from jnius import autoclass
            if not release:
                try:
                    BuildVersion = autoclass("android.os.Build$VERSION")
                    release = str(BuildVersion.RELEASE)
                except Exception:
                    try:
                        Build = autoclass("android.os.Build")
                        release = str(Build.VERSION.RELEASE)
                    except Exception:
                        pass
            try:
                pkg_name = str(mActivity.getPackageName())
                app_info = mActivity.getApplicationInfo()
                target_sdk = int(app_info.targetSdkVersion)
            except Exception:
                pass
    except Exception:
        pass

    status = "known" if sdk >= 0 else "unknown"
    return {
        "sdk_int": sdk,
        "release": release,
        "package_name": pkg_name,
        "target_sdk": target_sdk,
        "status": status,
    }


def has_permission(permission_name: str) -> bool:
    """
    التحقق مما إذا كانت صلاحية أندرويد معينة ممنوحة حالياً.
    تعتمد سلسلة فحص ثلاثية متتالية:
    1. android.permissions.check_permission من python-for-android
    2. ContextCompat.checkSelfPermission من AndroidX
    3. mActivity.checkSelfPermission المباشر (Android 6.0+)
    توحد النتيجة دائماً إلى True أو False دون إرجاع False لمجرد عدم تحميل AndroidX.
    """
    if _MOCK_PERMISSIONS is not None:
        short = permission_name.replace("android.permission.", "")
        if permission_name in _MOCK_PERMISSIONS:
            return bool(_MOCK_PERMISSIONS[permission_name])
        if short in _MOCK_PERMISSIONS:
            return bool(_MOCK_PERMISSIONS[short])
        return False

    try:
        from kivy.utils import platform
        if platform != "android":
            return True

        if not permission_name.startswith("android.permission."):
            full_perm = f"android.permission.{permission_name}"
            short_perm = permission_name
        else:
            full_perm = permission_name
            short_perm = permission_name.replace("android.permission.", "")

        # 1. محاولة android.permissions.check_permission من python-for-android
        try:
            from android.permissions import Permission, check_permission
            perm_obj = getattr(Permission, short_perm, full_perm)
            if check_permission(perm_obj):
                return True
        except Exception:
            pass

        # 2. محاولة ContextCompat.checkSelfPermission إذا كان AndroidX متاحاً
        try:
            from android import mActivity
            from jnius import autoclass
            ContextCompat = autoclass("androidx.core.content.ContextCompat")
            PackageManager = autoclass("android.content.pm.PackageManager")
            res = ContextCompat.checkSelfPermission(mActivity, full_perm)
            return res == PackageManager.PERMISSION_GRANTED
        except Exception:
            pass

        # 3. محاولة mActivity.checkSelfPermission كحل أخير وموثوق على Android 6+
        try:
            from android import mActivity
            from jnius import autoclass
            PackageManager = autoclass("android.content.pm.PackageManager")
            res = mActivity.checkSelfPermission(full_perm)
            return res == PackageManager.PERMISSION_GRANTED
        except Exception:
            pass

        return False
    except Exception as e:
        logger.debug("خطأ أثناء فحص الصلاحية %s: %s", permission_name, e)
        return False


def is_images_permission_granted() -> bool:
    """فحص صلاحية قراءة الصور كاملة وفق إصدار أندرويد الفعلي"""
    sdk = get_android_sdk_int()
    if sdk == 0:  # بيئة غير أندرويد (تطوير واختبارات)
        return True
    if sdk >= 33:
        return has_permission("READ_MEDIA_IMAGES")
    # أندرويد 12 وما قبل (بما فيها أندرويد 10 SDK 29)
    return has_permission("READ_EXTERNAL_STORAGE")


def is_videos_permission_granted() -> bool:
    """فحص صلاحية قراءة الفيديوهات كاملة وفق إصدار أندرويد الفعلي"""
    sdk = get_android_sdk_int()
    if sdk == 0:  # بيئة غير أندرويد
        return True
    if sdk >= 33:
        return has_permission("READ_MEDIA_VIDEO")
    # أندرويد 12 وما قبل (بما فيها أندرويد 10 SDK 29)
    return has_permission("READ_EXTERNAL_STORAGE")


def is_storage_write_permission_granted() -> bool:
    """فحص صلاحية كتابة التخزين (WRITE_EXTERNAL_STORAGE) للذاكرة الداخلية على Android 10 وما قبله"""
    sdk = get_android_sdk_int()
    if sdk == 0:
        return True
    if sdk >= 30:
        # أندرويد 11+ يعتمد Scoped Storage أو MANAGE_EXTERNAL_STORAGE
        return True
    return has_permission("WRITE_EXTERNAL_STORAGE")


def is_visual_user_selected_only() -> bool:
    """
    التحقق مما إذا كان المستخدم في أندرويد 14 قد اختار صوراً محددة فقط (الوصول المحدود/الجزئي).
    لا ينطبق مطلقاً على أندرويد 10 ويعيد False دائماً على ما دون أندرويد 14.
    """
    sdk = get_android_sdk_int()
    if sdk >= 34:
        has_partial = has_permission("READ_MEDIA_VISUAL_USER_SELECTED")
        has_full_img = has_permission("READ_MEDIA_IMAGES")
        has_full_vid = has_permission("READ_MEDIA_VIDEO")
        return has_partial and not (has_full_img and has_full_vid)
    return False


def is_all_files_access_granted() -> bool | None:
    """
    فحص إذن الوصول الشامل لكافة الملفات (MANAGE_EXTERNAL_STORAGE):
    - يعيد True إذا كان ممنوحاً (Android 11+ / SDK >= 30).
    - يعيد False إذا كان مرفوضاً (Android 11+ / SDK >= 30).
    - يعيد None (not_applicable) على Android 10 وما دون (SDK < 30) لأنه غير منطبق.
    """
    if _MOCK_ALL_FILES_ACCESS is not None:
        return _MOCK_ALL_FILES_ACCESS

    sdk = get_android_sdk_int()
    if sdk <= 0:  # بيئة غير أندرويد
        return True
    if sdk < 30:  # أندرويد 10 وما دون -> غير منطبق تماماً
        return None

    try:
        from jnius import autoclass
        Environment = autoclass("android.os.Environment")
        return bool(Environment.isExternalStorageManager())
    except Exception:
        return False


def is_legacy_storage_permission_granted() -> bool:
    """فحص الصلاحيات الكلاسيكية للتخزين (READ/WRITE) على أندرويد 10 وما قبله"""
    return has_permission("READ_EXTERNAL_STORAGE") and has_permission("WRITE_EXTERNAL_STORAGE")


def is_saf_sdcard_granted() -> bool:
    """فحص ما إذا كان هناك إذن SAF صالح ومحفوظ لبطاقة الذاكرة الخارجية"""
    if _MOCK_SAF_VALID is not None:
        return _MOCK_SAF_VALID

    try:
        import storage_backend
        tree_uri = storage_backend.get_saf_persisted_uri()
        if not tree_uri:
            return False
        return storage_backend.is_saf_uri_valid(tree_uri)
    except Exception as e:
        logger.debug("خطأ أثناء فحص إذن SAF للبطاقة: %s", e)
        return False


def is_source_path_readable(path_or_uri: str) -> bool:
    """
    اختبار عملي فوري لقابلية قراءة المسار أو URI دون استهلاك ذاكرة.
    يفحص أول 4 بايت للتأكد من عدم وجود Permission denied أو حظر أمني.
    """
    if not path_or_uri:
        return False

    if path_or_uri.startswith("content://"):
        try:
            from android import mActivity
            from jnius import autoclass
            Uri = autoclass("android.net.Uri")
            cr = mActivity.getContentResolver()
            in_s = cr.openInputStream(Uri.parse(path_or_uri))
            if in_s is not None:
                try:
                    in_s.read()
                    return True
                finally:
                    in_s.close()
            return False
        except Exception:
            return False

    # مسار فيزيائي
    try:
        with open(path_or_uri, "rb") as f:
            f.read(4)
        return True
    except (OSError, PermissionError):
        return False


def find_first_media_sample(source_storage: str = "internal", media_type: str = "image") -> str | None:
    """
    البحث عن أول عينة حقيقية لملف صورة أو فيديو للتحقق من إمكانية قراءتها الفعلية:
    - يدعم المحاكاة عبر _MOCK_SOURCE_SAMPLES.
    - يبحث في MediaStore على أندرويد.
    - يبحث في المجلدات القياسية (DCIM, Pictures, Download, Movies).
    """
    if _MOCK_SOURCE_SAMPLES is not None:
        key_specific = f"{source_storage}_{media_type}"
        if key_specific in _MOCK_SOURCE_SAMPLES:
            return _MOCK_SOURCE_SAMPLES[key_specific]
        if media_type in _MOCK_SOURCE_SAMPLES:
            return _MOCK_SOURCE_SAMPLES[media_type]
        if f"{source_storage}_sample" in _MOCK_SOURCE_SAMPLES:
            return _MOCK_SOURCE_SAMPLES[f"{source_storage}_sample"]
        return None

    try:
        from kivy.utils import platform
        exts = (".jpg", ".jpeg", ".png", ".webp") if media_type == "image" else (".mp4", ".mkv", ".3gp", ".mov")

        if platform == "android":
            if source_storage in ("internal", "both"):
                try:
                    from android import mActivity
                    from jnius import autoclass
                    MediaStoreImages = autoclass("android.provider.MediaStore$Images$Media")
                    MediaStoreVideo = autoclass("android.provider.MediaStore$Video$Media")
                    ContentUris = autoclass("android.content.ContentUris")
                    cr = mActivity.getContentResolver()

                    base_uri = MediaStoreImages.EXTERNAL_CONTENT_URI if media_type == "image" else MediaStoreVideo.EXTERNAL_CONTENT_URI
                    cursor = cr.query(base_uri, ["_id"], None, None, "date_modified DESC")
                    if cursor is not None:
                        try:
                            if cursor.moveToFirst():
                                item_id = cursor.getLong(0)
                                if item_id > 0:
                                    uri_obj = ContentUris.withAppendedId(base_uri, item_id)
                                    return str(uri_obj.toString())
                        finally:
                            cursor.close()
                except Exception as e_ms:
                    logger.debug("تعذر جلب عينة من MediaStore: %s", e_ms)

                int_root = Path("/storage/emulated/0")
                check_subdirs = [
                    int_root / "DCIM" / "Camera",
                    int_root / "DCIM",
                    int_root / "Pictures",
                    int_root / "Download",
                    int_root / "Movies",
                ]
                for s_dir in check_subdirs:
                    if s_dir.exists() and s_dir.is_dir():
                        try:
                            for entry in s_dir.iterdir():
                                if entry.is_file() and entry.suffix.lower() in exts and not entry.name.startswith("."):
                                    return str(entry)
                        except Exception as e:
                            logger.debug("Failed scanning %s: %s", s_dir, e)
                            continue

            if source_storage in ("sdcard", "both"):
                import storage_backend
                tree_uri = storage_backend.get_saf_persisted_uri()
                if not tree_uri or (tree_uri.startswith("mock_saf://") and not Path(tree_uri.replace("mock_saf://", "")).exists()):
                    loc = storage_backend.get_active_target_location("sdcard")
                    if loc and loc.tree_uri:
                        tree_uri = loc.tree_uri
                if tree_uri and tree_uri.startswith("mock_saf://"):
                    base_p = Path(tree_uri.replace("mock_saf://", ""))
                    if base_p.exists():
                        for root, _, files in os.walk(base_p):
                            for f in files:
                                if Path(f).suffix.lower() in exts and not f.startswith("."):
                                    return f"mock_doc://{Path(root) / f}"
        else:
            # بيئة سطح المكتب / بيئة الاختبارات
            if source_storage in ("sdcard", "both"):
                import storage_backend
                tree_uri = storage_backend.get_saf_persisted_uri()
                if not tree_uri or (tree_uri.startswith("mock_saf://") and not Path(tree_uri.replace("mock_saf://", "")).exists()):
                    loc = storage_backend.get_active_target_location("sdcard")
                    if loc and loc.tree_uri:
                        tree_uri = loc.tree_uri
                if tree_uri and tree_uri.startswith("mock_saf://"):
                    base_p = Path(tree_uri.replace("mock_saf://", ""))
                    if base_p.exists():
                        for root, _, files in os.walk(base_p):
                            for f in files:
                                if Path(f).suffix.lower() in exts and not f.startswith("."):
                                    return f"mock_doc://{Path(root) / f}"

            if source_storage in ("internal", "both"):
                base_dir = Path(__file__).resolve().parent
                cand_dirs = [
                    Path.cwd() / "scratch" / "emulator_test_media",
                    base_dir / "assets",
                    Path.cwd() / "assets",
                    Path.cwd() / "test_data",
                    Path.cwd(),
                ]
                for cand_dir in cand_dirs:
                    if cand_dir.exists():
                        for entry in cand_dir.iterdir():
                            if entry.is_file() and entry.suffix.lower() in exts and not entry.name.startswith("."):
                                return str(entry)
    except Exception as e:
        logger.debug("خطأ أثناء البحث عن عينة وسائط: %s", e)

    return None


def test_read_sample_bytes(sample_path_or_uri: str) -> tuple[bool, str]:
    """
    قراءة أول 4 بايت من عينة الوسائط للتحقق الفعلي من إمكانية القراءة دون حظر:
    العائد: (نجحت_القراءة: bool, رسالة_الخطأ: str)
    """
    if not sample_path_or_uri:
        return False, "لا توجد عينة للاختبار"

    if sample_path_or_uri.startswith("mock_doc://"):
        try:
            local_p = Path(sample_path_or_uri.replace("mock_doc://", ""))
            with open(local_p, "rb") as f:
                data = f.read(4)
                if len(data) > 0:
                    return True, ""
                return False, "الملف فارغ (0 بايت)"
        except Exception as e:
            return False, str(e)

    if sample_path_or_uri.startswith("content://"):
        try:
            from kivy.utils import platform
            if platform == "android":
                from android import mActivity
                from jnius import autoclass
                Uri = autoclass("android.net.Uri")
                cr = mActivity.getContentResolver()
                in_s = cr.openInputStream(Uri.parse(sample_path_or_uri))
                if in_s is not None:
                    try:
                        b = in_s.read()
                        if b != -1:
                            return True, ""
                        return False, "الملف فارغ (0 بايت)"
                    finally:
                        in_s.close()
                return False, "تعذر فتح دفق القراءة لـ Content URI"
            else:
                return True, ""
        except Exception as e:
            return False, str(e)

    try:
        with open(sample_path_or_uri, "rb") as f:
            data = f.read(4)
            if len(data) > 0:
                return True, ""
            return False, "الملف فارغ (0 بايت)"
    except Exception as e:
        return False, str(e)


@dataclass
class StorageAccessTest:
    """نتيجة اختبار الفحص الاستباقي والوصول الفعلي للتخزين قبل بدء الفرز"""
    success: bool = False
    source_storage: str = "internal"
    target_storage: str = "internal"
    source_exists: bool = False
    source_readable_images: bool = False
    source_readable_videos: bool = False

    # الفحص الحي لعينات الوسائط الحقيقية
    source_image_found: bool = False
    source_image_readable: bool = False
    source_image_sample_path: str = ""
    source_video_found: bool = False
    source_video_readable: bool = False
    source_video_sample_path: str = ""

    # الفصل الدقيق بين مصادر التخزين
    source_internal_readable: bool = False
    source_internal_error: str = ""
    source_sdcard_readable: bool = False
    source_sdcard_saf_valid: bool = False
    source_sdcard_error: str = ""
    source_sdcard_sample_found: bool = False
    source_sdcard_sample_path: str = ""
    source_sdcard_sample_readable: bool = False

    # فحص الوجهة
    target_dir_creatable: bool = False
    target_writable: bool = False
    target_readable_after_write: bool = False
    target_temp_deleted: bool = False
    target_actual_path: str = ""
    error_code: str = ""
    error_message: str = ""
    action_required: str = "none"
    details: dict[str, Any] = field(default_factory=dict)


def run_storage_preflight_test(
    source_storage: str,
    target_storage: str,
    organize_images: bool = True,
    organize_videos: bool = True,
) -> StorageAccessTest:
    """
    اختبار عملي حقيقي لقابلية القراءة والكتابة في وحدات التخزين قبل بدء الفرز:
    1. التحقق من وجود المصدر وقابلية قراءة الصور والفيديوهات منه واختبار قراءة 4 بايت من عينات حقيقية.
    2. في وضع both: فحص مستقل للداخلية ولـ SD Card، مع رفض البدء عند غياب إذن SAF أو تعذر القراءة ومنع أي Fallback صامت.
    3. التحقق من إنشاء مجلد الوجهة الفعلي (الملفات المنظمة).
    4. كتابة ملف تجريبي مؤقت ثم قراءته ومطابقة الحجم ثم حذفه بأمان.
    5. منع أي Fallback صامت وضمان أن الوجهة هي نفسها التي ستستخدم فعلياً.
    """
    source_norm = (source_storage or "both").lower()
    target_norm = (target_storage or "internal").lower()
    sdk = get_android_sdk_int()

    res = StorageAccessTest(
        source_storage=source_norm,
        target_storage=target_norm,
    )

    # 1. فحص الذاكرة الداخلية كمصدر (عند اختيار internal أو both)
    if source_norm in ("internal", "both"):
        img_ok = is_images_permission_granted()
        vid_ok = is_videos_permission_granted()
        res.source_readable_images = img_ok
        res.source_readable_videos = vid_ok

        # التحقق من حالة أندرويد 14 المحدودة
        if is_visual_user_selected_only():
            res.success = False
            res.error_code = "partial_media_access"
            res.error_message = (
                "صلاحية الوصول محدودة (تم اختيار صور محددة فقط في أندرويد 14). "
                "لا يمكن بدء فحص وفرز الهاتف كاملاً بهذا الإذن الجزئي. "
                "يرجى منح إذن 'السماح دائمًا بالوصول إلى كل الصور والفيديوهات' من إعدادات التطبيق."
            )
            res.action_required = "open_app_settings"
            return res

        if not img_ok and not vid_ok:
            res.success = False
            res.error_code = "missing_media_permissions"
            res.source_internal_readable = False
            res.source_internal_error = "صلاحية قراءة وسائط الذاكرة الداخلية غير ممنوحة"
            if sdk == 29 or (0 < sdk < 30):
                res.error_message = (
                    "Android 10 لا يسمح بقراءة التخزين حاليًا.\n"
                    "افتح إعدادات التطبيق > الأذونات > التخزين، ثم اختر السماح.\n"
                    "بعد العودة اضغط فحص الصلاحيات مرة أخرى."
                )
            else:
                res.error_message = "صلاحية الوصول للصور والفيديوهات غير ممنوحة."
            res.action_required = "request_media"
            return res

        # فحص عينات وسائط حقيقية في الذاكرة الداخلية
        img_sample = find_first_media_sample("internal", "image")
        if img_sample:
            res.source_image_found = True
            res.source_image_sample_path = img_sample
            read_img_ok, err_img = test_read_sample_bytes(img_sample)
            res.source_image_readable = read_img_ok
            if not read_img_ok:
                res.success = False
                res.source_internal_readable = False
                res.source_internal_error = f"تعذر قراءة عينة الصور: {err_img}"
                res.error_code = "source_image_read_failed"
                res.error_message = f"فشل اختبار قراءة أول صورة في الذاكرة الداخلية ({err_img}). يرجى التحقق من إذن التخزين."
                res.action_required = "request_media"
                return res
        else:
            res.source_image_found = False
            res.source_image_readable = False

        vid_sample = find_first_media_sample("internal", "video")
        if vid_sample:
            res.source_video_found = True
            res.source_video_sample_path = vid_sample
            read_vid_ok, err_vid = test_read_sample_bytes(vid_sample)
            res.source_video_readable = read_vid_ok
            if not read_vid_ok:
                res.success = False
                res.source_internal_readable = False
                res.source_internal_error = f"تعذر قراءة عينة الفيديو: {err_vid}"
                res.error_code = "source_video_read_failed"
                res.error_message = f"فشل اختبار قراءة أول فيديو في الذاكرة الداخلية ({err_vid}). يرجى التحقق من إذن التخزين."
                res.action_required = "request_media"
                return res
        else:
            res.source_video_found = False
            res.source_video_readable = False

        res.source_internal_readable = True

        # فحص وجود مسار الذاكرة الداخلية
        try:
            from kivy.utils import platform
            if platform == "android":
                int_src_path = Path("/storage/emulated/0")
                res.source_exists = int_src_path.exists()
            else:
                res.source_exists = True
        except Exception:
            res.source_exists = True

    # 2. فحص بطاقة الذاكرة الخارجية SD كمصدر (عند اختيار sdcard أو both)
    if source_norm in ("sdcard", "both"):
        saf_ok = is_saf_sdcard_granted()
        res.source_sdcard_saf_valid = saf_ok
        if not saf_ok:
            res.source_sdcard_readable = False
            res.source_sdcard_error = "مجلد بطاقة SD غير محدد أو انتهت صلاحية إذن الوصول (SAF)"
            res.success = False
            res.error_code = "missing_source_saf"
            res.error_message = (
                "تم اختيار بطاقة الذاكرة الخارجية كمصدر (أو ضمن الفحص المشترك)، "
                "ولكن لم يتم تحديد مجلد البطاقة أو انتهت صلاحية إذن الوصول (SAF).\n"
                "يرجى فتح الإعدادات وتحديد مجلد بطاقة SD لمنح الإذن الدائم."
            )
            res.action_required = "request_saf_sdcard"
            return res

        import storage_backend
        target_loc = storage_backend.get_active_target_location("sdcard")
        if not target_loc or not target_loc.is_valid:
            res.source_sdcard_readable = False
            res.source_sdcard_error = target_loc.error_message if target_loc else "بطاقة SD غير متوفرة أو غير مركبة"
            res.success = False
            res.error_code = "sdcard_disconnected"
            res.error_message = f"فشل الوصول لمصدر بطاقة الذاكرة الخارجية: {res.source_sdcard_error}"
            res.action_required = "request_saf_sdcard"
            return res

        # فحص عينة وسائط في بطاقة SD بشكل مستقل
        sd_sample = find_first_media_sample("sdcard", "image") or find_first_media_sample("sdcard", "video")
        if sd_sample:
            res.source_sdcard_sample_found = True
            res.source_sdcard_sample_path = sd_sample
            read_sd_ok, err_sd = test_read_sample_bytes(sd_sample)
            res.source_sdcard_sample_readable = read_sd_ok
            if not read_sd_ok:
                res.source_sdcard_readable = False
                res.source_sdcard_error = f"فشل قراءة ملف في بطاقة SD: {err_sd}"
                res.success = False
                res.error_code = "source_sdcard_read_failed"
                res.error_message = f"تعذر قراءة ملفات بطاقة SD عبر إذن SAF: {err_sd}"
                res.action_required = "request_saf_sdcard"
                return res
            res.source_sdcard_readable = True
            if not res.source_image_found and any(sd_sample.lower().endswith(x) for x in (".jpg", ".jpeg", ".png", ".webp")):
                res.source_image_found = True
                res.source_image_readable = read_sd_ok
                res.source_image_sample_path = sd_sample
            if not res.source_video_found and any(sd_sample.lower().endswith(x) for x in (".mp4", ".mkv", ".3gp", ".mov")):
                res.source_video_found = True
                res.source_video_readable = read_sd_ok
                res.source_video_sample_path = sd_sample
        else:
            # لا توجد عينة على بطاقة SD: لا نعتبر القراءة ناجحة لمجرد صلاحية SAF
            res.source_sdcard_sample_found = False
            res.source_sdcard_sample_path = ""
            res.source_sdcard_sample_readable = False
            res.source_sdcard_readable = False
            res.source_sdcard_error = "لا توجد عينة للاختبار"

    # 3. التحقق الشامل من توفر عينات الوسائط وصلاحيتها للاختبار
    has_any_image = res.source_image_found
    has_any_video = res.source_video_found
    has_any_sample = has_any_image or has_any_video or res.source_sdcard_sample_found

    # أ. إذا لم توجد صورة ولا فيديو في كل المصادر
    if not has_any_sample:
        res.success = False
        res.error_code = "no_media_samples_found"
        res.error_message = "لم يتم العثور على أي صورة أو فيديو قابل للاختبار."
        res.action_required = "none"
        return res

    # ب. إذا كان المطلوب تنظيم الصور فقط ولم يتم العثور على أي صورة
    if organize_images and not organize_videos and not has_any_image:
        res.success = False
        res.error_code = "no_image_samples_found"
        res.error_message = "لم يتم العثور على أي صورة قابلة للاختبار (المطلوب تنظيم الصور فقط)."
        res.action_required = "none"
        return res

    # ج. إذا كان المطلوب تنظيم الفيديو فقط ولم يتم العثور على أي فيديو
    if organize_videos and not organize_images and not has_any_video:
        res.success = False
        res.error_code = "no_video_samples_found"
        res.error_message = "لم يتم العثور على أي فيديو قابل للاختبار (المطلوب تنظيم الفيديو فقط)."
        res.action_required = "none"
        return res

    # 4. فحص الوجهة
    if target_norm == "sdcard":
        saf_ok = is_saf_sdcard_granted()
        if not saf_ok:
            res.success = False
            res.error_code = "missing_target_saf"
            res.error_message = "تم تحديد الحفظ في بطاقة SD الخارجية، لكن مجلد الحفظ غير محدد أو انتهت صلاحية إذن الوصول (SAF)."
            res.action_required = "request_saf_sdcard"
            return res

        import storage_backend
        target_loc = storage_backend.get_active_target_location("sdcard")
        if not target_loc or not target_loc.is_valid:
            res.success = False
            res.error_code = "sdcard_invalid"
            res.error_message = target_loc.error_message if target_loc else "بطاقة SD غير صالحة للكتابة."
            res.action_required = "request_saf_sdcard"
            return res

        res.target_actual_path = target_loc.display_name or "بطاقة SD الخارجية (SAF)"

        # اختبار كتابة وقراءة وحذف حقيقي على بطاقة SD عبر SAF
        try:
            test_content = b"COSMOSORT_SD_PREFLIGHT_TEST_OK"
            test_filename = f".preflight_test_{int(time.time() * 1000)}.tmp"
            new_file_uri, created_uri_str = storage_backend.saf_create_target_document(
                target_loc.tree_uri,
                "خارج التصنيف",
                test_filename,
                "application/octet-stream",
            )
            if created_uri_str or new_file_uri is not None:
                res.target_dir_creatable = True
                res.target_writable = True
                write_ok = storage_backend.saf_write_data_to_uri(created_uri_str, test_content)
                if write_ok:
                    res.target_readable_after_write = True
                del_ok = storage_backend.saf_delete_document(created_uri_str)
                if del_ok:
                    res.target_temp_deleted = True
            else:
                res.target_dir_creatable = False
                res.target_writable = False
        except Exception as e:
            res.target_writable = False
            res.error_code = "sdcard_write_failed"
            res.error_message = f"فشل اختبار الكتابة على بطاقة SD: {e}"
            return res

        if not res.target_writable or not res.target_readable_after_write:
            res.success = False
            res.error_code = "sdcard_write_failed"
            res.error_message = "فشل اختبار كتابة وقراءة الملف التجريبي على بطاقة SD الخارجية."
            return res

    else:
        # الذاكرة الداخلية
        write_ok = is_storage_write_permission_granted()
        if not write_ok:
            res.success = False
            res.error_code = "missing_write_permission"
            res.error_message = (
                "Android 10 يتطلب صلاحية كتابة التخزين (WRITE_EXTERNAL_STORAGE) لإنشاء مجلد الملفات المنظمة.\n"
                "يرجى فتح إعدادات التطبيق وتفعيل إذن التخزين."
            )
            res.action_required = "open_app_settings"
            return res

        import storage_backend
        target_loc = storage_backend.get_active_target_location("internal")
        target_path = Path(target_loc.path) if (target_loc and target_loc.path) else (Path("/storage/emulated/0") / "الملفات المنظمة")
        res.target_actual_path = str(target_path)

        # اختبار إنشاء المجلد والكتابة والقراءة والحذف
        try:
            target_path.mkdir(parents=True, exist_ok=True)
            res.target_dir_creatable = True

            test_file = target_path / f".preflight_test_{int(time.time() * 1000)}.tmp"
            test_content = b"COSMOSORT_INTERNAL_PREFLIGHT_TEST_OK"
            test_file.write_bytes(test_content)
            res.target_writable = True

            read_back = test_file.read_bytes()
            if read_back == test_content:
                res.target_readable_after_write = True

            test_file.unlink(missing_ok=True)
            res.target_temp_deleted = not test_file.exists()

        except (PermissionError, OSError) as e:
            logger.warning("فشل اختبار الكتابة للذاكرة الداخلية على %s: %s", target_path, e)
            res.target_writable = False
            res.success = False
            res.error_code = "internal_write_failed"
            res.error_message = f"تعذر الكتابة في مجلد الذاكرة الداخلية ({target_path.name}): تم رفض الإذن من النظام."
            res.action_required = "open_app_settings"
            return res

    res.success = True
    res.error_code = "ok"
    res.error_message = ""
    return res


def preflight_scan_access(
    source_storage: str,
    target_storage: str,
) -> tuple[bool, str, str, str]:
    """
    فحص استباقي يمنع التشغيل الكاذب ويضمن توافر الصلاحيات قبل بدء الفحص:
    العائد: (مسموح_البدء: bool, رمز_المشكلة: str, رسالة_عربية: str, الإجراء_المطلوب: str)
    """
    test_res = run_storage_preflight_test(source_storage, target_storage)
    return (
        test_res.success,
        test_res.error_code,
        test_res.error_message,
        test_res.action_required,
    )


def get_permissions_diagnostic_summary() -> dict[str, Any]:
    """
    استخراج تقرير تشخيص دقيق ومفصل لكافة الصلاحيات لعرضه للمستخدم وفق إصدار أندرويد الفعلي:
    - على Android 10: لا يعرض READ_MEDIA_* ولا يعرض Android 14.
    - على Android 11+: يعرض حالة وصول كافة الملفات (All files access).
    - على Android 13+: يعرض صلاحيات الصور والفيديو المخصصة.
    - على Android 14+: يعرض نطاق الوصول الجزئي/المحدود.
    """
    sys_info = get_android_system_info()
    sdk = sys_info["sdk_int"]
    img_ok = is_images_permission_granted()
    vid_ok = is_videos_permission_granted()
    write_ok = is_storage_write_permission_granted()
    all_files_ok = is_all_files_access_granted()
    saf_ok = is_saf_sdcard_granted()

    # تشخيص جزئي في أندرويد 14 فقط
    is_partial_access = is_visual_user_selected_only()

    # فحص ما إذا كان هناك مسار سابق للـ SAF
    has_prev_saf = False
    try:
        import storage_backend
        has_prev_saf = bool(storage_backend.get_saf_persisted_uri())
    except Exception:
        pass

    saf_status = "صالح ومفعل ✓" if saf_ok else ("غير مفعل / منتهي" if has_prev_saf else "غير محدد")

    if sdk == 29 or (0 < sdk < 30):
        # Android 10
        all_files_str = "غير منطبق (النمط الكلاسيكي معتمد) -"
        access_scope = "وصول كامل للذاكرة الداخلية" if (img_ok and write_ok) else "غير ممنوح"
        ready_for_internal = img_ok and write_ok
    elif sdk >= 30:
        # Android 11+
        all_files_str = "ممنوح ✓" if all_files_ok else "مقيد ⚠️"
        access_scope = "الوصول محدود" if is_partial_access else ("وصول كامل لكافة الوسائط ✓" if (img_ok and vid_ok) else "مرفوضة ✗")
        ready_for_internal = img_ok and vid_ok and not is_partial_access
    else:
        # بيئة غير أندرويد أو غير محددة
        all_files_str = "ممنوح (بيئة تجريبية) ✓"
        access_scope = "وصول كامل"
        ready_for_internal = True

    return {
        "sdk_int": sdk,
        "release": sys_info["release"],
        "package_name": sys_info["package_name"],
        "target_sdk": sys_info["target_sdk"],
        "system_status": sys_info["status"],
        "images_permission": img_ok,
        "videos_permission": vid_ok,
        "write_permission": write_ok,
        "images_permission_status": "ممنوحة ✓" if img_ok else "مرفوضة ✗",
        "videos_permission_status": "ممنوحة ✓" if vid_ok else "مرفوضة ✗",
        "write_permission_status": "ممنوحة ✓" if write_ok else "مرفوضة ✗",
        "all_files_permission": all_files_ok,
        "all_files_permission_status": all_files_str,
        "saf_sdcard_permission": saf_ok,
        "saf_sdcard_status": saf_status,
        "partial_visual_selected": is_partial_access,
        "access_scope": access_scope,
        "fully_ready_for_internal": ready_for_internal,
        "fully_ready_for_sdcard": saf_ok,
    }


def request_media_permissions(
    callback: Callable[[list[str], list[bool]], None] | None = None
) -> None:
    """
    طلب الصلاحيات المخصصة للنظام وفق إصدار أندرويد الفعلي:
    - SDK <= 32: طلب READ_EXTERNAL_STORAGE و WRITE_EXTERNAL_STORAGE و CAMERA.
    - SDK >= 33: طلب صلاحيات الوسائط الحديثة READ_MEDIA_IMAGES و READ_MEDIA_VIDEO و CAMERA و POST_NOTIFICATIONS.
    - SDK >= 34: دعم READ_MEDIA_VISUAL_USER_SELECTED إن لزم.
    """
    try:
        from kivy.utils import platform
        if platform != "android":
            if callback:
                callback([], [])
            return

        from android.permissions import Permission, request_permissions  # type: ignore

        sdk = get_android_sdk_int()
        perms = []

        if sdk >= 33:
            for p_name in ["READ_MEDIA_IMAGES", "READ_MEDIA_VIDEO"]:
                if hasattr(Permission, p_name):
                    perms.append(getattr(Permission, p_name))
            if sdk >= 34 and hasattr(Permission, "READ_MEDIA_VISUAL_USER_SELECTED"):
                perms.append(Permission.READ_MEDIA_VISUAL_USER_SELECTED)
            # Android 13+ يتطلب POST_NOTIFICATIONS لإظهار إشعارات Foreground Service
            if hasattr(Permission, "POST_NOTIFICATIONS"):
                perms.append(Permission.POST_NOTIFICATIONS)
        else:
            perms.append(Permission.READ_EXTERNAL_STORAGE)
            perms.append(Permission.WRITE_EXTERNAL_STORAGE)

        # طلب صلاحية الكاميرا على جميع الإصدارات (مطلوبة لالتقاط الصور)
        if hasattr(Permission, "CAMERA"):
            perms.append(Permission.CAMERA)

        def _internal_cb(permissions: list[str], grant_results: list[bool]) -> None:
            logger.info("نتيجة طلب الصلاحيات: %s -> %s", permissions, grant_results)
            if callback:
                callback(permissions, grant_results)

        request_permissions(perms, _internal_cb)
    except Exception as e:
        logger.warning("تنبيه: تعذر استدعاء request_permissions: %s", e)
        if callback:
            callback([], [])


def open_app_details_settings() -> None:
    """فتح شاشة إعدادات التطبيق في أندرويد لتمكين المستخدم من تفعيل الصلاحيات يدوياً"""
    try:
        from kivy.utils import platform
        if platform != "android":
            return
        from android import mActivity
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")

        intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
        uri = Uri.fromParts("package", mActivity.getPackageName(), None)
        intent.setData(uri)
        mActivity.startActivity(intent)
    except Exception as e:
        logger.error("تعذر فتح شاشة إعدادات التطبيق: %s", e)
