"""
شاشة تفاصيل المادة (SubjectDetailScreen):
- تعرض جميع صور أوراق الاختبار المحفوظة في شبكة متجاوبة (Responsive Grid).
- تتيح النقر على أي صورة لتكبيرها وقراءتها بوضوح في نافذة معاينة كاملة.
- توفر إمكانية حذف الصور الفردية أو حذف المادة بالكامل.
- توفر زر لفتح مجلد المادة مباشرة في مستكشف الملفات.
- توفر زر لإضافة ورقة اختبار جديدة مباشرة إلى هذه المادة.
"""

from pathlib import Path

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
from utils.ui_helper import get_category_ui_details, show_app_dialog


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

    def on_enter(self, *args: object) -> None:
        if Window is not None:
            try:
                Window.bind(size=self._on_window_resize)
            except Exception:
                pass
        self.apply_arabic_texts()
        self.update_grid_layout()

    def on_leave(self, *args: object) -> None:
        if Window is not None:
            try:
                Window.unbind(size=self._on_window_resize)
            except Exception:
                pass

    def apply_arabic_texts(self) -> None:
        if hasattr(self, "ids"):
            details = get_category_ui_details(self.subject_name)
            if "top_bar_title" in self.ids and self.subject_name:
                self.ids.top_bar_title.text = ar(self.subject_name)
            if "add_exam_btn_text" in self.ids:
                self.ids.add_exam_btn_text.text = ar(details["add_btn_text"])
            if "empty_label" in self.ids:
                self.ids.empty_label.text = ar(details["empty_title"])
            if "empty_action_text" in self.ids:
                self.ids.empty_action_text.text = ar(details["empty_action_text"])
            if "empty_icon" in self.ids:
                self.ids.empty_icon.icon = details["empty_icon"]
                self.ids.empty_icon.icon_color = details["color"]

    def load_subject(self, subject_name: str):
        """تحميل وعرض صور المادة المحددة"""
        self.subject_name = subject_name
        self.apply_arabic_texts()
        self.refresh_grid()

    def refresh_grid(self):
        """تحديث بطاقات الصور داخل الشبكة"""
        self.ids.images_grid.clear_widgets()

        if not self.subject_name:
            return

        import storage_backend
        target_loc = storage_backend.get_active_target_location()
        images = file_manager.get_subject_images(self.subject_name, target_location=target_loc)
        count = len(images)

        details = get_category_ui_details(self.subject_name)
        stats_u = details["stats_unit"]
        self.ids.info_label.text = ar(f"إجمالي الملفات: {count} {stats_u}")
        self.apply_arabic_texts()

        if not images:
            self.ids.empty_box.opacity = 1
            return

        self.ids.empty_box.opacity = 0

        for img_path in images:
            card = self.create_image_card(img_path)
            self.ids.images_grid.add_widget(card)

    def create_image_card(self, img_path: str) -> MDCard:
        """إنشاء بطاقة عرض أنيقة لكل صورة داخل الشبكة مع دعم مسارات SAF والذاكرة الداخلية"""
        import storage_backend
        filename = Path(img_path).name
        if img_path.startswith("content://"):
            details = storage_backend.query_content_uri_details(img_path)
            filename = details.get("display_name") or filename

        card = MDCard(
            size_hint=(1, None),
            height=dp(230),
            radius=[18, 18, 18, 18],
            elevation=0,
            orientation="vertical",
            padding=dp(8),
            spacing=dp(6),
            ripple_behavior=True,
            theme_bg_color="Custom",
            md_bg_color=(1.0, 1.0, 1.0, 0.98),
            on_release=lambda x, p=img_path: self.preview_image(p),
        )

        ext = Path(img_path).suffix.lower()
        is_video = ext in storage_backend.VIDEO_EXTENSIONS
        if not is_video and img_path.startswith("content://"):
            details = storage_backend.query_content_uri_details(img_path)
            is_video = bool(details.get("is_video") or ("video" in details.get("mime_type", "")))

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
            display_source = storage_backend.get_displayable_image_path(img_path)
            thumb = Image(source=display_source, size_hint=(1, 0.72))
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
        """عرض الصورة بحجم كبير أو تشغيل الفيديو في مشغل النظام الرسمي"""
        import storage_backend
        filename = Path(img_path).name
        if img_path.startswith("content://"):
            details = storage_backend.query_content_uri_details(img_path)
            filename = details.get("display_name") or filename

        ext = Path(img_path).suffix.lower()
        is_video = ext in storage_backend.VIDEO_EXTENSIONS
        if not is_video and img_path.startswith("content://"):
            details = storage_backend.query_content_uri_details(img_path)
            is_video = bool(details.get("is_video") or ("video" in details.get("mime_type", "")))

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
                on_release=lambda x: storage_backend.open_media_file_native(img_path)
            )
            v_center_box.add_widget(v_big_icon)
            v_center_box.add_widget(v_filename)
            v_center_box.add_widget(v_desc)
            v_center_box.add_widget(play_btn)
            content.add_widget(v_center_box)
        else:
            display_source = storage_backend.get_displayable_image_path(img_path)
            full_img = Image(source=display_source)
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
        import storage_backend
        target_loc = storage_backend.get_active_target_location()
        success = file_manager.delete_image_file(img_path, target_location=target_loc)
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
        import storage_backend
        target_loc = storage_backend.get_active_target_location()
        res = file_manager.delete_subject_folder(self.subject_name, target_location=target_loc)
        if res.files_deleted and res.folder_deleted:
            self.go_back()
        elif res.files_deleted and not res.folder_deleted:
            show_app_dialog(
                title="تنبيه: حذف جزئي",
                text=res.message or "تم حذف جميع أوراق المادة، ولكن تعذر حذف المجلد نفسه وبقي فارغاً في وحدة التخزين.",
                on_confirm=self.go_back,
            )
        else:
            show_app_dialog(
                title="تعذر الحذف الكامل",
                text=res.message or "فشل حذف بعض الملفات أو المجلد.",
                on_confirm=self.go_back,
            )

    def open_in_explorer(self):
        """فتح مجلد المادة في مستكشف النظام دون تحويل SAF URI لمسار لينكس"""
        if not self.subject_name:
            return
        import storage_backend
        target_loc = storage_backend.get_active_target_location()
        if target_loc.is_saf:
            tree_uri = target_loc.tree_uri or target_loc.saf_uri
            subject_saf_uri = storage_backend.saf_find_directory(tree_uri, self.subject_name)
            folder_to_open = subject_saf_uri or tree_uri
            success = storage_backend.open_saf_folder_in_file_manager(folder_to_open)
            if not success:
                show_app_dialog(
                    title="مجلد المادة (SD Card)",
                    text=(
                        f"أوراق مادة '{self.subject_name}' محفوظة في بطاقة الذاكرة الخارجية:\n\n"
                        f"{target_loc.display_name}\n\n"
                        "يمكنك تصفحها والوصول إليها عبر تطبيق 'ملفاتي' داخل مجلد 'الملفات المنظمة'."
                    ),
                )
            return

        clean_name = file_manager.sanitize_folder_name(self.subject_name)
        base_dir = target_loc.path or file_manager.get_internal_media_sorter_base_path()
        candidates = [
            base_dir / "صور الاختبارات" / clean_name,
            base_dir / clean_name,
        ]
        folder = candidates[0] if candidates[0].exists() else (candidates[1] if candidates[1].exists() else base_dir)
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
