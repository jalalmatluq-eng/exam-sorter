"""
وحدة مساعدة للواجهة (UI Helper)
توفر مكونات جاهزة وعصرية متوافقة تماماً مع إطار عمل KivyMD 2.0 (Material Design 3).
"""

from utils.arabic_helper import ar
from kivymd.uix.list import (
    MDListItem,
    MDListItemHeadlineText,
    MDListItemLeadingIcon,
    MDListItemSupportingText,
    MDListItemTrailingIcon,
)
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogHeadlineText,
    MDDialogSupportingText,
)


def get_category_icon_and_unit(name: str) -> tuple[str, tuple[float, float, float, float], str]:
    """تحديد الأيقونة واللون ونوع المحتوى بذكاء بناءً على اسم المجلد"""
    clean = name.strip()
    if "فيديو" in clean or "مضحك" in clean:
        return "emoticon-happy-outline", (0.82, 0.48, 0.22, 1), "مقطع فيديو مضحك"
    elif "محاضر" in clean or "تعلم" in clean:
        return "school-outline", (0.72, 0.44, 0.26, 1), "محاضرة تعليمية"
    elif "فيلم" in clean or "مسلسل" in clean or "افلام" in clean:
        return "movie-open-outline", (0.78, 0.40, 0.25, 1), "فيلم / مسلسل"
    elif "أغاني" in clean or "اغاني" in clean or "اناشيد" in clean:
        return "music-note-outline", (0.75, 0.48, 0.30, 1), "مقطع صوتي / أغنية"
    elif "صوري" in clean:
        return "account-heart-outline", (0.80, 0.42, 0.26, 1), "صورة شخصية"
    elif "اصدقاء" in clean or "أصدقاء" in clean:
        return "account-multiple-outline", (0.70, 0.45, 0.32, 1), "صورة للأصدقاء والإخوة"
    elif "اختبار" in clean:
        return "file-document-outline", (0.74, 0.42, 0.24, 1), "ورقة اختبار ومستند"
    else:
        # مادة دراسية جامعية (رياضيات، فيزياء، برمجة، إلخ)
        return "book-open-page-variant-outline", (0.72, 0.44, 0.26, 1), "ورقة اختبار مسجلة"


def create_subject_list_item(name: str, count: int, on_release_callback):
    """إنشاء بطاقة مادة/مجلد حديثة وفخمة بتنسيق البيج الدافئ"""
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
            text_color=(0.20, 0.16, 0.14, 1),
        ),
        MDListItemSupportingText(
            text=ar(sub_text),
            theme_text_color="Custom",
            text_color=(0.52, 0.45, 0.39, 1),
        ),
        MDListItemTrailingIcon(
            icon="chevron-left",
            theme_icon_color="Custom",
            icon_color=(0.70, 0.62, 0.54, 1),
        ),
        radius=[18, 18, 18, 18],
        theme_bg_color="Custom",
        md_bg_color=(1, 0.992, 0.980, 1),
        on_release=on_release_callback,
    )
    return item


def create_action_button(text: str, on_release_callback, style: str = "filled", icon: str | None = None):
    """إنشاء زر متوافق مع المظهر الحديث"""
    btn_children = []
    if icon:
        btn_children.append(MDButtonIcon(icon=icon))
    btn_children.append(MDButtonText(text=ar(text)))
    return MDButton(*btn_children, style=style, on_release=on_release_callback)


def show_app_dialog(title: str, text: str, on_confirm=None, confirm_text: str = "حسناً"):
    """عرض نافذة تنبيه أو نجاح متوافقة عبر KivyMD 2 Dialogs"""
    dialog = None

    def handle_click(x):
        if dialog:
            dialog.dismiss()
        if on_confirm:
            on_confirm()

    dialog = MDDialog(
        MDDialogHeadlineText(text=ar(title)),
        MDDialogSupportingText(text=ar(text)),
        MDDialogButtonContainer(
            MDButton(
                MDButtonText(text=ar(confirm_text)),
                style="filled",
                on_release=handle_click,
            ),
            spacing="8dp",
        ),
    )
    dialog.open()
    return dialog
