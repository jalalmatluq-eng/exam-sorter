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


def create_subject_list_item(name: str, count: int, on_release_callback):
    """إنشاء بطاقة مادة دراسية حديثة وفخمة متوافقة مع KivyMD 2"""
    item = MDListItem(
        MDListItemLeadingIcon(
            icon="folder-school",
            theme_icon_color="Custom",
            icon_color=(0.22, 0.26, 0.68, 1),
        ),
        MDListItemHeadlineText(
            text=ar(name),
            bold=True,
        ),
        MDListItemSupportingText(
            text=ar(f"{count} ورقة اختبار مسجلة"),
        ),
        MDListItemTrailingIcon(
            icon="chevron-left",
            theme_icon_color="Custom",
            icon_color=(0.35, 0.40, 0.55, 1),
        ),
        radius=[16, 16, 16, 16],
        theme_bg_color="Custom",
        md_bg_color=(1, 1, 1, 1),
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
