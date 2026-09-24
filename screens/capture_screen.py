# -*- coding: utf-8 -*-
"""
شاشة التقاط واختيار الصورة (CaptureScreen):
- تتيح للمستخدم التقاط صورة جديدة بالكاميرا أو اختيار صورة من المعرض/الملفات.
- تدعم العمل على بيئة سطح المكتب (للتطوير والاختبار) وعلى بيئة Android (الهاتف المحمول).
- تعرض معاينة فورية للصورة المختارة مع زر للمتابعة إلى شاشة التصنيف.
"""

import os
from pathlib import Path
from kivy.uix.screenmanager import Screen
from kivy.clock import Clock
from kivy.utils import platform

from utils.arabic_helper import ar
from utils.ui_helper import show_app_dialog
import file_manager


class CaptureScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_image_path = None
        self.dialog = None

    def on_enter(self):
        self.apply_arabic_texts()

    def apply_arabic_texts(self):
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("إضافة ورقة اختبار")
            if "placeholder_label" in self.ids:
                self.ids.placeholder_label.text = ar("لم يتم اختيار صورة بعد")
            if "placeholder_hint" in self.ids:
                self.ids.placeholder_hint.text = ar("اختر صورة واضحة لورقة الاختبار أو عدة صور دفعة واحدة")
            if "text_camera" in self.ids:
                self.ids.text_camera.text = ar("التقاط بالكاميرا")
            if "text_gallery" in self.ids:
                self.ids.text_gallery.text = ar("اختيار من المعرض / دفعة")
            if "text_proceed" in self.ids:
                self.ids.text_proceed.text = ar("تحليل وتصنيف بالذكاء الاصطناعي")

    def reset_view(self):
        """إعادة تعيين الشاشة إلى الحالة الأولية"""
        self.selected_image_path = None
        self.ids.image_preview.source = ""
        self.ids.image_preview.opacity = 0
        self.ids.placeholder_box.opacity = 1
        self.ids.btn_proceed.disabled = True

    def set_selected_image(self, file_path: str):
        """تعيين مسار الصورة المختارة وتحديث واجهة المعاينة"""
        if file_path and os.path.exists(file_path):
            self.selected_image_path = file_path
            self.ids.image_preview.source = file_path
            self.ids.image_preview.reload()
            self.ids.image_preview.opacity = 1
            self.ids.placeholder_box.opacity = 0
            self.ids.btn_proceed.disabled = False

            app = self.get_app()
            queue = getattr(app, "batch_queue", [])
            if queue and "text_proceed" in self.ids:
                self.ids.text_proceed.text = ar(f"تصنيف هذه الورقة ({len(queue)} ورقة إضافية في الانتظار)")
        else:
            self.show_error_dialog(ar("الملف المختار غير صالح أو غير موجود."))

    def pick_from_gallery(self):
        """اختيار صورة أو عدة صور من المعرض أو مستعرض الملفات"""
        # المحاولة أولاً عبر Plyer (يعمل على أندرويد وويندوز)
        try:
            from plyer import filechooser
            filechooser.open_file(
                title=ar("اختر صور أوراق الاختبار"),
                filters=["*.jpg", "*.jpeg", "*.png", "*.webp"],
                multiple=True,
                on_selection=self._on_file_selected
            )
            return
        except Exception as e:
            print("Plyer filechooser غير متوفر:", e)

        # بديل لبيئة سطح المكتب عبر Tkinter مع دعم الاختيار المتعدد
        try:
            import tkinter as tk
            from tkinter import filedialog
            root_tk = tk.Tk()
            root_tk.withdraw()
            root_tk.attributes("-topmost", True)
            file_paths = filedialog.askopenfilenames(
                title="اختر صورة أو عدة صور للاختبارات",
                filetypes=[("Image files", "*.jpg;*.jpeg;*.png;*.webp"), ("All files", "*.*")]
            )
            root_tk.destroy()
            if file_paths:
                self._on_file_selected(file_paths)
                return
        except Exception as e:
            print("تعذر فتح Tkinter filedialog:", e)

        self.show_error_dialog(ar("تعذر فتح مستعرض الملفات في هذا النظام."))

    def _on_file_selected(self, selection):
        """Callback عند اختيار ملف أو عدة ملفات (Batch Mode)"""
        if selection and len(selection) > 0:
            app = self.get_app()
            # الصورة الأولى للمعالجة الحالية، والباقي في طابور الدفعة
            app.batch_queue = list(selection[1:])
            Clock.schedule_once(lambda dt: self.set_selected_image(selection[0]), 0)

    def capture_from_camera(self):
        """التقاط صورة عبر الكاميرا وحفظها في مجلد temp الموحد"""
        if platform == "android":
            try:
                from plyer import camera
                save_dir = file_manager.get_temp_dir()
                temp_filename = f"capture_{os.urandom(4).hex()}.jpg"
                temp_filepath = str(save_dir / temp_filename)

                camera.take_picture(
                    filename=temp_filepath,
                    on_complete=lambda path: Clock.schedule_once(lambda dt: self.set_selected_image(path), 0)
                )
                return
            except Exception as e:
                print("فشل تشغيل كاميرا أندرويد عبر Plyer:", e)

        # على الحاسوب، إعلام المستخدم باختيار صورة كبديل
        self.show_error_dialog(
            ar("الكاميرا متاحة بشكل كامل على الهاتف. يرجى اختيار صورة من المعرض للتجربة على الحاسوب.")
        )

    def proceed_to_classify(self):
        """الانتقال لشاشة التصنيف والبدء في تحليل الصورة"""
        if not self.selected_image_path:
            return

        app = self.get_app()
        classifying_screen = app.root.get_screen("classifying_screen")
        classifying_screen.start_classification(self.selected_image_path)
        app.root.current = "classifying_screen"

    def go_back(self):
        """الرجوع إلى الشاشة الرئيسية"""
        self.reset_view()
        app = self.get_app()
        app.root.current = "home_screen"

    def show_error_dialog(self, message: str):
        """عرض رسالة تنبيه للمستخدم"""
        show_app_dialog(
            title="تنبيه",
            text=message,
        )

    def get_app(self):
        from kivy.app import App
        return App.get_running_app()
