# -*- coding: utf-8 -*-
"""
android_permissions.py
----------------------
مدير الصلاحيات الموحد لتطبيق رتّب / CosmoSort:
- فحص دقيق لكل صلاحية وفق إصدار أندرويد (SDK_INT من أندرويد 8 إلى 15).
- التفريق بين صلاحيات القراءة من الذاكرة الداخلية وصلاحيات الكتابة على بطاقة SD عبر SAF.
- تقديم فحص استباقي (Preflight Check) يمنع بدء الفحص عند غياب الصلاحيات اللازمة.
- تقديم تشخيص تفصيلي للمستخدم لحالة كل إذن.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("AndroidPermissions")


def get_android_sdk_int() -> int:
    """الحصول على رقم إصدار أندرويد (Build.VERSION.SDK_INT) بأمان تام"""
    try:
        from kivy.utils import platform
        if platform != "android":
            return 0
        from jnius import autoclass
        BuildVersion = autoclass("android.os.Build$VERSION")
        return int(BuildVersion.SDK_INT)
    except Exception as e:
        logger.debug("تعذر استخراج SDK_INT: %s", e)
        return 0


def has_permission(permission_name: str) -> bool:
    """
    التحقق مما إذا كانت صلاحية أندرويد معينة ممنوحة حالياً.
    يدعم المنصات غير أندرويد (يعيد True افتراضياً للاختبارات).
    """
    try:
        from kivy.utils import platform
        if platform != "android":
            return True
        from jnius import autoclass
        from android import mActivity

        ContextCompat = autoclass("androidx.core.content.ContextCompat")
        PackageManager = autoclass("android.content.pm.PackageManager")

        # تحويل اسم الصلاحية لصيغتها الكاملة
        if not permission_name.startswith("android.permission."):
            full_perm = f"android.permission.{permission_name}"
        else:
            full_perm = permission_name

        result = ContextCompat.checkSelfPermission(mActivity, full_perm)
        return result == PackageManager.PERMISSION_GRANTED
    except Exception as e:
        logger.debug("خطأ أثناء فحص الصلاحية %s: %s", permission_name, e)
        return False


def is_images_permission_granted() -> bool:
    """فحص صلاحية قراءة الصور حسب إصدار أندرويد"""
    sdk = get_android_sdk_int()
    if sdk == 0:  # بيئة غير أندرويد
        return True
    if sdk >= 33:
        if has_permission("READ_MEDIA_IMAGES"):
            return True
        if sdk >= 34 and has_permission("READ_MEDIA_VISUAL_USER_SELECTED"):
            return True
        return False
    # أندرويد 12 وما قبل
    return has_permission("READ_EXTERNAL_STORAGE")


def is_videos_permission_granted() -> bool:
    """فحص صلاحية قراءة الفيديوهات حسب إصدار أندرويد"""
    sdk = get_android_sdk_int()
    if sdk == 0:  # بيئة غير أندرويد
        return True
    if sdk >= 33:
        if has_permission("READ_MEDIA_VIDEO"):
            return True
        if sdk >= 34 and has_permission("READ_MEDIA_VISUAL_USER_SELECTED"):
            return True
        return False
    # أندرويد 12 وما قبل
    return has_permission("READ_EXTERNAL_STORAGE")


def is_all_files_access_granted() -> bool:
    """فحص إذن الوصول الشامل لكافة الملفات (MANAGE_EXTERNAL_STORAGE)"""
    sdk = get_android_sdk_int()
    if sdk < 30:  # أندرويد 10 وما دون
        return has_permission("READ_EXTERNAL_STORAGE") and has_permission("WRITE_EXTERNAL_STORAGE")
    try:
        from jnius import autoclass
        Environment = autoclass("android.os.Environment")
        return bool(Environment.isExternalStorageManager())
    except Exception:
        return False


def is_saf_sdcard_granted() -> bool:
    """فحص ما إذا كان هناك إذن SAF صالح ومحفوظ لبطاقة الذاكرة الخارجية"""
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
            import storage_backend
            from jnius import autoclass
            from android import mActivity
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


def get_permissions_diagnostic_summary() -> Dict[str, Any]:
    """
    استخراج تقرير تشخيص دقيق ومفصل لكافة الصلاحيات لعرضه للمستخدم.
    """
    sdk = get_android_sdk_int()
    img_ok = is_images_permission_granted()
    vid_ok = is_videos_permission_granted()
    all_files_ok = is_all_files_access_granted()
    saf_ok = is_saf_sdcard_granted()

    # تشخيص جزئي في أندرويد 14
    is_partial_access = False
    if sdk >= 34:
        if has_permission("READ_MEDIA_VISUAL_USER_SELECTED") and not (
            has_permission("READ_MEDIA_IMAGES") and has_permission("READ_MEDIA_VIDEO")
        ):
            is_partial_access = True

    return {
        "sdk_int": sdk,
        "images_permission": img_ok,
        "videos_permission": vid_ok,
        "all_files_permission": all_files_ok,
        "saf_sdcard_permission": saf_ok,
        "partial_visual_selected": is_partial_access,
        "fully_ready_for_internal": img_ok and vid_ok,
        "fully_ready_for_sdcard": saf_ok,
    }


def preflight_scan_access(
    source_storage: str,
    target_storage: str,
) -> Tuple[bool, str, str, str]:
    """
    فحص استباقي يمنع التشغيل الكاذب ويضمن توافر الصلاحيات قبل بدء الفحص:
    العائد: (مسموح_البدء: bool, رمز_المشكلة: str, رسالة_عربية: str, الإجراء_المطلوب: str)
    الإجراءات الممكنة:
    - 'none'
    - 'request_media'
    - 'request_saf_sdcard'
    - 'open_app_settings'
    """
    source_norm = (source_storage or "both").lower()
    target_norm = (target_storage or "internal").lower()

    # 1. فحص صلاحيات المصدر
    if source_norm in ("internal", "both"):
        img_ok = is_images_permission_granted()
        vid_ok = is_videos_permission_granted()
        if not img_ok and not vid_ok:
            return (
                False,
                "missing_media_permissions",
                "صلاحية الوصول إلى الصور والفيديوهات غير ممنوحة. يرجى منح الإذن للتمكن من قراءة ملفات الجهاز.",
                "request_media",
            )
        if not img_ok:
            return (
                False,
                "missing_images_permission",
                "صلاحية الوصول إلى الصور غير ممنوحة. يرجى منح الإذن.",
                "request_media",
            )
        if not vid_ok:
            return (
                False,
                "missing_videos_permission",
                "صلاحية الوصول إلى مقاطع الفيديو غير ممنوحة. يرجى منح الإذن.",
                "request_media",
            )

    if source_norm in ("sdcard", "both"):
        # فحص إذن SAF للبطاقة كمصدر
        if source_norm == "sdcard" and not is_saf_sdcard_granted():
            return (
                False,
                "missing_source_saf",
                "تم اختيار بطاقة الذاكرة الخارجية كمصدر، ولكن لم يتم تحديد مجلد البطاقة أو انتهت صلاحيته.",
                "request_saf_sdcard",
            )

    # 2. فحص صلاحيات الوجهة
    if target_norm == "sdcard":
        if not is_saf_sdcard_granted():
            return (
                False,
                "missing_target_saf",
                "تم تحديد الحفظ في بطاقة SD الخارجية، لكن مجلد الحفظ غير محدد أو انتهت صلاحية إذن الوصول (SAF). يرجى اختيار مجلد البطاقة وتفويضه.",
                "request_saf_sdcard",
            )

    return (True, "ok", "", "none")


def request_media_permissions(
    callback: Optional[Callable[[List[str], List[bool]], None]] = None
) -> None:
    """
    طلب الصلاحيات المخصصة للنظام وفق إصدار أندرويد الفعلي.
    """
    try:
        from kivy.utils import platform
        if platform != "android":
            if callback:
                callback([], [])
            return

        from android.permissions import Permission, request_permissions  # type: ignore

        sdk = get_android_sdk_int()
        perms = [Permission.CAMERA]

        if sdk >= 33:
            for p_name in ["READ_MEDIA_IMAGES", "READ_MEDIA_VIDEO", "POST_NOTIFICATIONS"]:
                if hasattr(Permission, p_name):
                    perms.append(getattr(Permission, p_name))
            if sdk >= 34 and hasattr(Permission, "READ_MEDIA_VISUAL_USER_SELECTED"):
                perms.append(getattr(Permission, "READ_MEDIA_VISUAL_USER_SELECTED"))
        else:
            perms.append(Permission.READ_EXTERNAL_STORAGE)
            perms.append(Permission.WRITE_EXTERNAL_STORAGE)

        def _internal_cb(permissions: List[str], grant_results: List[bool]) -> None:
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
        from jnius import autoclass
        from android import mActivity

        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")

        intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
        uri = Uri.fromParts("package", mActivity.getPackageName(), None)
        intent.setData(uri)
        mActivity.startActivity(intent)
    except Exception as e:
        logger.error("تعذر فتح شاشة إعدادات التطبيق: %s", e)
