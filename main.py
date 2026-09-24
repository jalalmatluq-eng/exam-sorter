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
        self.title = "Exam Sorter - مصنّف الاختبارات"
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.arabic_font = font_path or "Roboto"
        self.batch_queue = []

    def ar(self, text: str) -> str:
        """مساعد عام لتشكيل وعكس النصوص العربية في ملفات KV"""
        return ar(text)

    def build(self):
        """بناء التطبيق وضبط الواجهة والشاشات"""
        # ضبط مظهر Material Design 3 العصري
        self.theme_cls.primary_palette = "Indigo"
        self.theme_cls.theme_style = "Light"

        # تنظيف الملفات المؤقتة القديمة عند بدء التشغيل
        import file_manager
        file_manager.cleanup_temp_files()

        # محاكاة حجم شاشة الهاتف عند التشغيل على الحاسوب
        if platform not in ("android", "ios"):
            Window.size = (412, 732)

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

        sm.current = "home_screen"
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
            request_permissions(perms)
        except Exception as e:
            print("تنبيه: تعذر استدعاء مكتبة صلاحيات أندرويد:", e)


if __name__ == "__main__":
    ExamSorterApp().run()
