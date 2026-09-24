# -*- coding: utf-8 -*-
"""
شاشة انتظار التصنيف (ClassifyingScreen):
- تعرض مؤشر تحميل أنيق أثناء معالجة الصورة وإرسالها للذكاء الاصطناعي.
- تعمل في Thread مستقل حتى لا تتجمد واجهة المستخدم.
- تنقل المستخدم لشاشة التأكيد (ConfirmScreen) سواء نجح التصنيف التلقائي
  أو حدث خطأ (مع تمرير رسالة الخطأ ليقوم المستخدم بالإدخال اليدوي).
"""

import threading
from kivy.uix.screenmanager import Screen
from kivy.clock import Clock

import classifier
from utils.arabic_helper import ar


class ClassifyingScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.image_path = None
        self.is_cancelled = False
        self.worker_thread = None

    def on_enter(self):
        self.apply_arabic_texts()

    def apply_arabic_texts(self):
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("جاري تحليل الورقة")
            elif hasattr(self.ids.top_bar, "title"):
                self.ids.top_bar.title = ar("جاري تحليل الورقة")
            if "title_label" in self.ids:
                self.ids.title_label.text = ar("جاري تحليل ورقة الاختبار...")
            if "status_label" in self.ids:
                self.ids.status_label.text = ar("قراءة الترويسة واستخراج اسم المادة عبر الذكاء الاصطناعي")
            if "step1_label" in self.ids:
                self.ids.step1_label.text = ar("✓ فحص الصورة واستخراج النصوص")
            if "step2_label" in self.ids:
                self.ids.step2_label.text = ar("• تحديد اسم المادة والمقرر الدراسي...")
            if "text_cancel" in self.ids:
                self.ids.text_cancel.text = ar("إلغاء والعودة")

    def start_classification(self, image_path: str):
        """بدء عملية التصنيف في خلفية منفصلة"""
        self.image_path = image_path
        self.is_cancelled = False
        if hasattr(self, "ids") and "spinner" in self.ids:
            self.ids.spinner.active = True

        app = self.get_app()
        api_key = getattr(app, "api_key", None)

        self.worker_thread = threading.Thread(
            target=self._classify_worker,
            args=(image_path, api_key),
            daemon=True
        )
        self.worker_thread.start()

    def _classify_worker(self, image_path: str, api_key: str):
        """المهمة التي تعمل في الخلفية"""
        detected_name = ""
        error_msg = None

        try:
            detected_name = classifier.classify_exam_image(
                image_path=image_path,
                api_key=api_key,
                fallback_to_ocr=True
            )
        except classifier.ClassificationError as ce:
            error_msg = str(ce)
        except Exception as e:
            error_msg = f"خطأ غير متوقع: {str(e)}"

        # تحديث الواجهة عبر الثريد الرئيسي لـ Kivy
        Clock.schedule_once(
            lambda dt: self._on_classification_finished(detected_name, error_msg),
            0
        )

    def _on_classification_finished(self, detected_name: str, error_msg: str):
        """التعامل مع نتيجة التصنيف بعد انتهاء الـ Thread"""
        if self.is_cancelled:
            # تم الإلغاء من قبل المستخدم؛ نتجاهل النتيجة بهدوء
            return

        if hasattr(self, "ids") and "spinner" in self.ids:
            self.ids.spinner.active = False
        app = self.get_app()
        confirm_screen = app.root.get_screen("confirm_screen")
        confirm_screen.set_classification_data(
            image_path=self.image_path,
            detected_subject=detected_name,
            error_message=error_msg
        )
        app.root.current = "confirm_screen"

    def cancel_classification(self):
        """
        إلغاء العملية والعودة لشاشة الكاميرا/المعرض.
        ملاحظة: خيط الشبكة في بايثون يعمل كـ daemon وينتهي عند اكتمال الاستجابة،
        ولكن يتم تجاهل نتيجته بفضل علم self.is_cancelled ولن يتأثر التطبيق.
        """
        self.is_cancelled = True
        if hasattr(self, "ids") and "spinner" in self.ids:
            self.ids.spinner.active = False
        app = self.get_app()
        app.root.current = "capture_screen"

    def get_app(self):
        from kivy.app import App
        return App.get_running_app()
