"""
شاشة تأكيد وتعديل التصنيف (ConfirmScreen):
- تعرض معاينة مصغرة لورقة الاختبار.
- تعرض نتيجة الذكاء الاصطناعي أو تنبيه عند الحاجة للإدخال اليدوي.
- تتيح للمستخدم تعديل اسم المادة أو اختيار مادة سابقة بنقرة زر.
- تحفظ الصورة في المجلد المناسب وتظهر رسالة تأكيد بالمسار النهائي.
"""

from collections.abc import Callable
from pathlib import Path
from typing import override

from kivy.uix.screenmanager import Screen

import file_manager
from utils.arabic_helper import ar
from utils.ui_helper import create_action_button, show_app_dialog


class ConfirmScreen(Screen):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.image_path: str | None = None
        self.dialog: object = None

    @override
    def on_enter(self, *args: object) -> None:
        self.apply_arabic_texts()
        self.update_chips()

    def apply_arabic_texts(self) -> None:
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("تأكيد تصنيف المادة")
            elif hasattr(self.ids.top_bar, "title"):
                self.ids.top_bar.title = ar("تأكيد تصنيف المادة")
            self.ids.input_header.text = ar("اسم المادة الدراسية:")
            if hasattr(self.ids, "subject_hint"):
                self.ids.subject_hint.text = ar("اكتب اسم المادة هنا")
            self.ids.suggestions_label.text = ar(
                "أو اختر مادة بنقرة سريعة:"
            )
            self.ids.text_cancel.text = ar("إلغاء")
            self.ids.text_save.text = ar("حفظ وأرشفة الورقة")

    def set_classification_data(
        self,
        image_path: str,
        detected_subject: str = "",
        error_message: str | None = None,
    ) -> None:
        """تعبئة الشاشة ببيانات الصورة والنتيجة"""
        self.image_path = image_path
        self.ids.image_thumbnail.source = image_path or ""
        self.ids.image_thumbnail.reload()

        if detected_subject and detected_subject.strip():
            clean_name = detected_subject.strip()
            self.ids.subject_field.text = clean_name
            self.ids.status_badge.text = ar("تم التعرف بالذكاء الاصطناعي")
            self.ids.status_badge.text_color = (0.024, 0.765, 0.886, 1)
            self.ids.status_details.text = ar(
                "يمكنك اعتماد هذا الاسم أو تعديله أدناه قبل الحفظ"
            )
            self.update_target_label(clean_name)
        else:
            self.ids.subject_field.text = ""
            self.ids.status_badge.text = ar("إدخال يدوي مطلوب")
            self.ids.status_badge.text_color = (0.85, 0.45, 0.15, 1)
            err_fallback = "يرجى كتابة اسم المادة لحفظ الورقة"
            self.ids.status_details.text = ar(error_message or err_fallback)
            self.update_target_label("...")

    @override
    def on_kv_post(self, base_widget: object) -> None:
        super().on_kv_post(base_widget)
        if "subject_field" in self.ids:
            def _on_text(_instance: object, val: str) -> None:
                self.update_target_label(val.strip())

            self.ids.subject_field.bind(text=_on_text)

    def update_target_label(self, subject_name: str) -> None:
        """تحديث مسار الحفظ المتوقع المعروض لحظياً أثناء الكتابة"""
        display_name = subject_name if subject_name else "..."
        if display_name != "...":
            clean = file_manager.sanitize_folder_name(display_name)
        else:
            clean = "..."
        target_info = f"المجلد الوجهة: الملفات المنظمة/صور الاختبارات/{clean}/"
        self.ids.target_path_label.text = ar(target_info)

    def _make_chip_cb(self, target_name: str) -> Callable[[object], None]:
        return lambda _x: self.select_subject_from_chip(target_name)

    def update_chips(self) -> None:
        """تحميل قائمة المواد السابقة كأزرار سريعة للاختيار"""
        self.ids.chips_box.clear_widgets()

        # جلب المواد الموجودة حالياً في التخزين
        existing = file_manager.list_subjects()
        subject_names: list[str] = [
            str(s.get("name", "")) for s in existing if s.get("name")
        ]

        # إضافة مواد شائعة إن كانت القائمة صغيرة
        common_defaults = [
            "رياضيات",
            "فيزياء",
            "كيمياء",
            "لغة إنجليزية",
            "برمجة",
        ]
        for d in common_defaults:
            if d not in subject_names:
                subject_names.append(d)

        for name in subject_names[:8]:
            sub_name = str(name)
            btn = create_action_button(
                text=sub_name,
                on_release_callback=self._make_chip_cb(sub_name),
                style="outlined",
            )
            self.ids.chips_box.add_widget(btn)

    def select_subject_from_chip(self, name: str) -> None:
        """عند الضغط على أحد أزرار المواد المقترحة"""
        self.ids.subject_field.text = name
        self.update_target_label(name)

    def save_and_finish(self) -> None:
        """حفظ الصورة نهائياً في مجلد المادة المحدد"""
        if not self.image_path:
            _ = show_app_dialog(
                title="تنبيه", text="لا توجد صورة محددة للحفظ!"
            )
            return

        subject_name = self.ids.subject_field.text.strip()
        if not subject_name:
            _ = show_app_dialog(
                title="تنبيه", text="يرجى إدخال اسم المادة أولاً."
            )
            return

        try:
            saved_path = file_manager.save_image_to_subject(
                self.image_path, subject_name
            )
            folder_name = Path(saved_path).parent.name
            file_name = Path(saved_path).name

            success_info = (
                f"تم حفظ وتنظيم ورقة الاختبار بنجاح:\n"
                f"المادة: {folder_name}\n"
                f"الملف: {file_name}"
            )
            _ = show_app_dialog(
                title="تم الحفظ بنجاح",
                text=success_info,
                on_confirm=self._on_save_done,
                confirm_text="متابعة",
            )

        except (OSError, ValueError, RuntimeError) as e:
            _ = show_app_dialog(
                title="خطأ في الحفظ",
                text=f"تعذر حفظ الملف: {e}",
            )

    def _on_save_done(self) -> None:
        """الانتقال للورقة التالية في الدفعة أو الشاشة الرئيسية"""
        from kivy.app import App
        from kivy.uix.screenmanager import ScreenManager

        app = App.get_running_app()
        if app and isinstance(app.root, ScreenManager):
            root = app.root
            batch_q: object = getattr(app, "batch_queue", None)
            if isinstance(batch_q, list) and len(batch_q) > 0:
                next_img = str(batch_q.pop(0))
                capture_screen = root.get_screen("capture_screen")
                set_img = getattr(capture_screen, "set_selected_image", None)
                if callable(set_img):
                    set_img(next_img)
                root.current = "capture_screen"
            else:
                home_screen = root.get_screen("home_screen")
                refresh_fn = getattr(home_screen, "refresh_subjects", None)
                if callable(refresh_fn):
                    refresh_fn()
                root.current = "home_screen"

    def go_back(self) -> None:
        """العودة إلى شاشة التقاط الصورة"""
        from kivy.app import App
        from kivy.uix.screenmanager import ScreenManager

        app = App.get_running_app()
        if app and isinstance(app.root, ScreenManager):
            app.root.current = "capture_screen"
