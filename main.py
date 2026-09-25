# -*- coding: utf-8 -*-
"""
نقطة انطلاق تطبيق مصنّف صور الاختبارات الجامعية (Exam Sorter).
- تهيئة إطار العمل KivyMD وضبط الثيم والخطوط العربية.
- تحميل ملفات التصميم (.kv) وتسجيل الشاشات الخمس.
- طلب صلاحيات نظام Android (الكاميرا ووحدات التخزين) تلقائياً عند التشغيل.
- إدارة الانتقال بين الشاشات وحفظ مفتاح API.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from kivy.core.window import Window
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivy.core.text import LabelBase
from kivy.utils import platform

from kivymd.app import MDApp

# تحميل المتغيرات من .env
load_dotenv()

# استيراد الشاشات
from screens.home_screen import HomeScreen
from screens.capture_screen import CaptureScreen
from screens.classifying_screen import ClassifyingScreen
from screens.confirm_screen import ConfirmScreen
from screens.subject_detail_screen import SubjectDetailScreen
from screens.people_setup_screen import PeopleSetupScreen
from screens.settings_screen import SettingsScreen


# 1. تسجيل الخط العربي على مستوى المحرك بالكامل قبل تحميل أي واجهات
from utils.arabic_helper import get_arabic_font_path, ar
font_path = get_arabic_font_path()
if font_path and os.path.exists(font_path):
    for f_name in ("Roboto", "RobotoMedium", "RobotoLight", "RobotoThin", "RobotoBlack", "ArabicFont"):
        try:
            LabelBase.register(
                name=f_name,
                fn_regular=font_path,
                fn_bold=font_path,
                fn_italic=font_path,
                fn_bolditalic=font_path,
            )
        except Exception as e:
            print(f"تنبيه أثناء تسجيل الخط {f_name}:", e)


class ExamSorterApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "وسائط ذكية - AI Media Organizer"
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.arabic_font = font_path or "Roboto"
        self.batch_queue = []

    def ar(self, text: str) -> str:
        """مساعد عام لتشكيل وعكس النصوص العربية في ملفات KV"""
        return ar(text)

    def build(self):
        """بناء التطبيق وضبط الواجهة والشاشات"""
        # ضبط مظهر Material Design 3 العصري بالبيج والعاجي الفاخر
        self.theme_cls.primary_palette = "Brown"
        self.theme_cls.theme_style = "Light"
        Window.clearcolor = (0.976, 0.965, 0.945, 1)

        # تنظيف الملفات المؤقتة القديمة عند بدء التشغيل
        import file_manager
        file_manager.cleanup_temp_files()

        # إعداد الحجم المريح والملائم على الحاسوب وشاشات الويب
        if platform not in ("android", "ios"):
            Window.size = (420, 760)
            Window.minimum_width = 340
            Window.minimum_height = 500

        # طلب أذونات أندرويد عند بدء التشغيل
        if platform == "android":
            self.request_android_permissions()

        # تحميل ملفات التصميم .kv
        kv_dir = Path(__file__).resolve().parent / "kv"
        for kv_file in [
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
                Builder.load_file(str(file_path))

        # إنشاء مدير الشاشات وإضافة الشاشات
        sm = ScreenManager(transition=FadeTransition(duration=0.15))
        sm.add_widget(HomeScreen(name="home_screen"))
        sm.add_widget(CaptureScreen(name="capture_screen"))
        sm.add_widget(ClassifyingScreen(name="classifying_screen"))
        sm.add_widget(ConfirmScreen(name="confirm_screen"))
        sm.add_widget(SubjectDetailScreen(name="subject_detail_screen"))
        sm.add_widget(PeopleSetupScreen(name="people_setup_screen"))
        sm.add_widget(SettingsScreen(name="settings_screen"))

        sm.current = "home_screen"

        # بدء تشغيل خدمة المراقبة بالخلفية إذا كانت مفعلة برغبة المستخدم
        from kivy.clock import Clock
        from service import media_watcher_service
        if media_watcher_service.is_service_desired_running():
            Clock.schedule_once(lambda dt: media_watcher_service.start_system_service(), 2.0)

        return sm

    def request_android_permissions(self):
        """طلب صلاحيات الكاميرا والتخزين على أجهزة أندرويد"""
        try:
            from android.permissions import request_permissions, Permission
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
        except Exception as e:
            print("تنبيه: تعذر استدعاء مكتبة صلاحيات أندرويد:", e)

        self.check_and_request_all_files_permission()

    def check_and_request_all_files_permission(self):
        """طلب إذن الوصول الكامل لكافة الملفات (MANAGE_EXTERNAL_STORAGE) على أندرويد 11+"""
        if platform != "android":
            return
        try:
            from jnius import autoclass
            from android import mActivity

            Environment = autoclass("android.os.Environment")
            Build = autoclass("android.os.Build")

            if Build.VERSION.SDK_INT >= 30:  # Android 11+
                if not Environment.isExternalStorageManager():
                    Intent = autoclass("android.content.Intent")
                    Settings = autoclass("android.provider.Settings")
                    Uri = autoclass("android.net.Uri")

                    intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                    uri = Uri.fromParts("package", mActivity.getPackageName(), None)
                    intent.setData(uri)
                    mActivity.startActivity(intent)
        except Exception as e:
            print("تنبيه: تعذر فتح إعدادات إذن الوصول لكافة الملفات:", e)


if __name__ == "__main__":
    ExamSorterApp().run()
