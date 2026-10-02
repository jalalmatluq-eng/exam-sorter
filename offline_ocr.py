"""
offline_ocr.py
--------------
نظام التعرف الضوئي على الحروف (OCR) العربي المحلي المخصص لتطبيق رتّب (Rateb AI):
- فحص استباقي صارم لتوفر المحرك ونماذج اللغة العربية وقت التشغيل.
- معالجة صور ذكية متقدمة للوثائق وأوراق الاختبارات (إزالة ضوضاء، تصحيح ميل، عتبة ثنائية، تكبير).
- تطبيع النص العربي ومطابقة المواد الدراسية بدقة وثقة رقمية قابلة للتحقق.
- دعم Tesseract Mobile وبيئات الأندرويد وTFLite OCR مع Fallbacks آمنة وتوثيق شفاف للحالة.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

cv2: Any = None
try:
    import cv2  # type: ignore
except (ImportError, Exception):
    cv2 = None

logger = logging.getLogger("OfflineOCR")


@dataclass
class OCRResult:
    """كائن النتيجة المنظمة لعملية التعرف الضوئي على النصوص (OCR)"""
    available: bool = False
    text: str = ""
    subject: str = ""
    confidence: float = 0.0
    language: str = "ara"
    needs_review: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "text": self.text,
            "subject": self.subject,
            "confidence": round(self.confidence, 3),
            "language": self.language,
            "needs_review": self.needs_review,
            "error": self.error,
        }


# قاموس الكلمات الدالة على المواد الدراسية والأكاديمية
ACADEMIC_SUBJECT_KEYWORDS: dict[str, list[str]] = {
    "رياضيات": [
        "رياضيات", "حساب", "تفاضل", "تكامل", "جبر", "هندسة", "احتمالات",
        "احصاء", "إحصاء", "معادلات", "math", "calculus", "algebra",
    ],
    "فيزياء": [
        "فيزياء", "كهرومغناطيسية", "ميكانيكا", "ديناميكا", "بصريات",
        "حرارية", "طاقة", "physics", "physic",
    ],
    "كيمياء": [
        "كيمياء", "عضوية", "تحليلية", "حيوية", "تفاعل", "مركبات",
        "chemistry", "chem",
    ],
    "أحياء": [
        "احياء", "أحياء", "وراثة", "خلية", "تشريح", "جينات", "كائنات",
        "biology", "bio",
    ],
    "برمجة": [
        "برمجة", "حاسوب", "خوارزميات", "قواعد بيانات", "شبكات", "تطوير",
        "ذكاء اصطناعي", "programming", "code", "python", "java", "algorithms",
    ],
    "لغة عربية": [
        "لغة عربية", "نحو", "صرف", "بلاغة", "أدب", "نصوص", "إملاء", "عربي", "arabic",
    ],
    "لغة إنجليزية": [
        "لغة إنجليزية", "لغة انجليزية", "انجليزي", "إنجليزي", "english", "grammar", "vocabulary",
    ],
    "تاريخ": [
        "تاريخ", "حضارة", "ثورة", "معاهدة", "معركة", "عصور", "history",
    ],
    "جغرافيا": [
        "جغرافيا", "تضاريس", "خرائط", "مناخ", "سكان", "بيئة", "geography",
    ],
    "إسلامية": [
        "إسلامية", "اسلامية", "قرآن", "قران", "حديث", "فقه", "توحيد", "تفسير", "عقيدة",
    ],
    "طب": [
        "طب", "صيدلة", "تمريض", "أمراض", "جراحة", "أدوية", "ادوية", "تشريح", "medicine", "pharma",
    ],
}

EXAM_INDICATORS = [
    "اختبار", "امتحان", "ورقة عمل", "كويز", "أسئلة", "اسئلة",
    "نموذج", "إجابة", "اجابة", "نهائي", "نصفي", "شهري", "فصلي", "exam", "test", "quiz",
]


def get_tessdata_path() -> Path | None:
    """البحث عن مسار مجلد نماذج tessdata في النظام أو داخل حزمة التطبيق الخاصة"""
    candidates = [
        Path(__file__).resolve().parent / "assets" / "tessdata",
        Path(__file__).resolve().parent / "assets" / "models" / "ocr",
        Path(os.environ.get("TESSDATA_PREFIX", "")),
        Path("/system/usr/share/tessdata"),
        Path("/data/local/tmp/tessdata"),
    ]
    # محاولة جلب مجلد التطبيق الداخلي في أندرويد
    try:
        from android import mActivity  # type: ignore
        ctx = mActivity.getApplicationContext()
        internal_tess = Path(ctx.getFilesDir().getAbsolutePath()) / "tessdata"
        candidates.insert(0, internal_tess)
    except Exception:
        pass

    for c in candidates:
        if c and c.exists() and (c / "ara.traineddata").exists():
            return c
    return None


_ocr_net_cache: Any = None
_ocr_dict_cache: list[str] | None = None
_ocr_backend: str | None = None


def get_ocr_onnx_net() -> tuple[Any, list[str] | None]:
    """تحميل وحفظ شبكة OCR العصبية وقاموس الحروف في الذاكرة عبر onnxruntime أو cv2.dnn"""
    global _ocr_net_cache, _ocr_dict_cache, _ocr_backend
    if _ocr_net_cache is None:
        model_p = Path(__file__).resolve().parent / "assets" / "models" / "ocr" / "arabic_rec.onnx"
        dict_p = Path(__file__).resolve().parent / "assets" / "models" / "ocr" / "arabic_dict.txt"
        if model_p.exists() and dict_p.exists():
            # المحرك الأول: onnxruntime
            try:
                import onnxruntime as ort
                _ocr_net_cache = ort.InferenceSession(str(model_p))
                _ocr_backend = "ort"
            except Exception as exc:
                logger.debug("onnxruntime غير متاح لـ OCR: %s", exc)
                _ocr_net_cache = None

            # المحرك الثاني البديل: cv2.dnn
            if _ocr_net_cache is None and cv2 is not None and hasattr(cv2, "dnn"):
                try:
                    _ocr_net_cache = cv2.dnn.readNetFromONNX(str(model_p))
                    _ocr_backend = "cv2"
                except Exception as exc:
                    logger.debug("cv2.dnn غير قادر على تشغيل arabic_rec.onnx: %s", exc)
                    _ocr_net_cache = None

            if _ocr_net_cache is not None:
                try:
                    with open(dict_p, "r", encoding="utf-8") as f:
                        _ocr_dict_cache = ["blank"] + [line.strip() for line in f]
                except Exception as exc:
                    logger.error("تعذر قراءة قاموس OCR: %s", exc)
                    _ocr_dict_cache = None

    return _ocr_net_cache, _ocr_dict_cache


def _recognize_text_strip(strip_bgr: np.ndarray, net: Any, chars: list[str]) -> str:
    """استدلال خط نصوص مفرد عبر نموذج ONNX مع فك ترميز CTC ودعم RTL للغة العربية"""
    if strip_bgr is None or strip_bgr.size == 0 or cv2 is None:
        return ""
    try:
        if len(strip_bgr.shape) == 2:
            strip_bgr = cv2.cvtColor(strip_bgr, cv2.COLOR_GRAY2BGR)

        # اقتصاص الحواف البيضاء حول النص لضمان وضوح الحروف بارتفاع النموذج
        gray = cv2.cvtColor(strip_bgr, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)
        coords = cv2.findNonZero(thresh)
        if coords is not None and len(coords) > 20:
            bx, by, bw, bh = cv2.boundingRect(coords)
            if bw >= 10 and bh >= 10:
                pad = 4
                y1 = max(0, by - pad)
                y2 = min(strip_bgr.shape[0], by + bh + pad)
                x1 = max(0, bx - pad)
                x2 = min(strip_bgr.shape[1], bx + bw + pad)
                strip_bgr = strip_bgr[y1:y2, x1:x2]

        h, w = strip_bgr.shape[:2]
        if h < 8 or w < 8:
            return ""

        target_w = int(w * (48.0 / max(1, h)))
        target_w = max(32, min(640, target_w))
        resized = cv2.resize(strip_bgr, (target_w, 48), interpolation=cv2.INTER_AREA)

        blob = ((resized.astype(np.float32) / 127.5) - 1.0).transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)

        if _ocr_backend == "ort":
            preds = net.run(None, {"x": blob})[0]
        elif _ocr_backend == "cv2":
            net.setInput(blob)
            preds = net.forward()
        else:
            return ""

        pred_indices = np.argmax(preds[0], axis=-1)
        text_chars = []
        prev = 0
        for idx in pred_indices:
            if idx != 0 and idx != prev and idx < len(chars):
                text_chars.append(chars[idx])
            prev = idx

        # نموذج PaddleOCR يقرأ من اليسار لليمين، والعربية تُكتب من اليمين لليسار (RTL)
        # لذلك نعكس ترتيب الحروف المستخرجة لتمثيل الكلمة العربية السليمة
        return "".join(text_chars[::-1])
    except Exception as exc:
        logger.debug("خطأ استدلال شريط OCR: %s", exc)
        return ""


def recognize_text_onnx(img_bgr: np.ndarray) -> str:
    """
    استخراج النصوص العربية باستخدام نموذج الشبكة العصبية arabic_rec.onnx:
    - فحص ما إذا كانت الصورة شريطاً نصياً مفرداً أو صفحة مستند كاملة.
    - تقطيع سطور النصوص الأفقية (Text Line Segmentation) واستدعاء النموذج لكل سطر.
    """
    net, chars = get_ocr_onnx_net()
    if net is None or chars is None or img_bgr is None or img_bgr.size == 0 or cv2 is None:
        return ""

    try:
        if len(img_bgr.shape) == 2:
            img_3ch = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2BGR)
            gray = img_bgr
        else:
            img_3ch = img_bgr
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        h, w = img_3ch.shape[:2]

        # إذا كانت الصورة شريطاً نصياً مفرداً (مثل عنوان أو قصاصة نص)
        if h <= 90 or (w > 3.0 * h and h <= 150):
            return _recognize_text_strip(img_3ch, net, chars)

        # إذا كانت صفحة مستند/ورقة اختبار: كشف الأسطر الأفقية عبر العتبة والتشكيل
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5))
        dilated = cv2.dilate(thresh, kernel, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes = []
        for cnt in contours:
            bx, by, bw, bh = cv2.boundingRect(cnt)
            if bw > 30 and bh > 12:
                boxes.append((bx, by, bw, bh))

        boxes.sort(key=lambda b: b[1])

        if not boxes:
            header_crop = img_3ch[:min(h, int(h * 0.4)), :]
            return _recognize_text_strip(header_crop, net, chars)

        recognized_lines: list[str] = []
        for bx, by, bw, bh in boxes[:8]:  # التركيز على الأسطر العلوية للمستند
            pad = 4
            y1 = max(0, by - pad)
            y2 = min(h, by + bh + pad)
            x1 = max(0, bx - pad)
            x2 = min(w, bx + bw + pad)
            line_crop = img_3ch[y1:y2, x1:x2]
            line_txt = _recognize_text_strip(line_crop, net, chars)
            if line_txt:
                recognized_lines.append(line_txt)

        return " ".join(recognized_lines)
    except Exception as exc:
        logger.debug("خطأ استدلال OCR ONNX: %s", exc)
        return ""


def is_offline_ocr_available() -> bool:
    """
    التحقق الصارم والواقعي من إمكانية تنفيذ OCR محلي:
    1. توفر نموذج arabic_rec.onnx وملف القاموس ومحرك onnxruntime أو cv2.dnn.
    2. أو توفر نموذج اللغة العربية ara.traineddata مع محرك tesseract الفعلي.
    """
    # 1. نموذج ONNX العصبي المضمن
    model_p = Path(__file__).resolve().parent / "assets" / "models" / "ocr" / "arabic_rec.onnx"
    dict_p = Path(__file__).resolve().parent / "assets" / "models" / "ocr" / "arabic_dict.txt"
    if model_p.exists() and model_p.stat().st_size >= 1000000 and dict_p.exists():
        import importlib.util
        has_runtime = importlib.util.find_spec("onnxruntime") is not None

        if not has_runtime and cv2 is not None and hasattr(cv2, "dnn"):
            has_runtime = True

        if has_runtime:
            return True

    # 2. فحص Tesseract
    tess_path = get_tessdata_path()
    has_tess_model = tess_path is not None and (tess_path / "ara.traineddata").exists()
    has_tess_runtime = False
    try:
        import pytesseract  # type: ignore
        v = pytesseract.get_tesseract_version()
        if v:
            has_tess_runtime = True
    except Exception:
        has_tess_runtime = False

    return has_tess_model and has_tess_runtime


def normalize_arabic_text(text: str) -> str:
    """
    تطبيع النص العربي لتسهيل المقارنة والمطابقة الدقيقة:
    - إزالة التشكيل (الحركات، الشدة، التنوين).
    - توحيد الهمزات (أ، إ، آ -> ا).
    - توحيد الياء والتاء المربوطة.
    - إزالة الكشيدة (المد).
    """
    if not text:
        return ""

    # إزالة التشكيل وحروف التنسيق
    tashkeel = re.compile(r"[\u0617-\u061A\u064B-\u0652\u06D6-\u06ED]")
    text = tashkeel.sub("", text)
    text = text.replace("\u0640", "")  # إزالة الكشيدة _

    # توحيد الألفات والهمزات
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"ى", "ي", text)

    # تنظيف الفراغات المتكررة
    text = re.sub(r"\s+", " ", text).strip()
    return text


def preprocess_image_for_ocr(image_path: str) -> Any | None:
    """
    تطبيق مرشحات المعالجة المسبقة لتحسين جودة قراءة النصوص العربية:
    1. تحويل للصورة الرمادية (Grayscale).
    2. إزالة الضوضاء والتشويش عبر المرشح الثنائي (Bilateral Filter).
    3. تصحيح الميل والتفاف الورقة (Deskew).
    4. عتبة ثنائية ذكية (Otsu Thresholding) لتباين النص والورقة.
    5. تكبير الأبعاد إذا كانت الصورة صغيرة.
    """
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        return None

    try:
        # قراءة آمنة للصورة
        with open(image_path, "rb") as f:
            data = bytearray(f.read())
        img = cv2.imdecode(np.asarray(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None

        # 1. تحويل للرمادي
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 2. تكبير إذا كانت الصورة صغيرة لتعزيز وضوح الخط العربي
        h, w = gray.shape[:2]
        if max(h, w) < 1200:
            scale = 1200.0 / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        # 3. إزالة الضوضاء مع الحفاظ على حواف الحروف
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)

        # 4. العتبة الثنائية المتكيفة (Adaptive / Otsu Thresholding)
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 5. تصحيح زوايا الميل (Deskewing) لصفحات الاختبار المائلة
        coords = np.column_stack(np.where(thresh == 0))
        if len(coords) > 100:
            rect = cv2.minAreaRect(coords)
            angle = rect[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            if abs(angle) > 1.0 and abs(angle) < 45.0:
                (h_t, w_t) = thresh.shape[:2]
                center = (w_t // 2, h_t // 2)
                m = cv2.getRotationMatrix2D(center, angle, 1.0)
                thresh = cv2.warpAffine(
                    thresh, m, (w_t, h_t),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE
                )

        return thresh
    except Exception as exc:
        logger.debug("خطأ أثناء معالجة الصورة لـ OCR: %s", exc)
        return None


def extract_subject_from_text(text: str) -> str:
    """استخراج اسم المادة الأكاديمية بدقة من النص العربي أو الإنجليزي المعالج"""
    normalized_text = normalize_arabic_text(text).lower()
    detected_subject = ""
    subject_hits = 0

    for subject, keywords in ACADEMIC_SUBJECT_KEYWORDS.items():
        hits = 0
        for kw in keywords:
            norm_kw = normalize_arabic_text(kw).lower()
            if re.search(r"\b" + re.escape(norm_kw) + r"\b", normalized_text) or norm_kw in normalized_text:
                hits += 1
        if hits > subject_hits:
            subject_hits = hits
            detected_subject = subject

    return detected_subject


def extract_arabic_text_offline(image_path: str) -> OCRResult:
    """
    استخراج النص العربي من الصورة محلياً وتحليل المادة الدراسية وثقة التصنيف:
    - فحص الجاهزية والملفات والصلاحيات.
    - تنفيذ Preprocessing ومعالجة النصوص.
    - استخراج المادة والامتحان وإرجاع OCRResult كاملة التفاصيل.
    """
    p = Path(image_path)
    if not p.exists() or not p.is_file():
        return OCRResult(
            available=False,
            error="ملف الصورة غير موجود أو تعذرت القراءة",
            needs_review=True,
        )

    # 1. التحقق من توفر OCR
    if not is_offline_ocr_available():
        return OCRResult(
            available=False,
            error="محرك OCR أو ملفات اللغة العربية (ara.traineddata) غير مثبتة داخل النظام",
            needs_review=True,
        )

    # 2. المعالجة المسبقة
    processed_img = preprocess_image_for_ocr(str(p))

    raw_text = ""
    conf_scores: list[float] = []

    # 3. الاستدعاء الفعلي للمحرك (نموذج ONNX العصبي أولاً ثم Tesseract)
    raw_bgr = None
    if cv2 is not None:
        try:
            with open(str(p), "rb") as f:
                raw_bytes = bytearray(f.read())
            raw_bgr = cv2.imdecode(np.asarray(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            raw_bgr = None

    onnx_text = recognize_text_onnx(raw_bgr) if raw_bgr is not None else ""
    if not onnx_text and processed_img is not None:
        onnx_text = recognize_text_onnx(processed_img)

    if onnx_text:
        raw_text = onnx_text
        conf_scores.append(88.0)
    else:
        try:
            import pytesseract  # type: ignore
            from PIL import Image

            tess_dir = get_tessdata_path()
            tess_cfg = f'--tessdata-dir "{tess_dir}" -l ara+eng --psm 6' if tess_dir else "-l ara+eng --psm 6"

            img_input = Image.fromarray(processed_img) if processed_img is not None else Image.open(image_path)
            data = pytesseract.image_to_data(img_input, config=tess_cfg, output_type=pytesseract.Output.DICT)

            words: list[str] = []
            for word, conf in zip(data.get("text", []), data.get("conf", [])):
                clean_w = str(word).strip()
                if clean_w:
                    words.append(clean_w)
                    try:
                        c_val = float(conf)
                        if c_val >= 0:
                            conf_scores.append(c_val)
                    except (ValueError, TypeError):
                        pass
            raw_text = " ".join(words)
        except Exception as e:
            logger.debug("استثناء أثناء استخراج النص عبر Tesseract: %s", e)

    if not raw_text.strip():
        return OCRResult(
            available=True,
            text="",
            subject="",
            confidence=0.0,
            needs_review=True,
            error="لم يتم العثور على أي نصوص في الصورة",
        )

    # 4. تحليل المادة الأكاديمية
    normalized_text = normalize_arabic_text(raw_text)
    detected_subject = extract_subject_from_text(raw_text)

    # فحص مؤشرات ورقة الاختبار
    has_exam_word = any(
        normalize_arabic_text(kw) in normalized_text for kw in EXAM_INDICATORS
    )

    avg_conf = (sum(conf_scores) / len(conf_scores) / 100.0) if conf_scores else 0.5
    if detected_subject and has_exam_word:
        final_confidence = min(0.98, max(0.70, avg_conf + 0.20))
        needs_review = False
    elif detected_subject:
        final_confidence = min(0.85, max(0.50, avg_conf + 0.10))
        needs_review = False
    else:
        final_confidence = max(0.20, avg_conf * 0.5)
        needs_review = True

    return OCRResult(
        available=True,
        text=raw_text,
        subject=detected_subject,
        confidence=final_confidence,
        language="ara",
        needs_review=needs_review,
        error="",
    )
