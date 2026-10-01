"""
شاشة البداية الكونية المتحركة (IntroScreen):
- تظهر عند فتح التطبيق مباشرة.
- تعرض شكلاً كونياً بارزاً ومضيئاً في المنتصف.
- تدور حوله أيقونات الوسائط (صور، فيديوهات، ملفات، اختبارات، أغاني، مجلدات) دورتين كاملتين (720 درجة).
- بعد الدورتين تجتمع كافة الوسائط في قلب الكون بحركة انسيابية فائقة.
- تظهر تحت الشكل الكوني علامة CosmoSort مع العبارة الملهمة:
  "دليلك المفضل والذكي لتنظيم وترتيب ملفاتك في فضاء واحد"
- ثم تنتقل بسلاسة إلى الشاشة الرئيسية.
"""

import math
from typing import Any, Literal

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.screenmanager import Screen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel

from utils.arabic_helper import ar


class IntroScreen(Screen):
    orbit_angle = NumericProperty(0.0)
    orbit_radius = NumericProperty(dp(130))
    orbit_alpha = NumericProperty(1.0)
    center_pulse = NumericProperty(1.0)
    text_alpha = NumericProperty(0.0)

    def __init__(self, **kwargs: Any) -> None:
        self._orbit_widgets: list[MDCard] = []
        self._animation_started = False
        self._completed = False
        self._touch_locked = False
        self._orbit_clock_event: object = None
        super().__init__(**kwargs)

    def on_kv_post(self, base_widget: Any) -> None:
        super().on_kv_post(base_widget)
        # لا نربط bind فوري — سنستخدم مؤقت بمعدل ثابت بدلاً من ذلك
        self._create_orbit_items()

    def _create_orbit_items(self) -> None:
        """إنشاء كبسولات الوسائط التي تدور حول الكون"""
        container = self.ids.get("orbit_container")
        if not container:
            return

        media_types = [
            ("account", "صوري", (0.50, 0.22, 0.85, 1)),
            ("account-group", "زملائي", (0.02, 0.55, 0.85, 1)),
            ("book-education-outline", "اختبارات", (0.90, 0.52, 0.05, 1)),
            ("emoticon-lol-outline", "مضحكات", (0.95, 0.35, 0.20, 1)),
            ("school", "محاضرات", (0.05, 0.65, 0.48, 1)),
            ("movie-play", "أفلام", (0.85, 0.15, 0.45, 1)),
            ("music-note", "أغاني", (0.02, 0.68, 0.95, 1)),
            ("folder-star-outline", "منوعات", (0.45, 0.30, 0.75, 1)),
        ]

        for icon_name, label_text, color in media_types:
            card = MDCard(
                size_hint=(None, None),
                size=(dp(58), dp(58)),
                radius=[dp(29), dp(29), dp(29), dp(29)],
                elevation=0,
                theme_bg_color="Custom",
                md_bg_color=(1.0, 1.0, 1.0, 0.95),
            )
            box = MDBoxLayout(
                orientation="vertical",
                spacing=dp(2),
                pos_hint={"center_x": 0.5, "center_y": 0.5},
            )
            icon = MDIcon(
                icon=icon_name,
                font_size="22sp",
                halign="center",
                theme_icon_color="Custom",
                icon_color=color,
            )
            lbl = MDLabel(
                text=ar(label_text),
                font_size="9sp",
                bold=True,
                halign="center",
                theme_text_color="Custom",
                text_color=color,
            )
            box.add_widget(icon)
            box.add_widget(lbl)
            card.add_widget(box)

            container.add_widget(card)
            self._orbit_widgets.append(card)

    def _update_orbit_positions(self, _dt: float = 0.0) -> None:
        """تحديث مواقع الوسائط في المدار — تُستدعى بمؤقت ثابت 30 مرة/ثانية بدلاً من bind فوري"""
        if self._completed or not self._orbit_widgets:
            return
        container = self.ids.get("orbit_container")
        if not container:
            return

        cx, cy = container.center_x, container.center_y
        r = self.orbit_radius
        base_deg = self.orbit_angle
        alpha = self.orbit_alpha
        count = len(self._orbit_widgets)

        for i, widget in enumerate(self._orbit_widgets):
            deg = base_deg + (i * 360.0 / count)
            rad = math.radians(deg)
            widget.center_x = cx + r * math.cos(rad)
            widget.center_y = cy + r * math.sin(rad)
            widget.opacity = alpha

    def _start_orbit_clock(self) -> None:
        """بدء مؤقت تحديث المدار بمعدل 30 إطار/ثانية — أخف بكثير من bind الفوري"""
        self._stop_orbit_clock()
        self._orbit_clock_event = Clock.schedule_interval(
            self._update_orbit_positions, 1.0 / 30.0
        )

    def _stop_orbit_clock(self) -> None:
        """إيقاف مؤقت تحديث المدار"""
        if self._orbit_clock_event is not None:
            try:
                if hasattr(self._orbit_clock_event, "cancel"):
                    self._orbit_clock_event.cancel()
                else:
                    Clock.unschedule(self._orbit_clock_event)
            except Exception:
                pass
            self._orbit_clock_event = None

    def on_enter(self, *args: Any) -> None:
        """بدء حركة الدوران الكوني بمجرد فتح الشاشة"""
        if hasattr(self.ids, "app_title"):
            self.ids.app_title.text = ar("رتّب | Rateb AI")
        if hasattr(self.ids, "app_tagline"):
            self.ids.app_tagline.text = ar(
                "دليلك الأذكى والأسرع لتنظيم وترتيب وسائطك وملفاتك تلقائياً"
            )

        # إعادة ضبط المتغيرات
        self.orbit_angle = 0.0
        self.orbit_radius = dp(130)
        self.orbit_alpha = 1.0
        self.center_pulse = 1.0
        self.text_alpha = 0.0
        self._completed = False
        self._touch_locked = False

        # بدء مؤقت تحديث المدار (30fps بدلاً من bind فوري)
        self._start_orbit_clock()

        Clock.schedule_once(self._start_orbit_sequence, 0.3)

    def on_leave(self, *args: Any) -> None:
        """إيقاف كل شيء عند مغادرة الشاشة — حماية من SIGSEGV"""
        self._cleanup_all()

    def _cleanup_all(self) -> None:
        """إيقاف كافة الحركات والمؤقتات وتنظيف المدار بالكامل"""
        self._completed = True
        # 1. إيقاف جميع حركات Kivy المرتبطة بهذه الشاشة
        Animation.stop_all(self)
        # 2. إيقاف مؤقت تحديث المدار
        self._stop_orbit_clock()
        # 3. إخفاء الودجتات المدارية فوراً (تحرير VBO)
        for widget in self._orbit_widgets:
            widget.opacity = 0

    def _start_orbit_sequence(self, _dt: float) -> None:
        """تنفيذ دورتين كاملتين (720 درجة) ثم تجميع الملفات في المركز"""
        if self._completed:
            return

        # 1. دوران دورتين كاملتين
        anim_orbit = Animation(
            orbit_angle=720.0,
            duration=3.0,
            t="in_out_quad",
        )

        def _on_orbit_complete(*_a: Any) -> None:
            if self._completed:
                return
            # 2. اجتماع الوسائط نحو المركز في نقطة واحدة
            anim_converge = Animation(
                orbit_radius=0.0,
                orbit_alpha=0.0,
                duration=0.8,
                t="in_cubic",
            )

            def _on_converge_complete(*_b: Any) -> None:
                if self._completed:
                    return
                # إيقاف مؤقت المدار — لم نعد بحاجته بعد التجمع
                self._stop_orbit_clock()

                # 3. نبضة المركز وظهور النص — بدون Ellipse ديناميكي
                anim_pulse = (
                    Animation(center_pulse=1.15, duration=0.2, t="out_quad")
                    + Animation(center_pulse=1.0, duration=0.3, t="in_out_sine")
                )
                anim_text = Animation(text_alpha=1.0, duration=0.7, t="out_quad")

                if not self._completed:
                    anim_pulse.start(self)
                    anim_text.start(self)

                # 4. الانتقال للشاشة الرئيسية بعد استعراض الشعار
                if not self._completed:
                    Clock.schedule_once(self.go_to_home, 1.8)

            anim_converge.bind(on_complete=_on_converge_complete)
            if not self._completed:
                anim_converge.start(self)

        anim_orbit.bind(on_complete=_on_orbit_complete)
        if not self._completed:
            anim_orbit.start(self)

    def go_to_home(self, *_args: Any) -> None:
        """الانتقال بسلاسة إلى الشاشة الرئيسية — مع إيقاف كافة الحركات أولاً"""
        if self._completed:
            return
        # ★ الإصلاح الأهم: إيقاف كل شيء قبل الانتقال لمنع SIGSEGV
        self._cleanup_all()

        try:
            import file_manager

            file_manager.save_sorter_preferences({"intro_seen": True})
        except (OSError, RuntimeError):
            pass

        # تأخير بسيط ليكتمل إيقاف الرسم قبل تبديل الشاشة
        Clock.schedule_once(lambda _dt: self._switch_to_home(), 0.1)

    def _switch_to_home(self) -> None:
        if self.manager and self.manager.has_screen("home_screen"):
            self.manager.current = "home_screen"

    def on_touch_down(self, touch: object) -> bool:
        """النقر في أي مكان لتخطي المقدمة فورياً — مع حماية من اللمس المتكرر"""
        if self._touch_locked or self._completed:
            return True
        self._touch_locked = True
        self.go_to_home()
        return True
