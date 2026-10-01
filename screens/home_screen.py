"""
الشاشة الرئيسية (HomeScreen):
- عرض قائمة المواد التي تحتوي على أوراق اختبار مصنفة.
- إحصائيات سريعة بعدد المواد والأوراق.
- زر عائم (FAB) لإضافة ورقة اختبار جديدة.
- نافذة إعدادات لإدخال وتعديل مفتاح API الخاص بـ Claude.
"""

import logging
import os
from pathlib import Path
from typing import Any

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.properties import ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput
from kivy.utils import platform

import file_manager
from utils.arabic_helper import ar
from utils.ui_helper import (
    create_subject_list_item,
    show_app_dialog,
    show_confirm_dialog,
    show_modern_notification,
)

logger = logging.getLogger("HomeScreen")


class HomeScreen(Screen):
    cosmic_glow_color: list[float] = ListProperty([0.02, 0.65, 0.95, 0.55])
    hero_card_color: list[float] = ListProperty([0.90, 0.95, 1.0, 0.98])

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dialog: object = None
        self.all_subjects: list[dict[str, Any]] = []
        self._is_scanning: bool = False
        self._anim_running: bool = False
        self._has_requested_perms: bool = False

    def on_enter(self, *args: object) -> None:
        """يتم استدعاؤها في كل مرة يدخل فيها المستخدم للشاشة لتحديث القائمة"""
        self.apply_arabic_texts()
        self.refresh_subjects()
        self.check_initial_setup()

        # فحص وجود ملف سام تسبب بانهيار في الجلسة السابقة لحمايته وتنبيه المستخدم
        poison_file = file_manager.check_and_handle_poison_file_on_boot()
        if poison_file:
            poison_name = Path(poison_file).name
            show_modern_notification(
                "درع الحماية",
                f"تم تجاوز الملف ({poison_name}) لحماية التطبيق من الانهيار.",
                icon="shield-check",
                notif_type="magic",
            )

        # استئناف الفحص المعلق تلقائياً إن كان المستخدم قد غادر لمنح الصلاحيات وعاد
        is_pending, p_src, p_tgt = file_manager.get_pending_scan_info()
        if is_pending and file_manager.is_all_files_access_granted():
            file_manager.clear_pending_scan()
            Clock.schedule_once(
                lambda _dt: self.start_scan_with_options(p_src, p_tgt), 0.5
            )

        # طلب الصلاحيات الأساسية مرة واحدة فقط عند الإقلاع وليس مع كل دخول
        if platform == "android" and not self._has_requested_perms:
            self._has_requested_perms = True
            from kivy.app import App
            app = App.get_running_app()
            if hasattr(app, "request_android_permissions"):
                Clock.schedule_once(lambda _dt: app.request_android_permissions(), 1.5)

    def start_cosmic_animation(self) -> None:
        """تم تعطيل الحركة الكونية المستمرة لحماية الأجهزة ذات GPU Adreno القديمة من SIGSEGV"""
        pass

    def on_leave(self, *args: object) -> None:
        """إيقاف الحركة الكونية عند مغادرة الشاشة لتوفير طاقة المعالج والبطارية"""
        self.stop_cosmic_animation()

    def stop_cosmic_animation(self) -> None:
        """إيقاف كامل للمؤثرات التكرارية لتوفير البطارية"""
        Animation.stop_all(self)
        self._anim_running = False

    def apply_arabic_texts(self):
        """تطبيق إعادة التشكيل العربي على عناصر الشاشة الثابتة"""
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("CosmoSort | جامع العوالم")
            if "hero_title" in self.ids:
                self.ids.hero_title.text = ar("جامع وسائط العالم | CosmoHub")
            if "hero_sub" in self.ids:
                self.ids.hero_sub.text = ar(
                    "يلم كل وسائط العالم وينظمها بذكاء اصطناعي"
                )
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
                self.ids.empty_state_sub.text = ar(
                    "التقط ورقة امتحان، أو فعّل المراقبة التلقائية"
                    " لفرز صورك وفيديوهاتك فورياً."
                )

    def refresh_subjects(self):
        """تحديث قائمة المواد والمعارض المعروضة من خلال فحص مجلد التخزين"""
        try:
            self.all_subjects = file_manager.list_subjects()
            count = len(self.all_subjects)
            total_exams = 0
            for s in self.all_subjects:
                c = s.get("count", 0)
                if isinstance(c, int):
                    total_exams += c
                elif isinstance(c, str) and c.isdigit():
                    total_exams += int(c)

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

    def filter_subjects(self, query: str) -> None:
        """تصفية المواد المعروضة في الوقت الفعلي أثناء كتابة المستخدم"""
        self.render_subjects(self.all_subjects, query=query.strip())

    def render_subjects(
        self, subjects: list[dict[str, Any]], query: str = ""
    ) -> None:
        """رسم قائمة كروت المواد في الواجهة"""
        self.ids.subjects_list.clear_widgets()

        filtered = subjects
        if query:
            clean_q = query.lower()
            filtered = [
                s for s in subjects if clean_q in str(s.get("name", "")).lower()
            ]

        if not filtered:
            self.ids.empty_state.opacity = 1
            if query and "empty_state_label" in self.ids:
                self.ids.empty_state_label.text = ar(
                    f"لا توجد مادة تطابق: '{query}'"
                )
            elif "empty_state_label" in self.ids:
                self.ids.empty_state_label.text = ar(
                    "لا توجد أوراق اختبار مصنفة بعد"
                )
            return

        self.ids.empty_state.opacity = 0

        for subj in filtered:
            name = str(subj.get("name", ""))
            img_count = int(subj.get("count", 0))

            item = create_subject_list_item(
                name=name,
                count=img_count,
                on_release_callback=lambda _x, s=name: (
                    self.open_subject_details(s)
                ),
            )
            self.ids.subjects_list.add_widget(item)

    def clean_empty_folders(self) -> None:
        """تنظيف المجلدات الفارغة التي لا تحوي صوراً"""
        deleted = file_manager.clean_empty_subject_folders()
        self.refresh_subjects()
        if deleted > 0:
            _ = show_app_dialog(
                title="تم التنظيف",
                text=f"تم إزالة {deleted} مجلد فارغ بنجاح لتنظيم التخزين.",
            )
        else:
            _ = show_app_dialog(
                title="المجلدات سليمة",
                text=(
                    "لا توجد مجلدات فارغة، جميع مجلدات المواد منظمة"
                    " وتحتوي على أوراق اختبار."
                ),
            )

    def run_instant_scan(self) -> None:
        """عند الضغط على فحص فوري، إظهار نافذة خيارات الفحص"""
        if getattr(self, "_is_scanning", False):
            _ = show_app_dialog(
                title="الفحص قيد التشغيل",
                text=(
                    "عملية الفحص جارية بالفعل في الخلفية،"
                    " يرجى الانتظار..."
                ),
            )
            return
        self.show_scan_options_dialog(is_initial=False)

    def check_initial_setup(self) -> None:
        """فحص إذا كان المستخدم يفتح التطبيق لأول مرة"""
        prefs = file_manager.get_sorter_preferences()
        if not prefs.get("initial_setup_completed", False):
            Clock.schedule_once(
                lambda _dt: self.show_scan_options_dialog(is_initial=True), 0.6
            )

    def show_scan_options_dialog(self, is_initial: bool = False):
        """
        نافذة تفاعلية تسأل المستخدم:
        1. أي ذاكرة تريد فحصها وسحب ملفاتها؟ (الداخلية / كرت SD / كلاهما)
        2. أين تريد حفظ وترتيب الملفات المنظمة؟ (الداخلية / كرت SD)
        مع شرح ديناميكي مباشر لما سيقوم به التطبيق، وزر البدء.
        """
        from kivy.metrics import dp
        from kivy.uix.scrollview import ScrollView
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
        from kivymd.uix.dialog import (
            MDDialog,
            MDDialogButtonContainer,
            MDDialogContentContainer,
            MDDialogHeadlineText,
            MDDialogSupportingText,
        )
        from kivymd.uix.label import MDLabel

        prefs = file_manager.get_sorter_preferences()
        dests = file_manager.get_available_storage_destinations()
        internal_info = dests.get("internal", {})
        sdcard_info = dests.get("sdcard", {})
        int_free = int(float(str(internal_info.get("free_gb", 0))))
        has_sd = bool(sdcard_info.get("available", False))
        sd_free = int(float(str(sdcard_info.get("free_gb", 0))))

        initial_target: str = str(prefs.get("target_storage", "internal"))
        initial_source: str = str(prefs.get("source_storage", "internal"))

        state: dict[str, str] = {"target": initial_target, "source": initial_source}

        dialog = None

        # عناصر الواجهة بنافذة زجاجية داكنة فاخرة
        scroll = ScrollView(
            size_hint=(1, None), height=dp(250), do_scroll_x=False
        )
        content_box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
            adaptive_height=True,
            padding=[dp(4), dp(4), dp(4), dp(4)],
        )
        scroll.add_widget(content_box)

        # 1. عنوان القسم الأول: مصدر الفحص
        lbl_sec1 = MDLabel(
            text=ar("1. أي ذاكرة تريد فحصها وسحب وسائطها؟"),
            bold=True,
            adaptive_height=True,
            halign="right",
            font_size="13sp",
            theme_text_color="Custom",
            text_color=(0.96, 0.97, 0.99, 1),
        )
        content_box.add_widget(lbl_sec1)

        def set_btn_visuals(
            btn: Any,
            icon_w: Any,
            text_w: Any,
            is_active: bool,
        ) -> None:
            if is_active:
                btn.style = "filled"
                btn.md_bg_color = (0.02, 0.52, 0.80, 1)
                if icon_w:
                    icon_w.icon_color = (1, 1, 1, 1)
                if text_w:
                    text_w.text_color = (1, 1, 1, 1)
            else:
                btn.style = "outlined"
                btn.md_bg_color = (0.92, 0.95, 1.0, 0.95)
                if icon_w:
                    icon_w.icon_color = (0.48, 0.22, 0.85, 1)
                if text_w:
                    text_w.text_color = (0.35, 0.45, 0.60, 1)

        # أزرار المصدر (دائماً كلا الخيارين متاحان ومرئيان بوضوح للمستخدم)
        # أ) الذاكرة الداخلية
        src_int_label = (
            f"الذاكرة الداخلية ({int_free}GB)"
            if int_free > 0
            else "الذاكرة الداخلية للهاتف"
        )
        btn_src_int_icon = MDButtonIcon(
            icon="cellphone", theme_icon_color="Custom"
        )
        btn_src_int_text = MDButtonText(
            text=ar(src_int_label),
            bold=True,
            font_size="12sp",
            theme_text_color="Custom",
        )
        btn_src_int = MDButton(
            btn_src_int_icon,
            btn_src_int_text,
            size_hint_x=1,
            height=dp(40),
            radius=[14, 14, 14, 14],
            on_release=lambda _x: on_select_source("internal"),
        )
        content_box.add_widget(btn_src_int)

        # ب) بطاقة الذاكرة الخارجية SD
        src_sd_label = (
            f"الذاكرة الخارجية (كرت SD) ({sd_free}GB)"
            if (has_sd and sd_free > 0)
            else "الذاكرة الخارجية (بطاقة SD)"
        )
        btn_src_sd_icon = MDButtonIcon(
            icon="micro-sd", theme_icon_color="Custom"
        )
        btn_src_sd_text = MDButtonText(
            text=ar(src_sd_label),
            bold=True,
            font_size="12sp",
            theme_text_color="Custom",
        )
        btn_src_sd = MDButton(
            btn_src_sd_icon,
            btn_src_sd_text,
            size_hint_x=1,
            height=dp(40),
            radius=[14, 14, 14, 14],
            on_release=lambda _x: on_select_source("sdcard"),
        )
        content_box.add_widget(btn_src_sd)

        # ج) كلا الذاكرتين معاً
        btn_src_both_icon = MDButtonIcon(
            icon="folder-multiple-check", theme_icon_color="Custom"
        )
        btn_src_both_text = MDButtonText(
            text=ar("كلا الذاكرتين معاً (فحص وسحب شامل)"),
            bold=True,
            font_size="12sp",
            theme_text_color="Custom",
        )
        btn_src_both = MDButton(
            btn_src_both_icon,
            btn_src_both_text,
            size_hint_x=1,
            height=dp(40),
            radius=[14, 14, 14, 14],
            on_release=lambda _x: on_select_source("both"),
        )
        content_box.add_widget(btn_src_both)

        # 2. عنوان القسم الثاني: مكان الحفظ والتنظيم
        lbl_sec2 = MDLabel(
            text=ar("2. أين تريد حفظ وترتيب الملفات المنظمة؟"),
            bold=True,
            adaptive_height=True,
            halign="right",
            font_size="13sp",
            theme_text_color="Custom",
            text_color=(0.96, 0.97, 0.99, 1),
        )
        content_box.add_widget(lbl_sec2)

        # أزرار الوجهة (دائماً كلا الخيارين متاحان ومرئيان بوضوح للمستخدم)
        # أ) حفظ في الداخلية
        btn_tgt_int_icon = MDButtonIcon(
            icon="cellphone-arrow-down", theme_icon_color="Custom"
        )
        btn_tgt_int_text = MDButtonText(
            text=ar("في الذاكرة الداخلية (الملفات المنظمة)"),
            bold=True,
            font_size="12sp",
            theme_text_color="Custom",
        )
        btn_tgt_int = MDButton(
            btn_tgt_int_icon,
            btn_tgt_int_text,
            size_hint_x=1,
            height=dp(40),
            radius=[14, 14, 14, 14],
            on_release=lambda _x: on_select_target("internal"),
        )
        content_box.add_widget(btn_tgt_int)

        # ب) حفظ في كرت SD
        tgt_sd_label = "في كرت SD الخارجي (الملفات المنظمة)"
        btn_tgt_sd_icon = MDButtonIcon(
            icon="micro-sd", theme_icon_color="Custom"
        )
        btn_tgt_sd_text = MDButtonText(
            text=ar(tgt_sd_label),
            bold=True,
            font_size="12sp",
            theme_text_color="Custom",
        )
        btn_tgt_sd = MDButton(
            btn_tgt_sd_icon,
            btn_tgt_sd_text,
            size_hint_x=1,
            height=dp(40),
            radius=[14, 14, 14, 14],
            on_release=lambda _x: on_select_target("sdcard"),
        )
        content_box.add_widget(btn_tgt_sd)

        # 3. صندوق التوضيح الحي التفاعلي بألوان فخمة متوهجة
        lbl_explanation = MDLabel(
            text="",
            adaptive_height=True,
            halign="right",
            font_size="11sp",
            theme_text_color="Custom",
            text_color=(0.024, 0.765, 0.886, 1),
        )
        content_box.add_widget(lbl_explanation)

        def update_ui_state():
            # تحديث أزرار المصدر
            set_btn_visuals(
                btn_src_int,
                btn_src_int_icon,
                btn_src_int_text,
                state["source"] == "internal",
            )
            set_btn_visuals(
                btn_src_sd,
                btn_src_sd_icon,
                btn_src_sd_text,
                state["source"] == "sdcard",
            )
            set_btn_visuals(
                btn_src_both,
                btn_src_both_icon,
                btn_src_both_text,
                state["source"] == "both",
            )

            # تحديث أزرار الوجهة
            set_btn_visuals(
                btn_tgt_int,
                btn_tgt_int_icon,
                btn_tgt_int_text,
                state["target"] == "internal",
            )
            set_btn_visuals(
                btn_tgt_sd,
                btn_tgt_sd_icon,
                btn_tgt_sd_text,
                state["target"] == "sdcard",
            )

            # نص الشرح الحي الواضح للمستخدم
            src = state["source"]
            tgt = state["target"]
            if src == "internal" and tgt == "internal":
                txt = (
                    "✨ الخطة: سحب صور وفيديوهات (الداخلية)،"
                    " وترتيبها في (الذاكرة الداخلية)."
                )
            elif src == "internal" and tgt == "sdcard":
                txt = (
                    "✨ الخطة: سحب صور وفيديوهات (الداخلية)،"
                    " ونقلها في (كرت SD) لتفريغ مساحة الهاتف."
                )
            elif src == "sdcard" and tgt == "sdcard":
                txt = (
                    "✨ الخطة: فحص وسائط (كرت SD)،"
                    " وترتيبها في (كرت SD)."
                )
            elif src == "sdcard" and tgt == "internal":
                txt = (
                    "✨ الخطة: فحص وسائط (كرت SD)،"
                    " ونقلها في (الذاكرة الداخلية)."
                )
            elif src == "both" and tgt == "sdcard":
                txt = (
                    "✨ الخطة: فحص شامل (الداخلية + كرت SD)،"
                    " ونقلها في (كرت SD)."
                )
            else:
                txt = (
                    "✨ الخطة: فحص شامل (الداخلية + كرت SD)،"
                    " وترتيبها في (الذاكرة الداخلية)."
                )
            lbl_explanation.text = ar(txt)

        def on_select_source(new_src: str):
            state["source"] = new_src
            update_ui_state()

        def on_select_target(new_tgt: str):
            state["target"] = new_tgt
            update_ui_state()

        update_ui_state()

        # أزرار التنفيذ السفلية
        btn_action_box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(8),
            size_hint_y=None,
            adaptive_height=True,
            padding=[0, dp(8), 0, 0],
        )

        def on_start_pressed(_x: Any = None) -> None:
            if dialog:
                dialog.dismiss()

            # حفظ التفضيلات
            file_manager.save_sorter_preferences(
                {
                    "target_storage": state["target"],
                    "source_storage": state["source"],
                    "initial_setup_completed": True,
                }
            )

            # إنشاء شجرة المجلدات المنظمة الرسمية فوراً
            _ = file_manager.create_initial_category_folders()

            # فحص الصلاحية
            if not file_manager.is_all_files_access_granted():
                # حفظ حالة الفحص المعلق لبدء الفحص فور العودة مع الصلاحية
                file_manager.set_pending_scan(
                    True, source=state["source"], target=state["target"]
                )

                def open_perm_settings() -> None:
                    _ = file_manager.open_all_files_permission_settings()

                def on_proceed_without_full_access() -> None:
                    file_manager.clear_pending_scan()
                    self.start_scan_with_options(
                        state["source"], state["target"]
                    )

                _ = show_confirm_dialog(
                    title="صلاحية الوصول لكافة الملفات",
                    text=(
                        "لسحب كافة الصور والفيديوهات من مجلدات واتساب"
                        " وبلوتوث والكاميرا، يرجى تفعيل مفتاح"
                        " 'السماح بالوصول لإدارة جميع الملفات'.\n\n"
                        "عند منح الصلاحية والعودة للتطبيق، سيبدأ الفحص تلقائياً."
                    ),
                    on_confirm=open_perm_settings,
                    on_cancel=on_proceed_without_full_access,
                    confirm_text="فتح الإعدادات لمنح الصلاحية",
                    cancel_text="المتابعة بالصلاحيات الحالية",
                )
            else:
                file_manager.clear_pending_scan()
                self.start_scan_with_options(
                    state["source"], state["target"]
                )

        btn_start = MDButton(
            MDButtonIcon(
                icon="rocket-launch",
                theme_icon_color="Custom",
                icon_color=(1, 1, 1, 1),
            ),
            MDButtonText(
                text=ar("بدء الفحص والتنظيم الآن"),
                bold=True,
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1),
            ),
            style="filled",
            theme_bg_color="Custom",
            md_bg_color=(0.486, 0.302, 0.988, 1),
            size_hint_x=1,
            height=dp(44),
            radius=[16, 16, 16, 16],
            on_release=on_start_pressed,
        )
        btn_action_box.add_widget(btn_start)

        if not is_initial:
            btn_cancel = MDButton(
                MDButtonText(
                    text=ar("إلغاء"),
                    theme_text_color="Custom",
                    text_color=(0.60, 0.66, 0.76, 1),
                ),
                style="text",
                size_hint_x=1,
                height=dp(34),
                on_release=lambda _x: dialog.dismiss() if dialog else None,
            )
            btn_action_box.add_widget(btn_cancel)

        headline_text = (
            ar("مرحباً بك: خيارات الفحص والتنظيم")
            if is_initial
            else ar("أين تريد الفحص والتنظيم؟")
        )
        sub_text = ar(
            "حدد الذاكرة المراد سحب ملفاتها، ومكان حفظ المجلدات المنظمة:"
        )

        dialog = MDDialog(
            MDDialogHeadlineText(
                text=headline_text,
                bold=True,
                theme_text_color="Custom",
                text_color=(0.96, 0.97, 0.99, 1),
            ),
            MDDialogSupportingText(
                text=sub_text,
                theme_text_color="Custom",
                text_color=(0.65, 0.72, 0.82, 1),
            ),
            MDDialogContentContainer(
                scroll,
                orientation="vertical",
            ),
            MDDialogButtonContainer(
                btn_action_box,
                orientation="vertical",
                spacing=dp(4),
            ),
            theme_bg_color="Custom",
            md_bg_color=(0.090, 0.114, 0.176, 0.98),
            radius=[26, 26, 26, 26],
        )
        dialog.open()

    def start_scan_with_options(
        self, source_choice: str, target_choice: str
    ) -> None:
        """بدء الفحص والفرز الشامل التلقائي وفق المصدر والوجهة المحددين"""
        import threading

        import media_scanner

        if getattr(self, "_is_scanning", False):
            return

        self._is_scanning = True
        if hasattr(self, "ids") and "btn_quick_scan_text" in self.ids:
            self.ids.btn_quick_scan_text.text = ar("جارٍ الفرز...")

        src_name = (
            "الذاكرة الداخلية"
            if source_choice == "internal"
            else (
                "بطاقة SD الخارجية"
                if source_choice == "sdcard"
                else "كلا الذاكرتين معاً"
            )
        )
        tgt_name = (
            "الذاكرة الداخلية"
            if target_choice == "internal"
            else "بطاقة SD الخارجية"
        )
        show_modern_notification(
            "بدء الفحص والفرز",
            f"جارٍ فحص {src_name} والتنظيم في {tgt_name}...",
            icon="rocket-launch",
            notif_type="magic",
        )

        def worker():
            try:
                app = self.get_app()
                api_key = getattr(app, "api_key", None) if app else None

                res = media_scanner.run_continuous_scan(
                    batch_size=35, api_key=api_key, source_storage=source_choice
                )
            except Exception as e:
                logger.error("خطأ أثناء الفحص المستمر: %s", e)
                res = {"total_processed": 0, "batches": 0}

            def on_finish(_dt: float) -> None:
                self._is_scanning = False
                if hasattr(self, "ids") and "btn_quick_scan_text" in self.ids:
                    self.ids.btn_quick_scan_text.text = ar("فحص فوري")
                self.refresh_subjects()
                total = res.get("total_processed", 0)

                show_modern_notification(
                    "اكتمل الفرز والتنظيم",
                    f"تم بنجاح تنظيم {total} ملف في مجلد 'الملفات المنظمة'!",
                    notif_type="success",
                )

                _ = show_app_dialog(
                    title="اكتمل الفرز والتنظيم بنجاح",
                    text=(
                        f"تم بنجاح فحص وسائط ({src_name})،"
                        f" وفرز {total} ملف وترتيبها في مجلد"
                        f" 'الملفات المنظمة' على ({tgt_name})"
                        " بحسب التصنيفات المعتمدة!"
                    ),
                )

            Clock.schedule_once(on_finish, 0)

        threading.Thread(target=worker, daemon=True).start()

    def open_storage_folder(self) -> None:
        """فتح المجلد الرئيسي للتخزين أو إظهار المسار"""
        base_path = file_manager.get_media_sorter_base_path()
        success = file_manager.open_folder_native(str(base_path))
        if not success:
            _ = show_app_dialog(
                title="مجلد الملفات المنظمة",
                text=(
                    f"جميع الوسائط المصنفة محفوظة في المسار:\n{base_path}"
                    "\n\n(على الهاتف يمكنك الوصول إليها عبر تطبيق"
                    " ملفاتي في مجلد الملفات المنظمة)."
                ),
            )

    def open_subject_details(self, subject_name: str) -> None:
        """الانتقال لشاشة تفاصيل المادة"""
        if self.manager and self.manager.has_screen("subject_detail_screen"):
            screen = self.manager.get_screen("subject_detail_screen")
            if hasattr(screen, "load_subject"):
                screen.load_subject(subject_name)
            self.manager.current = "subject_detail_screen"

    def go_to_capture(self) -> None:
        """الانتقال لشاشة التقاط أو اختيار الصورة"""
        if self.manager:
            self.manager.current = "capture_screen"

    def open_settings_screen(self) -> None:
        """الانتقال إلى شاشة الإعدادات ومنظّم الوسائط"""
        if self.manager:
            self.manager.current = "settings_screen"

    def open_people_setup(self) -> None:
        """الانتقال المباشر لشاشة بصمة وجه صاحب الجهاز"""
        if self.manager:
            self.manager.current = "people_setup_screen"

    def open_settings_dialog(self) -> None:
        """فتح نافذة لإدخال أو تعديل مفتاح API"""
        app = self.get_app()
        current_key = getattr(app, "api_key", "") if app else ""

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

        btn_box = BoxLayout(
            orientation="horizontal", spacing=10, size_hint_y=None, height=44
        )

        cancel_btn = Button(text=ar("إلغاء"), size_hint_x=0.5)
        save_btn = Button(text=ar("حفظ"), size_hint_x=0.5)

        popup = Popup(
            title=ar("إعدادات مفتاح الذكاء الاصطناعي"),
            content=layout,
            size_hint=(0.85, 0.35),
            auto_dismiss=False,
        )

        cancel_btn.bind(on_release=popup.dismiss)

        def save_and_close(_instance: Any = None) -> None:
            self.save_api_key(text_input.text.strip())
            popup.dismiss()

        save_btn.bind(on_release=save_and_close)

        btn_box.add_widget(cancel_btn)
        btn_box.add_widget(save_btn)
        layout.add_widget(btn_box)

        popup.open()

    def save_api_key(self, new_key: str) -> None:
        """حفظ مفتاح API الجديد داخل التطبيق وملف .env"""
        app = self.get_app()
        if app:
            app.api_key = new_key  # type: ignore[attr-defined]
        os.environ["ANTHROPIC_API_KEY"] = new_key

        paths_to_update = [Path(".env")]
        if app and hasattr(app, "user_data_dir"):
            user_data = getattr(app, "user_data_dir", None)
            if user_data:
                paths_to_update.append(Path(user_data) / ".env")

        for env_path in paths_to_update:
            try:
                env_lines: list[str] = []
                key_updated = False
                if env_path.exists():
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("ANTHROPIC_API_KEY="):
                                env_lines.append(
                                    f"ANTHROPIC_API_KEY={new_key}\n"
                                )
                                key_updated = True
                            else:
                                env_lines.append(line)
                if not key_updated:
                    env_lines.append(f"ANTHROPIC_API_KEY={new_key}\n")
                    if not any("CLAUDE_MODEL" in ln for ln in env_lines):
                        env_lines.append(
                            "CLAUDE_MODEL=claude-haiku-4-5-20251001\n"
                        )

                env_path.parent.mkdir(parents=True, exist_ok=True)
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(env_lines)
            except Exception as e:
                logger.warning("تعذر حفظ المفتاح في %s: %s", env_path, e)

        # حفظ المفتاح في مسار التخزين المشترك للخدمات الخلفية
        file_manager.save_api_key_to_persistent_storage(new_key)

    def get_app(self) -> Any:
        from kivy.app import App

        return App.get_running_app()
