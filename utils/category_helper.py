"""
وحدة تصنيف مجلدات وأقسام الوسائط (Category Helper)
توفر تصنيفاً دقيقاً لكل مجلد (صور شخصية، أفلام، مقاطع مضحكة، محاضرات، مستندات، اختبارات، مجلدات عامة)
مع الأيقونة واللون والوحدة ورسائل الحالة الفارغة وأزرار الإضافة المناسبة.
وحدة نقية (Pure Python) بدون أي تبعيات لواجهات العرض، آمنة 100% لبيئات الفحص الآلي والخلفية.
"""

from typing import Any

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
