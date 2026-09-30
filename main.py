"""
تطبيق CosmoSort (كوزمو سورت): منظّم الوسائط الكوني والذكي لفرز الصور والفيديوهات والاختبارات.
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


class CosmoSortApp(MDApp):
    title: str = "CosmoSort - جامع العوالم الذكي"
    api_key: str = ""
    arabic_font: str = ""
    batch_queue: list[object]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.title = "CosmoSort - جامع العوالم الذكي"
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

        # بدء تشغيل خدمة المراقبة بالخلفية إذا كانت مفعلة برغبة المستخدم
        if media_watcher_service.is_service_desired_running():
            def _delayed_service_start(_dt: float) -> None:
                media_watcher_service.start_system_service()

            Clock.schedule_once(_delayed_service_start, 2.0)

        return sm

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
        if Window is not None:
            try:
                Window.update_viewport()
            except Exception:
                pass

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

if __name__ == "__main__":
    CosmoSortApp().run()
