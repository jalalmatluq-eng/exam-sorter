# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""
وحدة تصدير سجل التشخيص (Export Diagnostic Logs):
- نسخ سجل cosmosort_debug.log من التخزين الداخلي الخاص بالتطبيق (ANDROID_PRIVATE)
  إلى مجلد التنزيلات العام (Downloads) بدون الحاجة إلى صلاحيات إدارة الملفات.
- يدعم MediaStore (Android 10+ / Scoped Storage)، و SharedStorage، والنسخ المباشر.
"""

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("ExportLogs")


def get_private_log_file() -> Path:
    """استرجاع مسار ملف التشخيص الداخلي الخاص بالتطبيق."""
    candidates: list[Path] = []

    android_private = os.environ.get("ANDROID_PRIVATE")
    if android_private:
        candidates.append(Path(android_private) / "cosmosort_debug.log")
        candidates.append(Path(android_private) / "app" / "cosmosort_debug.log")

    base_dir = Path(__file__).resolve().parent.parent
    candidates.append(base_dir / "cosmosort_debug.log")
    candidates.append(Path.home() / ".cosmosort" / "cosmosort_debug.log")

    for p in candidates:
        if p.exists() and p.is_file():
            return p

    # إذا لم يكن موجوداً بعد، نعتمد المسار الافتراضي وننشئه
    target = candidates[0] if candidates else base_dir / "cosmosort_debug.log"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with open(target, "w", encoding="utf-8") as f:
                f.write(
                    f"=== Rateb - رتّب | المُنظّم الذكي Diagnostic Log ===\n"
                    f"Platform: {sys.platform}\n"
                    f"Version: 2.0.1\n"
                    f"Initialized\n"
                )
    except Exception as e:
        logger.warning("تعذر إنشاء ملف السجل الافتراضي: %s", e)
    return target


def export_diagnostic_log() -> tuple[bool, str]:
    """
    تصدير ملف cosmosort_debug.log إلى مجلد التنزيلات (Download).
    يعيد (نجاح/فشل، رسالة توضيحية أو مسار الحفظ).
    """
    src_file = get_private_log_file()
    if not src_file.exists():
        return False, "لم يتم العثور على ملف التشخيص cosmosort_debug.log"

    # التأكد من كتابة سطر تشخيصي أخير قبل التصدير
    try:
        with open(src_file, "a", encoding="utf-8") as f:
            f.write(f"\n[Export Triggered] Source: {src_file}\n")
    except Exception:
        pass

    # 1. محاولة التصدير عبر androidstorage4kivy إذا كانت مثبتة
    try:
        from androidstorage4kivy import SharedStorage  # type: ignore
        ss = SharedStorage()
        res = ss.copy_to_shared(
            str(src_file), collection="Download", filepath="cosmosort_debug.log"
        )
        if res:
            logger.info("تم تصدير السجل عبر SharedStorage: %s", res)
            return True, "Download/cosmosort_debug.log"
    except Exception as e:
        logger.debug("تخطي androidstorage4kivy: %s", e)

    # 2. محاولة التصدير عبر MediaStore الأصلي لأندرويد (API 29+ / Android 10+)
    try:
        from android import mActivity  # type: ignore
        from jnius import autoclass  # type: ignore

        ContentValues = autoclass("android.content.ContentValues")
        MediaStoreDownloads = autoclass("android.provider.MediaStore$Downloads")
        MediaStoreMediaColumns = autoclass(
            "android.provider.MediaStore$MediaColumns"
        )
        FileInputStream = autoclass("java.io.FileInputStream")
        FileUtils = autoclass("android.os.FileUtils")

        cv = ContentValues()
        cv.put(MediaStoreMediaColumns.DISPLAY_NAME, "cosmosort_debug.log")
        cv.put(MediaStoreMediaColumns.MIME_TYPE, "text/plain")
        cv.put(MediaStoreMediaColumns.RELATIVE_PATH, "Download/")

        cr = mActivity.getContentResolver()
        uri = cr.insert(MediaStoreDownloads.EXTERNAL_CONTENT_URI, cv)
        if uri:
            ws = cr.openOutputStream(uri, "rwt")
            fis = FileInputStream(str(src_file))
            try:
                FileUtils.copy(fis, ws)
            finally:
                try:
                    fis.close()
                except Exception:
                    pass
                try:
                    ws.close()
                except Exception:
                    pass
            logger.info("تم تصدير السجل عبر MediaStore بنجاح: %s", uri)
            return True, "Download/cosmosort_debug.log"
    except Exception as e:
        logger.debug("تخطي MediaStore المباشر: %s", e)

    # 3. محاولة النسخ المباشر لمجلد التنزيلات القياسي على أندرويد
    android_download_candidates = [
        Path("/storage/emulated/0/Download"),
        Path("/storage/emulated/0/Downloads"),
        Path("/sdcard/Download"),
    ]
    for d_dir in android_download_candidates:
        try:
            if d_dir.exists() and d_dir.is_dir():
                target_dest = d_dir / "cosmosort_debug.log"
                shutil.copy2(str(src_file), str(target_dest))
                logger.info("تم النسخ المباشر إلى: %s", target_dest)
                return True, str(target_dest)
        except Exception as e:
            logger.debug("تعذر النسخ المباشر إلى %s: %s", d_dir, e)

    # 4. بيئة سطح المكتب (Windows / Linux / macOS)
    try:
        desktop_download = Path.home() / "Downloads" / "cosmosort_debug.log"
        desktop_download.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src_file), str(desktop_download))
        logger.info("تم التصدير إلى مجلد تنزيلات سطح المكتب: %s", desktop_download)
        return True, str(desktop_download)
    except Exception as e:
        logger.error("فشل التصدير في سطح المكتب: %s", e)

    return False, "تعذر تصدير السجل لعدم توفر مسار حفظ متاح"
