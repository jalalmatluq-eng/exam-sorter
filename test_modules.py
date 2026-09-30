"""
سكربت فحص وتأكيد سلامة الوحدات الأساسية لتطبيق Exam Sorter:
- فحص إدارة الملفات (إنشاء مجلدات، حفظ صور وهمية، ترقيم متسلسل).
- فحص وحدة معالجة النصوص العربية.
- فحص ترميز وتجهيز الصور في وحدة الذكاء الاصطناعي.
"""

import os
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import classifier
import face_classifier
import file_manager
import video_classifier
from service import media_watcher_service
from utils.arabic_helper import ar, get_arabic_font_path


def test_arabic_helper() -> None:
    print("--- 1. فحص وحدة اللغة العربية ---")
    sample_text = "رياضيات 1 - الفصل الأول"
    reshaped = ar(sample_text)
    print("النص الأصلي:", sample_text)
    print("النص بعد التشكيل:", reshaped)
    font_path = get_arabic_font_path()
    print("مسار الخط العربي:", font_path)
    assert font_path and os.path.exists(font_path), (
        "ملف الخط العربي غير موجود!"
    )
    print("✓ نجح فحص وحدة اللغة العربية والخطوط.\n")


def test_file_manager() -> None:
    print("--- 2. فحص وحدة إدارة الملفات ---")
    test_dir = Path("test_data")
    test_dir.mkdir(exist_ok=True)
    sample_img = test_dir / "sample_exam.jpg"

    img = Image.new("RGB", (200, 200), color=(240, 240, 240))
    img.save(sample_img)
    print("تم إنشاء صورة تجريبية:", sample_img)

    subject = "رياضيات هندسة 101"
    clean_name = file_manager.sanitize_folder_name(subject)
    print(f"اسم المادة بعد التنظيف: '{clean_name}'")
    assert clean_name == "رياضيات هندسة 101"

    saved1 = file_manager.save_image_to_subject(str(sample_img), "رياضيات")
    print("الصورة الأولى المحفوظة:", Path(saved1).name)
    assert Path(saved1).exists()

    saved2 = file_manager.save_image_to_subject(str(sample_img), "رياضيات")
    print("الصورة الثانية المحفوظة:", Path(saved2).name)
    assert Path(saved2).exists()
    assert saved1 != saved2

    saved3 = file_manager.save_image_to_subject(
        str(sample_img), "فيزياء حديثة"
    )
    print("صورة الفيزياء:", Path(saved3).name)
    assert Path(saved3).exists()

    subjects = file_manager.list_subjects()
    print(f"قائمة المواد المسترجعة: {len(subjects)} مواد")
    for s in subjects:
        print(f" - المادة: {s['name']}, عدد الصور: {s['count']}")

    math_entry = next((s for s in subjects if s["name"] == "رياضيات"), None)
    assert math_entry is not None
    assert int(str(math_entry["count"])) >= 2

    # تنظيف
    if sample_img.exists():
        sample_img.unlink()
    if test_dir.exists():
        test_dir.rmdir()

    print("✓ نجح فحص وحدة إدارة الملفات بالكامل.\n")


def test_classifier_encoding() -> None:
    print("--- 3. فحص وحدة التصنيف وتجهيز الصور ---")
    test_img = Path("test_sample.png")
    img = Image.new("RGB", (50, 50), color=(100, 150, 200))
    img.save(test_img)

    b64_data, mime_type = classifier.encode_and_resize_image(str(test_img))
    print("نوع الوسائط:", mime_type)
    assert mime_type == "image/png"

    print("طول نص Base64 المشفر:", len(b64_data), "حرف")
    assert len(b64_data) > 0

    test_img.unlink()

    # 1. فحص سلوك الخطأ عند عدم وجود ملف الصورة
    try:
        _ = classifier.classify_exam_image(
            "non_existent.jpg", api_key="sk-test-dummy"
        )
        print("تحذير: كان من المفترض رفع استثناء لعدم وجود ملف الصورة!")
    except classifier.ClassificationError as ce:
        print(f"الاستثناء المتوقع عند غياب ملف الصورة: {ce}")
        assert "لم يتم العثور على ملف الصورة" in str(ce)
        print("✓ تم التحقق بنجاح من معالجة غياب ملف الصورة.")

    # 2. فحص سلوك الخطأ عند عدم وجود مفتاح API مع وجود الصورة
    dummy_test_img = Path("dummy_for_key.jpg")
    Image.new("RGB", (100, 100), color=(255, 255, 255)).save(dummy_test_img)
    saved_env_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    saved_stored_key = file_manager.get_stored_api_key()
    file_manager.save_api_key_to_persistent_storage("")
    try:
        _ = classifier.classify_exam_image(
            str(dummy_test_img), api_key="", fallback_to_ocr=False
        )
        print("تحذير: كان من المفترض رفع استثناء لعدم توفر مفتاح API!")
    except classifier.ClassificationError as ce:
        print(f"الاستثناء المتوقع عند غياب المفتاح: {ce}")
        assert "مفتاح" in str(ce)
        print("✓ تم التحقق بنجاح من معالجة غياب مفتاح API.")
    finally:
        if dummy_test_img.exists():
            dummy_test_img.unlink()
        if saved_env_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved_env_key
        if saved_stored_key:
            file_manager.save_api_key_to_persistent_storage(saved_stored_key)

    print("✓ نجح فحص وحدة التصنيف.\n")


def test_face_classifier() -> None:
    print(
        "--- 4. فحص وحدة تصنيف الوجوه والتعرف عليها (Face Classifier) ---"
    )
    sandbox = Path("test_sandbox_face")
    sandbox.mkdir(exist_ok=True)
    profile_path = sandbox / "test_face_profile.json"

    # 1. فحص استخراج تضمين الوجه من مصفوفة وجه اصطناعية
    mock_face = np.full((120, 120), 128, dtype=np.uint8)
    _ = cv2.circle(mock_face, (40, 40), 10, (50, 50, 50), -1)  # عين يسرى
    _ = cv2.circle(mock_face, (80, 40), 10, (50, 50, 50), -1)  # عين يمنى
    _ = cv2.rectangle(mock_face, (45, 80), (75, 95), (40, 40, 40), -1)  # فم

    emb1 = face_classifier.extract_face_embedding(mock_face)
    assert emb1 is not None and len(emb1) == 512, (
        "فشل استخراج التضمين أو طول المتجه ليس 512!"
    )
    norm = np.linalg.norm(emb1)
    assert abs(norm - 1.0) < 1e-4, f"المتجه غير معياري: norm={norm}"
    print("✓ تم استخراج التضمين بنجاح بطول 512 وبمعيارية 1.0.")

    # 2. فحص تطابق الوجه مع نفسه
    sim_self = face_classifier.cosine_similarity(emb1, emb1)
    diff = abs(sim_self - 1.0)
    assert diff < 1e-4, (
        f"تشابه الوجه مع نفسه يجب أن يكون 1.0 ولكن وجد: {sim_self}"
    )
    print("✓ تم التحقق من حساب جيب التمام بنجاح (تشابه تام = 1.0).")

    # 3. فحص إنشاء وحفظ وتحديث الملف الشخصي من صورة واحدة
    profile = face_classifier.build_and_save_profile(
        [emb1], profile_path=profile_path
    )
    assert profile is not None, "الملف الشخصي للبصمة فارغ!"
    assert profile["registered"] is True
    assert profile["sample_count"] == 1
    print(
        "✓ تم بنجاح إنشاء واعتماد بصمة الوجه من صورة مرجعية واحدة."
    )

    # تنظيف
    if sandbox.exists():
        shutil.rmtree(sandbox)
    print("✓ نجح فحص وحدة تصنيف الوجوه بالكامل.\n")


def test_video_classifier() -> None:
    print("--- 5. فحص وحدة تصنيف الفيديوهات (Video Classifier) ---")
    c1 = video_classifier.classify_video(
        duration_seconds=15, width=1080, height=1920, title="funny reel"
    )
    print(f"✓ فيديو مضحك: {c1}")
    assert c1 == "فيديوهات مضحكة"

    c2 = video_classifier.classify_video(
        duration_seconds=3600,
        width=1920,
        height=1080,
        title="محاضرة تحليل دوائر كهربائية دكتور علي",
    )
    print(f"✓ فيديو محاضرة: {c2}")
    assert c2 == "محاضرات ودروس"

    c3 = video_classifier.classify_video(
        duration_seconds=7200,
        width=1920,
        height=1080,
        title="The Batman 2022",
    )
    print(f"✓ فيديو فيلم: {c3}")
    assert c3 == "أفلام ومسلسلات"

    c4 = video_classifier.classify_video(
        duration_seconds=210,
        width=1280,
        height=720,
        title="Official Audio Song track",
    )
    print(f"✓ فيديو أغنية: {c4}")
    assert c4 == "أغاني وأناشيد"

    print("✓ نجح فحص وحدة تصنيف الفيديوهات بالكامل.\n")


def test_media_scanner_and_rollback() -> None:
    print(
        "--- 6. فحص النقل الآمن، السجل، والتراجع "
        "(Safety Move & Rollback) ---"
    )
    sandbox = Path("test_sandbox_scanner")
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.mkdir()

    src_dir = sandbox / "source"
    dest_dir = sandbox / "destination"
    src_dir.mkdir()
    dest_dir.mkdir()

    # إنشاء ملفات تجريبية
    file1 = src_dir / "funny_memes.mp4"
    _ = file1.write_bytes(b"TEST_VIDEO_DATA_FOR_VERIFICATION_BYTES_123456789")
    size_before = file1.stat().st_size

    # فحص النسخ الآمن
    dest_path = file_manager.move_to_category(
        src_path=str(file1),
        category_name="فيديوهات مضحكة",
        base_path=dest_dir,
    )

    assert file1.exists(), (
        "الملف المصدر يجب أن يظل موجوداً وسليماً في وضع النسخ الآمن!"
    )
    dest_file = Path(dest_path)
    assert dest_file.exists(), (
        "الملف النهائي المنسوخ غير موجود في الوجهة!"
    )
    assert dest_file.stat().st_size == size_before, (
        "حجم الملف في الوجهة لا يتطابق مع المصدر بالبايت!"
    )
    print(
        "✓ تم النسخ بأمان مع الحفاظ التام على الملف الأصلي والتحقق بالحجم."
    )

    # فحص السجل والتراجع (Rollback) في بيئة معزولة
    history = file_manager.get_transfer_history(base_path=dest_dir)
    assert len(history) > 0, (
        "العملية لم تُسجل في transfer_history.json المعزول!"
    )
    rec_id = int(str(history[0]["id"]))

    undo_ok = file_manager.undo_transfer(rec_id, base_path=dest_dir)
    assert undo_ok, "فشلت عملية التراجع عن النقل!"
    assert file1.exists(), (
        "الملف الأصلي يجب أن يظل في مكانه دون مساس!"
    )
    assert not dest_file.exists(), (
        "النسخة المفرزة لم تُحذف من الوجهة بعد التراجع!"
    )
    print(
        f"✓ تم التراجع بنجاح وحذف النسخة بدقة مع بقاء الأصل (ID: {rec_id})."
    )

    # تنظيف
    shutil.rmtree(sandbox)
    print("✓ نجح فحص النقل الآمن والتراجع بالكامل.\n")


def test_service_watcher() -> None:
    print("--- 7. فحص خدمة المراقبة بالخلفية (Media Watcher Service) ---")
    media_watcher_service.stop_watcher_thread()
    assert not media_watcher_service.is_watcher_running(), (
        "الخدمة يجب أن تكون متوقفة بعد الاستدعاء"
    )
    media_watcher_service.start_watcher_thread(interval_seconds=1)
    assert media_watcher_service.is_watcher_running(), "فشل بدء ثريد الخدمة!"
    time.sleep(0.5)
    media_watcher_service.stop_watcher_thread()
    assert not media_watcher_service.is_watcher_running(), (
        "فشل إيقاف ثريد الخدمة!"
    )
    print("✓ تم بدء وإيقاف ثريد خدمة المراقبة بنجاح.\n")


def test_poison_files_and_pending_scan() -> None:
    print("--- 8. فحص درع الملف السام والفحص المعلق وحفظ المفتاح ---")

    # 1. فحص تتبع الملف الجاري ومعالجة الملف السام
    fake_poison_file = "test_corrupt_video.mp4"
    file_manager.mark_file_processing_start(fake_poison_file)
    last_proc_path = file_manager.get_last_processing_file_path()
    assert last_proc_path.exists(), "ملف تتبع المعالجة يجب أن ينشأ عند البدء!"

    # محاكاة إقلاع التطبيق بعد انهيار غير متوقع
    detected_poison = file_manager.check_and_handle_poison_file_on_boot()
    assert detected_poison == fake_poison_file, "يجب اكتشاف الملف السام عند الإقلاع!"
    assert not last_proc_path.exists(), "يجب مسح ملف التتبع بعد نقله لقائمة poison_files!"

    poisons = file_manager.get_poison_files_set()
    assert fake_poison_file in poisons, "الملف السام يجب أن يكون مضافاً في قائمة poison_files!"

    # تنظيف قائمة الملفات السامة
    file_manager.save_sorter_preferences({"poison_files": []})
    assert fake_poison_file not in file_manager.get_poison_files_set()

    # 2. فحص الفحص المعلق (Pending Scan)
    file_manager.set_pending_scan(True, source="internal", target="sdcard")
    is_pending, p_src, p_tgt = file_manager.get_pending_scan_info()
    assert is_pending is True, "يجب حفظ حالة الفحص المعلق!"
    assert p_src == "internal"
    assert p_tgt == "sdcard"

    file_manager.clear_pending_scan()
    is_pending_after, _, _ = file_manager.get_pending_scan_info()
    assert is_pending_after is False, "يجب إلغاء الفحص المعلق بعد clear_pending_scan!"

    # 3. فحص حفظ واسترجاع مفتاح API المشترك
    test_key = "sk-ant-test-key-12345"
    file_manager.save_api_key_to_persistent_storage(test_key)
    retrieved_key = file_manager.get_stored_api_key()
    assert retrieved_key == test_key, "المفتاح المسترجع يجب أن يتطابق مع المحفوظ!"

    # تنظيف
    file_manager.save_api_key_to_persistent_storage("")

    print("✓ نجح فحص درع الملف السام والفحص المعلق والمفتاح المشترك بنجاح.\n")


if __name__ == "__main__":
    test_arabic_helper()
    test_file_manager()
    test_classifier_encoding()
    test_face_classifier()
    test_video_classifier()
    test_media_scanner_and_rollback()
    test_service_watcher()
    test_poison_files_and_pending_scan()
    print("==================================================")
    print("  جميع الفحوصات الآلية للوحدات تمت بنجاح 100%!  ")
    print("==================================================")
