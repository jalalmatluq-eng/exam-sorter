"""
شاشة التقاط واختيار الصورة (CaptureScreen):
- تتيح للمستخدم التقاط صورة جديدة بالكاميرا أو اختيار صورة من المعرض.
- تدعم العمل على سطح المكتب وعلى Android.
- تعرض معاينة فورية للصورة مع زر للمتابعة إلى شاشة التصنيف.
"""

import os

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.utils import platform

import file_manager
from utils.arabic_helper import ar
from utils.ui_helper import show_app_dialog


class CaptureScreen(Screen):
    selected_image_path: str | None
    dialog: object | None

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.selected_image_path = None
        self.dialog = None

    def on_enter(self, *args: object) -> None:
        self.apply_arabic_texts()

    def apply_arabic_texts(self) -> None:
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("إضافة ورقة اختبار")
            if "placeholder_label" in self.ids:
                self.ids.placeholder_label.text = ar(
                    "لم يتم اختيار صورة بعد"
                )
            if "placeholder_hint" in self.ids:
                self.ids.placeholder_hint.text = ar(
                    "اختر صورة واضحة لورقة الاختبار"
                )
            if "text_camera" in self.ids:
                self.ids.text_camera.text = ar("التقاط بالكاميرا")
            if "text_gallery" in self.ids:
                self.ids.text_gallery.text = ar(
                    "اختيار من المعرض / دفعة"
                )
            if "text_proceed" in self.ids:
                self.ids.text_proceed.text = ar(
                    "تحليل وتصنيف بالذكاء الاصطناعي"
                )

    def reset_view(self) -> None:
        """إعادة تعيين الشاشة إلى الحالة الأولية"""
        self.selected_image_path = None
        self.ids.image_preview.source = ""
        self.ids.image_preview.opacity = 0
        self.ids.placeholder_box.opacity = 1
        self.ids.btn_proceed.disabled = True

    def set_selected_image(self, file_path: str) -> None:
        """تعيين مسار الصورة المختارة وتحديث واجهة المعاينة"""
        if file_path and os.path.exists(file_path):
            self.selected_image_path = file_path
            self.ids.image_preview.source = file_path
            self.ids.image_preview.reload()
            self.ids.image_preview.opacity = 1
            self.ids.placeholder_box.opacity = 0
            self.ids.btn_proceed.disabled = False

            app = self.get_app()
            queue: list[str] = getattr(app, "batch_queue", [])
            if queue and "text_proceed" in self.ids:
                self.ids.text_proceed.text = ar(
                    f"تصنيف هذه الورقة ({len(queue)} ورقة في الانتظار)"
                )
        else:
            self.show_error_dialog(
                ar("الملف المختار غير صالح أو غير موجود.")
            )

    def pick_from_gallery(self) -> None:
        """اختيار صورة أو عدة صور من المعرض أو مستعرض الملفات"""
        try:
            from plyer import filechooser  # type: ignore[import-untyped]
            filechooser.open_file(
                title=ar("اختر صور أوراق الاختبار"),
                filters=["*.jpg", "*.jpeg", "*.png", "*.webp"],
                multiple=True,
                on_selection=self._on_file_selected,
            )
            return
        except Exception as e:
            print("Plyer filechooser غير متوفر:", e)

        try:
            import tkinter as tk
            from tkinter import filedialog
            root_tk = tk.Tk()
            root_tk.withdraw()
            root_tk.attributes("-topmost", True)
            file_paths = filedialog.askopenfilenames(
                title="اختر صورة أو عدة صور للاختبارات",
                filetypes=[
                    ("Image files", "*.jpg;*.jpeg;*.png;*.webp"),
                    ("All files", "*.*"),
                ],
            )
            root_tk.destroy()
            if file_paths:
                self._on_file_selected(list(file_paths))
                return
        except Exception as e:
            print("تعذر فتح Tkinter filedialog:", e)

        self.show_error_dialog(
            ar("تعذر فتح مستعرض الملفات في هذا النظام.")
        )

    def _on_file_selected(self, selection: list[str]) -> None:
        """Callback عند اختيار ملف أو عدة ملفات (Batch Mode)"""
        if selection and len(selection) > 0:
            app = self.get_app()
            app.batch_queue = list(selection[1:])
            Clock.schedule_once(
                lambda dt: self.set_selected_image(selection[0]), 0
            )

    def capture_from_camera(self) -> None:
        """التقاط صورة عبر الكاميرا وحفظها في مجلد temp"""
        if platform == "android":
            try:
                from plyer import camera  # type: ignore[import-untyped]
                save_dir = file_manager.get_temp_dir()
                temp_filename = f"capture_{os.urandom(4).hex()}.jpg"
                temp_filepath = str(save_dir / temp_filename)

                camera.take_picture(
                    filename=temp_filepath,
                    on_complete=lambda path: Clock.schedule_once(
                        lambda dt: self.set_selected_image(path), 0
                    ),
                )
                return
            except Exception as e:
                print("فشل تشغيل كاميرا أندرويد عبر Plyer:", e)

        self.show_error_dialog(
            ar(
                "الكاميرا متاحة على الهاتف. "
                "يرجى اختيار صورة من المعرض على الحاسوب."
            )
        )

    def proceed_to_classify(self) -> None:
        """الانتقال لشاشة التصنيف والبدء في تحليل الصورة"""
        if not self.selected_image_path:
            return

        app = self.get_app()
        classifying_screen = app.root.get_screen("classifying_screen")
        classifying_screen.start_classification(self.selected_image_path)
        app.root.current = "classifying_screen"

    def go_back(self) -> None:
        """الرجوع إلى الشاشة الرئيسية"""
        self.reset_view()
        app = self.get_app()
        app.root.current = "home_screen"

    def show_error_dialog(self, message: str) -> None:
        """عرض رسالة تنبيه للمستخدم"""
        show_app_dialog(title="تنبيه", text=message)

    def get_app(self) -> object:
        from kivy.app import App
        return App.get_running_app()
