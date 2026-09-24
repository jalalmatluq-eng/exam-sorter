# -*- coding: utf-8 -*-
"""
شاشة إعداد بصمة وجه صاحب الجهاز (PeopleSetupScreen):
- تتيح للمستخدم التقاط أو اختيار 3-5 صور لوجهه.
- استخراج بصمة الوجه وحفظها محلياً في my_face_profile.json.
- تجربة فورية للتعرف على أي صورة وتصنيفها ('me' / 'other' / 'none').
"""

import os
from pathlib import Path
from kivy.uix.screenmanager import Screen
from kivy.uix.image import Image
from kivy.clock import Clock
from kivy.utils import platform
from kivy.metrics import dp
from kivymd.uix.card import MDCard

import face_classifier
import file_manager
from utils.arabic_helper import ar
from utils.ui_helper import show_app_dialog


class PeopleSetupScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_paths: list[str] = []
        self.threshold: float = 0.68

    def on_enter(self):
        self.apply_arabic_texts()
        self.refresh_profile_status()

    def on_threshold_change(self, value):
        """تحديث قيمة عتبة الدقة عند سحب السلايدر"""
        self.threshold = round(float(value) / 100.0, 2)
        if hasattr(self, "ids") and "threshold_val_label" in self.ids:
            self.ids.threshold_val_label.text = f"{int(value)}%"

    def apply_arabic_texts(self):
        if hasattr(self, "ids"):
            if "top_bar_title" in self.ids:
                self.ids.top_bar_title.text = ar("إعداد بصمة وجهي")
            if "header_title" in self.ids:
                self.ids.header_title.text = ar("التعرف على صاحب الجهاز")
            if "header_subtitle" in self.ids:
                self.ids.header_subtitle.text = ar("أضف 3 إلى 5 صور واضحة لوجهك في ظروف إضاءة وزوايا مختلفة لتمييز صورك عن صور الزملاء.")
            if "photos_section_title" in self.ids:
                self.ids.photos_section_title.text = ar("صور وجهك المرجعية (3 - 5 صور)")
            if "btn_gallery_text" in self.ids:
                self.ids.btn_gallery_text.text = ar("من المعرض")
            if "btn_camera_text" in self.ids:
                self.ids.btn_camera_text.text = ar("التقاط صورة")
            if "threshold_title" in self.ids:
                self.ids.threshold_title.text = ar("عتبة دقة المطابقة (Similarity Threshold):")
            if "btn_train_text" in self.ids:
                self.ids.btn_train_text.text = ar("حفظ وتحديث بصمة وجهي")
            if "test_title" in self.ids:
                self.ids.test_title.text = ar("تجربة التعرف على أي صورة الآن:")
            if "btn_test_text" in self.ids:
                self.ids.btn_test_text.text = ar("اختر صورة للتجربة")

    def refresh_profile_status(self):
        """تحديث بطاقة حالة البصمة المسجلة وسلايدر العتبة"""
        profile = face_classifier.load_user_face_profile()
        if profile and profile.get("registered"):
            cnt = profile.get("sample_count", 0)
            th = profile.get("threshold", 0.68)
            self.threshold = float(th)
            if "threshold_slider" in self.ids:
                self.ids.threshold_slider.value = int(self.threshold * 100)
            if "threshold_val_label" in self.ids:
                self.ids.threshold_val_label.text = f"{int(self.threshold * 100)}%"

            self.ids.profile_status_label.text = ar(f"بصمة الوجه: مسجلة ومفعلة ({cnt} صور مرجعية)")
            self.ids.status_icon.icon = "check-decagram"
            self.ids.status_icon.icon_color = (0.20, 0.65, 0.35, 1)
        else:
            self.ids.profile_status_label.text = ar("بصمة الوجه: غير مسجلة بعد")
            self.ids.status_icon.icon = "alert-circle-outline"
            self.ids.status_icon.icon_color = (0.85, 0.45, 0.15, 1)

    def pick_from_gallery(self):
        """اختيار صور الوجه من المعرض"""
        try:
            from plyer import filechooser
            filechooser.open_file(
                title=ar("اختر صوراً واضحة لوجهك"),
                filters=["*.jpg", "*.jpeg", "*.png", "*.webp"],
                multiple=True,
                on_selection=self._on_files_selected
            )
            return
        except Exception as e:
            print("Plyer filechooser:", e)

        try:
            import tkinter as tk
            from tkinter import filedialog
            root_tk = tk.Tk()
            root_tk.withdraw()
            root_tk.attributes("-topmost", True)
            paths = filedialog.askopenfilenames(
                title="اختر صوراً لوجهك (3 إلى 5)",
                filetypes=[("Image files", "*.jpg;*.jpeg;*.png;*.webp"), ("All files", "*.*")]
            )
            root_tk.destroy()
            if paths:
                self._on_files_selected(paths)
        except Exception as e:
            print("Tkinter filedialog:", e)

    def _on_files_selected(self, paths):
        if not paths:
            return
        for p in paths:
            if p not in self.selected_paths and len(self.selected_paths) < 5:
                self.selected_paths.append(p)
        Clock.schedule_once(lambda dt: self.render_samples_grid(), 0)

    def capture_from_camera(self):
        """التقاط صورة للوجه عبر الكاميرا"""
        if platform == "android":
            try:
                from plyer import camera
                save_dir = file_manager.get_temp_dir()
                temp_filename = f"face_ref_{os.urandom(4).hex()}.jpg"
                temp_filepath = str(save_dir / temp_filename)
                camera.take_picture(
                    filename=temp_filepath,
                    on_complete=lambda path: Clock.schedule_once(lambda dt: self._on_files_selected([path]), 0)
                )
                return
            except Exception as e:
                print("الكاميرا:", e)

        show_app_dialog(
            title="الكاميرا",
            text="الكاميرا متاحة تلقائياً على الهاتف. يرجى اختيار صور من المعرض على الحاسوب."
        )

    def render_samples_grid(self):
        """رسم مربعات معاينة الصور المرجعية المحددة"""
        self.ids.samples_grid.clear_widgets()
        for idx, path in enumerate(self.selected_paths):
            card = MDCard(
                size_hint=(1, None),
                height=dp(120),
                radius=[12, 12, 12, 12],
                elevation=1,
                padding=dp(2),
                md_bg_color=(1, 1, 1, 1),
            )
            img = Image(
                source=path,
                allow_stretch=True,
                keep_ratio=True
            )
            card.add_widget(img)
            self.ids.samples_grid.add_widget(card)

    def train_and_save(self):
        """تدريب وحفظ بصمة الوجه المرجعية مع العتبة المحددة"""
        if len(self.selected_paths) < 3:
            show_app_dialog(
                title="تنبيه",
                text="يشترط اختيار أو التقاط 3 صور واضحة لوجهك على الأقل (ويفضل 3-5 صور بزوايا وإضاءات مختلفة) لتكوين بصمة دقيقة."
            )
            return

        result = face_classifier.save_user_face_profile(self.selected_paths, threshold=self.threshold)
        if result["success"]:
            self.refresh_profile_status()
            show_app_dialog(
                title="تم الحفظ بنجاح",
                text=result["message"]
            )
        else:
            show_app_dialog(
                title="تعذر التعرف",
                text=result["message"]
            )

    def test_recognition(self):
        """تجربة فحص صورة فورياً"""
        try:
            from plyer import filechooser
            filechooser.open_file(
                title=ar("اختر صورة لفحصها"),
                filters=["*.jpg", "*.jpeg", "*.png", "*.webp"],
                on_selection=self._on_test_file_selected
            )
            return
        except Exception:
            pass

        try:
            import tkinter as tk
            from tkinter import filedialog
            root_tk = tk.Tk()
            root_tk.withdraw()
            root_tk.attributes("-topmost", True)
            p = filedialog.askopenfilename(
                title="اختر صورة للاختبار",
                filetypes=[("Image files", "*.jpg;*.jpeg;*.png;*.webp"), ("All files", "*.*")]
            )
            root_tk.destroy()
            if p:
                self._on_test_file_selected([p])
        except Exception:
            pass

    def _on_test_file_selected(self, selection):
        if not selection or len(selection) == 0:
            return
        test_path = selection[0]
        category = face_classifier.detect_and_match_face(test_path, threshold=self.threshold)

        def update_label(dt):
            if category == "me":
                self.ids.test_result_label.text = ar("✓ نتيجة الفحص: صورتك أنت (صوري)!")
                self.ids.test_result_label.theme_text_color = "Custom"
                self.ids.test_result_label.text_color = (0.2, 0.7, 0.3, 1)
            elif category == "other":
                self.ids.test_result_label.text = ar("👥 نتيجة الفحص: أشخاص آخرون (صور الزملاء والإخوة)!")
                self.ids.test_result_label.theme_text_color = "Custom"
                self.ids.test_result_label.text_color = (0.2, 0.4, 0.8, 1)
            else:
                self.ids.test_result_label.text = ar("❌ نتيجة الفحص: لا يوجد وجه بشري في الصورة.")
                self.ids.test_result_label.theme_text_color = "Custom"
                self.ids.test_result_label.text_color = (0.7, 0.3, 0.3, 1)

        Clock.schedule_once(update_label, 0)

    def go_back(self):
        app = self.get_app()
        app.root.current = "home_screen"

    def get_app(self):
        from kivy.app import App
        return App.get_running_app()
