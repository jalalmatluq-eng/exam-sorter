"""
خدمة مراقبة الوسائط الخلفية المستمرة (Media Watcher Background Service):
- تعمل كـ Foreground Service منفصلة على أندرويد.
- تراقب مجلدات الالتقاط والتنزيل الشائعة.
- تفحص اكتمال كتابة الملفات قبل فرزها.
"""

import json
import sys
import time
from pathlib import Path

# إضافة المجلد الرئيسي للمشروع إلى sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import file_manager
import media_scanner

CHECK_INTERVAL_SECONDS = 5.0
STABILITY_DELAY_SECONDS = 1.5

WATCH_SUBDIRECTORIES = [
    "DCIM/Camera",
    "DCIM",
    "Pictures",
    "Pictures/Screenshots",
    "DCIM/Screenshots",
    "Download",
    "Bluetooth",
    "Facebook",
    "Pictures/Facebook",
    "Snapseed",
    "Pictures/Snapseed",
    "Movies",
    "Music",
    "WhatsApp/Media/WhatsApp Images",
    "WhatsApp/Media/WhatsApp Video",
    "WhatsApp/Media/WhatsApp Documents",
    "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images",
    "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video",
    "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents",
    "Telegram/Telegram Images",
    "Telegram/Telegram Video",
]


def get_service_control_file() -> Path:
    """ملف التحكم في تشغيل وإيقاف الخدمة في التخزين الخاص بالتطبيق"""
    p = file_manager.get_app_private_storage_dir() / "service_control.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def set_service_desired_state(running: bool) -> None:
    """تحديث حالة تشغيل الخدمة المطلوبة من الواجهة"""
    ctrl = get_service_control_file()
    try:
        with open(ctrl, "w", encoding="utf-8") as f:
            json.dump({"running": running, "updated_at": time.time()}, f)
    except Exception as e:
        print("تعذر كتابة حالة الخدمة:", e)


def is_service_desired_running() -> bool:
    """التحقق مما إذا كان المستخدم يرغب بتشغيل الخدمة (افتراضياً معطلة حتى يفعلها المستخدم لتوفير البطارية ومنع أخطاء الإقلاع)"""
    ctrl = get_service_control_file()
    if not ctrl.exists():
        return False
    try:
        with open(ctrl, "r", encoding="utf-8") as f:
            data = json.load(f)
            return bool(data.get("running", False))
    except Exception:
        return False


def setup_android_foreground_notification() -> None:
    """
    إنشاء إشعار Foreground Service دائم على أندرويد.
    """
    try:
        from jnius import autoclass
        PythonService = autoclass("org.kivy.android.PythonService")
        service_instance = PythonService.mService
        if service_instance is not None:
            NotificationBuilder = autoclass(
                "android.app.Notification$Builder"
            )
            NotificationManager = autoclass(
                "android.app.NotificationManager"
            )
            Context = autoclass("android.content.Context")

            app_context = service_instance.getApplicationContext()
            channel_id = "media_sorter_service_channel"

            try:
                NotificationChannel = autoclass(
                    "android.app.NotificationChannel"
                )
                channel = NotificationChannel(
                    channel_id,
                    "خدمة فرز الوسائط",
                    NotificationManager.IMPORTANCE_LOW,
                )
                nm = app_context.getSystemService(
                    Context.NOTIFICATION_SERVICE
                )
                nm.createNotificationChannel(channel)
                builder = NotificationBuilder(app_context, channel_id)
            except Exception:
                builder = NotificationBuilder(app_context)

            builder.setContentTitle("رتّب | المُنظّم الذكي للوسائط")
            builder.setContentText(
                "خدمة المراقبة والفرز التلقائي للوسائط قيد العمل في الخلفية"
            )
            builder.setSmallIcon(
                app_context.getApplicationInfo().icon
            )
            notification = builder.build()
            service_instance.startForeground(101, notification)
            print("✓ تم تفعيل Android Foreground Service Notification.")
    except Exception:
        pass


def get_monitored_directories() -> list[Path]:
    """تحديد مجلدات المراقبة النشطة حسب بيئة التشغيل"""
    dirs: list[Path] = []
    roots = media_scanner.scan_storage_roots()

    for r in roots:
        r_str = str(r).lower()
        if "/storage" in r_str or "\\storage" in r_str:
            for sub in WATCH_SUBDIRECTORIES:
                target = r / sub
                if target.exists() and target.is_dir():
                    dirs.append(target)
        else:
            dirs.append(r)

    return dirs


def is_file_stable(file_path: Path) -> bool:
    """
    التحقق من ثبات حجم الملف لضمان اكتمال تحميله:
    - فحص الحجم في t0، الانتظار ثانية ونصف، فحصه مجدداً في t1.
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


_RESTRICTED_PATHS_CACHE: dict[str, float] = {}


def _is_path_temporarily_restricted(path_str: str) -> bool:
    """التحقق مما إذا كان المسار محظوراً بالصلاحيات ومحفوظاً في كاش التبريد"""
    now = time.time()
    exp = _RESTRICTED_PATHS_CACHE.get(path_str, 0.0)
    if now < exp:
        return True
    _RESTRICTED_PATHS_CACHE.pop(path_str, None)
    return False


def _mark_path_restricted(path_str: str, cooldown: float = 120.0) -> None:
    """تسجيل مسار في كاش الحظر المؤقت لتفادي تكرار طلبه كل 5 ثوان"""
    _RESTRICTED_PATHS_CACHE[path_str] = time.time() + cooldown


def _collect_monitored_files(
    dir_path: Path,
    max_depth: int = 3,
) -> list[Path]:
    """جمع ملفات الوسائط في المجلد ومجلداته الفرعية مع تخطي المجلدات المحمية"""
    found_files: list[Path] = []
    if not dir_path.exists() or not dir_path.is_dir():
        return found_files

    dir_str = str(dir_path)
    if _is_path_temporarily_restricted(dir_str):
        return found_files

    def _walk(curr: Path, depth: int) -> None:
        if depth > max_depth or not curr.exists() or not curr.is_dir():
            return
        curr_str = str(curr)
        if _is_path_temporarily_restricted(curr_str):
            return
        try:
            for entry in curr.iterdir():
                if entry.is_file():
                    ext = entry.suffix.lower()
                    if (
                        ext in media_scanner.IMAGE_EXTENSIONS
                        or ext in media_scanner.VIDEO_EXTENSIONS
                    ):
                        found_files.append(entry)
                elif (
                    entry.is_dir()
                    and not entry.name.startswith(".")
                    and entry.name not in (
                        "الملفات المنظمة", "MediaSorter", "ExamSorter"
                    )
                ):
                    _walk(entry, depth + 1)
        except (PermissionError, OSError):
            _mark_path_restricted(curr_str, cooldown=180.0)

    try:
        _walk(dir_path, 0)
    except (PermissionError, OSError):
        _mark_path_restricted(dir_str, cooldown=180.0)

    return found_files


def run_watcher_loop() -> None:
    """
    حلقة المراقبة الدورية المستمرة للخدمة الخلفية.
    """
    print("بدء خدمة مراقبة الوسائط Media Watcher...")
    setup_android_foreground_notification()
    media_scanner.init_cache_db()

    while True:
        if not is_service_desired_running():
            time.sleep(CHECK_INTERVAL_SECONDS * 2)
            continue

        # فحص استباقي للصلاحيات قبل قراءة الملفات في الخدمة الخلفية
        try:
            import android_permissions
            import file_manager
            import storage_backend

            prefs = file_manager.get_sorter_preferences()
            source_storage = str(prefs.get("source_storage", "both"))
            target_loc = storage_backend.get_active_target_location()
            tgt_name = target_loc.storage_type if target_loc else "internal"

            can_proceed, issue_code, issue_msg, _act = (
                android_permissions.preflight_scan_access(source_storage, tgt_name)
            )
            if not can_proceed:
                print(f"[خدمة المراقبة] تعليق الفحص لغياب الإذن: {issue_code} ({issue_msg})")
                time.sleep(CHECK_INTERVAL_SECONDS * 4)
                continue
        except Exception as e_pref:
            print("[خدمة المراقبة] خطأ أثناء فحص الصلاحيات:", e_pref)

        try:
            watch_dirs = get_monitored_directories()
            for w_dir in watch_dirs:
                if not w_dir.exists():
                    continue

                for entry in _collect_monitored_files(w_dir, max_depth=3):
                    try:
                        st = entry.stat()
                        if media_scanner.is_file_already_processed(
                            str(entry), st.st_size, st.st_mtime
                        ):
                            continue

                        if is_file_stable(entry):
                            print(
                                f"[خدمة المراقبة] معالجة آمنة: {entry.name}"
                            )
                            # في الخدمة الخلفية، نعتمد وضع النسخ دائماً (copy_only=True)
                            # لمنع حذف أو نقل أي ملف دون إشراف مباشر من المستخدم
                            res = media_scanner.process_one_file(entry, copy_only=True)
                            print(
                                "[خدمة المراقبة] النتيجة:",
                                res.get("category"),
                            )
                    except (OSError, PermissionError):
                        continue

        except Exception as e:
            print("خطأ في حلقة الخدمة الخلفية:", e)


_watcher_thread = None
_stop_event = None


def is_watcher_running() -> bool:
    """التحقق مما إذا كان ثريد الخدمة نشطاً"""
    if _watcher_thread is not None and _watcher_thread.is_alive():
        return True
    return is_service_desired_running()


def start_watcher_thread(
    interval_seconds: float = CHECK_INTERVAL_SECONDS,
) -> None:
    """بدء المراقبة في ثريد خلفي (للبيئات التجريبية أو سطح المكتب)"""
    import threading

    global _watcher_thread, _stop_event

    set_service_desired_state(True)
    if _watcher_thread is not None and _watcher_thread.is_alive():
        return

    _stop_event = threading.Event()

    def thread_worker() -> None:
        media_scanner.init_cache_db()
        assert _stop_event is not None
        while not _stop_event.is_set():
            if not is_service_desired_running():
                time.sleep(interval_seconds)
                continue

            try:
                import android_permissions
                import file_manager
                import storage_backend

                prefs = file_manager.get_sorter_preferences()
                source_storage = str(prefs.get("source_storage", "both"))
                target_loc = storage_backend.get_active_target_location()
                tgt_name = target_loc.storage_type if target_loc else "internal"

                can_proceed, _issue_code, _issue_msg, _act = (
                    android_permissions.preflight_scan_access(source_storage, tgt_name)
                )
                if not can_proceed:
                    time.sleep(interval_seconds * 2)
                    continue
            except Exception:
                pass

            try:
                watch_dirs = get_monitored_directories()
                for w_dir in watch_dirs:
                    if not w_dir.exists():
                        continue
                    for entry in w_dir.iterdir():
                        if entry.is_file():
                            ext = entry.suffix.lower()
                            if (
                                ext in media_scanner.IMAGE_EXTENSIONS
                                or ext in media_scanner.VIDEO_EXTENSIONS
                            ):
                                st = entry.stat()
                                if media_scanner.is_file_already_processed(
                                    str(entry), st.st_size, st.st_mtime
                                ):
                                    continue
                                _ = media_scanner.process_one_file(entry)
            except Exception:
                pass
            time.sleep(interval_seconds)

    _watcher_thread = threading.Thread(
        target=thread_worker, daemon=True
    )
    _watcher_thread.start()


def stop_watcher_thread() -> None:
    """إيقاف ثريد المراقبة الخلفي مع انتظار انتهاء المعالجة الجارية"""
    global _watcher_thread
    set_service_desired_state(False)
    if _stop_event is not None:
        _stop_event.set()
    if _watcher_thread is not None and _watcher_thread.is_alive():
        _watcher_thread.join(timeout=2.5)
    _watcher_thread = None


def start_system_service() -> None:
    """بدء خدمة المراقبة بحسب البيئة مع فحص توفر الخدمة وعدم الانهيار"""
    from kivy.utils import platform
    set_service_desired_state(True)
    if platform == "android":
        try:
            from android import mActivity
            from jnius import autoclass
            pkg = mActivity.getPackageName()
            service_class = None
            for s_name in (f"{pkg}.ServiceMediawatcher", f"{pkg}.ServiceMediaWatcher"):
                try:
                    service_class = autoclass(s_name)
                    break
                except Exception:
                    pass

            if service_class is not None:
                service_class.start(mActivity, "")
                print("✓ تم استدعاء بدء خدمة أندرويد بنجاح.")
                return
            else:
                print("تنبيه: لم يتم العثور على فئة الخدمة الخلفية، سيتم استخدام الثريد الداخلي.")
        except Exception as e:
            print("تنبيه: تعذر بدء خدمة أندرويد، البديل الثريد:", e)
    start_watcher_thread()


def stop_system_service() -> None:
    """إيقاف خدمة المراقبة بحسب البيئة بأمان"""
    from kivy.utils import platform
    set_service_desired_state(False)
    if platform == "android":
        try:
            from android import mActivity
            from jnius import autoclass
            pkg = mActivity.getPackageName()
            service_class = None
            for s_name in (f"{pkg}.ServiceMediawatcher", f"{pkg}.ServiceMediaWatcher"):
                try:
                    service_class = autoclass(s_name)
                    break
                except Exception:
                    pass

            if service_class is not None:
                service_class.stop(mActivity)
                print("✓ تم استدعاء إيقاف خدمة أندرويد بنجاح.")
        except Exception as e:
            print("تنبيه: تعذر إيقاف خدمة أندرويد:", e)
    stop_watcher_thread()


if __name__ == "__main__":
    run_watcher_loop()
