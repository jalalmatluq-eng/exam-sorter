# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""
شاشة الإعدادات والتحكم بمنظّم الوسائط (SettingsScreen):
- تفعيل / إيقاف خدمة المراقبة التلقائية بالخلفية.
- زر "امسح الآن يدوياً" لتشغيل فحص فوري ونقل الوسائط.
- إدارة وتعديل بصمة وجه صاحب الجهاز.
- استعراض سجل عمليات النقل الأخيرة مع إمكانية التراجع الفوري عن أي نقل خاطئ.
"""

import threading
from pathlib import Path
from typing import override

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel

import face_classifier
import file_manager
import media_scanner
from service import media_watcher_service
from utils.arabic_helper import ar
from utils.ui_helper import show_app_dialog


class SettingsScreen(Screen):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.is_scanning: bool = False

    @override
    def on_enter(self, *args: object) -> None:
        self.apply_arabic_texts()
        self.refresh_service_ui()
        self.refresh_face_status()
        self.refresh_history()

    def apply_arabic_texts(self) -> None:
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("الإعدادات ومنظّم الوسائط")
            if "service_title" in self.ids:
                self.ids.service_title.text = ar("خدمة المراقبة التلقائية اللحظية")
            if "service_desc" in self.ids:
                self.ids.service_desc.text = ar("فرز ونقل أي صورة أو فيديو جديد فور التقاطه أو تنزيله")
            if "manual_scan_title" in self.ids:
                self.ids.manual_scan_title.text = ar("فحص وتصنيف الذاكرة يدوياً الآن")
            if "btn_scan_text" in self.ids:
                self.ids.btn_scan_text.text = ar("بدء الفحص الشامل للوسائط")
            if "face_card_title" in self.ids:
                self.ids.face_card_title.text = ar("بصمة وجهي وصوري الخاصة")
            if "btn_edit_face_text" in self.ids:
                self.ids.btn_edit_face_text.text = ar("تعديل البصمة")
            if "history_section_title" in self.ids:
                self.ids.history_section_title.text = ar("سجل عمليات النقل الأخيرة والتراجع")
            if "refresh_history_text" in self.ids:
                self.ids.refresh_history_text.text = ar("تحديث")

    def refresh_service_ui(self) -> None:
        """تحديث شكل زر وأيقونة خدمة المراقبة حسب حالتها"""
        running = media_watcher_service.is_service_desired_running()
        if running:
            self.ids.text_service_toggle.text = ar("تعمل")
            self.ids.btn_service_toggle.md_bg_color = (0.15, 0.65, 0.35, 1)
            self.ids.service_icon.icon_color = (0.15, 0.65, 0.35, 1)
        else:
            self.ids.text_service_toggle.text = ar("متوقفة")
            self.ids.btn_service_toggle.md_bg_color = (0.6, 0.6, 0.65, 1)
            self.ids.service_icon.icon_color = (0.6, 0.6, 0.65, 1)

    def toggle_service(self) -> None:
        """التبديل بين تفعيل وإيقاف الخدمة الخلفية مع تشغيلها الفعلي"""
        current_state = media_watcher_service.is_service_desired_running()
        new_state = not current_state
        if new_state:
            media_watcher_service.start_system_service()
        else:
            media_watcher_service.stop_system_service()

        self.refresh_service_ui()

        if new_state:
            _ = show_app_dialog(
                title="تم التفعيل",
                text="تم تفعيل خدمة المراقبة التلقائية وبدء تشغيلها. سيتم رصد وتصنيف أي وسائط جديدة فور كتابتها."
            )
        else:
            _ = show_app_dialog(
                title="تم الإيقاف",
                text="تم إيقاف المراقبة التلقائية مؤقتاً."
            )

    def refresh_face_status(self) -> None:
        """تحديث بطاقة حالة بصمة الوجه"""
        if face_classifier.is_user_profile_registered():
            self.ids.face_card_status.text = ar("البصمة مسجلة وجاهزة لتمييز صورك الخاصة")
        else:
            self.ids.face_card_status.text = ar("لم يتم تسجيل بصمة وجهك بعد (انقر للإعداد)")

    def open_people_setup(self) -> None:
        """الانتقال لشاشة تدريب بصمة الوجه"""
        app = self.get_app()
        if app and app.root:
            app.root.current = "people_setup_screen"

    def start_manual_scan(self) -> None:
        """بدء الفحص الشامل للوسائط في خلفية منفصلة"""
        if self.is_scanning:
            return
        self.is_scanning = True
        self.ids.btn_scan_text.text = ar("جاري الفحص الآن...")

        def worker() -> None:
            app = self.get_app()
            api_key = getattr(app, "api_key", None)
            res = media_scanner.run_batch_scan(max_files=40, api_key=api_key)

            def on_finish(_dt: float) -> None:
                self._on_scan_finished(res)

            Clock.schedule_once(on_finish, 0)

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_finished(self, result: dict[str, object]) -> None:
        self.is_scanning = False
        self.ids.btn_scan_text.text = ar("بدء الفحص الشامل للوسائط")
        self.refresh_history()

        processed = result.get("processed_count", 0)
        total = result.get("total_unprocessed_found", 0)
        _ = show_app_dialog(
            title="اكتمل الفحص الشامل",
            text=(
                f"اكتملت دورة الفحص بنجاح!\n\n"
                f"- الملفات الجديدة المفحوصة والمصنفة: {processed}\n"
                f"- إجمالي الملفات المعالجة: {total}"
            )
        )

    def refresh_history(self) -> None:
        """رسم بطاقات سجل عمليات النقل الأخيرة مع زر التراجع"""
        self.ids.history_list.clear_widgets()
        history = file_manager.get_transfer_history()

        if not history:
            card = MDCard(
                size_hint_y=None,
                height=dp(54),
                radius=[12, 12, 12, 12],
                padding=dp(10),
                elevation=0,
                md_bg_color=(1, 1, 1, 0.6)
            )
            card.add_widget(MDLabel(
                text=ar("لا توجد عمليات نقل مسجلة بعد"),
                halign="center",
                font_size="12sp",
                theme_text_color="Secondary"
            ))
            self.ids.history_list.add_widget(card)
            return

        for record in history[:20]:
            card = self.create_history_card(record)
            self.ids.history_list.add_widget(card)

    def create_history_card(self, record: dict[str, object]) -> MDCard:
        """إنشاء بطاقة عرض لكل عملية نقل مع زر التراجع الفوري"""
        src_name = Path(str(record.get("source", ""))).name
        category = str(record.get("category", "خارج التصنيف"))
        rec_id = int(str(record.get("id", 0)))

        card = MDCard(
            size_hint_y=None,
            height=dp(60),
            radius=[14, 14, 14, 14],
            elevation=1,
            padding=[dp(12), dp(6), dp(12), dp(6)],
            theme_bg_color="Custom",
            md_bg_color=(1, 1, 1, 1),
            orientation="horizontal",
            spacing=dp(10)
        )

        def on_undo_click(_btn: object) -> None:
            self.undo_record(rec_id)

        undo_btn = MDButton(
            style="outlined",
            size_hint=(None, None),
            size=(dp(80), dp(36)),
            pos_hint={"center_y": 0.5},
            on_release=on_undo_click
        )
        _ = undo_btn.add_widget(MDButtonIcon(icon="undo"))
        _ = undo_btn.add_widget(MDButtonText(text=ar("تراجع")))
        _ = card.add_widget(undo_btn)

        info_box = BoxLayout(
            orientation="vertical",
            spacing=dp(2),
            pos_hint={"center_y": 0.5}
        )

        name_label = MDLabel(
            text=ar(src_name),
            bold=True,
            font_size="12sp",
            shorten=True,
            shorten_from="center",
            halign="right",
            theme_text_color="Primary"
        )
        cat_label = MDLabel(
            text=ar(f"نُسخ إلى: {category}"),
            font_size="10sp",
            halign="right",
            theme_text_color="Custom",
            text_color=(0.22, 0.26, 0.68, 1)
        )

        _ = info_box.add_widget(name_label)
        _ = info_box.add_widget(cat_label)
        _ = card.add_widget(info_box)

        return card

    def undo_record(self, record_id: int) -> None:
        """التراجع عن عملية نسخ معينة وإلغاء تصنيفها"""
        success = file_manager.undo_transfer(record_id)
        if success:
            self.refresh_history()
            _ = show_app_dialog(
                title="تم التراجع",
                text="تم حذف النسخة بنجاح من مجلد التصنيف، وملفك الأصلي باقٍ في مكانه دون أي مساس."
            )
        else:
            _ = show_app_dialog(
                title="تعذر التراجع",
                text="تعذر العثور على النسخة أو ربما تم حذفها مسبقاً."
            )

    def undo_all_records(self) -> None:
        """التراجع عن كافة عمليات الفرز والنسخ بنقرة واحدة"""
        history = file_manager.get_transfer_history()
        if not history:
            _ = show_app_dialog(
                title="السجل فارغ",
                text="لا توجد أي عمليات حالية للتراجع عنها."
            )
            return

        count = file_manager.undo_all_transfers()
        self.refresh_history()
        _ = show_app_dialog(
            title="تم التراجع الشامل",
            text=f"تم التراجع عن {count} ملف بنجاح وإلغاء نسخها، وملفاتك الأصلية بأمان تام في أماكنها."
        )

    def go_back(self) -> None:
        app = self.get_app()
        if app and app.root:
            home = app.root.get_screen("home_screen")
            if hasattr(home, "refresh_subjects"):
                home.refresh_subjects()
            app.root.current = "home_screen"

    def get_app(self) -> App | None:
        return App.get_running_app()
