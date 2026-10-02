"""
شاشة إعداد بصمة وجه صاحب الجهاز (PeopleSetupScreen):
- تتيح للمستخدم التقاط أو اختيار 3-5 صور لوجهه.
- استخراج بصمة الوجه وحفظها محلياً في my_face_profile.json.
- تجربة فورية للتعرف على أي صورة وتصنيفها ('me' / 'other' / 'none').
"""

import logging
import os

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.image import Image
from kivy.uix.screenmanager import Screen
from kivy.utils import platform
from kivymd.uix.card import MDCard

import face_classifier
import file_manager
from utils.arabic_helper import ar
from utils.ui_helper import show_app_dialog, show_modern_notification

logger = logging.getLogger("PeopleSetupScreen")


class PeopleSetupScreen(Screen):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.selected_paths: list[str] = []
        self.threshold: float = 0.68

    def on_enter(self, *args: object) -> None:
        self.apply_arabic_texts()
        self.refresh_profile_status()

    def on_threshold_change(self, value: object) -> None:
        """تحديث قيمة عتبة الدقة عند سحب السلايدر"""
        val_float = float(str(value))
        self.threshold = round(val_float / 100.0, 2)
        if hasattr(self, "ids") and "threshold_val_label" in self.ids:
            self.ids.threshold_val_label.text = f"{int(val_float)}%"

    def apply_arabic_texts(self) -> None:
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("إعداد بصمة وجهي")
            if "header_title" in self.ids:
                self.ids.header_title.text = ar("التعرف على صاحب الجهاز")
            if "header_subtitle" in self.ids:
                sub_txt = (
                    "أضف صورة أو أكثر واضحة لوجهك "
                    "لتمييز صورك عن صور الإخوة والأصدقاء."
                )
                self.ids.header_subtitle.text = ar(sub_txt)
            if "photos_section_title" in self.ids:
                self.ids.photos_section_title.text = ar(
                    "صور وجهك المرجعية (1 - 5 صور)"
                )
            if "btn_gallery_text" in self.ids:
                self.ids.btn_gallery_text.text = ar("من المعرض")
            if "btn_camera_text" in self.ids:
                self.ids.btn_camera_text.text = ar("التقاط صورة")
            if "threshold_title" in self.ids:
                self.ids.threshold_title.text = ar(
                    "عتبة دقة المطابقة (Similarity Threshold):"
                )
            if "btn_train_text" in self.ids:
                self.ids.btn_train_text.text = ar("حفظ وتحديث بصمة وجهي")
            if "test_title" in self.ids:
                self.ids.test_title.text = ar(
                    "تجربة التعرف على أي صورة الآن:"
                )
            if "btn_test_text" in self.ids:
                self.ids.btn_test_text.text = ar("اختر صورة للتجربة")

    def refresh_profile_status(self) -> None:
        """تحديث بطاقة حالة البصمة المسجلة وسلايدر العتبة"""
        profile = face_classifier.load_user_face_profile()
        if profile and profile.get("registered"):
            cnt = profile.get("sample_count", 0)
            th = profile.get("threshold", 0.68)
            self.threshold = float(str(th))
            th_pct = int(self.threshold * 100)
            if "threshold_slider" in self.ids:
                self.ids.threshold_slider.value = th_pct
            if "threshold_val_label" in self.ids:
                self.ids.threshold_val_label.text = f"{th_pct}%"

            st_msg = f"بصمة الوجه: مسجلة ومفعلة ({cnt} صور مرجعية)"
            self.ids.profile_status_label.text = ar(st_msg)
            self.ids.status_icon.icon = "check-decagram"
            self.ids.status_icon.icon_color = (0.063, 0.780, 0.549, 1)
        else:
            self.ids.profile_status_label.text = ar(
                "بصمة الوجه: غير مسجلة بعد"
            )
            self.ids.status_icon.icon = "alert-circle-outline"
            self.ids.status_icon.icon_color = (0.85, 0.45, 0.15, 1)

    def pick_from_gallery(self) -> None:
        """اختيار صور الوجه من المعرض"""
        try:
            from plyer import filechooser
            open_fn = getattr(filechooser, "open_file", None)
            if callable(open_fn):
                _ = open_fn(
                    title=ar("اختر صوراً واضحة لوجهك"),
                    filters=["*.jpg", "*.jpeg", "*.png", "*.webp"],
                    multiple=True,
                    on_selection=self._on_files_selected,
                )
                return
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.debug("Plyer filechooser: %s", e)

        try:
            import tkinter as tk
            from tkinter import filedialog
            root_tk = tk.Tk()
            root_tk.withdraw()
            _ = root_tk.attributes("-topmost", True)
            img_types = [
                ("Image files", "*.jpg;*.jpeg;*.png;*.webp"),
                ("All files", "*.*"),
            ]
            paths = filedialog.askopenfilenames(
                title="اختر صوراً لوجهك (1 إلى 5)",
                filetypes=img_types,
            )
            root_tk.destroy()
            if paths:
                self._on_files_selected(list(paths))
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.debug("Tkinter filedialog: %s", e)

    def _on_files_selected(self, paths: list[str]) -> None:
        if not paths:
            return
        for p in paths:
            if p not in self.selected_paths and len(self.selected_paths) < 5:
                self.selected_paths.append(p)

        def _do_render(_dt: float) -> None:
            self.render_samples_grid()

        Clock.schedule_once(_do_render, 0)

    def capture_from_camera(self) -> None:
        """التقاط صورة للوجه عبر الكاميرا"""
        if platform == "android":
            try:
                from plyer import camera
                save_dir = file_manager.get_temp_dir()
                temp_filename = f"face_ref_{os.urandom(4).hex()}.jpg"
                temp_filepath = str(save_dir / temp_filename)
                take_pic_fn = getattr(camera, "take_picture", None)
                if callable(take_pic_fn):
                    def _on_pic_done(p: str) -> None:
                        def _do_select(_dt: float) -> None:
                            self._on_files_selected([p])

                        Clock.schedule_once(_do_select, 0)

                    _ = take_pic_fn(
                        filename=temp_filepath,
                        on_complete=_on_pic_done,
                    )
                    return
            except (ImportError, AttributeError, RuntimeError) as e:
                logger.debug("الكاميرا: %s", e)

        cam_msg = (
            "الكاميرا متاحة تلقائياً على الهاتف. "
            "يرجى اختيار صور من المعرض على الحاسوب."
        )
        _ = show_app_dialog(title="الكاميرا", text=cam_msg)

    def render_samples_grid(self) -> None:
        """رسم مربعات معاينة الصور المرجعية المحددة"""
        self.ids.samples_grid.clear_widgets()
        for _idx, path in enumerate(self.selected_paths):
            card = MDCard(
                size_hint=(1, None),
                height=dp(120),
                radius=[14, 14, 14, 14],
                elevation=0,
                padding=dp(2),
                theme_bg_color="Custom",
                md_bg_color=(1.0, 1.0, 1.0, 0.98),
            )
            img = Image(
                source=path,
                allow_stretch=True,
                keep_ratio=True,
            )
            card.add_widget(img)
            self.ids.samples_grid.add_widget(card)

    def train_and_save(self) -> None:
        """تدريب وحفظ بصمة الوجه المرجعية مع العتبة المحددة (3 - 5 صور)"""
        if len(self.selected_paths) < 3:
            warn_msg = (
                "يرجى اختيار أو التقاط 3 صور على الأقل وحتى 5 صور مختلفة لوجهك "
                "لضمان دقة التعرف ومنع الأخطاء في زوايا الوجه المختلفة."
            )
            _ = show_app_dialog(title="تنبيه: عدد الصور غير كافٍ", text=warn_msg)
            return

        # الحفظ الموحد لبصمة الوجه في مخزن واحد آمن
        result = face_classifier.save_user_face_profile(
            self.selected_paths, threshold=self.threshold
        )
        if result.get("success"):
            self.refresh_profile_status()
            show_modern_notification(
                title="بصمة الوجه",
                message="تم حفظ بصمة وجهك بنجاح وسيتعرف التطبيق على صورك!",
                icon="check-decagram",
                notif_type="success",
            )
            msg_ok = str(result.get("message", "تم حفظ وتحديث بصمة وجهك بنجاح."))
            _ = show_app_dialog(title="تم الحفظ بنجاح", text=msg_ok)
        else:
            msg_err = str(
                result.get("message", "تعذر التعرف على الوجه في الصور المحددة")
            )
            _ = show_app_dialog(title="تعذر التعرف", text=msg_err)

    def delete_face_profile(self) -> None:
        """حذف بيانات وبصمات الوجه المسجلة نهائياً وتعطيل الميزة محلياً من المخزن الموحد"""
        try:
            face_classifier.delete_user_face_profile()
        except Exception as e:
            logger.debug("حذف البصمة: %s", e)

        self.selected_paths.clear()
        if hasattr(self, "ids") and "samples_grid" in self.ids:
            self.ids.samples_grid.clear_widgets()
        self.refresh_profile_status()
        _ = show_app_dialog(
            title="حذف البصمة",
            text="تم حذف بيانات وبصمة وجهك بالكامل من هاتفك بنجاح."
        )

    def test_recognition(self) -> None:
        """تجربة فحص صورة فورياً"""
        try:
            from plyer import filechooser
            open_fn = getattr(filechooser, "open_file", None)
            if callable(open_fn):
                _ = open_fn(
                    title=ar("اختر صورة لفحصها"),
                    filters=["*.jpg", "*.jpeg", "*.png", "*.webp"],
                    on_selection=self._on_test_file_selected,
                )
                return
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.debug("Test recognition filechooser error: %s", e)

        try:
            import tkinter as tk
            from tkinter import filedialog
            root_tk = tk.Tk()
            root_tk.withdraw()
            _ = root_tk.attributes("-topmost", True)
            img_types = [
                ("Image files", "*.jpg;*.jpeg;*.png;*.webp"),
                ("All files", "*.*"),
            ]
            p = filedialog.askopenfilename(
                title="اختر صورة للاختبار",
                filetypes=img_types,
            )
            root_tk.destroy()
            if p:
                self._on_test_file_selected([p])
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.debug("Test recognition tkinter error: %s", e)

    def _on_test_file_selected(self, selection: list[str]) -> None:
        if not selection or len(selection) == 0:
            return
        test_path = selection[0]
        category = face_classifier.detect_and_match_face(
            test_path, threshold=self.threshold
        )

        def update_label(_dt: float) -> None:
            if category == "me":
                txt = "✓ نتيجة الفحص: صورتك أنت (صوري)!"
                self.ids.test_result_label.text = ar(txt)
                self.ids.test_result_label.theme_text_color = "Custom"
                self.ids.test_result_label.text_color = (
                    0.063, 0.780, 0.549, 1
                )
            elif category == "other":
                txt = "👥 نتيجة الفحص: أشخاص آخرون (صور الزملاء والإخوة)!"
                self.ids.test_result_label.text = ar(txt)
                self.ids.test_result_label.theme_text_color = "Custom"
                self.ids.test_result_label.text_color = (
                    0.024, 0.765, 0.886, 1
                )
            else:
                txt = "❌ نتيجة الفحص: لا يوجد وجه بشري في الصورة."
                self.ids.test_result_label.text = ar(txt)
                self.ids.test_result_label.theme_text_color = "Custom"
                self.ids.test_result_label.text_color = (
                    0.95, 0.35, 0.35, 1
                )

        Clock.schedule_once(update_label, 0)

    def go_back(self) -> None:
        from kivy.app import App
        from kivy.uix.screenmanager import ScreenManager

        app = App.get_running_app()
        if app and isinstance(app.root, ScreenManager):
            app.root.current = "home_screen"
