"""
الشاشة الرئيسية (HomeScreen):
- عرض قائمة المواد التي تحتوي على أوراق اختبار مصنفة.
- إحصائيات سريعة بعدد المواد والأوراق.
- زر عائم (FAB) لإضافة ورقة اختبار جديدة.
- نافذة إعدادات لإدخال وتعديل مفتاح API الخاص بـ Claude.
"""

import os
from pathlib import Path
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

import file_manager
from utils.arabic_helper import ar
from utils.ui_helper import create_subject_list_item


class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dialog = None
        self.all_subjects = []

    def on_enter(self):
        """يتم استدعاؤها في كل مرة يدخل فيها المستخدم للشاشة لتحديث القائمة"""
        self.apply_arabic_texts()
        self.refresh_subjects()

    def apply_arabic_texts(self):
        """تطبيق إعادة التشكيل العربي على عناصر الشاشة الثابتة"""
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("منظّم الوسائط الذكي")
            if "hero_title" in self.ids:
                self.ids.hero_title.text = ar("لوحة الفرز والتحكم الذكي")
            if "stats_title" in self.ids:
                self.ids.stats_title.text = ar("المجلدات المنظمة")
            if "stats_exams_title" in self.ids:
                self.ids.stats_exams_title.text = ar("إجمالي الملفات")
            if "btn_quick_face_text" in self.ids:
                self.ids.btn_quick_face_text.text = ar("بصمة وجهي")
            if "btn_quick_scan_text" in self.ids:
                self.ids.btn_quick_scan_text.text = ar("فحص فوري")
            if "btn_quick_folder_text" in self.ids:
                self.ids.btn_quick_folder_text.text = ar("المجلد")
            if "btn_quick_clean_text" in self.ids:
                self.ids.btn_quick_clean_text.text = ar("تنظيف")
            if "section_title" in self.ids:
                self.ids.section_title.text = ar("الأقسام والمجلدات المنظمة")
            if "search_input" in self.ids:
                self.ids.search_input.hint_text = ar("ابحث عن مجلد أو مادة...")
            if "empty_state_label" in self.ids:
                self.ids.empty_state_label.text = ar("لا توجد ملفات مصنفة بعد")
            if "empty_state_sub" in self.ids:
                self.ids.empty_state_sub.text = ar("التقط ورقة امتحان، أو فعّل المراقبة التلقائية لفرز صورك وفيديوهاتك فورياً.")

    def refresh_subjects(self):
        """تحديث قائمة المواد والمعارض المعروضة من خلال فحص مجلد التخزين"""
        try:
            self.all_subjects = file_manager.list_subjects()
            count = len(self.all_subjects)
            total_exams = sum(s.get("count", 0) for s in self.all_subjects)

            if "stats_count" in self.ids:
                self.ids.stats_count.text = ar(f"{count} مجلد")
            if "stats_exams_count" in self.ids:
                self.ids.stats_exams_count.text = ar(f"{total_exams} ملف")

            # إعادة تطبيق البحث الحالي إن وجد نص بحث
            query = ""
            if "search_input" in self.ids and self.ids.search_input.text:
                query = self.ids.search_input.text.strip()
            self.render_subjects(self.all_subjects, query=query)

        except Exception as e:
            print("خطأ أثناء تحديث المواد:", e)

    def filter_subjects(self, query: str):
        """تصفية المواد المعروضة في الوقت الفعلي أثناء كتابة المستخدم"""
        self.render_subjects(self.all_subjects, query=query.strip())

    def render_subjects(self, subjects: list, query: str = ""):
        """رسم قائمة كروت المواد في الواجهة"""
        self.ids.subjects_list.clear_widgets()

        filtered = subjects
        if query:
            clean_q = query.lower()
            filtered = [s for s in subjects if clean_q in s["name"].lower()]

        if not filtered:
            self.ids.empty_state.opacity = 1
            if query and "empty_state_label" in self.ids:
                self.ids.empty_state_label.text = ar(f"لا توجد مادة تطابق: '{query}'")
            elif "empty_state_label" in self.ids:
                self.ids.empty_state_label.text = ar("لا توجد أوراق اختبار مصنفة بعد")
            return

        self.ids.empty_state.opacity = 0

        for subj in filtered:
            name = subj["name"]
            img_count = subj["count"]

            item = create_subject_list_item(
                name=name,
                count=img_count,
                on_release_callback=lambda x, s=name: self.open_subject_details(s),
            )
            self.ids.subjects_list.add_widget(item)

    def clean_empty_folders(self):
        """تنظيف المجلدات الفارغة التي لا تحوي صوراً"""
        deleted = file_manager.clean_empty_subject_folders()
        self.refresh_subjects()
        from utils.ui_helper import show_app_dialog
        if deleted > 0:
            show_app_dialog(
                title="تم التنظيف",
                text=f"تم إزالة {deleted} مجلد فارغ بنجاح لتنظيم التخزين."
            )
        else:
            show_app_dialog(
                title="المجلدات سليمة",
                text="لا توجد مجلدات فارغة، جميع مجلدات المواد منظمة وتحتوي على أوراق اختبار."
            )

    def run_instant_scan(self):
        """تشغيل فحص فوري وسريع للوسائط وتحديث القائمة"""
        import media_scanner
        from utils.ui_helper import show_app_dialog
        try:
            res = media_scanner.run_batch_scan(max_files=50)
            processed = res.get("processed_count", 0)
            self.refresh_subjects()
            if processed > 0:
                show_app_dialog(
                    title="اكتمل الفحص الذكي",
                    text=f"تم فحص وتصنيف {processed} ملف بنجاح وتنظيمها في مجلداتها المخصصة."
                )
            else:
                show_app_dialog(
                    title="الوسائط منظمة",
                    text="تم فحص الذاكرة الداخلية بنجاح، وجميع الصور والفيديوهات مصنفة مسبقاً ولا توجد ملفات جديدة مفرزة."
                )
        except Exception as e:
            show_app_dialog(title="تنبيه الفحص", text=f"حدث خطأ أثناء الفحص: {e}")

    def open_storage_folder(self):
        """فتح المجلد الرئيسي للتخزين في مستكشف ويندوز أو إظهار المسار على الهاتف"""
        base_path = file_manager.get_base_storage_path()
        success = file_manager.open_folder_native(str(base_path))
        if not success:
            from utils.ui_helper import show_app_dialog
            show_app_dialog(
                title="مجلد التخزين الرئيسي",
                text=f"جميع أوراق ومجلدات الاختبارات محفوظة في المسار:\n{base_path}\n\n(على الهاتف يمكنك الوصول إليها عبر تطبيق ملفاتي في مجلد ExamSorter)."
            )

    def open_subject_details(self, subject_name: str):
        """الانتقال لشاشة تفاصيل المادة"""
        app = self.get_app()
        app.root.get_screen("subject_detail_screen").load_subject(subject_name)
        app.root.current = "subject_detail_screen"

    def go_to_capture(self):
        """الانتقال لشاشة التقاط أو اختيار الصورة"""
        app = self.get_app()
        app.root.current = "capture_screen"

    def open_settings_screen(self):
        """الانتقال إلى شاشة الإعدادات ومنظّم الوسائط"""
        app = self.get_app()
        app.root.current = "settings_screen"

    def open_people_setup(self):
        """الانتقال المباشر لشاشة بصمة وجه صاحب الجهاز"""
        app = self.get_app()
        app.root.current = "people_setup_screen"

    def open_settings_dialog(self):
        """فتح نافذة لإدخال أو تعديل مفتاح API"""
        app = self.get_app()
        current_key = getattr(app, "api_key", "")

        layout = BoxLayout(orientation="vertical", spacing=10, padding=12)
        text_input = TextInput(
            text=current_key,
            hint_text=ar("أدخل مفتاح Anthropic API هنا..."),
            multiline=False,
            password=True,
            size_hint_y=None,
            height=44,
        )
        layout.add_widget(text_input)

        btn_box = BoxLayout(orientation="horizontal", spacing=10, size_hint_y=None, height=44)

        cancel_btn = Button(text=ar("إلغاء"), size_hint_x=0.5)
        save_btn = Button(text=ar("حفظ"), size_hint_x=0.5)

        popup = Popup(
            title=ar("إعدادات مفتاح الذكاء الاصطناعي"),
            content=layout,
            size_hint=(0.85, 0.35),
            auto_dismiss=False,
        )

        cancel_btn.bind(on_release=popup.dismiss)

        def save_and_close(instance):
            self.save_api_key(text_input.text.strip())
            popup.dismiss()

        save_btn.bind(on_release=save_and_close)

        btn_box.add_widget(cancel_btn)
        btn_box.add_widget(save_btn)
        layout.add_widget(btn_box)

        popup.open()

    def save_api_key(self, new_key: str):
        """حفظ مفتاح API الجديد داخل التطبيق وملف .env مع الحفاظ على المتغيرات الأخرى"""
        app = self.get_app()
        app.api_key = new_key
        os.environ["ANTHROPIC_API_KEY"] = new_key

        paths_to_update = [Path(".env")]
        if hasattr(app, "user_data_dir"):
            paths_to_update.append(Path(app.user_data_dir) / ".env")

        for env_path in paths_to_update:
            try:
                env_lines: list[str] = []
                key_updated = False
                if env_path.exists():
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("ANTHROPIC_API_KEY="):
                                env_lines.append(f"ANTHROPIC_API_KEY={new_key}\n")
                                key_updated = True
                            else:
                                env_lines.append(line)
                if not key_updated:
                    env_lines.append(f"ANTHROPIC_API_KEY={new_key}\n")
                    if not any("CLAUDE_MODEL" in l for l in env_lines):
                        env_lines.append("CLAUDE_MODEL=claude-3-haiku-20240307\n")

                env_path.parent.mkdir(parents=True, exist_ok=True)
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(env_lines)
            except Exception as e:
                print(f"تعذر حفظ المفتاح في {env_path}:", e)

    def get_app(self):
        from kivy.app import App
        return App.get_running_app()
