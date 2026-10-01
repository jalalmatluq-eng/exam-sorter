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
            if app is not None and hasattr(app, "request_android_permissions"):
                req_fn = getattr(app, "request_android_permissions")  # noqa: B009
                Clock.schedule_once(lambda _dt: req_fn(), 1.5)

    def start_cosmic_animation(self) -> None:
        """تم تعطيل الحركة الكونية المستمرة لحماية الأجهزة ذات GPU Adreno القديمة من SIGSEGV"""

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
                self.ids.top_bar_title.text = ar("رتّب | Rateb AI")
            if "hero_title" in self.ids:
                self.ids.hero_title.text = ar("رتّب | المُنظّم الذكي")
            if "hero_sub" in self.ids:
                self.ids.hero_sub.text = ar(
                    "فرز وتنظيم ذكي للصور والفيديوهات والمستندات"
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

            # 1. إذا اختار المستخدم بطاقة SD كوجهة: التحقق الصارم من توفر إذن SAF دون أي fallback صامت
            if state["target"] == "sdcard":
                import storage_backend
                target_loc = storage_backend.get_active_target_location("sdcard")
                if not target_loc.is_valid:
                    file_manager.set_pending_scan(
                        True, source=state["source"], target="sdcard"
                    )

                    def open_saf_picker_for_home() -> None:
                        _ = storage_backend.request_saf_folder_picker()

                    def on_cancel_saf_home() -> None:
                        file_manager.clear_pending_scan()

                    show_confirm_dialog(
                        title="إذن مجلد بطاقة الذاكرة (SAF)",
                        text=(
                            "لقد اخترت بطاقة الذاكرة الخارجية (MicroSD) كوجهة لحفظ وترتيب الوسائط.\n\n"
                            "على نظام أندرويد الحديث، تتطلب الكتابة في بطاقة SD اختيار مجلد الحفظ عبر منتقي النظام الرسمي (Storage Access Framework).\n\n"
                            "اضغط 'اختيار المجلد (SAF)' ثم حدد بطاقتك واضغط 'استخدام هذا المجلد'. سيبدأ الفحص تلقائياً بمجرد منح الإذن."
                        ),
                        on_confirm=open_saf_picker_for_home,
                        on_cancel=on_cancel_saf_home,
                        confirm_text="اختيار المجلد (SAF)",
                        cancel_text="إلغاء",
                    )
                    return

            # حفظ التفضيلات
            file_manager.save_sorter_preferences(
                {
                    "target_storage": state["target"],
                    "source_storage": state["source"],
                    "initial_setup_completed": True,
                }
            )

            # إنشاء شجرة المجلدات المنظمة الرسمية فوراً بدعم TargetLocation
            import storage_backend
            target_loc = storage_backend.get_active_target_location(state["target"])
            try:
                _ = file_manager.create_initial_category_folders(target_location=target_loc)
            except Exception as e_init:
                logger.warning("تنبيه تهيئة مجلدات الوجهة: %s", e_init)

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
        """بدء الفحص والفرز الشامل التلقائي وفق المصدر والوجهة المحددين مع فحص استباقي للصلاحيات"""
        import threading

        import android_permissions
        import media_scanner
        from utils.ui_helper import show_rich_results_dialog

        if getattr(self, "_is_scanning", False):
            return

        # 1. الفحص الاستباقي للصلاحيات لمنع التشغيل الكاذب والإخفاقات المتكررة
        can_proceed, _issue_code, issue_msg, action_req = android_permissions.preflight_scan_access(
            source_choice, target_choice
        )
        if not can_proceed:
            preflight_buttons = []
            if action_req == "request_media":
                def _on_grant():
                    def _after_perms(_p, _r):
                        import android_permissions
                        if not android_permissions.is_images_permission_granted():
                            android_permissions.open_app_details_settings()
                        Clock.schedule_once(lambda _dt: self.start_scan_with_options(source_choice, target_choice), 0.5)
                    android_permissions.request_media_permissions(_after_perms)

                preflight_buttons.append({
                    "text": "منح صلاحيات الصور والفيديو",
                    "callback": _on_grant,
                    "filled": True,
                    "bg_color": (0.486, 0.302, 0.988, 1),
                })
                preflight_buttons.append({
                    "text": "فتح إعدادات الهاتف مباشرة",
                    "callback": lambda: android_permissions.open_app_details_settings(),
                    "filled": False,
                    "bg_color": (0.92, 0.95, 1.0, 1),
                })

            elif action_req == "request_saf_sdcard":
                preflight_buttons.append({
                    "text": "اختيار مجلد بطاقة SD (SAF)",
                    "callback": lambda: self.choose_sdcard_saf_folder(),
                    "filled": True,
                    "bg_color": (0.02, 0.52, 0.80, 1),
                })
            elif action_req == "open_app_settings":
                preflight_buttons.append({
                    "text": "فتح إعدادات التطبيق",
                    "callback": lambda: android_permissions.open_app_details_settings(),
                    "filled": True,
                    "bg_color": (0.9, 0.4, 0.1, 1),
                })
            preflight_buttons.append({"text": "إلغاء", "callback": None, "filled": False})

            dlg_title = "الوصول محدود (أندرويد 14)" if action_req == "open_app_settings" else "مطلوب إذن وصول للتخزين"
            show_rich_results_dialog(
                title=dlg_title,
                stats_dict={"total_found": 0, "success_count": 0, "failed_count": 0},
                failures_by_reason={issue_msg: 1},
                buttons=preflight_buttons,
            )
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
                res = {"total_processed": 0, "failed_count": 1, "failures_by_reason": {"استثناء عام": 1}, "batches": 0}

            def on_finish(_dt: float) -> None:
                self._is_scanning = False
                if hasattr(self, "ids") and "btn_quick_scan_text" in self.ids:
                    self.ids.btn_quick_scan_text.text = ar("فحص فوري")
                self.refresh_subjects()
                success_count: int = int(str(res.get("total_processed") or 0))
                failed_count: int = int(str(res.get("failed_count") or 0))
                raw_failures = res.get("failures_by_reason", {})
                failures_by_reason: dict[str, int] = (
                    {str(k): int(v) for k, v in raw_failures.items()}
                    if isinstance(raw_failures, dict)
                    else {}
                )
                total_files: int = success_count + failed_count

                # تحديد أزرار الإجراء المناسبة بناءً على نوع الأخطاء
                dlg_buttons = []
                has_perm_issue = any(
                    "صلاحية" in r or "permission" in r.lower()
                    for r in failures_by_reason
                )
                has_saf_issue = any(
                    "saf" in r.lower() or "إذن" in r or "بطاقة" in r
                    for r in failures_by_reason
                )

                if has_perm_issue:
                    dlg_buttons.append({
                        "text": "منح صلاحيات الوسائط",
                        "callback": lambda: android_permissions.request_media_permissions(
                            lambda _p, _r: self.start_scan_with_options(source_choice, target_choice)
                        ),
                        "filled": True,
                        "bg_color": (0.486, 0.302, 0.988, 1),
                    })
                if has_saf_issue:
                    dlg_buttons.append({
                        "text": "إعادة اختيار بطاقة SD",
                        "callback": lambda: self.choose_sdcard_saf_folder(),
                        "filled": True,
                        "bg_color": (0.02, 0.52, 0.80, 1),
                    })
                if failed_count > 0:
                    dlg_buttons.append({
                        "text": "إعادة محاولة الفاشلة",
                        "callback": lambda: self.start_scan_with_options(source_choice, target_choice),
                        "filled": not (has_perm_issue or has_saf_issue),
                        "bg_color": (0.15, 0.65, 0.45, 1),
                    })

                # زر فتح مجلد الوجهة
                dlg_buttons.append({
                    "text": "فتح مجلد الوجهة",
                    "callback": lambda: self.open_storage_folder(),
                    "filled": False,
                })

                # زر تصدير تقرير التشخيص (JSON + TXT دون تسريب أي مفاتيح)
                def _export_report():
                    try:
                        import json
                        import time

                        import file_manager
                        base_rep_dir = file_manager.get_app_private_storage_dir()
                        rep_txt = base_rep_dir / "diagnostic_report.txt"
                        rep_json = base_rep_dir / "diagnostic_report.json"

                        report_data = {
                            "source_storage": src_name,
                            "target_storage": tgt_name,
                            "total_found": res.get("total_found", total_files),
                            "success_count": success_count,
                            "failed_count": failed_count,
                            "readable_count": res.get("readable_count", 0),
                            "classified_count": res.get("classified_count", 0),
                            "copied_count": res.get("copied_count", 0),
                            "moved_count": res.get("moved_count", 0),
                            "read_failed_count": res.get("read_failed_count", 0),
                            "classification_failed_count": res.get("classification_failed_count", 0),
                            "write_failed_count": res.get("write_failed_count", 0),
                            "permission_rejected_count": res.get("permission_rejected_count", 0),
                            "saf_reselect_count": res.get("saf_reselect_count", 0),
                            "failures_by_reason": failures_by_reason,
                            "timestamp": time.time(),
                        }

                        with open(rep_json, "w", encoding="utf-8") as jf:
                            json.dump(report_data, jf, ensure_ascii=False, indent=2)

                        with open(rep_txt, "w", encoding="utf-8") as rf:
                            rf.write("=== تقرير تشخيص فرز الوسائط (Rateb / CosmoSort) ===\n")
                            rf.write(f"المصدر: {src_name} | الوجهة: {tgt_name}\n")
                            rf.write(f"إجمالي الملفات المكتشفة: {report_data['total_found']}\n")
                            rf.write(f"الملفات القابلة للقراءة: {report_data['readable_count']}\n")
                            rf.write(f"الملفات المصنفة: {report_data['classified_count']}\n")
                            rf.write(f"الناجحة: {success_count} (نسخ: {report_data['copied_count']} | نقل: {report_data['moved_count']})\n")
                            rf.write(f"الفاشلة: {failed_count}\n")
                            rf.write(f"فشل القراءة: {report_data['read_failed_count']}\n")
                            rf.write(f"فشل الكتابة: {report_data['write_failed_count']}\n")
                            rf.write(f"مرفوض بسبب إذن Android: {report_data['permission_rejected_count']}\n")
                            rf.write(f"يحتاج إعادة اختيار SAF: {report_data['saf_reselect_count']}\n\n")
                            rf.write("تفصيل الإخفاقات المشخصة:\n")
                            rf.writelines(f"  - {r_k}: {r_v} ملف\n" for r_k, r_v in failures_by_reason.items())

                        show_modern_notification("تقرير التشخيص", f"تم حفظ التقرير في:\n{rep_txt.name}", notif_type="info")
                    except Exception as ex_rep:
                        logger.error("تعذر تصدير تقرير التشخيص: %s", ex_rep)

                dlg_buttons.append({"text": "تصدير التقرير", "callback": _export_report, "filled": False})
                dlg_buttons.append({"text": "إغلاق", "callback": None, "filled": False})

                if failed_count == 0 and success_count > 0:
                    show_modern_notification(
                        "اكتمل الفرز والتنظيم",
                        f"تم بنجاح تنظيم {success_count} ملف دون أي أخطاء!",
                        notif_type="success",
                    )
                    dialog_title = "اكتمل الفرز والتنظيم بنجاح ✓"
                elif success_count == 0 and failed_count > 0:
                    show_modern_notification(
                        "فشل الفرز بالكامل",
                        f"فشل معالجة {failed_count} ملف. يرجى مراجعة الصلاحيات.",
                        notif_type="error",
                    )
                    dialog_title = f"فشل الفرز (0 ناجح / {failed_count} فشل)"
                else:
                    show_modern_notification(
                        "اكتمل الفرز مع تنبيهات",
                        f"تم تنظيم {success_count} ملف، وفشل {failed_count} ملف.",
                        notif_type="warning",
                    )
                    dialog_title = f"اكتمل الفرز ({success_count} ناجح / {failed_count} فشل)"

                show_rich_results_dialog(
                    title=dialog_title,
                    stats_dict={
                        "total_found": res.get("total_found", total_files),
                        "success_count": success_count,
                        "failed_count": failed_count,
                        "readable_count": res.get("readable_count", 0),
                        "classified_count": res.get("classified_count", 0),
                        "copied_count": res.get("copied_count", 0),
                        "moved_count": res.get("moved_count", 0),
                        "read_failed_count": res.get("read_failed_count", 0),
                        "classification_failed_count": res.get("classification_failed_count", 0),
                        "write_failed_count": res.get("write_failed_count", 0),
                        "permission_rejected_count": res.get("permission_rejected_count", 0),
                        "saf_reselect_count": res.get("saf_reselect_count", 0),
                    },
                    failures_by_reason=failures_by_reason,
                    buttons=dlg_buttons,
                )

            Clock.schedule_once(on_finish, 0)

        threading.Thread(target=worker, daemon=True).start()

    def open_storage_folder(self) -> None:
        """فتح المجلد الرئيسي للتخزين أو إظهار المسار"""
        import storage_backend
        target_loc = storage_backend.get_active_target_location()
        if target_loc.is_saf:
            tree_uri = target_loc.tree_uri or target_loc.saf_uri
            opened = storage_backend.open_saf_folder_in_file_manager(tree_uri)
            if not opened:
                _ = show_app_dialog(
                    title="مجلد الملفات المنظمة (SD Card)",
                    text=(
                        f"الوسائط المصنفة محفوظة في بطاقة الذاكرة الخارجية عبر إذن SAF:\n\n{target_loc.display_name}\n\n"
                        "يمكنك تصفحها والوصول إليها عبر تطبيق 'ملفاتي' مباشرة داخل بطاقة SD في مجلد 'الملفات المنظمة'."
                    ),
                )
            return

        base_path = target_loc.path or file_manager.get_internal_media_sorter_base_path()
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
