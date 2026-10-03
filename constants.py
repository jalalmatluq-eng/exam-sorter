"""
الثوابت الموحدة لتطبيق رتّب (Rateb AI):
- أسماء تصنيفات المجلدات المعتمدة لجميع أجزاء التطبيق.
- امتدادات الصور والفيديوهات.
- خريطة أنواع MIME.
- خريطة توحيد أسماء التصنيفات القديمة.

ملاحظة: هذا هو المصدر الوحيد للحقيقة (Single Source of Truth) لجميع الثوابت.
كافة الوحدات الأخرى يجب أن تستورد من هنا بدلاً من تعريف ثوابت مكررة.
"""

from __future__ import annotations

# ─── إصدار التطبيق ────────────────────────────────────────────────────────────
APP_VERSION = "2.0.1"
APP_TITLE = "Rateb - رتّب | المُنظّم الذكي"

# ─── اسم مجلد التخزين الرئيسي ─────────────────────────────────────────────────
ORGANIZED_FOLDER_NAME = "الملفات المنظمة"

# ─── أسماء التصنيفات المعتمدة والموحدة ─────────────────────────────────────────
CATEGORY_MY_PHOTOS = "صوري"
CATEGORY_FRIENDS_PHOTOS = "صور اخوتي وزملائي"
CATEGORY_EXAMS_ROOT = "صور الاختبارات"
CATEGORY_EXAMS_GENERAL = "صور الاختبارات/اختبارات عامة"
CATEGORY_LECTURES = "محاضرات ودروس"
CATEGORY_FUNNY_VIDEOS = "فيديوهات مضحكة"
CATEGORY_MOVIES = "أفلام ومسلسلات"
CATEGORY_SONGS = "أغاني وأناشيد"
CATEGORY_UNCLASSIFIED = "خارج التصنيف"
CATEGORY_PERSONAL = "فيديوهات شخصية"
CATEGORY_NEEDS_REVIEW = "يحتاج مراجعة"

# قائمة الأصناف القياسية المعتمدة
STANDARD_CATEGORIES: list[str] = [
    CATEGORY_MY_PHOTOS,
    CATEGORY_FRIENDS_PHOTOS,
    CATEGORY_MOVIES,
    CATEGORY_LECTURES,
    CATEGORY_SONGS,
    CATEGORY_FUNNY_VIDEOS,
    CATEGORY_EXAMS_ROOT,
    CATEGORY_UNCLASSIFIED,
]

# ─── خريطة توحيد الأسماء القديمة والمتباينة ────────────────────────────────────
LEGACY_CATEGORY_MAPPINGS: dict[str, str] = {
    "محاضرات وتعلم": CATEGORY_LECTURES,
    "محاضرات_وتعلم": CATEGORY_LECTURES,
    "محاضرات": CATEGORY_LECTURES,
    "دروس": CATEGORY_LECTURES,
    "صور_الاختبارات": CATEGORY_EXAMS_ROOT,
    "صور اختبارات": CATEGORY_EXAMS_ROOT,
    "صور_اخوتي_وزملائي": CATEGORY_FRIENDS_PHOTOS,
    "صور_الزملاء_والإخوة": CATEGORY_FRIENDS_PHOTOS,
    "فيديوهات_مضحكة": CATEGORY_FUNNY_VIDEOS,
    "افلام ومسلسلات": CATEGORY_MOVIES,
    "أفلام_ومسلسلات": CATEGORY_MOVIES,
    "اغاني واناشيد": CATEGORY_SONGS,
    "أغاني_وأناشيد": CATEGORY_SONGS,
}

# ─── امتدادات الملفات المدعومة ──────────────────────────────────────────────────
IMAGE_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".gif", ".bmp", ".heic", ".heif",
}

VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".3gp", ".mov",
    ".avi", ".webm", ".m4v", ".flv",
}

# ─── خريطة أنواع MIME ───────────────────────────────────────────────────────────
MIME_TYPE_MAP: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "video/x-matroska": ".mkv",
    "video/3gpp": ".3gp",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/webm": ".webm",
    "video/x-m4v": ".m4v",
    "video/x-flv": ".flv",
}

# ─── مهلة اتصال API ─────────────────────────────────────────────────────────────
API_TIMEOUT_SECONDS = 12.0
