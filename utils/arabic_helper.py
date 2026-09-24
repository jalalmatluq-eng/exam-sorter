# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAny=false
"""
وحدة مساعدة لمعالجة النصوص العربية وتشكيلها لتعمل بسلاسة داخل Kivy / KivyMD.
تقوم بإعادة تشكيل الحروف العربية (Arabic Reshaping) وعكس الاتجاه (BiDi)
لتظهر الكلمات العربية متصلة ومن اليمين إلى اليسار بدون تقطيع.
"""

from pathlib import Path

# استيراد مكتبات التشكيل وإعادة الترتيب
try:
    import arabic_reshaper  # type: ignore
    from bidi.algorithm import get_display  # type: ignore

    has_arabic_support: bool = True
except ImportError:
    arabic_reshaper = None  # type: ignore
    get_display = None  # type: ignore
    has_arabic_support = False


def ar(text: str) -> str:
    """
    تحويل النص العربي ليظهر بصورة صحيحة ومتصلة في Kivy.

    المعاملات:
        text: النص العربي أو المختلط.

    العائد:
        النص بعد إعادة التشكيل والعكس.
    """
    if not text:
        return ""

    # إذا كان النص لا يحتوي على أي حرف عربي، نعيده كما هو
    has_arabic: bool = any(
        "\u0600" <= char <= "\u06FF" or "\u0750" <= char <= "\u077F"
        for char in text
    )
    if not has_arabic:
        return text

    if has_arabic_support and arabic_reshaper is not None and get_display is not None:
        try:
            # تكوين معالج النصوص ليدعم الأرقام والتشكيل
            configuration: dict[str, bool] = {
                "delete_harakat": False,
                "support_ligatures": True,
                "shift_harakat_position": False,
            }
            reshaper = arabic_reshaper.ArabicReshaper(configuration=configuration)
            reshaped_text: str = str(reshaper.reshape(text))
            display_result = get_display(reshaped_text)
            if isinstance(display_result, bytes):
                return display_result.decode("utf-8", errors="replace")
            return str(display_result)
        except (ValueError, TypeError, AttributeError):
            return text
    return text


def get_arabic_font_path() -> str:
    """
    استرجاع مسار الخط العربي المتوفر في مجلد assets/fonts/ لربطه بـ Kivy.
    """
    base_dir: Path = Path(__file__).resolve().parent.parent
    font_path: Path = base_dir / "assets" / "fonts" / "Amiri-Regular.ttf"
    if font_path.exists():
        return str(font_path)

    return ""
