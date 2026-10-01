"""
وحدة مساعدة للواجهة (UI Helper)
توفر مكونات جاهزة وعصرية متوافقة تماماً مع إطار عمل KivyMD 2.0.
"""

from collections.abc import Callable
from typing import Any

from kivy.uix.widget import Widget
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogHeadlineText,
    MDDialogSupportingText,
)
from kivymd.uix.list import (
    MDListItem,
    MDListItemHeadlineText,
    MDListItemLeadingIcon,
    MDListItemSupportingText,
    MDListItemTrailingIcon,
)

from utils.arabic_helper import ar

ColorTuple = tuple[float, float, float, float]


def get_category_ui_details(name: str) -> dict[str, Any]:
    """تحديد التفاصيل الشاملة للأيقونة واللون والوحدة ورسائل الحالة الفارغة لكل نوع مجلد بذكاء فائق"""
    clean = (name or "").strip().lower()

    # 1. صور شخصية وبصمة الوجه
    is_personal = (
        any(
            k in clean
            for k in (
                "صوري",
                "شخصي",
                "وجهي",
                "بصمة",
                "selfie",
                "portrait",
                "my_photos",
                "my photos",
            )
        )
        or clean == "me"
        or " me " in clean
        or clean.startswith("me ")
        or clean.endswith(" me")
    )
    if is_personal:
        return {
            "icon": "account-star-outline",
            "color": (0.78, 0.42, 0.98, 1),
            "unit": "صورة شخصية خاصة",
            "empty_icon": "account-search-outline",
            "empty_title": "لا توجد صور شخصية في هذا المجلد بعد",
            "empty_action_text": "إضافة صورة شخصية",
            "add_btn_text": "إضافة صورة",
            "stats_unit": "صورة شخصية",
        }

    # 2. صور الأصدقاء والعائلة
    elif any(
        k in clean
        for k in (
            "اصدقاء",
            "أصدقاء",
            "اخوتي",
            "إخوتي",
            "زملاء",
            "عائلة",
            "اهل",
            "أهل",
            "friends",
            "family",
        )
    ):
        return {
            "icon": "account-group-outline",
            "color": (0.22, 0.65, 0.98, 1),
            "unit": "صور الأصدقاء والزملاء",
            "empty_icon": "account-multiple-outline",
            "empty_title": "لا توجد صور للأصدقاء في هذا المجلد بعد",
            "empty_action_text": "إضافة صورة للأصدقاء",
            "add_btn_text": "إضافة صورة",
            "stats_unit": "صورة",
        }

    # 3. أفلام ومسلسلات
    elif any(
        k in clean
        for k in (
            "فيلم",
            "افلام",
            "أفلام",
            "مسلسل",
            "مسلسلات",
            "سينما",
            "movie",
            "movies",
            "series",
            "films",
            "cinema",
        )
    ):
        return {
            "icon": "movie-open-star-outline",
            "color": (0.96, 0.32, 0.42, 1),
            "unit": "فيلم ومسلسل",
            "empty_icon": "movie-off-outline",
            "empty_title": "لا توجد أفلام أو مسلسلات في هذا المجلد بعد",
            "empty_action_text": "إضافة فيلم أو مسلسل",
            "add_btn_text": "إضافة فيلم",
            "stats_unit": "فيلم ومسلسل",
        }

    # 4. مقاطع فيديو مضحكة وطرائف
    elif any(
        k in clean
        for k in (
            "مضحك",
            "طرائف",
            "فيديو مضحك",
            "كوميدي",
            "مقالب",
            "نكت",
            "ضحك",
            "funny",
            "comedy",
        )
    ):
        return {
            "icon": "emoticon-excited-outline",
            "color": (0.98, 0.72, 0.12, 1),
            "unit": "مقطع فيديو مضحك",
            "empty_icon": "emoticon-happy-outline",
            "empty_title": "لا توجد مقاطع مضحكة في هذا المجلد بعد",
            "empty_action_text": "إضافة فيديو مضحك",
            "add_btn_text": "إضافة مقطع",
            "stats_unit": "مقطع مضحك",
        }

    # 5. محاضرات ودروس تعليمية
    elif any(
        k in clean
        for k in (
            "محاضر",
            "دروس",
            "درس",
            "شروحات",
            "شرح",
            "تعلم",
            "تعليمي",
            "دورات",
            "دورة",
            "كورس",
            "lectures",
            "lessons",
            "courses",
            "tutorial",
        )
    ):
        return {
            "icon": "school-outline",
            "color": (0.06, 0.78, 0.90, 1),
            "unit": "محاضرة ودرس تعليمي",
            "empty_icon": "school-outline",
            "empty_title": "لا توجد محاضرات أو شروحات في هذا المجلد بعد",
            "empty_action_text": "إضافة محاضرة أو درس",
            "add_btn_text": "إضافة محاضرة",
            "stats_unit": "محاضرة",
        }

    # 6. صوتيات وأناشيد وأغاني
    elif any(
        k in clean
        for k in (
            "أغاني",
            "اغاني",
            "أناشيد",
            "اناشيد",
            "صوتيات",
            "صوت",
            "بودكاست",
            "music",
            "songs",
            "nasheed",
            "audio",
            "podcasts",
        )
    ):
        return {
            "icon": "music-circle-outline",
            "color": (0.12, 0.82, 0.55, 1),
            "unit": "مقطع صوتي ونشيد",
            "empty_icon": "music-off",
            "empty_title": "لا توجد مقاطع صوتية أو أناشيد في هذا المجلد بعد",
            "empty_action_text": "إضافة مقطع صوتي",
            "add_btn_text": "إضافة صوت",
            "stats_unit": "مقطع صوتي",
        }

    # 7. مستندات وكتب وأبحاث
    elif any(
        k in clean
        for k in (
            "مستند",
            "مستندات",
            "وثائق",
            "وثيقة",
            "كتب",
            "كتاب",
            "ابحاث",
            "أبحاث",
            "تقارير",
            "documents",
            "docs",
            "books",
            "pdf",
        )
    ):
        return {
            "icon": "file-document-outline",
            "color": (0.35, 0.55, 0.90, 1),
            "unit": "مستند ووثيقة",
            "empty_icon": "file-document-alert-outline",
            "empty_title": "لا توجد مستندات في هذا المجلد بعد",
            "empty_action_text": "إضافة مستند أو وثيقة",
            "add_btn_text": "إضافة مستند",
            "stats_unit": "مستند",
        }

    # 8. اختبارات ومواد دراسية صريحة فقط
    is_exam = (
        any(
            k in clean
            for k in (
                "اختبار",
                "امتحان",
                "مقرر",
                "واجب",
                "ملخص",
                "دراسة",
                "exam",
                "quiz",
                "homework",
                "رياضيات",
                "فيزياء",
                "كيمياء",
                "أحياء",
                "احياء",
                "علوم",
                "حاسب",
                "برمجة",
                "هندسة",
                "تاريخ",
                "جغرافيا",
                "إسلامية",
                "اسلامية",
                "فقه",
                "توحيد",
                "لغة عربية",
                "إنجليزي",
                "انجليزي",
                "english",
                "كلية الطب",
                "الطب",
            )
        )
        or any(
            w in clean.split()
            for w in ("test", "tests", "طب", "دين", "عربي")
        )
    )
    if is_exam:
        return {
            "icon": "book-education-outline",
            "color": (0.58, 0.40, 0.98, 1),
            "unit": "ورقة اختبار ومستند",
            "empty_icon": "file-document-check-outline",
            "empty_title": "لا توجد أوراق اختبار في هذه المادة بعد",
            "empty_action_text": "التقط ورقة اختبار لهذه المادة",
            "add_btn_text": "إضافة ورقة",
            "stats_unit": "ورقة اختبار",
        }

    # 9. خارج التصنيف
    elif any(
        k in clean
        for k in (
            "خارج التصنيف",
            "غير مصنف",
            "غير مصنفة",
            "unclassified",
            "other",
            "misc",
        )
    ):
        return {
            "icon": "folder-question-outline",
            "color": (0.60, 0.65, 0.75, 1),
            "unit": "ملف خارج التصنيف",
            "empty_icon": "folder-alert-outline",
            "empty_title": "لا توجد ملفات غير مصنفة هنا بعد",
            "empty_action_text": "إضافة ملف",
            "add_btn_text": "إضافة ملف",
            "stats_unit": "ملف",
        }

    # 10. أي مجلد عام أو ألبوم وسائط آخر (جديد، Download، Android، WhatsApp، Camera، إلخ)
    else:
        return {
            "icon": "folder-outline",
            "color": (0.12, 0.58, 0.85, 1),
            "unit": "ملف وسائط منظم",
            "empty_icon": "folder-open-outline",
            "empty_title": "لا توجد ملفات في هذا المجلد بعد",
            "empty_action_text": "إضافة ملف إلى هذا المجلد",
            "add_btn_text": "إضافة ملف",
            "stats_unit": "ملف",
        }


def get_category_icon_and_unit(
    name: str,
) -> tuple[str, ColorTuple, str]:
    """تحديد الأيقونة واللون ونوع المحتوى بذكاء وجمالية حديثة فائقة"""
    details = get_category_ui_details(name)
    return details["icon"], details["color"], details["unit"]


def create_subject_list_item(
    name: str,
    count: int,
    on_release_callback: Callable[[object], None] | None = None,
) -> MDListItem:
    """إنشاء بطاقة مادة/مجلد حديثة ومزخرفة بتنسيق الزجاج الليلي الفاخر"""
    icon, color, unit = get_category_icon_and_unit(name)
    if count == 1:
        sub_text = f"1 {unit}"
    elif count == 2:
        sub_text = f"2 {unit}"
    elif count > 2:
        sub_text = f"{count} {unit}"
    else:
        sub_text = f"0 {unit}"

    item = MDListItem(
        MDListItemLeadingIcon(
            icon=icon,
            theme_icon_color="Custom",
            icon_color=color,
        ),
        MDListItemHeadlineText(
            text=ar(name),
            bold=True,
            theme_text_color="Custom",
            text_color=(0.08, 0.16, 0.34, 1),
        ),
        MDListItemSupportingText(
            text=ar(sub_text),
            theme_text_color="Custom",
            text_color=(0.35, 0.45, 0.60, 1),
        ),
        MDListItemTrailingIcon(
            icon="chevron-left",
            theme_icon_color="Custom",
            icon_color=(0.50, 0.60, 0.75, 1),
        ),
        radius=[20, 20, 20, 20],
        theme_bg_color="Custom",
        md_bg_color=(1.0, 1.0, 1.0, 0.98),
        on_release=on_release_callback,
    )
    return item


def create_action_button(
    text: str,
    on_release_callback: Callable[[object], None] | None = None,
    style: str = "filled",
    icon: str | None = None,
) -> MDButton:
    """إنشاء زر متوافق مع المظهر الحديث"""
    btn_children: list[Widget] = []
    if icon:
        btn_children.append(MDButtonIcon(icon=icon))
    btn_children.append(MDButtonText(text=ar(text)))
    return MDButton(
        *btn_children, style=style, on_release=on_release_callback
    )


def show_app_dialog(
    title: str,
    text: str,
    on_confirm: Callable[[], None] | None = None,
    confirm_text: str = "حسناً",
) -> MDDialog:
    """عرض نافذة تنبيه أو نجاح عصرية متوافقة مع KivyMD 2 Dialogs"""
    dialog: MDDialog | None = None

    def handle_click(_x: object) -> None:
        if dialog:
            dialog.dismiss()
        if on_confirm:
            on_confirm()

    btn_confirm = MDButton(
        MDButtonText(
            text=ar(confirm_text),
            bold=True,
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
        ),
        style="filled",
        theme_bg_color="Custom",
        md_bg_color=(0.02, 0.52, 0.80, 1),
        on_release=handle_click,
    )

    dialog = MDDialog(
        MDDialogHeadlineText(
            text=ar(title),
            bold=True,
            theme_text_color="Custom",
            text_color=(0.08, 0.16, 0.34, 1),
        ),
        MDDialogSupportingText(
            text=ar(text),
            theme_text_color="Custom",
            text_color=(0.35, 0.45, 0.60, 1),
        ),
        MDDialogButtonContainer(
            btn_confirm,
            spacing="8dp",
        ),
        theme_bg_color="Custom",
        md_bg_color=(1.0, 1.0, 1.0, 0.98),
        radius=[24, 24, 24, 24],
    )
    dialog.open()
    return dialog


def show_confirm_dialog(
    title: str,
    text: str,
    on_confirm: Callable[[], None] | None = None,
    on_cancel: Callable[[], None] | None = None,
    confirm_text: str = "تأكيد",
    cancel_text: str = "إلغاء",
) -> MDDialog:
    """عرض نافذة تأكيد ثنائية الخيارات (تأكيد / إلغاء) متوافقة مع KivyMD 2"""
    dialog: MDDialog | None = None

    def handle_confirm(_x: object) -> None:
        if dialog:
            dialog.dismiss()
        if on_confirm:
            on_confirm()

    def handle_cancel(_x: object) -> None:
        if dialog:
            dialog.dismiss()
        if on_cancel:
            on_cancel()

    btn_cancel = MDButton(
        MDButtonText(
            text=ar(cancel_text),
            bold=True,
            theme_text_color="Custom",
            text_color=(0.35, 0.45, 0.60, 1),
        ),
        style="outlined",
        on_release=handle_cancel,
    )
    btn_confirm = MDButton(
        MDButtonText(
            text=ar(confirm_text),
            bold=True,
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
        ),
        style="filled",
        theme_bg_color="Custom",
        md_bg_color=(0.02, 0.52, 0.80, 1),
        on_release=handle_confirm,
    )

    dialog = MDDialog(
        MDDialogHeadlineText(
            text=ar(title),
            bold=True,
            theme_text_color="Custom",
            text_color=(0.08, 0.16, 0.34, 1),
        ),
        MDDialogSupportingText(
            text=ar(text),
            theme_text_color="Custom",
            text_color=(0.35, 0.45, 0.60, 1),
        ),
        MDDialogButtonContainer(
            btn_cancel,
            btn_confirm,
            spacing="10dp",
        ),
        theme_bg_color="Custom",
        md_bg_color=(1.0, 1.0, 1.0, 0.98),
        radius=[24, 24, 24, 24],
    )
    dialog.open()
    return dialog


def show_modern_notification(
    title: str,
    message: str,
    icon: str = "check-circle",
    notif_type: str = "success",
) -> None:
    """عرض إشعار جميل فاخر داخل التطبيق بنمط الكبسولة العصرية العائمة"""
    _ = icon
    from kivymd.uix.snackbar import (
        MDSnackbar,
        MDSnackbarCloseButton,
        MDSnackbarSupportingText,
        MDSnackbarText,
    )

    color_map = {
        "success": (0.05, 0.65, 0.40, 1),
        "info": (0.02, 0.52, 0.80, 1),
        "warning": (0.85, 0.55, 0.05, 1),
        "magic": (0.48, 0.22, 0.85, 1),
        "error": (0.85, 0.20, 0.30, 1),
    }
    accent = color_map.get(notif_type, (0.48, 0.22, 0.85, 1))

    try:
        snackbar = MDSnackbar(
            MDSnackbarText(
                text=ar(title),
                bold=True,
                theme_text_color="Custom",
                text_color=accent,
            ),
            MDSnackbarSupportingText(
                text=ar(message),
                theme_text_color="Custom",
                text_color=(0.25, 0.35, 0.50, 1),
            ),
            MDSnackbarCloseButton(
                icon="close-circle-outline",
                theme_icon_color="Custom",
                icon_color=(0.50, 0.60, 0.75, 1),
            ),
            y="28dp",
            pos_hint={"center_x": 0.5},
            size_hint_x=0.94,
            radius=[22, 22, 22, 22],
            theme_bg_color="Custom",
            md_bg_color=(1.0, 1.0, 1.0, 0.98),
            duration=3.8,
        )
        snackbar.open()
    except Exception:
        # إذا تعذر الـ Snackbar (مثل نقص دعم FBO في بعض المعالجات) نفتح Dialog لطيف
        _ = show_app_dialog(title=title, text=message)
