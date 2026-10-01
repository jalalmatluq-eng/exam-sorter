"""
وحدة مساعدة للواجهة (UI Helper)
توفر مكونات جاهزة وعصرية متوافقة تماماً مع إطار عمل KivyMD 2.0.
"""

from collections.abc import Callable
from typing import Any

try:
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
except Exception:
    Widget = object  # type: ignore
    MDButton = MDButtonIcon = MDButtonText = None  # type: ignore
    MDDialog = MDDialogButtonContainer = MDDialogHeadlineText = MDDialogSupportingText = None  # type: ignore
    MDListItem = MDListItemHeadlineText = MDListItemLeadingIcon = MDListItemSupportingText = MDListItemTrailingIcon = None  # type: ignore

from utils.arabic_helper import ar
from utils.category_helper import (
    ColorTuple,
    get_category_icon_and_unit,
    get_category_ui_details,
)


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
