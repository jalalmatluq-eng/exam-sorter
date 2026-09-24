# -*- coding: utf-8 -*-
"""
شاشة تفاصيل المادة (SubjectDetailScreen):
- تعرض جميع صور أوراق الاختبار المحفوظة لمادة معينة في شبكة منظمة متجاوبة (Responsive Grid).
- تتيح النقر على أي صورة لتكبيرها وقراءتها بوضوح في نافذة معاينة كاملة.
- توفر إمكانية حذف الصور الفردية أو حذف المادة بالكامل.
- توفر زر لفتح مجلد المادة مباشرة في مستكشف الملفات.
- توفر زر لإضافة ورقة اختبار جديدة مباشرة إلى هذه المادة.
"""

from pathlib import Path
from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.image import Image
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.metrics import dp
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText

import file_manager
from utils.arabic_helper import ar
from utils.ui_helper import show_app_dialog


class SubjectDetailScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.subject_name = ""

    def _on_window_resize(self, instance, size):
        self.update_grid_layout()

    def update_grid_layout(self):
        """تحديث عدد الأعمدة بناءً على عرض الشاشة الحالي"""
        if hasattr(self, "ids") and "images_grid" in self.ids:
            width = Window.width
            if width > 900:
                self.ids.images_grid.cols = 4
            elif width > 600:
                self.ids.images_grid.cols = 3
            else:
                self.ids.images_grid.cols = 2

    def on_enter(self):
        try:
            Window.bind(size=self._on_window_resize)
        except Exception:
            pass
        self.apply_arabic_texts()
        self.update_grid_layout()

    def on_leave(self):
        try:
            Window.unbind(size=self._on_window_resize)
        except Exception:
            pass

    def apply_arabic_texts(self):
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids and self.subject_name:
                self.ids.top_bar_title.text = ar(self.subject_name)
            if "add_exam_btn_text" in self.ids:
                self.ids.add_exam_btn_text.text = ar("إضافة ورقة")
            if "empty_label" in self.ids:
                self.ids.empty_label.text = ar("لا توجد أوراق اختبار في هذه المادة بعد")
            if "empty_action_text" in self.ids:
                self.ids.empty_action_text.text = ar("التقط ورقة اختبار لهذه المادة")

    def load_subject(self, subject_name: str):
        """تحميل وعرض صور المادة المحددة"""
        self.subject_name = subject_name
        if hasattr(self, "ids") and "top_bar_title" in self.ids:
            self.ids.top_bar_title.text = ar(subject_name)
        self.refresh_grid()

    def refresh_grid(self):
        """تحديث بطاقات الصور داخل الشبكة"""
        self.ids.images_grid.clear_widgets()

        if not self.subject_name:
            return

        images = file_manager.get_subject_images(self.subject_name)
        count = len(images)

        self.ids.info_label.text = ar(f"إجمالي الأوراق: {count} ورقة")

        if not images:
            self.ids.empty_box.opacity = 1
            return

        self.ids.empty_box.opacity = 0

        for img_path in images:
            card = self.create_image_card(img_path)
            self.ids.images_grid.add_widget(card)

    def create_image_card(self, img_path: str) -> MDCard:
        """إنشاء بطاقة عرض أنيقة لكل صورة داخل الشبكة"""
        filename = Path(img_path).name

        card = MDCard(
            size_hint=(1, None),
            height=dp(230),
            radius=[16, 16, 16, 16],
            elevation=2,
            orientation="vertical",
            padding=dp(8),
            spacing=dp(6),
            ripple_behavior=True,
            md_bg_color=(1, 1, 1, 1),
            on_release=lambda x, p=img_path: self.preview_image(p)
        )

        # صورة مصغرة
        thumb = Image(
            source=img_path,
            size_hint=(1, 0.72),
            allow_stretch=True,
            keep_ratio=True
        )
        card.add_widget(thumb)

        # شريط سفلي للبطاقة يحوي الاسم وأيقونة الحذف
        bottom_bar = BoxLayout(
            orientation="horizontal",
            size_hint=(1, 0.28),
            spacing=dp(4),
            padding=[dp(4), 0, dp(4), 0]
        )

        del_btn = Button(
            text="✕",
            size_hint=(None, 1),
            width=dp(32),
            background_color=(0.95, 0.3, 0.3, 1),
            color=(1, 1, 1, 1),
            font_size="13sp",
            bold=True
        )
        del_btn.bind(on_release=lambda x, p=img_path: self.confirm_delete_image(p))
        bottom_bar.add_widget(del_btn)

        label = MDLabel(
            text=filename,
            size_hint=(1, 1),
            font_size="11sp",
            halign="center",
            shorten=True,
            shorten_from="center",
            theme_text_color="Primary"
        )
        bottom_bar.add_widget(label)

        card.add_widget(bottom_bar)
        return card

    def preview_image(self, img_path: str):
        """عرض الصورة بحجم كبير في نافذة منبثقة للمعاينة"""
        filename = Path(img_path).name

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10)
        )

        full_img = Image(
            source=img_path,
            allow_stretch=True,
            keep_ratio=True
        )
        content.add_widget(full_img)

        actions_box = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(10)
        )

        popup = Popup(
            title=ar(filename),
            content=content,
            size_hint=(0.96, 0.92),
            auto_dismiss=True
        )

        del_btn = Button(
            text=ar("حذف هذه الورقة"),
            background_color=(0.85, 0.2, 0.2, 1),
            color=(1, 1, 1, 1),
            size_hint_x=0.45
        )

        def do_delete_from_popup(instance):
            popup.dismiss()
            self.confirm_delete_image(img_path)

        del_btn.bind(on_release=do_delete_from_popup)

        close_btn = Button(
            text=ar("إغلاق"),
            size_hint_x=0.55
        )
        close_btn.bind(on_release=popup.dismiss)

        actions_box.add_widget(del_btn)
        actions_box.add_widget(close_btn)
        content.add_widget(actions_box)

        popup.open()

    def confirm_delete_image(self, img_path: str):
        """تأكيد حذف ورقة اختبار فردية"""
        filename = Path(img_path).name
        show_app_dialog(
            title="تأكيد الحذف",
            text=f"هل أنت متأكد من حذف ورقة الاختبار:\n{filename} ؟",
            on_confirm=lambda: self._execute_delete_image(img_path)
        )

    def _execute_delete_image(self, img_path: str):
        success = file_manager.delete_image_file(img_path)
        if success:
            self.refresh_grid()

    def confirm_delete_subject(self):
        """تأكيد حذف المادة ومجلدها بالكامل"""
        if not self.subject_name:
            return
        show_app_dialog(
            title="حذف المادة بالكامل",
            text=f"تحذير: سيتم حذف مجلد المادة '{self.subject_name}' وجميع أوراق الاختبار المحفوظة بداخله نهائياً!\nهل تريد المتابعة؟",
            on_confirm=self._execute_delete_subject
        )

    def _execute_delete_subject(self):
        file_manager.delete_subject_folder(self.subject_name)
        self.go_back()

    def open_in_explorer(self):
        """فتح مجلد المادة في مستكشف النظام"""
        if not self.subject_name:
            return
        clean_name = file_manager.sanitize_folder_name(self.subject_name)
        folder = Path(file_manager.get_base_storage_path()) / clean_name
        success = file_manager.open_folder_native(str(folder))
        if not success:
            show_app_dialog(
                title="مسار المجلد",
                text=f"ملفات هذه المادة محفوظة في المسار:\n{folder}\n\n(على الهاتف يمكنك الوصول إليها عبر تطبيق ملفاتي في جهازك)."
            )

    def add_new_exam(self):
        """الانتقال لشاشة التقاط أو اختيار ورقة اختبار جديدة"""
        app = self.get_app()
        app.root.current = "capture_screen"

    def go_back(self):
        """العودة إلى الشاشة الرئيسية"""
        app = self.get_app()
        app.root.get_screen("home_screen").refresh_subjects()
        app.root.current = "home_screen"

    def get_app(self):
        from kivy.app import App
        return App.get_running_app()
