"""
شاشة تأكيد وتعديل التصنيف (ConfirmScreen):
- تعرض معاينة مصغرة لورقة الاختبار.
- تعرض نتيجة الذكاء الاصطناعي أو تنبيه في حال الحاجة للإدخال اليدوي.
- تتيح للمستخدم تعديل اسم المادة أو اختيار مادة سابقة بنقرة زر (Chips).
- تحفظ الصورة في المجلد المناسب وتظهر رسالة تأكيد بالمسار النهائي قبل الرجوع للرئيسية.
"""

from pathlib import Path
from kivy.uix.screenmanager import Screen

import file_manager
from utils.arabic_helper import ar
from utils.ui_helper import create_action_button, show_app_dialog


class ConfirmScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.image_path = None
        self.dialog = None

    def on_enter(self):
        self.apply_arabic_texts()
        self.update_chips()

    def apply_arabic_texts(self):
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("تأكيد تصنيف المادة")
            elif hasattr(self.ids.top_bar, "title"):
                self.ids.top_bar.title = ar("تأكيد تصنيف المادة")
            self.ids.input_header.text = ar("اسم المادة الدراسية:")
            if hasattr(self.ids, "subject_hint"):
                self.ids.subject_hint.text = ar("اكتب اسم المادة هنا")
            self.ids.suggestions_label.text = ar("أو اختر مادة بنقرة سريعة:")
            self.ids.text_cancel.text = ar("إلغاء")
            self.ids.text_save.text = ar("حفظ وأرشفة الورقة")

    def set_classification_data(self, image_path: str, detected_subject: str = "", error_message: str = None):
        """تعبئة الشاشة ببيانات الصورة والنتيجة"""
        self.image_path = image_path
        self.ids.image_thumbnail.source = image_path or ""
        self.ids.image_thumbnail.reload()

        if detected_subject and detected_subject.strip():
            clean_name = detected_subject.strip()
            self.ids.subject_field.text = clean_name
            self.ids.status_badge.text = ar("تم التعرف بالذكاء الاصطناعي")
            self.ids.status_badge.text_color = (0.15, 0.65, 0.35, 1)
            self.ids.status_details.text = ar("يمكنك اعتماد هذا الاسم أو تعديله أدناه قبل الحفظ")
            self.update_target_label(clean_name)
        else:
            self.ids.subject_field.text = ""
            self.ids.status_badge.text = ar("إدخال يدوي مطلوب")
            self.ids.status_badge.text_color = (0.85, 0.45, 0.15, 1)
            self.ids.status_details.text = ar(error_message or "يرجى كتابة اسم المادة لحفظ الورقة")
            self.update_target_label("...")

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        if "subject_field" in self.ids:
            self.ids.subject_field.bind(text=lambda instance, val: self.update_target_label(val.strip()))

    def update_target_label(self, subject_name: str):
        """تحديث مسار الحفظ المتوقع المعروض لحظياً أثناء الكتابة"""
        display_name = subject_name if subject_name else "..."
        clean = file_manager.sanitize_folder_name(display_name) if display_name != "..." else "..."
        self.ids.target_path_label.text = ar(f"المجلد الوجهة: ExamSorter/{clean}/")

    def update_chips(self):
        """تحميل قائمة المواد السابقة كأزرار سريعة للاختيار"""
        self.ids.chips_box.clear_widgets()

        # جلب المواد الموجودة حالياً في التخزين
        existing = file_manager.list_subjects()
        subject_names = [s["name"] for s in existing]

        # إضافة مواد شائعة إن كانت القائمة صغيرة
        common_defaults = ["رياضيات", "فيزياء", "كيمياء", "لغة إنجليزية", "برمجة"]
        for d in common_defaults:
            if d not in subject_names:
                subject_names.append(d)

        for name in subject_names[:8]:
            btn = create_action_button(
                text=name,
                on_release_callback=lambda x, n=name: self.select_subject_from_chip(n),
                style="outlined",
            )
            self.ids.chips_box.add_widget(btn)

    def select_subject_from_chip(self, name: str):
        """عند الضغط على أحد أزرار المواد المقترحة"""
        self.ids.subject_field.text = name
        self.update_target_label(name)

    def save_and_finish(self):
        """حفظ الصورة في مجلد المادة المحدد والرجوع للشاشة الرئيسية"""
        subject_name = self.ids.subject_field.text.strip()
        if not subject_name:
            show_app_dialog(
                title="تنبيه",
                text="يرجى إدخال أو اختيار اسم المادة قبل الحفظ.",
            )
            return

        if not self.image_path:
            show_app_dialog(
                title="خطأ",
                text="لم يتم العثور على مسار الصورة المراد حفظها.",
            )
            return

        try:
            # استدعاء file_manager لحفظ الصورة بتسمية فريدة وتاريخ
            saved_path = file_manager.save_image_to_subject(
                image_path=self.image_path,
                subject_name=subject_name,
            )

            # استخراج اسم المجلد والمجلد الأب للإشعار
            saved_file_name = Path(saved_path).name
            folder_name = Path(saved_path).parent.name

            # إظهار رسالة النجاح للمستخدم
            show_app_dialog(
                title="تم الحفظ بنجاح",
                text=(
                    f"تم تنظيم ورقة الاختبار وأرشفتها بنجاح!\n\n"
                    f"المادة: {subject_name}\n"
                    f"المجلد: ExamSorter/{folder_name}/\n"
                    f"الملف: {saved_file_name}"
                ),
                on_confirm=self._on_save_done,
            )

        except Exception as e:
            show_app_dialog(
                title="خطأ في الحفظ",
                text=f"حدث خطأ أثناء حفظ الملف: {e!s}",
            )

    def _on_save_done(self):
        """الانتقال للورقة التالية في الدفعة أو الشاشة الرئيسية بعد الحفظ"""
        app = self.get_app()
        if hasattr(app, "batch_queue") and app.batch_queue:
            next_img = app.batch_queue.pop(0)
            capture_screen = app.root.get_screen("capture_screen")
            capture_screen.set_selected_image(next_img)
            app.root.current = "capture_screen"
        else:
            app.root.get_screen("home_screen").refresh_subjects()
            app.root.current = "home_screen"

    def go_back(self):
        """العودة إلى شاشة التقاط الصورة"""
        app = self.get_app()
        app.root.current = "capture_screen"

    def get_app(self):
        from kivy.app import App
        return App.get_running_app()
