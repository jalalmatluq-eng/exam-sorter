"""
شاشة تفاصيل المادة (SubjectDetailScreen):
- تعرض جميع صور أوراق الاختبار المحفوظة في شبكة متجاوبة (Responsive Grid).
- تتيح النقر على أي صورة لتكبيرها وقراءتها بوضوح في نافذة معاينة كاملة.
- توفر إمكانية حذف الصور الفردية أو حذف المادة بالكامل.
- توفر زر لفتح مجلد المادة مباشرة في مستكشف الملفات.
- توفر زر لإضافة ورقة اختبار جديدة مباشرة إلى هذه المادة.
"""

from pathlib import Path
from typing import Any

try:
    from typing import override
except ImportError:
    def override(func: Any) -> Any:  # type: ignore
        return func

from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel

import file_manager
from utils.arabic_helper import ar
from utils.ui_helper import show_app_dialog


class SubjectDetailScreen(Screen):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.subject_name: str = ""

    def _on_window_resize(self, _instance: object, _size: object) -> None:
        self.update_grid_layout()

    def update_grid_layout(self) -> None:
        """تحديث عدد الأعمدة بناءً على عرض الشاشة الحالي"""
        if (
            hasattr(self, "ids")
            and "images_grid" in self.ids
            and Window is not None
        ):
            width = Window.width
            if width > 900:
                self.ids.images_grid.cols = 4
            elif width > 600:
                self.ids.images_grid.cols = 3
            else:
                self.ids.images_grid.cols = 2

    @override
    def on_enter(self, *args: object) -> None:
        if Window is not None:
            try:
                Window.bind(size=self._on_window_resize)
            except Exception:
                pass
        self.apply_arabic_texts()
        self.update_grid_layout()

    @override
    def on_leave(self, *args: object) -> None:
        if Window is not None:
            try:
                Window.unbind(size=self._on_window_resize)
            except Exception:
                pass

    def apply_arabic_texts(self) -> None:
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids and self.subject_name:
                self.ids.top_bar_title.text = ar(self.subject_name)
            if "add_exam_btn_text" in self.ids:
                self.ids.add_exam_btn_text.text = ar("إضافة ورقة")
            if "empty_label" in self.ids:
                self.ids.empty_label.text = ar(
                    "لا توجد أوراق اختبار في هذه المادة بعد"
                )
            if "empty_action_text" in self.ids:
                self.ids.empty_action_text.text = ar(
                    "التقط ورقة اختبار لهذه المادة"
                )

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
            radius=[18, 18, 18, 18],
            elevation=3,
            orientation="vertical",
            padding=dp(8),
            spacing=dp(6),
            ripple_behavior=True,
            theme_bg_color="Custom",
            md_bg_color=(1.0, 1.0, 1.0, 0.98),
            on_release=lambda x, p=img_path: self.preview_image(p),
        )

        ext = Path(img_path).suffix.lower()
        is_video = ext in [".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm"]

        if is_video:
            video_thumb_box = BoxLayout(
                orientation="vertical",
                size_hint=(1, 0.72),
                padding=dp(10),
                spacing=dp(4),
            )
            v_icon = MDIcon(
                icon="movie-play-outline",
                font_size="48sp",
                pos_hint={"center_x": 0.5},
                theme_icon_color="Custom",
                icon_color=(0.486, 0.302, 0.988, 1),
            )
            v_badge = MDLabel(
                text=ar("مقطع فيديو"),
                font_size="11sp",
                halign="center",
                bold=True,
                theme_text_color="Custom",
                text_color=(0.02, 0.52, 0.80, 1),
            )
            video_thumb_box.add_widget(v_icon)
            video_thumb_box.add_widget(v_badge)
            card.add_widget(video_thumb_box)
        else:
            thumb = Image(source=img_path, size_hint=(1, 0.72))
            card.add_widget(thumb)

        # شريط سفلي للبطاقة يحوي الاسم وأيقونة الحذف
        bottom_bar = BoxLayout(
            orientation="horizontal",
            size_hint=(1, 0.28),
            spacing=dp(6),
            padding=[dp(6), 0, dp(6), 0],
        )

        del_btn = Button(
            text="✕",
            size_hint=(None, 1),
            width=dp(32),
            background_color=(0.85, 0.25, 0.25, 1),
            color=(1, 1, 1, 1),
            font_size="13sp",
            bold=True,
        )
        del_btn.bind(
            on_release=lambda x, p=img_path: self.confirm_delete_image(p)
        )
        bottom_bar.add_widget(del_btn)

        label = MDLabel(
            text=filename,
            size_hint=(1, 1),
            font_size="11sp",
            halign="center",
            shorten=True,
            shorten_from="center",
            theme_text_color="Custom",
            text_color=(0.08, 0.16, 0.34, 1),
        )
        bottom_bar.add_widget(label)

        card.add_widget(bottom_bar)
        return card

    def preview_image(self, img_path: str):
        """عرض الصورة بحجم كبير أو تشغيل الفيديو في مشغل النظام"""
        filename = Path(img_path).name
        ext = Path(img_path).suffix.lower()
        is_video = ext in [".mp4", ".mkv", ".3gp", ".mov", ".avi", ".webm"]

        content = BoxLayout(
            orientation="vertical", spacing=dp(10), padding=dp(10)
        )

        if is_video:
            v_center_box = BoxLayout(
                orientation="vertical",
                spacing=dp(12),
                padding=dp(16),
                size_hint=(1, 0.8),
            )
            v_big_icon = MDIcon(
                icon="play-circle",
                font_size="76sp",
                pos_hint={"center_x": 0.5},
                theme_icon_color="Custom",
                icon_color=(0.486, 0.302, 0.988, 1),
            )
            v_filename = MDLabel(
                text=filename,
                halign="center",
                bold=True,
                font_size="13sp",
                theme_text_color="Custom",
                text_color=(0.96, 0.97, 0.99, 1),
            )
            v_desc = MDLabel(
                text=ar("انقر أدناه لتشغيل الفيديو في مشغل الوسائط الرسمي"),
                halign="center",
                font_size="11sp",
                theme_text_color="Custom",
                text_color=(0.60, 0.66, 0.76, 1),
            )
            play_btn = Button(
                text=ar("▶ تشغيل مقطع الفيديو الآن"),
                background_color=(0.486, 0.302, 0.988, 1),
                color=(1, 1, 1, 1),
                size_hint=(0.85, None),
                height=dp(46),
                pos_hint={"center_x": 0.5},
            )
            play_btn.bind(
                on_release=lambda x: file_manager.open_folder_native(img_path)
            )
            v_center_box.add_widget(v_big_icon)
            v_center_box.add_widget(v_filename)
            v_center_box.add_widget(v_desc)
            v_center_box.add_widget(play_btn)
            content.add_widget(v_center_box)
        else:
            full_img = Image(source=img_path)
            content.add_widget(full_img)

        actions_box = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(10),
        )

        popup = Popup(
            title=ar(filename),
            content=content,
            size_hint=(0.96, 0.92),
            auto_dismiss=True,
        )

        del_btn = Button(
            text=ar("حذف هذه الورقة"),
            background_color=(0.85, 0.2, 0.2, 1),
            color=(1, 1, 1, 1),
            size_hint_x=0.45,
        )

        def do_delete_from_popup(instance):
            popup.dismiss()
            self.confirm_delete_image(img_path)

        del_btn.bind(on_release=do_delete_from_popup)

        close_btn = Button(text=ar("إغلاق"), size_hint_x=0.55)
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
            on_confirm=lambda: self._execute_delete_image(img_path),
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
            text=(
                f"تحذير: سيتم حذف مجلد المادة"
                f" '{self.subject_name}' وجميع"
                " أوراق الاختبار نهائياً!"
                "\nهل تريد المتابعة؟"
            ),
            on_confirm=self._execute_delete_subject,
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
                text=(
                    f"ملفات هذه المادة محفوظة"
                    f" في المسار:\n{folder}"
                    "\n\n(على الهاتف عبر تطبيق ملفاتي)."
                ),
            )

    def add_new_exam(self) -> None:
        """الانتقال لشاشة التقاط أو اختيار ورقة اختبار جديدة"""
        if self.manager:
            self.manager.current = "capture_screen"

    def go_back(self) -> None:
        """العودة إلى الشاشة الرئيسية"""
        if self.manager and self.manager.has_screen("home_screen"):
            home = self.manager.get_screen("home_screen")
            if hasattr(home, "refresh_subjects"):
                home.refresh_subjects()
            self.manager.current = "home_screen"
