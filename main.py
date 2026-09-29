"""
تطبيق CosmoSort (كوزمو سورت): منظّم الوسائط الكوني والذكي لفرز الصور والفيديوهات والاختبارات.
- تهيئة إطار العمل KivyMD وضبط الثيم والخطوط العربية.
- تحميل ملفات التصميم (.kv) وتسجيل الشاشات.
- إدارة أذونات الأجهزة والخدمات بالخلفية والانتقال بين الشاشات.
"""

import logging
import os
from pathlib import Path
from typing import override

from dotenv import load_dotenv
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.uix.screenmanager import FadeTransition, ScreenManager
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

logger = logging.getLogger("CosmoSortApp")

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
    title: str = "CosmoSort ✦ جامع العوالم الذكي"
    api_key: str = ""
    arabic_font: str = ""
    batch_queue: list[object]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.title = "CosmoSort ✦ جامع العوالم الذكي"
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.arabic_font = font_path or "Roboto"
        self.batch_queue = []

    def ar(self, text: str) -> str:
        """مساعد عام لتشكيل وعكس النصوص العربية في ملفات KV"""
        return ar(text)

    @override
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

        # طلب أذونات أندرويد عند بدء التشغيل
        if platform == "android":
            self.request_android_permissions()

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
        sm = ScreenManager(transition=FadeTransition(duration=0.25))
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

    def request_android_permissions(self) -> None:
        """طلب صلاحيات الكاميرا والتخزين على أجهزة أندرويد"""
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
            if hasattr(Permission, "READ_MEDIA_IMAGES"):
                perms.append(Permission.READ_MEDIA_IMAGES)
            if hasattr(Permission, "READ_MEDIA_VIDEO"):
                perms.append(Permission.READ_MEDIA_VIDEO)
            if hasattr(Permission, "POST_NOTIFICATIONS"):
                perms.append(Permission.POST_NOTIFICATIONS)
            request_permissions(perms)
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.warning("تنبيه: تعذر استدعاء مكتبة صلاحيات أندرويد: %s", e)

        self.check_and_request_all_files_permission()

    def check_and_request_all_files_permission(self) -> None:
        """طلب إذن الوصول الكامل لكافة الملفات على أندرويد 11+"""
        if platform != "android":
            return
        try:
            from android import mActivity  # type: ignore
            from jnius import autoclass  # type: ignore

            Environment = autoclass("android.os.Environment")
            BuildVersion = autoclass("android.os.Build$VERSION")

            sdk_ver = int(BuildVersion.SDK_INT)
            is_mgr = bool(Environment.isExternalStorageManager())
            if sdk_ver >= 30 and not is_mgr:
                Intent = autoclass("android.content.Intent")
                Settings = autoclass("android.provider.Settings")
                Uri = autoclass("android.net.Uri")

                action = Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION
                intent = Intent(action)
                pkg_name = str(mActivity.getPackageName())
                uri = Uri.fromParts("package", pkg_name, None)
                intent.setData(uri)
                mActivity.startActivity(intent)
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.warning(
                "تنبيه: تعذر فتح إعدادات إذن الوصول لكافة الملفات: %s", e
            )


# التوافق مع أي استدعاءات خارجية سابقة
ExamSorterApp = CosmoSortApp

if __name__ == "__main__":
    CosmoSortApp().run()
