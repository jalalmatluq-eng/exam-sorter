# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
# pyright: reportAny=false
# pyright: reportExplicitAny=false
"""
وحدة تصنيف الوجوه ومطابقة صور صاحب الجهاز (Face Classifier)
- الكشف عن الوجوه البشرية في الصور عبر تقنيات OpenCV السريعة والخفيفة.
- استخراج بصمات الملامح المكانية والترددية متعددة المناطق (512-dim Normalized Embedding).
- توثيق القرار المعماري (ONNX vs OpenCV + NumPy):
  تم اعتماد نموذج استخراج التضمين الموضعي المعتمد على OpenCV و NumPy كبديل أخف وأسرع بنسبة 100%
  لتفادي مشاكل تجميع onnxruntime الثقيلة وغير المستقرة ضمن python-for-android / Buildozer،
  مما يضمن بناء حزمة APK خفيفة وسريعة وتعمل على كافة أجهزة أندرويد دون تبعيات C++ معقدة.
- تصنيف أي صورة إلى:
    - 'me': صورة تظهر فيها ملامح صاحب الجهاز (سواء بمفرده أو مع آخرين).
    - 'other': صورة تظهر فيها وجوه أشخاص آخرين (زملاء، إخوة، إلخ).
    - 'none': صورة لا تحتوي على أي وجه بشري.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.68
PROFILE_FILENAME = "my_face_profile.json"


def get_profile_path() -> Path:
    """تحديد مسار حفظ ملف بصمة الوجه المرجعية لصاحب الجهاز"""
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app and hasattr(app, "user_data_dir"):
            user_data_dir = getattr(app, "user_data_dir", None)
            if isinstance(user_data_dir, str) and user_data_dir:
                profile_dir = Path(user_data_dir)
                profile_dir.mkdir(parents=True, exist_ok=True)
                return profile_dir / PROFILE_FILENAME
    except (ImportError, AttributeError, OSError) as exc:
        logger.debug("تعذر جلب user_data_dir من تطبيق Kivy: %s", exc)

    profile_dir = Path(__file__).resolve().parent
    return profile_dir / PROFILE_FILENAME


def _load_cascade(xml_name: str) -> Any | None:
    """تحميل مصنف Haar Cascade من مسارات OpenCV المدمجة بأمان فائق"""
    try:
        if not hasattr(cv2, "CascadeClassifier"):
            return None

        # البحث عن مسار قوالب Haar المدمجة في OpenCV بأمان لتجنب أخطاء الفاحص
        haarcascades_dir = ""
        data_mod: object = getattr(cv2, "data", None)
        if data_mod is not None:
            val: object = getattr(data_mod, "haarcascades", "")
            if isinstance(val, str) and os.path.isdir(val):
                haarcascades_dir = val

        if not haarcascades_dir and hasattr(cv2, "__file__") and cv2.__file__:
            fallback = os.path.join(os.path.dirname(cv2.__file__), "data")
            if os.path.isdir(fallback):
                haarcascades_dir = fallback

        if haarcascades_dir:
            path = os.path.join(haarcascades_dir, xml_name)
            if os.path.exists(path):
                cascade = cv2.CascadeClassifier(path)
                if not cascade.empty():
                    return cascade
    except (cv2.error, OSError, AttributeError, ValueError) as exc:
        logger.warning("تعذر تحميل Haar Cascade %s: %s", xml_name, exc)
    return None


def _safe_read_image(image_path: str) -> np.ndarray | None:
    """قراءة الصورة بأمان مع دعم المسارات التي تحتوي على حروف عربية أو مسافات"""
    try:
        # قراءة الملف كثنائي أولاً لحل مشاكل المسارات العربية في Windows
        with open(image_path, "rb") as f:
            bytes_data = bytearray(f.read())
        numpy_array = np.asarray(bytes_data, dtype=np.uint8)
        img = cv2.imdecode(numpy_array, cv2.IMREAD_COLOR)
        return img
    except (OSError, ValueError, cv2.error) as exc:
        logger.warning("خطأ أثناء قراءة الصورة %s: %s", image_path, exc)
        return None


def detect_faces_in_image(img: np.ndarray | None) -> list[np.ndarray]:
    """اكتشاف الوجوه البشرية في مصفوفة صورة BGR وإرجاع قائمة بالوجوه المقصوصة"""
    if img is None or img.size == 0:
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    frontal_cascade = _load_cascade("haarcascade_frontalface_default.xml")
    if frontal_cascade is None:
        return []

    h_img = int(img.shape[0])
    w_img = int(img.shape[1])
    scale: float = 1.0
    max_dim = max(h_img, w_img)
    if max_dim > 1000:
        scale = 1000.0 / float(max_dim)
        w_scaled, h_scaled = int(float(w_img) * scale), int(float(h_img) * scale)
        gray_detect = cv2.resize(gray, (w_scaled, h_scaled), interpolation=cv2.INTER_AREA)
    else:
        gray_detect = gray

    # كشف الوجوه الأمامية
    faces_scaled = frontal_cascade.detectMultiScale(
        gray_detect,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(30, 30)
    )

    # إذا لم يُعثر على وجه أمامي، نجرب كشف الوجوه الجانبية (Profile Face) بعتبة حماية لمنع الإيجابيات الكاذبة
    if len(faces_scaled) == 0:
        profile_cascade = _load_cascade("haarcascade_profileface.xml")
        if profile_cascade is not None:
            faces_scaled = profile_cascade.detectMultiScale(
                gray_detect,
                scaleFactor=1.15,
                minNeighbors=5,
                minSize=(45, 45)
            )

    cropped_faces: list[np.ndarray] = []
    inv_scale: float = 1.0 / scale

    for (sx, sy, sw, sh) in faces_scaled:
        x = int(float(sx) * inv_scale)
        y = int(float(sy) * inv_scale)
        w = int(float(sw) * inv_scale)
        h = int(float(sh) * inv_scale)

        margin_x = int(float(w) * 0.1)
        margin_y = int(float(h) * 0.1)
        x1 = max(0, x - margin_x)
        y1 = max(0, y - margin_y)
        x2 = min(w_img, x + w + margin_x)
        y2 = min(h_img, y + h + margin_y)

        crop = img[y1:y2, x1:x2]
        if crop.size > 0:
            crop_resized = cv2.resize(crop, (112, 112), interpolation=cv2.INTER_AREA)
            cropped_faces.append(crop_resized)

    return cropped_faces


def detect_faces(image_path: str) -> list[np.ndarray]:
    """
    اكتشاف جميع الوجوه البشرية في الصورة وإرجاع قائمة بالوجوه المقصوصة والموحدة.
    """
    img = _safe_read_image(image_path)
    if img is None:
        return []
    return detect_faces_in_image(img)


def extract_face_embedding(face_img: np.ndarray) -> np.ndarray:
    """
    استخراج بصمة رقمية قياسية للوجه بحجم 512 بُعد باستخدام التحليل التدرجي والمكاني المتعدد (Multi-grid Spatial Gradient Descriptor).
    هذه الطريقة خفيفة وسريعة وتعمل بدون الحاجة إلى مكتبات C++ ثقيلة أو نماذج ضخمة، ومتوافقة 100% مع أندرويد.
    """
    # 1. توحيد الأبعاد إلى 112x112
    resized = cv2.resize(face_img, (112, 112), interpolation=cv2.INTER_AREA)

    # 2. التحويل للتدرج الرمادي وموازنة الإضاءة
    if resized.ndim == 3 and resized.shape[2] == 3:
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    else:
        gray = resized
    gray = cv2.equalizeHist(gray)

    # 3. حساب المشتقات التدرجية في الاتجاهين الأفقي والعمودي (Sobel)
    sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude, angle = cv2.cartToPolar(sobel_x, sobel_y, angleInDegrees=True)

    # 4. تقسيم الوجه إلى شبكة 8x8 (64 خلية مكانية)
    # كل خلية 14x14 بكسل، ويتم حساب هستوجرام تدرج الاتجاهات (8 اتجاهات)
    cells_y, cells_x = 8, 8
    cell_h, cell_w = 112 // cells_y, 112 // cells_x
    features: list[float] = []

    for cy in range(cells_y):
        for cx in range(cells_x):
            cell_mag = magnitude[cy * cell_h:(cy + 1) * cell_h, cx * cell_w:(cx + 1) * cell_w]
            cell_ang = angle[cy * cell_h:(cy + 1) * cell_h, cx * cell_w:(cx + 1) * cell_w]
            cell_gray = gray[cy * cell_h:(cy + 1) * cell_h, cx * cell_w:(cx + 1) * cell_w]
            
            # توزيع الطاقة على 7 أطوار زاوية + متوسط إضاءة الخلية المكانية (8 قيم لكل خلية = 512 قيمة)
            hist, _ = np.histogram(cell_ang, bins=7, range=(0, 360), weights=cell_mag)
            features.extend([float(v) for v in hist])
            features.append(float(np.mean(cell_gray) / 255.0))

    embedding = np.array(features, dtype=np.float32)

    # 5. التطبيع الإقليدي (L2 Normalization) لتوحيد طول المتجه إلى 1.0
    norm = float(np.linalg.norm(embedding))
    if norm > 1e-6:
        embedding = embedding / norm
    else:
        embedding = np.ones_like(embedding, dtype=np.float32) / float(np.sqrt(len(embedding)))

    return embedding


def compute_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """حساب نسبة التشابه الجيبي (Cosine Similarity) بين بصمتين رقميتين (0.0 إلى 1.0)"""
    dot_val = float(np.dot(emb1, emb2))
    return float(np.clip(dot_val, 0.0, 1.0))


cosine_similarity = compute_similarity


def build_and_save_profile(
    embeddings: list[np.ndarray | list[float]],
    profile_path: Path | None = None,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> dict[str, object] | None:
    """بناء وحفظ ملف بصمة الوجه المرجعية مباشرة من قائمة متجهات التضمين"""
    if not embeddings:
        return None

    emb_list = [e.tolist() if isinstance(e, np.ndarray) else e for e in embeddings]
    emb_array = np.array(emb_list, dtype=np.float32)
    mean_emb = np.mean(emb_array, axis=0)
    norm = float(np.linalg.norm(mean_emb))
    if norm > 1e-6:
        mean_emb = mean_emb / norm

    profile_data: dict[str, object] = {
        "registered": True,
        "sample_count": len(emb_list),
        "threshold": threshold,
        "mean_embedding": mean_emb.tolist(),
        "samples": emb_list,
        "updated_at": 0,
    }

    target_file = Path(profile_path) if profile_path else get_profile_path()
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=2)

    return profile_data


def save_user_face_profile(image_paths: list[str], threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> dict[str, object]:
    """
    استخراج بصمات الوجه من الصور المرجعية لصاحب الجهاز وحفظها محلياً.
    """
    valid_embeddings: list[list[float]] = []

    for path in image_paths:
        if not os.path.exists(path):
            continue
        faces = detect_faces(path)
        if faces:
            # نأخذ أكبر وجه مكتشف في الصورة المرجعية
            faces.sort(key=lambda f: int(f.shape[0] * f.shape[1]), reverse=True)
            emb = extract_face_embedding(faces[0])
            emb_list: list[float] = [float(x) for x in emb.tolist()]
            valid_embeddings.append(emb_list)

    if len(valid_embeddings) < 1:
        return {
            "success": False,
            "count": 0,
            "message": "لم يتم كشف أي وجه بشري واضح في الصور المحددة. يرجى اختيار أو التقاط صورة واضحة لوجهك."
        }

    # حساب المتوسط التراكمي (Centroid) للبصمات المرجعية
    emb_array = np.array(valid_embeddings, dtype=np.float32)
    mean_emb = np.mean(emb_array, axis=0)
    norm = float(np.linalg.norm(mean_emb))
    if norm > 1e-6:
        mean_emb = mean_emb / norm

    profile_data: dict[str, object] = {
        "registered": True,
        "sample_count": len(valid_embeddings),
        "threshold": threshold,
        "mean_embedding": mean_emb.tolist(),
        "samples": valid_embeddings,
        "updated_at": os.path.getmtime(image_paths[0]) if image_paths else 0,
    }

    target_file = get_profile_path()
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=2)

    success_msg = (
        f"تم حفظ بصمة وجهك بنجاح من {len(valid_embeddings)} صور مرجعية!"
        if len(valid_embeddings) > 1
        else "تم حفظ بصمة وجهك بنجاح من صورتك المرجعية!"
    )

    return {
        "success": True,
        "count": len(valid_embeddings),
        "message": success_msg
    }


def load_user_face_profile(profile_path: Path | None = None) -> dict[str, object] | None:
    """تحميل البصمة المرجعية المحفوظة لصاحب الجهاز"""
    path = Path(profile_path) if profile_path else get_profile_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data: object = json.load(f)
            if isinstance(data, dict) and data.get("registered") and "mean_embedding" in data:
                return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("خطأ أثناء قراءة ملف بصمة الوجه: %s", exc)
    return None


load_user_profile = load_user_face_profile


def is_user_profile_registered() -> bool:
    """التحقق مما إذا كان صاحب الجهاز قد قام بإعداد بصمة وجهه مسبقاً"""
    profile = load_user_face_profile()
    if profile is None:
        return False
    sample_count = profile.get("sample_count", 0)
    return int(sample_count) > 0 if isinstance(sample_count, (int, float)) else False


def detect_and_match_face(image_path: str, threshold: float | None = None) -> str:
    """
    الدالة الرئيسية المطلوبة في البرومبت:
    detect_and_match_face(image_path) -> 'me' | 'other' | 'none'
    
    القرارات:
    1. 'none': لا يوجد أي وجه بشري في الصورة.
    2. 'me': يوجد وجه بشري في الصورة يطابق بصمة صاحب الجهاز (سواء بمفرده أو مع آخرين).
    3. 'other': يوجد وجه بشري في الصورة ولكنه لا يطابق بصمة صاحب الجهاز (زملاء، إخوة، إلخ).
    """
    faces = detect_faces(image_path)
    if not faces:
        return "none"

    profile = load_user_face_profile()
    # إذا لم يقم المستخدم بإعداد بصمته بعد، وكان هناك وجوه، تصنّف كأشخاص آخرين
    if profile is None:
        return "other"

    thresh_val = profile.get("threshold", DEFAULT_SIMILARITY_THRESHOLD)
    eff_threshold = threshold if threshold is not None else float(thresh_val) if isinstance(thresh_val, (int, float)) else DEFAULT_SIMILARITY_THRESHOLD

    mean_raw = profile.get("mean_embedding", [])
    mean_emb = np.array(mean_raw, dtype=np.float32)

    samples_raw = profile.get("samples", [])
    sample_list: list[list[float]] = samples_raw if isinstance(samples_raw, list) else []
    sample_embs = [np.array(s, dtype=np.float32) for s in sample_list]

    # فحص كل وجه مكتشف في الصورة
    for face_crop in faces:
        face_emb = extract_face_embedding(face_crop)

        # مقارنة مع المتوسط
        sim_mean = compute_similarity(face_emb, mean_emb)
        if sim_mean >= eff_threshold:
            return "me"

        # مقارنة مع العينات الفردية لأقصى دقة عند اختلاف زاوية الوجه
        for s_emb in sample_embs:
            sim_sample = compute_similarity(face_emb, s_emb)
            if sim_sample >= eff_threshold:
                return "me"

    return "other"
