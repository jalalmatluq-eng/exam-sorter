"""
وحدة التصنيف بالذكاء الاصطناعي (AI Classifier) لتطبيق Exam Sorter.

الوظيفة:
قراءة صورة ورقة الاختبار الجامعي واستخراج اسم المادة الدراسية تلقائياً.

طرق العمل:
1. الطريقة الأساسية (الافتراضية والأدق):
   - استخدام Anthropic Claude Vision API عبر endpoint الرسائل.
   - قراءة المفتاح من ملف .env أو الإعدادات المحفوظة.
   - ضغط الصورة قبل الإرسال لتسريع الرفع وتوفير الباقة.
2. الطريقة البديلة (بدون إنترنت - Offline Mode):
   - استخدام OCR محلي عبر pytesseract لمطابقة الكلمات المفتاحية الشائعة.
"""

import base64
import importlib
from io import BytesIO
import json
import os
from pathlib import Path
from typing import Any, cast
import urllib.error
import urllib.request

from dotenv import load_dotenv
from PIL import Image

# تحميل المتغيرات من ملف .env إن وجد
_ = load_dotenv()

# =========================================================================
# أين تضع مفتاح API؟
# -------------------------------------------------------------------------
# الخيار 1 (الأفضل): أنشئ ملفاً باسم `.env` في المجلد الرئيسي للتطبيق واكتب:
#    ANTHROPIC_API_KEY=sk-ant-api03-...
#
# الخيار 2: أدخله عبر شاشة الإعدادات داخل التطبيق وسيحفظ تلقائياً.
#
# الخيار 3 (للتجربة السريعة فقط): يمكنك وضعه كقيمة افتراضية في المتغير أدناه:
DEFAULT_API_KEY = ""
# =========================================================================

# الرابط الخاص بـ Anthropic Messages API
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
# النموذج المقترح (سريع واقتصادي وممتاز في قراءة المستندات)
DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-haiku-20240307").strip()


class ClassificationError(Exception):
    """استثناء مخصص لأخطاء التصنيف (انقطاع الاتصال، مفتاح غير صالح، إلخ)"""


def get_api_key(custom_key: str | None = None) -> str:
    """
    استرجاع مفتاح الـ API بالترتيب التالي:
    1. المفتاح الممرر يدوياً من الشاشة/الإعدادات.
    2. متغير البيئة ANTHROPIC_API_KEY من ملف .env.
    3. القيمة الافتراضية DEFAULT_API_KEY.
    """
    if custom_key is not None and custom_key.strip():
        return custom_key.strip()

    env_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if env_key:
        return env_key

    # فحص مسار user_data_dir لتطبيقات الجوال
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app and hasattr(app, "user_data_dir"):
            user_env = Path(app.user_data_dir) / ".env"
            if user_env.exists():
                load_dotenv(user_env)
                k = os.getenv("ANTHROPIC_API_KEY", "").strip()
                if k:
                    return k
    except Exception:
        pass

    return DEFAULT_API_KEY.strip()


def encode_and_resize_image(image_path: str, max_dimension: int = 1500) -> tuple[str, str]:
    """
    تجهيز الصورة للإرسال:
    - تصغير الأبعاد القصوى للصورة لتفادي أحجام الملفات الضخمة للكاميرا وتسريع الإرسال.
    - ترميز الصورة بصيغة Base64 وتحديد Media Type.

    العائد: (base64_string, media_type)
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"لم يتم العثور على الصورة: {image_path}")

    ext = Path(image_path).suffix.lower()
    media_type = "image/jpeg"
    if ext == ".png":
        media_type = "image/png"
    elif ext == ".webp":
        media_type = "image/webp"

    with Image.open(image_path) as img:
        # تحويل صيغ RGBA إلى RGB إن كانت JPEG
        if img.mode in ("RGBA", "P") and media_type == "image/jpeg":
            img = img.convert("RGB")

        # تصغير الحجم إذا كانت الصورة أكبر من max_dimension
        width, height = img.size
        if max(width, height) > max_dimension:
            scale = max_dimension / max(width, height)
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        buffer = BytesIO()
        save_format = "PNG" if media_type == "image/png" else "JPEG"
        img.save(buffer, format=save_format, quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return encoded, media_type


def classify_with_claude(image_path: str, api_key: str | None = None) -> str:
    """
    إرسال الصورة إلى Anthropic Claude Vision API والتعرف على اسم المادة.
    """
    key = get_api_key(api_key)
    if not key:
        raise ClassificationError(
            "مفتاح Anthropic API غير متوفر! يرجى إضافته في ملف .env أو إدخال اسم المادة يدوياً."
        )

    try:
        base64_data, media_type = encode_and_resize_image(image_path)
    except FileNotFoundError as fnf:
        raise ClassificationError(f"لم يتم العثور على ملف الصورة: {image_path}") from fnf

    prompt_instruction = (
        "هذه صورة ورقة اختبار جامعي. اقرأ العنوان والترويسة وحدد اسم المادة الدراسية فقط. "
        "أجب باسم المادة فقط بدون أي نص إضافي أو علامات ترقيم، وبالعربية إن كانت مكتوبة بالعربية."
    )

    payload: dict[str, Any] = {
        "model": DEFAULT_MODEL,
        "max_tokens": 100,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt_instruction,
                    },
                ],
            }
        ],
    }

    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(ANTHROPIC_API_URL, data=req_data, headers=headers, method="POST")

        # مهلة 20 ثانية للاتصال بالشبكة
        with urllib.request.urlopen(req, timeout=20) as response:
            raw_response = response.read().decode("utf-8")
            result = cast(dict[str, Any], json.loads(raw_response))

            # استخراج النص الناتج من استجابة Claude
            content_blocks = cast(list[dict[str, Any]], result.get("content", []))
            for block in content_blocks:
                if block.get("type") == "text":
                    raw_text = str(block.get("text", "")).strip()
                    # تنظيف النص الناتج من علامات الاقتباس أو الكلمات الزائدة
                    cleaned = raw_text.replace('"', "").replace("'", "").strip()
                    if cleaned:
                        return cleaned

            raise ClassificationError("لم يتمكن النموذج من استنتاج اسم المادة من الورقة.")

    except urllib.error.HTTPError as e:
        error_msg = f"خطأ في خادم الذكاء الاصطناعي (رمز {e.code})"
        try:
            err_body = cast(dict[str, Any], json.loads(e.read().decode("utf-8")))
            error_data = cast(dict[str, Any], err_body.get("error", {}))
            detail = str(error_data.get("message", ""))
            if "invalid x-api-key" in detail.lower() or "authentication" in detail.lower():
                error_msg = "مفتاح API غير صالح أو منتهي الصلاحية."
            elif detail:
                error_msg = f"خطأ API: {detail}"
        except (KeyError, ValueError, json.JSONDecodeError):
            pass
        raise ClassificationError(error_msg)

    except urllib.error.URLError:
        raise ClassificationError("تعذر الاتصال بالإنترنت. يرجى التحقق من اتصال الشبكة.")

    except TimeoutError:
        raise ClassificationError("استغرق الطلب وقتاً طويلاً (انتهت مهلة الاتصال).")

    except Exception as ex:
        if isinstance(ex, ClassificationError):
            raise
        raise ClassificationError(f"حدث خطأ غير متوقع أثناء التصنيف: {ex!s}")


# =========================================================================
# الخيار الثاني: OCR محلي بديل (Offline Mode) يعمل بدون إنترنت
# =========================================================================
COMMON_SUBJECT_KEYWORDS = [
    "رياضيات", "حساب التفاضل والتكامل", "جبر خطي", "إحصاء", "احتمالات",
    "فيزياء", "كيمياء", "أحياء", "لغة عربية", "لغة إنجليزية", "English",
    "برمجة", "حاسوب", "ذكاء اصطناعي", "شبكات", "قواعد بيانات",
    "هندسة برمجيات", "نظم تشغيل", "خوارزميات", "تراكيب بيانات",
    "محاسبة", "إدارة أعمال", "اقتصاد", "تمويل", "تسويق",
    "قانون", "تاريخ", "جغرافيا", "فلسفة", "طب", "صيدلة", "تمريض",
]


def classify_with_local_ocr(image_path: str) -> str:
    """
    استخراج النص باستخدام مكتبة pytesseract محلياً، ومطابقة الكلمات المفتاحية للمواد.
    تُستخدم هذه الدالة كبديل عند عدم توفر إنترنت أو إذا اختار المستخدم وضع الأوفلاين.
    """
    try:
        pytesseract = importlib.import_module("pytesseract")
    except ModuleNotFoundError:
        raise ClassificationError("مكتبة pytesseract غير مثبتة في النظام.")

    try:
        with Image.open(image_path) as img:
            # قص الثلث العلوي من الصورة (حيث توجد الترويسة واسم المادة عادة)
            width, height = img.size
            header_crop = img.crop((0, 0, width, int(height * 0.35)))

            # استخراج النص باللغتين العربية والإنجليزية
            extracted_text: str = pytesseract.image_to_string(header_crop, lang="ara+eng")

            # مطابقة النص مع الكلمات المفتاحية للمواد
            for kw in COMMON_SUBJECT_KEYWORDS:
                if kw.lower() in extracted_text.lower():
                    return kw

            # إذا لم يُعثر على كلمة معروفة، نأخذ أول سطر غير فارغ
            lines = [line.strip() for line in extracted_text.splitlines() if len(line.strip()) > 3]
            if lines:
                return lines[0][:30]

    except ClassificationError:
        raise
    except Exception as e:
        raise ClassificationError(f"فشل الـ OCR المحلي: {e!s}")

    raise ClassificationError("لم يتم العثور على اسم مادة معروف بواسطة الـ OCR المحلي.")


def classify_exam_image(
    image_path: str,
    api_key: str | None = None,
    fallback_to_ocr: bool = False,
) -> str:
    """
    الدالة الرئيسية للتصنيف:
    1. تحاول أولاً استخدام Claude Vision API (الخيار الأذكى والأدق).
    2. إذا فشل وكان خيار fallback_to_ocr مفعلاً، تحاول استخدام OCR المحلي.
    3. إذا فشلت كافة الطرق، ترفع ClassificationError لطلب الإدخال اليدوي.
    """
    try:
        return classify_with_claude(image_path, api_key=api_key)
    except ClassificationError:
        if fallback_to_ocr:
            try:
                return classify_with_local_ocr(image_path)
            except ClassificationError:
                pass
        # رفع الخطأ للواجهة ليتمكن المستخدم من الإدخال اليدوي
        raise
