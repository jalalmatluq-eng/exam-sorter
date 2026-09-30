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
from typing import Any

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
from utils.ui_helper import show_app_dialog, show_confirm_dialog


class SettingsScreen(Screen):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.is_scanning: bool = False
        self.is_continuous_scanning: bool = False
        self._stop_continuous_scan: bool = False

    def on_enter(self, *args: object) -> None:
        self.apply_arabic_texts()
        self.refresh_storage_source_ui()
        self.refresh_storage_destination_ui()
        self.refresh_permission_ui()
        self.refresh_operation_mode_ui()
        self.refresh_service_ui()
        self.refresh_face_status()
        self.refresh_skip_intro_ui()
        self.refresh_history()

    def apply_arabic_texts(self) -> None:
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("الإعدادات ومنظّم الوسائط")
            if "storage_source_title" in self.ids:
                self.ids.storage_source_title.text = ar(
                    "أين تريد فحص وسحب الملفات؟ (المصدر)"
                )
            if "text_src_internal" in self.ids:
                self.ids.text_src_internal.text = ar("الذاكرة الداخلية")
            if "text_src_sdcard" in self.ids:
                self.ids.text_src_sdcard.text = ar("كرت SD الخارجي")
            if "text_src_both" in self.ids:
                self.ids.text_src_both.text = ar("كلا الذاكرتين معاً")
            if "storage_dest_title" in self.ids:
                self.ids.storage_dest_title.text = ar(
                    "أين تريد وضع وحفظ الملفات المنظمة؟ (الوجهة)"
                )
            if "perm_title" in self.ids:
                self.ids.perm_title.text = ar(
                    "صلاحية الوصول الشامل للملفات (Android 11+)"
                )
            if "mode_card_title" in self.ids:
                self.ids.mode_card_title.text = ar("طريقة فرز ونقل الملفات")
            if "continuous_scan_title" in self.ids:
                self.ids.continuous_scan_title.text = ar(
                    "الفرز الشامل لجميع وسائط الهاتف"
                )
            if "text_open_folder_btn" in self.ids:
                self.ids.text_open_folder_btn.text = ar(
                    "فتح مجلد الملفات المنظمة في مدير الملفات"
                )
            if "text_clear_cache_btn" in self.ids:
                self.ids.text_clear_cache_btn.text = ar(
                    "إعادة فحص كل شيء من جديد (مسح سجل التتبع)"
                )
            if "text_single_batch_scan" in self.ids:
                self.ids.text_single_batch_scan.text = ar("دفعة 40")
            if "service_title" in self.ids:
                self.ids.service_title.text = ar(
                    "خدمة المراقبة التلقائية اللحظية"
                )
            if "service_desc" in self.ids:
                self.ids.service_desc.text = ar(
                    "فرز ونقل أي صورة أو فيديو جديد فور التقاطه أو تنزيله"
                )
            if "face_card_title" in self.ids:
                self.ids.face_card_title.text = ar("بصمة وجهي وصوري الخاصة")
            if "btn_edit_face_text" in self.ids:
                self.ids.btn_edit_face_text.text = ar("تعديل البصمة")
            if "history_section_title" in self.ids:
                self.ids.history_section_title.text = ar(
                    "سجل عمليات النقل الأخيرة والتراجع"
                )
            if "refresh_history_text" in self.ids:
                self.ids.refresh_history_text.text = ar("تحديث")

    def refresh_storage_source_ui(self) -> None:
        """تحديث بطاقة اختيار مكان الفحص (الداخلية / كرت SD / كلاهما)"""
        try:
            prefs = file_manager.get_sorter_preferences()
            active_src = prefs.get("source_storage", "both")

            def style_btn(
                btn: Any,
                icon_w: Any,
                text_w: Any,
                is_active: bool,
            ) -> None:
                if not btn:
                    return
                if is_active:
                    btn.style = "filled"
                    btn.md_bg_color = (0.486, 0.302, 0.988, 1)
                    if icon_w:
                        icon_w.icon_color = (1, 1, 1, 1)
                    if text_w:
                        text_w.text_color = (1, 1, 1, 1)
                else:
                    btn.style = "outlined"
                    btn.md_bg_color = (0.92, 0.95, 1.0, 0.95)
                    if icon_w:
                        icon_w.icon_color = (0.486, 0.302, 0.988, 1)
                    if text_w:
                        text_w.text_color = (0.35, 0.45, 0.60, 1)

            if "btn_src_internal" in self.ids:
                style_btn(
                    self.ids.btn_src_internal,
                    self.ids.get("icon_src_internal"),
                    self.ids.get("text_src_internal"),
                    active_src == "internal",
                )
            if "btn_src_sdcard" in self.ids:
                style_btn(
                    self.ids.btn_src_sdcard,
                    self.ids.get("icon_src_sdcard"),
                    self.ids.get("text_src_sdcard"),
                    active_src == "sdcard",
                )
            if "btn_src_both" in self.ids:
                style_btn(
                    self.ids.btn_src_both,
                    self.ids.get("icon_src_both"),
                    self.ids.get("text_src_both"),
                    active_src == "both",
                )

            if "storage_source_desc_label" in self.ids:
                if active_src == "internal":
                    txt = (
                        "الخطة: فحص وسحب صور وفيديوهات"
                        " الذاكرة الداخلية فقط."
                    )
                elif active_src == "sdcard":
                    txt = "الخطة: فحص وسحب وسائط كرت SD فقط."
                else:
                    txt = (
                        "الخطة: فحص شامل لكافة وسائط"
                        " الذاكرة الداخلية وكرت SD معاً."
                    )
                self.ids.storage_source_desc_label.text = ar(txt)
        except Exception as e:
            print("خطأ أثناء تحديث واجهة مصدر الفحص:", e)

    def select_storage_source(self, choice: str) -> None:
        """اختيار مكان فحص وسحب الملفات (الداخلية / كرت SD / كلاهما)"""
        file_manager.save_sorter_preferences({"source_storage": choice})
        self.refresh_storage_source_ui()
        from utils.ui_helper import show_modern_notification

        names = {
            "internal": "الذاكرة الداخلية فقط",
            "sdcard": "بطاقة الذاكرة الخارجية SD فقط",
            "both": "كلا الذاكرتين معاً (شامل)",
        }
        chosen_name = names.get(choice, choice)
        show_modern_notification(
            title="مصدر فحص الملفات",
            message=f"تم اعتماد: {chosen_name}",
            icon="folder-search-outline",
            notif_type="info",
        )

    def refresh_storage_destination_ui(self) -> None:
        """تحديث بطاقة اختيار مكان الفرز والتخزين والمسار النشط"""
        try:
            prefs = file_manager.get_sorter_preferences()
            active_dest = prefs.get("target_storage", "internal")
            base_path = file_manager.get_media_sorter_base_path()
            dests = file_manager.get_available_storage_destinations()

            if "storage_current_path_label" in self.ids:
                self.ids.storage_current_path_label.text = ar(
                    f"المسار: {base_path}"
                )

            internal_info = dests.get("internal", {})
            sdcard_info = dests.get("sdcard")

            int_free = internal_info.get("free_gb", 0)
            if "text_dest_internal" in self.ids:
                self.ids.text_dest_internal.text = ar(
                    f"الداخلية ({int_free}GB حر)"
                )

            if sdcard_info and sdcard_info.get("available"):
                sd_free = sdcard_info.get("free_gb", 0)
                if "text_dest_sdcard" in self.ids:
                    self.ids.text_dest_sdcard.text = ar(
                        f"كرت SD ({sd_free}GB)"
                    )
            else:
                if "text_dest_sdcard" in self.ids:
                    self.ids.text_dest_sdcard.text = ar("كرت SD (غير متوفر)")

            if (
                active_dest == "sdcard"
                and sdcard_info
                and sdcard_info.get("available")
            ):
                self.ids.btn_dest_sdcard.style = "filled"
                self.ids.btn_dest_sdcard.md_bg_color = (0.486, 0.302, 0.988, 1)
                self.ids.icon_dest_sdcard.icon_color = (1, 1, 1, 1)
                self.ids.text_dest_sdcard.text_color = (1, 1, 1, 1)

                self.ids.btn_dest_internal.style = "outlined"
                self.ids.btn_dest_internal.md_bg_color = (
                    0.92, 0.95, 1.0, 0.95
                )
                self.ids.icon_dest_internal.icon_color = (
                    0.486,
                    0.302,
                    0.988,
                    1,
                )
                self.ids.text_dest_internal.text_color = (0.35, 0.45, 0.60, 1)
            else:
                self.ids.btn_dest_internal.style = "filled"
                self.ids.btn_dest_internal.md_bg_color = (
                    0.486,
                    0.302,
                    0.988,
                    1,
                )
                self.ids.icon_dest_internal.icon_color = (1, 1, 1, 1)
                self.ids.text_dest_internal.text_color = (1, 1, 1, 1)

                self.ids.btn_dest_sdcard.style = "outlined"
                self.ids.btn_dest_sdcard.md_bg_color = (0.92, 0.95, 1.0, 0.95)
                self.ids.icon_dest_sdcard.icon_color = (0.486, 0.302, 0.988, 1)
                self.ids.text_dest_sdcard.text_color = (0.35, 0.45, 0.60, 1)
        except Exception as e:
            print("خطأ أثناء تحديث واجهة التخزين:", e)

    def select_storage_destination(self, choice: str) -> None:
        """اختيار وجهة التخزين والفرز (داخلية / كرت SD)"""
        dests = file_manager.get_available_storage_destinations()
        if choice == "sdcard":
            sd_info = dests.get("sdcard")
            if not sd_info or not sd_info.get("available"):
                show_app_dialog(
                    title="كرت الذاكرة غير متوفر",
                    text=(
                        "لم يتم العثور على بطاقة ذاكرة"
                        " خارجية SD Card قابلة للكتابة."
                        " تم الإبقاء على الذاكرة الداخلية."
                    ),
                )
                return

        file_manager.save_sorter_preferences({"target_storage": choice})
        self.refresh_storage_destination_ui()
        new_path = file_manager.get_media_sorter_base_path()
        target_name = (
            "بطاقة الذاكرة الخارجية SD Card"
            if choice == "sdcard"
            else "الذاكرة الداخلية"
        )
        from utils.ui_helper import show_modern_notification

        show_modern_notification(
            "تم حفظ مكان الفرز",
            f"الوجهة المعتمدة: {target_name}",
            notif_type="success",
        )
        show_app_dialog(
            title="تم حفظ مكان الفرز",
            text=(
                f"تم اعتماد {target_name} مكاناً"
                f" لحفظ وفرز كافة الوسائط:\n\n{new_path}"
            ),
        )

    def open_current_media_folder(self) -> None:
        """فتح مجلد الملفات المنظمة الحالي في تطبيق الملفات"""
        path = file_manager.get_media_sorter_base_path()
        success = file_manager.open_folder_native(str(path))
        if not success:
            show_app_dialog(
                title="مسار مجلد الملفات المنظمة",
                text=(
                    f"المسار الفعلي لحفظ ملفاتك"
                    f" المفرزة هو:\n{path}\n\n"
                    "يمكنك فتحه من تطبيق 'ملفاتي'."
                ),
            )

    def refresh_permission_ui(self) -> None:
        """فحص وتحديث شارة صلاحية الوصول لكافة الملفات"""
        granted = file_manager.is_all_files_access_granted()
        if granted:
            if "perm_desc_label" in self.ids:
                self.ids.perm_desc_label.text = ar(
                    "الحالة: الصلاحية ممنوحة بالكامل وتغطي كافة المجلدات ✓"
                )
                self.ids.perm_desc_label.text_color = (0.063, 0.780, 0.549, 1)
            if "perm_icon" in self.ids:
                self.ids.perm_icon.icon = "shield-check"
                self.ids.perm_icon.icon_color = (0.063, 0.780, 0.549, 1)
            if "btn_permission_text" in self.ids:
                self.ids.btn_permission_text.text = ar(
                    "الصلاحية مفعلة (انقر لإدارة الإذن)"
                )
        else:
            if "perm_desc_label" in self.ids:
                self.ids.perm_desc_label.text = ar(
                    "الحالة: الصلاحية مقيدة ⚠️"
                    " (مطلوبة لدخول WhatsApp و Bluetooth)"
                )
                self.ids.perm_desc_label.text_color = (0.980, 0.647, 0.102, 1)
            if "perm_icon" in self.ids:
                self.ids.perm_icon.icon = "shield-alert"
                self.ids.perm_icon.icon_color = (0.980, 0.647, 0.102, 1)
            if "btn_permission_text" in self.ids:
                self.ids.btn_permission_text.text = ar(
                    "منح صلاحية الوصول لكافة الملفات الآن"
                )

    def request_all_files_permission(self) -> None:
        """فتح صفحة النظام لمنح صلاحية MANAGE_ALL_FILES_ACCESS_PERMISSION"""
        opened = file_manager.open_all_files_permission_settings()
        if opened:
            show_app_dialog(
                title="إذن الوصول لكافة الملفات",
                text=(
                    "تم فتح إعدادات النظام. يرجى تفعيل مفتاح"
                    " 'السماح بالوصول لإدارة جميع الملفات'"
                    " لتمكين التطبيق من فحص كافة مجلدات هاتفك."
                ),
            )
        else:
            show_app_dialog(
                title="الصلاحيات",
                text=(
                    "على جهازك الحالي الصلاحيات مفعلة"
                    " أو يتم إدارتها تلقائياً."
                ),
            )
        Clock.schedule_once(lambda _dt: self.refresh_permission_ui(), 2.0)

    def refresh_operation_mode_ui(self) -> None:
        """تحديث حالة أزرار نمط الفرز (نسخ أم نقل)"""
        prefs = file_manager.get_sorter_preferences()
        mode = prefs.get("operation_mode", "copy")

        if mode == "move":
            self.ids.btn_mode_move.style = "filled"
            self.ids.btn_mode_move.md_bg_color = (0.486, 0.302, 0.988, 1)
            self.ids.icon_mode_move.icon_color = (1, 1, 1, 1)
            self.ids.text_mode_move.text_color = (1, 1, 1, 1)

            self.ids.btn_mode_copy.style = "outlined"
            self.ids.btn_mode_copy.md_bg_color = (0.92, 0.95, 1.0, 0.95)
            self.ids.icon_mode_copy.icon_color = (0.486, 0.302, 0.988, 1)
            self.ids.text_mode_copy.text_color = (0.35, 0.45, 0.60, 1)

            if "mode_desc_label" in self.ids:
                self.ids.mode_desc_label.text = ar(
                    "الوضع الحالي: نقل الملف"
                    " وحذف الأصل لتوفير المساحة."
                )
        else:
            self.ids.btn_mode_copy.style = "filled"
            self.ids.btn_mode_copy.md_bg_color = (0.486, 0.302, 0.988, 1)
            self.ids.icon_mode_copy.icon_color = (1, 1, 1, 1)
            self.ids.text_mode_copy.text_color = (1, 1, 1, 1)

            self.ids.btn_mode_move.style = "outlined"
            self.ids.btn_mode_move.md_bg_color = (0.92, 0.95, 1.0, 0.95)
            self.ids.icon_mode_move.icon_color = (0.486, 0.302, 0.988, 1)
            self.ids.text_mode_move.text_color = (0.35, 0.45, 0.60, 1)

            if "mode_desc_label" in self.ids:
                self.ids.mode_desc_label.text = ar(
                    "الوضع الحالي: نسخ آمن"
                    " مع إبقاء أصل الملف."
                )

    def select_operation_mode(self, mode: str) -> None:
        """التبديل بين النسخ الآمن والنقل الكامل مع تنبيه تأكيدي عند النقل"""
        if mode == "move":

            def on_confirm_move():
                file_manager.save_sorter_preferences(
                    {"operation_mode": "move"}
                )
                self.refresh_operation_mode_ui()
                show_app_dialog(
                    title="تم تفعيل وضع النقل",
                    text=(
                        "سيقوم التطبيق بنقل الملفات وحذف الأصل"
                        " لتوفير مساحة الذاكرة.\n"
                        "(ملاحظة: يمكنك التراجع عبر زر التراجع.)"
                    ),
                )

            show_confirm_dialog(
                title="تأكيد وضع النقل وحذف الأصل",
                text=(
                    "في وضع النقل، سيتم نقل الصور والفيديوهات"
                    " من أماكنها الأصلية وتفريغ"
                    " مساحتها. هل تريد المتابعة؟"
                ),
                on_confirm=on_confirm_move,
                confirm_text="نعم، تفعيل النقل",
                cancel_text="إلغاء (إبقاء النسخ)",
            )
        else:
            file_manager.save_sorter_preferences({"operation_mode": "copy"})
            self.refresh_operation_mode_ui()
            show_app_dialog(
                title="تم تفعيل النسخ الآمن",
                text=(
                    "سيتم نسخ الملفات المنظمة"
                    " مع الحفاظ على النسخ الأصلية."
                ),
            )

    def toggle_continuous_scan(self) -> None:
        """تشغيل أو إيقاف الفرز الشامل المتواصل لجميع وسائط الهاتف"""
        if self.is_continuous_scanning:
            self._stop_continuous_scan = True
            if "text_continuous_scan" in self.ids:
                self.ids.text_continuous_scan.text = ar("جاري التوقف...")
            return

        self.is_continuous_scanning = True
        self._stop_continuous_scan = False
        if "text_continuous_scan" in self.ids:
            self.ids.text_continuous_scan.text = ar("إيقاف الفرز الشامل")
        if "icon_continuous_scan" in self.ids:
            self.ids.icon_continuous_scan.icon = "stop-circle"
        if "btn_continuous_scan" in self.ids:
            self.ids.btn_continuous_scan.md_bg_color = (0.85, 0.35, 0.25, 1)

        def worker():
            app = self.get_app()
            api_key = getattr(app, "api_key", None)

            def on_progress(p_data: dict[str, object]) -> None:
                def update_label(_dt: float) -> None:
                    if p_data.get("is_finished"):
                        return
                    curr = str(p_data.get("current_file", ""))
                    done = p_data.get("total_processed", 0)
                    rem = p_data.get("remaining_count", 0)
                    if "continuous_progress_label" in self.ids:
                        self.ids.continuous_progress_label.text = ar(
                            f"المفرز: {done} | المتبقي: {rem} | {curr[:16]}"
                        )

                Clock.schedule_once(update_label, 0)

            prefs = file_manager.get_sorter_preferences()
            source_storage = str(prefs.get("source_storage", "both"))

            results = media_scanner.run_continuous_scan(
                batch_size=35,
                api_key=api_key,
                progress_callback=on_progress,
                stop_check=lambda: self._stop_continuous_scan,
                source_storage=source_storage,
            )

            def on_complete(_dt: float) -> None:
                self.is_continuous_scanning = False
                self._stop_continuous_scan = False
                if "text_continuous_scan" in self.ids:
                    self.ids.text_continuous_scan.text = ar(
                        "فرز شامل حتى النهاية"
                    )
                if "icon_continuous_scan" in self.ids:
                    self.ids.icon_continuous_scan.icon = "play-circle"
                if "btn_continuous_scan" in self.ids:
                    self.ids.btn_continuous_scan.md_bg_color = (
                        0.72,
                        0.42,
                        0.24,
                        1,
                    )
                if "continuous_progress_label" in self.ids:
                    self.ids.continuous_progress_label.text = ar(
                        "فرز مستمر لكافة الصور والفيديوها"
                        " حتى اكتمال 100%"
                    )

                self.refresh_history()
                total_sorted = results.get("total_processed", 0)
                show_app_dialog(
                    title="اكتمل الفرز الشامل",
                    text=(
                        f"تم فرز وتنظيم {total_sorted} ملف"
                        " وسائط بنجاح!"
                    ),
                )

            Clock.schedule_once(on_complete, 0)

        threading.Thread(target=worker, daemon=True).start()

    def confirm_clear_cache(self) -> None:
        """مسح قاعدة بيانات التتبع لتمكين إعادة فحص وسحب الملفات من الصفر"""

        def do_clear():
            media_scanner.clear_all_cache()
            show_app_dialog(
                title="تم تصفير سجل التتبع",
                text=(
                    "تم مسح سجل الملفات المفحوصة بنجاح."
                    " يمكنك الآن بدء الفحص"
                    " الشامل من جديد."
                ),
            )

        show_confirm_dialog(
            title="إعادة فحص كافة الملفات",
            text=(
                "هل تريد تصفير سجل التتبع؟ سيتيح هذا"
                " للتطبيق إعادة فحص الوسائط القديمة."
            ),
            on_confirm=do_clear,
            confirm_text="نعم، إعادة الضبط",
            cancel_text="إلغاء",
        )

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
                text=(
                    "تم تفعيل خدمة المراقبة التلقائية"
                    " وبدء تشغيلها. سيتم رصد"
                    " وتصنيف أي وسائط جديدة فور."
                ),
            )
        else:
            _ = show_app_dialog(
                title="تم الإيقاف", text="تم إيقاف المراقبة التلقائية مؤقتاً."
            )

    def refresh_face_status(self) -> None:
        """تحديث بطاقة حالة بصمة الوجه"""
        if face_classifier.is_user_profile_registered():
            self.ids.face_card_status.text = ar(
                "البصمة مسجلة وجاهزة لتمييز صورك الخاصة"
            )
        else:
            self.ids.face_card_status.text = ar(
                "لم يتم تسجيل بصمة وجهك بعد (انقر للإعداد)"
            )

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
        if "text_single_batch_scan" in self.ids:
            self.ids.text_single_batch_scan.text = ar("جاري...")

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
        if "text_single_batch_scan" in self.ids:
            self.ids.text_single_batch_scan.text = ar("دفعة 40")
        self.refresh_history()

        processed = result.get("processed_count", 0)
        total = result.get("total_unprocessed_found", 0)

        # احضر إحصائيات التخزين الحديثة بعد الفحص
        stats_text = ""
        try:
            import storage_utils

            stats = storage_utils.get_storage_stats()
            cats_count = len(stats["categories"])
            stats_text = (
                f"\n\n📊 إحصائيات التخزين:\n"
                f"- الملفات المنظمة: {stats['total_files']} ملف\n"
                f"- الحجم الكلي: {stats['total_size_mb']} MB\n"
                f"- الأقسام النشطة: {cats_count}"
            )
        except (KeyError, ValueError, OSError, RuntimeError):
            stats_text = ""

        result_message = (
            f"اكتملت دورة الفحص بنجاح!\n\n"
            f"- الملفات الجديدة المصنفة: {processed}\n"
            f"- إجمالي الملفات المعالجة: {total}{stats_text}"
        )
        _ = show_app_dialog(title="اكتمل الفحص الشامل", text=result_message)

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
                theme_bg_color="Custom",
                md_bg_color=(1.0, 1.0, 1.0, 0.95),
            )
            card.add_widget(
                MDLabel(
                    text=ar("لا توجد عمليات نقل مسجلة بعد"),
                    halign="center",
                    font_size="12sp",
                    theme_text_color="Custom",
                    text_color=(0.35, 0.45, 0.60, 1),
                )
            )
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
            elevation=0,
            padding=[dp(12), dp(6), dp(12), dp(6)],
            theme_bg_color="Custom",
            md_bg_color=(1.0, 1.0, 1.0, 0.98),
            orientation="horizontal",
            spacing=dp(10),
        )

        def on_undo_click(_btn: object) -> None:
            self.undo_record(rec_id)

        undo_btn = MDButton(
            style="outlined",
            size_hint=(None, None),
            size=(dp(80), dp(36)),
            pos_hint={"center_y": 0.5},
            on_release=on_undo_click,
        )
        _ = undo_btn.add_widget(
            MDButtonIcon(
                icon="undo",
                theme_icon_color="Custom",
                icon_color=(0.486, 0.302, 0.988, 1),
            )
        )
        _ = undo_btn.add_widget(
            MDButtonText(
                text=ar("تراجع"),
                theme_text_color="Custom",
                text_color=(0.35, 0.45, 0.60, 1),
            )
        )
        _ = card.add_widget(undo_btn)

        info_box = BoxLayout(
            orientation="vertical", spacing=dp(2), pos_hint={"center_y": 0.5}
        )

        name_label = MDLabel(
            text=ar(src_name),
            bold=True,
            font_size="12sp",
            shorten=True,
            shorten_from="center",
            halign="right",
            theme_text_color="Custom",
            text_color=(0.08, 0.16, 0.34, 1),
        )
        cat_label = MDLabel(
            text=ar(f"نُسخ إلى: {category}"),
            font_size="10sp",
            halign="right",
            theme_text_color="Custom",
            text_color=(0.02, 0.52, 0.80, 1),
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
                text=(
                    "تم حذف النسخة بنجاح من مجلد"
                    " التصنيف، وملفك الأصلي باقٍ."
                ),
            )
        else:
            _ = show_app_dialog(
                title="تعذر التراجع",
                text="تعذر العثور على النسخة أو ربما تم حذفها مسبقاً.",
            )

    def undo_all_records(self) -> None:
        """التراجع عن كافة عمليات الفرز والنسخ بنقرة واحدة"""
        history = file_manager.get_transfer_history()
        if not history:
            _ = show_app_dialog(
                title="السجل فارغ",
                text="لا توجد أي عمليات حالية للتراجع عنها.",
            )
            return

        count = file_manager.undo_all_transfers()
        self.refresh_history()
        _ = show_app_dialog(
            title="تم التراجع الشامل",
            text=(
                f"تم التراجع عن {count} ملف بنجاح"
                " وملفاتك الأصلية بأمان تام."
            ),
        )

    def find_duplicates_action(self) -> None:
        """كشف الملفات المكررة داخل مجلدات التخزين مع خيار الحذف الآمن المباشر"""
        try:
            import storage_utils

            dupes = storage_utils.find_duplicate_files()
            if not dupes:
                _ = show_app_dialog(
                    title="لا توجد مكررات ✓",
                    text=(
                        "ممتاز! لم يتم اكتشاف أي"
                        " ملفات مكررة في مجلداتك المنظمة."
                    ),
                )
                return

            total_dupes = sum(len(g) - 1 for g in dupes)
            total_bytes = 0
            for g in dupes:
                for f in g[1:]:
                    try:
                        total_bytes += Path(f).stat().st_size
                    except OSError:
                        pass
            size_mb = round(total_bytes / 1048576, 2)

            def _do_remove_dupes() -> None:
                del_count, freed = storage_utils.remove_duplicate_files(dupes)
                freed_mb = round(freed / 1048576, 2)
                _ = show_app_dialog(
                    title="تم التنظيف بنجاح ✓",
                    text=(
                        f"تم حذف {del_count} ملف مكرر بأمان،"
                        f" وتم تحرير {freed_mb} MB من مساحة التخزين.\n"
                        "ملفاتك الأصلية الأولى بقيت بأمان تام دون أي مساس."
                    ),
                )

            sample_text = "\n".join(f"• {Path(g[0]).name}" for g in dupes[:3])
            _ = show_confirm_dialog(
                title="كشف ملفات مكررة",
                text=(
                    f"تم العثور على {total_dupes} ملف مكرر تستهلك قرابة {size_mb} MB.\n\n"
                    f"أمثلة:\n{sample_text}\n\n"
                    "هل ترغب بحذف النسخ المكررة مع إبقاء النسخة الأصلية لكل ملف؟"
                ),
                on_confirm=_do_remove_dupes,
                confirm_text="حذف المكرر وتحرير المساحة",
                cancel_text="إلغاء",
            )
        except (OSError, RuntimeError, ValueError) as e:
            _ = show_app_dialog(title="خطأ", text=f"تعذر فحص المكررات: {e}")

    def replay_intro(self) -> None:
        """إعادة تشغيل شاشة البداية الكونية والاستمتاع بالمؤثرات"""
        if self.manager and self.manager.has_screen("intro_screen"):
            self.manager.current = "intro_screen"

    def toggle_skip_intro(self) -> None:
        """تبديل تفضيل تخطي شاشة البداية عند فتح التطبيق"""
        prefs = file_manager.get_sorter_preferences()
        skip_pref = prefs.get("skip_intro", None)
        if skip_pref is None:
            current = bool(prefs.get("intro_seen", False))
        else:
            current = bool(skip_pref)
        new_val = not current
        file_manager.save_sorter_preferences({"skip_intro": new_val})
        self.refresh_skip_intro_ui()

    def refresh_skip_intro_ui(self) -> None:
        """تحديث بطاقة وزر تفضيل شاشة البداية"""
        prefs = file_manager.get_sorter_preferences()
        skip_pref = prefs.get("skip_intro", None)
        if skip_pref is None:
            is_active_skip = bool(prefs.get("intro_seen", False))
        else:
            is_active_skip = bool(skip_pref)

        if "text_skip_intro" in self.ids:
            self.ids.text_skip_intro.text = ar(
                "تخطي البداية: مفعل ✓" if is_active_skip else "تخطي البداية: معطل"
            )
        if "btn_skip_intro" in self.ids:
            self.ids.btn_skip_intro.md_bg_color = (
                (0.88, 0.96, 1.0, 0.95) if is_active_skip else (0.92, 0.95, 1.0, 0.95)
            )

    def show_storage_stats(self) -> None:
        """عرض إحصائيات التخزين الشاملة"""
        try:
            import storage_utils

            stats = storage_utils.get_storage_stats()
            cats = stats["categories"]
            lines = [f"📁 الملفات المنظمة: {stats['total_files']} ملف"]
            lines.append(f"💾 الحجم الكلي: {stats['total_size_mb']} MB")
            lines.append(f"📂 الأقسام: {len(cats)}")
            if cats:
                lines.append("")
                sorted_cats = sorted(
                    cats.items(),
                    key=lambda item: item[1]["count"],
                    reverse=True,
                )[:6]
                for name, info in sorted_cats:
                    lines.append(
                        f"  • {name}: {info['count']} ملف"
                        f" ({info['size_mb']} MB)"
                    )
            _ = show_app_dialog(
                title="إحصائيات التخزين الذكي", text="\n".join(lines)
            )
        except (KeyError, ValueError, OSError, RuntimeError) as e:
            _ = show_app_dialog(title="خطأ", text=f"تعذر جلب الإحصائيات: {e}")

    def go_back(self) -> None:
        app = self.get_app()
        if app and app.root:
            home = app.root.get_screen("home_screen")
            if hasattr(home, "refresh_subjects"):
                home.refresh_subjects()
            app.root.current = "home_screen"

    def get_app(self) -> App | None:
        return App.get_running_app()
