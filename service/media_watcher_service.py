# -*- coding: utf-8 -*-
"""
خدمة مراقبة الوسائط الخلفية المستمرة (Media Watcher Background Service):
- تعمل كـ Foreground Service منفصلة على أندرويد لضمان عدم إيقافها من قِبل النظام.
- تراقب مجلدات الالتقاط والتنزيل الشائعة:
    - DCIM/Camera
    - Pictures
    - Download
    - WhatsApp Media
- تفحص اكتمال كتابة الملفات (ثبات الحجم بين قراءتين متتاليتين) قبل فرزها.
- تطبق قواعد الفرز والأولويات التلقائية عبر media_scanner.process_one_file.
"""

import json
import os
from pathlib import Path
import time
import sys

# إضافة المجلد الرئيسي للمشروع إلى sys.path لتمكين استيراد الوحدات
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import media_scanner
import file_manager

CHECK_INTERVAL_SECONDS = 5.0
STABILITY_DELAY_SECONDS = 1.5

WATCH_SUBDIRECTORIES = [
    "DCIM/Camera",
    "DCIM",
    "Pictures",
    "Download",
    "WhatsApp/Media/WhatsApp Images",
    "WhatsApp/Media/WhatsApp Video",
    "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images",
    "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video",
    "Telegram/Telegram Images",
    "Telegram/Telegram Video"
]


def get_service_control_file() -> Path:
    """ملف التحكم في تشغيل وإيقاف الخدمة"""
    base = file_manager.get_media_sorter_base_path()
    return base / "service_control.json"


def set_service_desired_state(running: bool) -> None:
    """تحديث حالة تشغيل الخدمة المطلوبة من الواجهة"""
    ctrl = get_service_control_file()
    try:
        with open(ctrl, "w", encoding="utf-8") as f:
            json.dump({"running": running, "updated_at": time.time()}, f)
    except Exception as e:
        print("تعذر كتابة حالة الخدمة:", e)


def is_service_desired_running() -> bool:
    """التحقق مما إذا كان المستخدم يرغب بتشغيل الخدمة"""
    ctrl = get_service_control_file()
    if not ctrl.exists():
        return True  # افتراضياً تعمل
    try:
        with open(ctrl, "r", encoding="utf-8") as f:
            data = json.load(f)
            return bool(data.get("running", True))
    except Exception:
        return True


def setup_android_foreground_notification():
    """
    إنشاء إشعار Foreground Service دائم على أندرويد لمنع إيقاف الخدمة.
    """
    try:
        from jnius import autoclass
        PythonService = autoclass("org.kivy.android.PythonService")
        service_instance = PythonService.mService
        if service_instance is not None:
            NotificationBuilder = autoclass("android.app.Notification$Builder")
            NotificationManager = autoclass("android.app.NotificationManager")
            Context = autoclass("android.content.Context")

            app_context = service_instance.getApplicationContext()
            channel_id = "media_sorter_service_channel"

            # إنشاء Notification Channel لأندرويد 8+ (API 26+)
            try:
                NotificationChannel = autoclass("android.app.NotificationChannel")
                channel = NotificationChannel(
                    channel_id,
                    "خدمة فرز الوسائط",
                    NotificationManager.IMPORTANCE_LOW
                )
                notification_manager = app_context.getSystemService(Context.NOTIFICATION_SERVICE)
                notification_manager.createNotificationChannel(channel)
                builder = NotificationBuilder(app_context, channel_id)
            except Exception:
                builder = NotificationBuilder(app_context)

            builder.setContentTitle("منظّم الوسائط الذكي")
            builder.setContentText("المراقبة والفرز التلقائي قيد العمل في الخلفية")
            builder.setSmallIcon(app_context.getApplicationInfo().icon)
            notification = builder.build()

            service_instance.startForeground(101, notification)
            print("✓ تم تفعيل Android Foreground Service Notification بنجاح.")
    except Exception as e:
        # بيئة ديسكتوب أو غياب pyjnius
        pass


def get_monitored_directories() -> list[Path]:
    """تحديد مجلدات المراقبة النشطة حسب بيئة التشغيل"""
    dirs: list[Path] = []
    roots = media_scanner.scan_storage_roots()

    for r in roots:
        if "/storage/emulated/0" in str(r) or "\\storage" in str(r):
            # على أندرويد
            for sub in WATCH_SUBDIRECTORIES:
                target = r / sub
                if target.exists() and target.is_dir():
                    dirs.append(target)
        else:
            # على الحاسوب: نراقب مجلدات الاختبار ومجلد المشروع
            dirs.append(r)

    return dirs


def is_file_stable(file_path: Path) -> bool:
    """
    التحقق من ثبات حجم الملف لضمان اكتمال تحميله أو التقاطه بالكاميرا قبل معالجته:
    - فحص الحجم في اللحظة t0.
    - الانتظار ثانية ونصف.
    - فحص الحجم في اللحظة t1.
    - إذا كان الحجم ثابتاً وأكبر من 0، نعتبره مكتملاً.
    """
    try:
        if not file_path.exists():
            return False
        s0 = file_path.stat().st_size
        if s0 <= 0:
            return False
        time.sleep(STABILITY_DELAY_SECONDS)
        if not file_path.exists():
            return False
        s1 = file_path.stat().st_size
        return s0 == s1 and s1 > 0
    except Exception:
        return False


def _collect_monitored_files(dir_path: Path, max_depth: int = 3) -> list[Path]:
    """جمع ملفات الوسائط في المجلد ومجلداته الفرعية حتى عمق محدد لالتقاط وسائط WhatsApp وTelegram الفرعية"""
    found_files: list[Path] = []
    if not dir_path.exists() or not dir_path.is_dir():
        return found_files

    def _walk(curr: Path, depth: int) -> None:
        if depth > max_depth or not curr.exists() or not curr.is_dir():
            return
        try:
            for entry in curr.iterdir():
                if entry.is_file():
                    ext = entry.suffix.lower()
                    if ext in media_scanner.IMAGE_EXTENSIONS or ext in media_scanner.VIDEO_EXTENSIONS:
                        found_files.append(entry)
                elif entry.is_dir() and not entry.name.startswith(".") and entry.name != "MediaSorter":
                    _walk(entry, depth + 1)
        except (PermissionError, OSError):
            pass

    _walk(dir_path, 0)
    return found_files


def run_watcher_loop():
    """
    حلقة المراقبة الدورية المستمرة للخدمة الخلفية مع الفحص الشامل للمجلدات الفرعية.
    """
    print("بدء خدمة مراقبة الوسائط Media Watcher...")
    setup_android_foreground_notification()
    media_scanner.init_cache_db()

    while True:
        # فحص إذن التشغيل من الإعدادات
        if not is_service_desired_running():
            time.sleep(CHECK_INTERVAL_SECONDS * 2)
            continue

        try:
            watch_dirs = get_monitored_directories()
            for w_dir in watch_dirs:
                if not w_dir.exists():
                    continue

                for entry in _collect_monitored_files(w_dir, max_depth=3):
                    try:
                        st = entry.stat()
                        # هل عولج مسبقاً؟
                        if media_scanner.is_file_already_processed(str(entry), st.st_size, st.st_mtime):
                            continue

                        # التأكد من اكتمال كتابة الملف
                        if is_file_stable(entry):
                            print(f"[خدمة المراقبة] معالجة ملف جديد: {entry.name}")
                            res = media_scanner.process_one_file(entry)
                            print(f"[خدمة المراقبة] النتيجة: {res.get('category')}")
                    except (OSError, PermissionError):
                        continue

        except Exception as e:
            print("خطأ في حلقة الخدمة الخلفية:", e)

_watcher_thread = None
_stop_event = None

def is_watcher_running() -> bool:
    """التحقق مما إذا كان ثريد الخدمة أو الرغبة بتشغيل الخدمة نشطاً"""
    global _watcher_thread
    if _watcher_thread is not None and _watcher_thread.is_alive():
        return True
    return is_service_desired_running()


def start_watcher_thread(interval_seconds: float = CHECK_INTERVAL_SECONDS) -> None:
    """بدء المراقبة في ثريد خلفي (للبيئات التجريبية أو سطح المكتب)"""
    global _watcher_thread, _stop_event
    import threading

    set_service_desired_state(True)
    if _watcher_thread is not None and _watcher_thread.is_alive():
        return

    _stop_event = threading.Event()

    def thread_worker():
        media_scanner.init_cache_db()
        while not _stop_event.is_set():
            if not is_service_desired_running():
                time.sleep(interval_seconds)
                continue
            try:
                watch_dirs = get_monitored_directories()
                for w_dir in watch_dirs:
                    if not w_dir.exists():
                        continue
                    for entry in w_dir.iterdir():
                        if entry.is_file():
                            ext = entry.suffix.lower()
                            if ext in media_scanner.IMAGE_EXTENSIONS or ext in media_scanner.VIDEO_EXTENSIONS:
                                st = entry.stat()
                                if media_scanner.is_file_already_processed(str(entry), st.st_size, st.st_mtime):
                                    continue
                                media_scanner.process_one_file(entry)
            except Exception:
                pass
            time.sleep(interval_seconds)

    _watcher_thread = threading.Thread(target=thread_worker, daemon=True)
    _watcher_thread.start()


def stop_watcher_thread() -> None:
    """إيقاف ثريد المراقبة الخلفي"""
    global _stop_event, _watcher_thread
    set_service_desired_state(False)
    if _stop_event is not None:
        _stop_event.set()
    _watcher_thread = None


def start_system_service() -> None:
    """بدء خدمة المراقبة بحسب البيئة (Android Service أو ثريد ديسكتوب)"""
    from kivy.utils import platform
    set_service_desired_state(True)
    if platform == "android":
        try:
            from android import mActivity
            from jnius import autoclass
            Service = autoclass("org.examsorter.app.ServiceMediawatcher")
            Service.start(mActivity, "")
            print("✓ تم استدعاء بدء خدمة أندرويد بنجاح.")
            return
        except Exception as e:
            print("تنبيه: تعذر بدء خدمة أندرويد عبر pyjnius، جاري البدء عبر الثريد:", e)
    start_watcher_thread()


def stop_system_service() -> None:
    """إيقاف خدمة المراقبة بحسب البيئة"""
    from kivy.utils import platform
    set_service_desired_state(False)
    if platform == "android":
        try:
            from android import mActivity
            from jnius import autoclass
            Service = autoclass("org.examsorter.app.ServiceMediawatcher")
            Service.stop(mActivity)
            print("✓ تم استدعاء إيقاف خدمة أندرويد بنجاح.")
        except Exception as e:
            print("تنبيه: تعذر إيقاف خدمة أندرويد عبر pyjnius:", e)
    stop_watcher_thread()


if __name__ == "__main__":
    run_watcher_loop()

