"""
تطبيق Rateb (رتّب): المُنظّم الذكي للوسائط لفرز الصور والفيديوهات والمستندات والاختبارات.
- تهيئة إطار العمل KivyMD وضبط الثيم والخطوط العربية.
- تحميل ملفات التصميم (.kv) وتسجيل الشاشات.
- إدارة أذونات الأجهزة والخدمات بالخلفية والانتقال بين الشاشات.
"""

from __future__ import annotations

import faulthandler
import logging
import os
from pathlib import Path
import sys
import traceback
from typing import Any, Literal

from dotenv import load_dotenv
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.uix.screenmanager import NoTransition, ScreenManager
from kivy.utils import platform
from kivymd.app import MDApp

import file_manager
from screens.capture_screen import CaptureScreen
from screens.classifying_screen import ClassifyingScreen
from screens.confirm_screen import ConfirmScreen
from screens.home_screen import HomeScreen
from screens.intro_screen import IntroScreen
from screens.people_setup_screen import PeopleSetupScreen
from screens.settings_screen import SettingsScreen
from screens.subject_detail_screen import SubjectDetailScreen
from service import media_watcher_service
from utils.arabic_helper import ar, get_arabic_font_path

# مسار ملف التشخيص الدائم cosmosort_debug.log في التخزين الخاص للتطبيق (ANDROID_PRIVATE)
DEBUG_LOG_FILE: Path | None = None
_private_candidates: list[Path] = []

_android_private = os.environ.get("ANDROID_PRIVATE")
if _android_private:
    _private_candidates.append(Path(_android_private) / "cosmosort_debug.log")
    _private_candidates.append(Path(_android_private) / "app" / "cosmosort_debug.log")

_app_dir = Path(__file__).resolve().parent
_private_candidates.append(_app_dir / "cosmosort_debug.log")
_private_candidates.append(Path.home() / ".cosmosort" / "cosmosort_debug.log")

for _candidate in _private_candidates:
    try:
        _candidate.parent.mkdir(parents=True, exist_ok=True)
        _candidate.touch(exist_ok=True)
        DEBUG_LOG_FILE = _candidate
        break
    except Exception:
        pass

# تفعيل faulthandler فوراً لالتقاط انهيارات C/C++ و SIGSEGV قبل تحميل أي مكتبات
if DEBUG_LOG_FILE is not None:
    try:
        _fh_stream = open(DEBUG_LOG_FILE, "a", encoding="utf-8", buffering=1)
        faulthandler.enable(file=_fh_stream, all_threads=True)
    except Exception:
        pass

# إعداد السجل الرئيسي FileHandler لتسجيل كل ما يحدث في التطبيق
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
if DEBUG_LOG_FILE is not None:
    try:
        _file_handler = logging.FileHandler(
            str(DEBUG_LOG_FILE), encoding="utf-8"
        )
        _file_handler.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
        )
        logging.getLogger().addHandler(_file_handler)
    except Exception:
        pass

logger = logging.getLogger("CosmoSortApp")
logger.info("=== بدء تشغيل تطبيق CosmoSort (كوزمو سورت) ===")
logger.info("Python: %s | Platform: %s", sys.version, sys.platform)


def _handle_uncaught_exception(exctype: Any, value: Any, tb: Any) -> None:
    err = "".join(traceback.format_exception(exctype, value, tb))
    logger.critical("CRITICAL UNCAUGHT EXCEPTION: %s", err)
    try:
        for log_target in [
            DEBUG_LOG_FILE,
            Path("/storage/emulated/0/Download/cosmosort_crash.log"),
            Path("/storage/emulated/0/cosmosort_crash.log"),
            Path(__file__).resolve().parent / "crash.log",
        ]:
            if log_target is not None:
                try:
                    with open(log_target, "a", encoding="utf-8") as f:
                        f.write(f"\n--- CRASH AT {err}\n")
                    break
                except Exception:
                    pass
    except Exception:
        pass
    sys.__excepthook__(exctype, value, tb)


sys.excepthook = _handle_uncaught_exception


def _handle_thread_exception(args: Any) -> None:
    err = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    thread_name = getattr(args.thread, "name", "unknown_thread")
    logger.critical("CRITICAL THREAD EXCEPTION in [%s]: %s", thread_name, err)
    if DEBUG_LOG_FILE is not None:
        try:
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n--- THREAD CRASH [{thread_name}] ---\n{err}\n")
        except Exception:
            pass


import threading
threading.excepthook = _handle_thread_exception

# تحميل المتغيرات من .env بأمان
try:
    dotenv_file = Path(__file__).resolve().parent / ".env"
    if dotenv_file.exists():
        _ = load_dotenv(dotenv_path=str(dotenv_file))
except OSError as e:
    logger.debug("Failed to load .env: %s", e)

# 1. تسجيل الخط العربي على مستوى المحرك بالكامل قبل تحميل أي واجهات
font_path = get_arabic_font_path()
if font_path and os.path.exists(font_path):
    font_names = (
        "Roboto",
        "RobotoMedium",
        "RobotoLight",
        "RobotoThin",
        "RobotoBlack",
        "ArabicFont",
    )
    for f_name in font_names:
        try:
            LabelBase.register(
                name=f_name,
                fn_regular=font_path,
                fn_bold=font_path,
                fn_italic=font_path,
                fn_bolditalic=font_path,
            )
        except OSError as e:
            logger.warning("تنبيه أثناء تسجيل الخط %s: %s", f_name, e)

# 2. درع حماية معالجات الرسوميات Adreno من انهيار FBO / Stencil داخل Ripple
try:
    import kivymd.uix.behaviors.ripple_behavior as rb

    def _no_op_ripple(*args: Any, **kwargs: Any) -> None:
        return None

    if hasattr(rb, "M3CommonRipple"):
        rb.M3CommonRipple.call_ripple_animation_methods = _no_op_ripple
        rb.M3CommonRipple.lay_canvas_instructions = _no_op_ripple
        rb.M3CommonRipple._call_ripple_animation_methods = _no_op_ripple
        rb.M3CommonRipple.start_ripple = _no_op_ripple
    if hasattr(rb, "CommonRipple"):
        rb.CommonRipple.lay_canvas_instructions = _no_op_ripple
except Exception as _e:
    pass


class CosmoSortApp(MDApp):
    title: str = "Rateb - رتّب | المُنظّم الذكي"
    api_key: str = ""
    arabic_font: str = ""
    batch_queue: list[object]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.title = "Rateb - رتّب | المُنظّم الذكي"
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.arabic_font = font_path or "Roboto"
        self.batch_queue = []

    def ar(self, text: str) -> str:
        """مساعد عام لتشكيل وعكس النصوص العربية في ملفات KV"""
        return ar(text)

    def build(self) -> ScreenManager:
        """بناء التطبيق وضبط الواجهة والشاشات"""
        # ضبط نمط سمائي كوني فاتح ومضيء (Light Celestial Sky)
        self.theme_cls.primary_palette = "#0284C7"
        self.theme_cls.theme_style = "Light"
        if Window is not None:
            # خلفية سماء فاتحة كونية ناصعة ومريحة للعين
            Window.clearcolor = (0.94, 0.97, 1.0, 1.0)

        # تنظيف الملفات المؤقتة القديمة عند بدء التشغيل
        _ = file_manager.cleanup_temp_files()

        # إعداد الحجم المريح والملائم على الحاسوب وشاشات الويب
        if Window is not None and platform not in ("android", "ios"):
            Window.size = (420, 760)
            Window.minimum_width = 340
            Window.minimum_height = 500

        # تحميل ملفات التصميم .kv
        kv_dir = Path(__file__).resolve().parent / "kv"
        for kv_file in [
            "intro_screen.kv",
            "home_screen.kv",
            "capture_screen.kv",
            "classifying_screen.kv",
            "confirm_screen.kv",
            "subject_detail_screen.kv",
            "people_setup_screen.kv",
            "settings_screen.kv",
        ]:
            file_path = kv_dir / kv_file
            if file_path.exists():
                _ = Builder.load_file(str(file_path))

        # إنشاء مدير الشاشات وإضافة الشاشات
        sm = ScreenManager(transition=NoTransition())
        sm.add_widget(IntroScreen(name="intro_screen"))
        sm.add_widget(HomeScreen(name="home_screen"))
        sm.add_widget(CaptureScreen(name="capture_screen"))
        sm.add_widget(ClassifyingScreen(name="classifying_screen"))
        sm.add_widget(ConfirmScreen(name="confirm_screen"))
        sm.add_widget(SubjectDetailScreen(name="subject_detail_screen"))
        sm.add_widget(PeopleSetupScreen(name="people_setup_screen"))
        sm.add_widget(SettingsScreen(name="settings_screen"))

        # فحص تفضيل تخطي شاشة البداية (تظهر أول مرة فقط تلقائياً، أو حسب خيار الإعدادات)
        prefs = file_manager.get_sorter_preferences()
        skip_pref = prefs.get("skip_intro", None)
        if skip_pref is None:
            should_skip = bool(prefs.get("intro_seen", False))
        else:
            should_skip = bool(skip_pref)

        if should_skip:
            sm.current = "home_screen"
        else:
            sm.current = "intro_screen"

        # ربط زر الرجوع الفعلي للجوال للعودة للرئيسية بدلاً من الخروج
        if Window is not None:
            Window.bind(on_keyboard=self.on_hardware_back_key)

        return sm

    def on_start(self) -> None:
        """يُستدعى تلقائياً فور اكتمال MDApp.build() وبدء عرض الإطار الرسومي"""
        logger.info("تم اكتمال MDApp.build() وبدء دورة حياة on_start")

        # 1. تسجيل التشخيص الشامل للجهاز والصلاحيات والتخزين
        self._log_system_diagnostics()

        # 2. ربط معالج نتائج أنشطة أندرويد الرسمية (SAF Folder Picker)
        if platform == "android":
            try:
                from android import activity
                activity.bind(on_activity_result=self.on_activity_result)
                logger.info("تم ربط on_activity_result بنجاح لمتابعة أذونات SAF")
            except Exception as e:
                logger.debug("تنبيه أثناء ربط activity result: %s", e)

            # طلب الصلاحيات الأساسية بعد ظهور الواجهة
            Clock.schedule_once(lambda _dt: self.request_android_permissions(), 1.0)

        # استرجاع أي عملية حذف معلقة لـ RecoverableSecurityException من التخزين الخاص بالتطبيق
        try:
            pending_rec = storage_backend.get_pending_recoverable_deletion()
            if pending_rec:
                logger.info(
                    "توجد عملية حذف معلقة لـ RecoverableSecurityException محفوظة من جلسة سابقة (الملف: %s)",
                    pending_rec.get("src_path"),
                )
        except Exception as e_p:
            logger.debug("تنبيه فحص العملية المعلقة لـ RecoverableSecurityException: %s", e_p)

        # 3. تشغيل خدمة المراقبة بالخلفية فقط إذا كانت مفعلة برغبة المستخدم بعد تأخير آمن
        if media_watcher_service.is_service_desired_running():
            def _delayed_service_start(_dt: float) -> None:
                try:
                    if platform == "android":
                        if file_manager.is_all_files_access_granted():
                            media_watcher_service.start_system_service()
                        else:
                            logger.info("تأجيل تشغيل خدمة المراقبة لحين منح صلاحية الوصول للملفات")
                    else:
                        media_watcher_service.start_system_service()
                except Exception as e:
                    logger.error("فشل بدء الخدمة في on_start: %s", e, exc_info=True)

            Clock.schedule_once(_delayed_service_start, 3.5)

    def _log_system_diagnostics(self) -> None:
        """تسجيل تفاصيل المنظومة ومسارات التخزين بدقة في سجل دائم"""
        try:
            lines = [
                f"Rateb App Version: 2.0.1",
                f"Platform: {platform} | Python: {sys.version.split()[0]}",
            ]
            if platform == "android":
                try:
                    from jnius import autoclass
                    Build = autoclass("android.os.Build")
                    BuildVersion = autoclass("android.os.Build$VERSION")
                    lines.append(f"Device: {Build.MANUFACTURER} {Build.MODEL}")
                    lines.append(f"Android SDK: {BuildVersion.SDK_INT} (Release: {BuildVersion.RELEASE})")
                    lines.append(f"ABIs: {list(Build.SUPPORTED_ABIS)}")
                except Exception as e:
                    lines.append(f"Build info query error: {e}")

                try:
                    lines.append(f"All Files Access: {file_manager.is_all_files_access_granted()}")
                except Exception as e:
                    lines.append(f"All Files Access query error: {e}")

            try:
                import storage_backend
                locs = storage_backend.detect_storage_locations()
                for lid, loc in locs.items():
                    lines.append(
                        f"Storage [{lid}]: detected={loc.detected}, mounted={loc.mounted}, "
                        f"writable={loc.writable}, requires_saf={loc.requires_saf}, "
                        f"free={loc.free_gb}GB, path={loc.path}"
                    )
            except Exception as e:
                lines.append(f"Storage locations query error: {e}")

            logger.info("=== SYSTEM DIAGNOSTICS REPORT ===\n%s\n=================================", "\n".join(lines))
        except Exception as e:
            logger.debug("Failed writing diagnostics: %s", e)

    def on_activity_result(self, request_code: int, result_code: int, intent: Any) -> None:
        """معالجة نتيجة منتقي مجلدات بطاقة الذاكرة الخارجية عبر SAF (Request Code 4201)"""
        logger.info("on_activity_result: request_code=%s, result_code=%s", request_code, result_code)
        if request_code == 4201:
            try:
                from jnius import autoclass
                Activity = autoclass("android.app.Activity")
                if result_code == Activity.RESULT_OK and intent is not None:
                    tree_uri = intent.getData()
                    if tree_uri is not None:
                        from android import mActivity
                        Intent = autoclass("android.content.Intent")
                        intent_flags = intent.getFlags() if hasattr(intent, "getFlags") else 0
                        take_flags = intent_flags & (
                            Intent.FLAG_GRANT_READ_URI_PERMISSION
                            | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                        )
                        if not take_flags:
                            take_flags = (
                                Intent.FLAG_GRANT_READ_URI_PERMISSION
                                | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                            )
                        cr = mActivity.getContentResolver()
                        try:
                            cr.takePersistableUriPermission(tree_uri, take_flags)
                            logger.info("تم منح وحفظ takePersistableUriPermission بنجاح (Flags: %s)", take_flags)
                        except Exception as e:
                            logger.warning("تنبيه takePersistableUriPermission: %s", e)

                        uri_str = str(tree_uri.toString())
                        import storage_backend
                        storage_backend.save_saf_persisted_uri(uri_str)
                        storage_backend.clear_storage_detect_cache()
                        file_manager.save_sorter_preferences({
                            "target_storage": "sdcard",
                            "saf_sdcard_uri": uri_str,
                        })

                        # التحقق من صلاحية SAF URI الفعلية بعد الحفظ قبل بدء أي فحص
                        saf_valid = storage_backend.is_saf_uri_valid(uri_str)
                        if not saf_valid:
                            logger.warning("إذن SAF غير مكتمل أو لم يتم تثبيته لـ URI: %s", uri_str)
                            from utils.ui_helper import show_modern_notification
                            show_modern_notification(
                                "تنبيه إذن البطاقة",
                                "لم يتم تثبيت إذن الكتابة لبطاقة الذاكرة بشكل صحيح، يرجى إعادة المحاولة",
                                notif_type="warning",
                            )
                            return

                        from utils.ui_helper import show_modern_notification
                        show_modern_notification(
                            "تم اعتماد كرت SD",
                            "تم منح إذن الحفظ والفرز في بطاقة الذاكرة الخارجية بنجاح",
                            notif_type="success",
                        )

                        if self.root and hasattr(self.root, "get_screen"):
                            try:
                                settings = self.root.get_screen("settings_screen")
                                if settings and hasattr(settings, "refresh_storage_destination_ui"):
                                    settings.refresh_storage_destination_ui()
                            except Exception:
                                pass

                            # استئناف الفحص المعلق إن وجد بعد التأكد من الصلاحية
                            pending = file_manager.get_pending_scan()
                            if pending.get("active") and pending.get("target") == "sdcard":
                                if storage_backend.is_saf_uri_valid(uri_str):
                                    file_manager.clear_pending_scan()
                                    try:
                                        home = self.root.get_screen("home_screen")
                                        if home and hasattr(home, "start_scan_with_options"):
                                            from kivy.clock import Clock
                                            src_chosen = pending.get("source", "both")
                                            Clock.schedule_once(
                                                lambda _dt: home.start_scan_with_options(
                                                    src_chosen, "sdcard"
                                                ),
                                                0.5,
                                            )
                                    except Exception as e_res:
                                        logger.warning("تعذر استئناف الفحص المعلق: %s", e_res)
            except Exception as e:
                logger.error("خطأ أثناء معالجة إذن SAF: %s", e, exc_info=True)

        elif request_code == 4202:
            try:
                from jnius import autoclass
                Activity = autoclass("android.app.Activity")
                import storage_backend
                is_ok = (result_code == Activity.RESULT_OK)
                logger.info(
                    "on_activity_result 4202: تم استلام استجابة المستخدم لطلب تأكيد الحذف (موافقة: %s)",
                    is_ok,
                )
                storage_backend.handle_recoverable_deletion_result(is_ok)
            except Exception as e:
                logger.error("خطأ أثناء معالجة نتيجة RecoverableSecurityException: %s", e, exc_info=True)

    def on_hardware_back_key(
        self, _window: object, key: int, *_args: object
    ) -> bool:
        """التعامل الذكي مع زر الرجوع بأندرويد (مفتاح 27)"""
        if (
            key == 27
            and hasattr(self, "root")
            and self.root
            and hasattr(self.root, "current")
            and self.root.current not in ("home_screen", "intro_screen")
        ):
            try:
                cur_screen = self.root.get_screen(self.root.current)
                if hasattr(cur_screen, "go_back"):
                    cur_screen.go_back()
                else:
                    self.root.current = "home_screen"
            except (AttributeError, KeyError, RuntimeError) as e:
                logger.debug("خطأ أثناء الرجوع بالزر الخلفي: %s", e)
                self.root.current = "home_screen"
            return True  # استهلاك الحدث لمنع خروج التطبيق
        return False

    def on_pause(self) -> Literal[True]:
        """السماح للتطبيق بالبقاء في الخلفية دون إنهاء السياق الرسومي"""
        return True

    def on_resume(self) -> None:
        """استئناف التطبيق عند العودة من الخلفية والتحقق من الفحص المعلق"""
        # استئناف أي فحص كان معلقاً بانتظار موافقة المستخدم على الصلاحيات
        try:
            is_pending, p_src, p_tgt = file_manager.get_pending_scan_info()
            if is_pending and file_manager.is_all_files_access_granted():
                file_manager.clear_pending_scan()
                if self.root and hasattr(self.root, "get_screen"):
                    home = self.root.get_screen("home_screen")
                    if home and hasattr(home, "start_scan_with_options"):
                        Clock.schedule_once(
                            lambda _dt: home.start_scan_with_options(p_src, p_tgt),
                            0.5,
                        )
        except Exception as e:
            logger.debug("تنبيه أثناء فحص الفحص المعلق في on_resume: %s", e)

    def request_android_permissions(self) -> None:
        """طلب صلاحيات الكاميرا والوسائط الأساسية على أجهزة أندرويد (تغطي أندرويد 8 حتى 15)"""
        try:
            from android.permissions import (  # type: ignore
                Permission,
                request_permissions,
            )

            perms = [
                Permission.CAMERA,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ]
            # دعم أندرويد 13+ و 14+ للصور والفيديوهات والصوتيات
            for extra_perm in [
                "READ_MEDIA_IMAGES",
                "READ_MEDIA_VIDEO",
                "READ_MEDIA_AUDIO",
                "READ_MEDIA_VISUAL_USER_SELECTED",
                "POST_NOTIFICATIONS",
            ]:
                if hasattr(Permission, extra_perm):
                    perms.append(getattr(Permission, extra_perm))

            request_permissions(perms)
        except Exception as e:
            logger.warning("تنبيه: تعذر استدعاء مكتبة صلاحيات أندرويد: %s", e)

    def check_and_request_all_files_permission(self) -> None:
        """طلب إذن الوصول الكامل لكافة الملفات عبر المعالج الآمن في file_manager"""
        if platform != "android":
            return
        try:
            if not file_manager.is_all_files_access_granted():
                file_manager.open_all_files_permission_settings()
        except Exception as e:
            logger.warning("تنبيه: تعذر فتح إعدادات إذن الملفات: %s", e)


# التوافق مع أي استدعاءات خارجية سابقة
ExamSorterApp = CosmoSortApp
RatebApp = CosmoSortApp

if __name__ == "__main__":
    CosmoSortApp().run()
