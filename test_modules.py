# -*- coding: utf-8 -*-
"""
سكربت فحص وتأكيد سلامة الوحدات الأساسية لتطبيق Exam Sorter:
- فحص إدارة الملفات (إنشاء مجلدات، حفظ صور وهمية، ترقيم متسلسل، إحصائيات).
- فحص وحدة معالجة النصوص العربية.
- فحص ترميز وتجهيز الصور في وحدة الذكاء الاصطناعي.
"""

import os
import sys
import shutil
from pathlib import Path
from PIL import Image

# استيراد الوحدات الخاصة بالتطبيق
import file_manager
import classifier
from utils.arabic_helper import ar, get_arabic_font_path

def test_arabic_helper():
    print("--- 1. فحص وحدة اللغة العربية ---")
    sample_text = "رياضيات 1 - الفصل الأول"
    reshaped = ar(sample_text)
    print("النص الأصلي:", sample_text)
    print("النص بعد التشكيل:", reshaped)
    font_path = get_arabic_font_path()
    print("مسار الخط العربي:", font_path)
    assert font_path and os.path.exists(font_path), "ملف الخط العربي غير موجود!"
    print("✓ نجح فحص وحدة اللغة العربية والخطوط.\n")

def test_file_manager():
    print("--- 2. فحص وحدة إدارة الملفات ---")
    # إنشاء صورة تجريبية صغيرة
    test_img_dir = Path("test_data")
    test_img_dir.mkdir(exist_ok=True)
    sample_img_path = test_img_dir / "sample_exam.jpg"
    
    img = Image.new("RGB", (800, 1000), color=(240, 240, 240))
    img.save(sample_img_path)
    print(f"تم إنشاء صورة تجريبية: {sample_img_path}")

    # مسار تخزين اختباري
    test_storage = Path("test_storage")
    if test_storage.exists():
        shutil.rmtree(test_storage)
    test_storage.mkdir(exist_ok=True)

    # 1. تنظيف اسم المادة وإنشاء المجلد
    subject_raw = 'رياضيات/هندسة: 101*?'
    folder = file_manager.ensure_subject_folder(test_storage, subject_raw)
    clean_name = folder.name
    print(f"اسم المادة بعد التنظيف: '{clean_name}'")
    assert clean_name == "رياضيات هندسة 101", f"التنظيف غير متوقع: {clean_name}"

    # 2. حفظ صورتين للتأكد من الترقيم المتسلسل (_01, _02)
    saved1 = file_manager.save_image_to_subject(str(sample_img_path), "رياضيات", base_path=test_storage)
    saved2 = file_manager.save_image_to_subject(str(sample_img_path), "رياضيات", base_path=test_storage)
    print(f"الصورة الأولى المحفوظة: {Path(saved1).name}")
    print(f"الصورة الثانية المحفوظة: {Path(saved2).name}")
    assert "_01.jpg" in saved1, "فشل ترقيم الصورة الأولى!"
    assert "_02.jpg" in saved2, "فشل ترقيم الصورة الثانية المتتالية!"

    # 3. حفظ مادة أخرى
    saved_physics = file_manager.save_image_to_subject(str(sample_img_path), "فيزياء حديثة", base_path=test_storage)
    print(f"صورة الفيزياء: {Path(saved_physics).name}")

    # 4. استرجاع قائمة المواد والإحصائيات
    subjects = file_manager.list_subjects(base_path=test_storage)
    print(f"قائمة المواد المسترجعة: {len(subjects)} مواد")
    for s in subjects:
        print(f" - المادة: {s['name']}, عدد الصور: {s['count']}")

    assert len(subjects) == 3, f"المتوقع 3 مواد، وُجد {len(subjects)}"
    assert subjects[0]["name"] == "رياضيات" and subjects[0]["count"] == 2

    # 5. استرجاع صور مادة معينة
    math_images = file_manager.get_subject_images("رياضيات", base_path=test_storage)
    assert len(math_images) == 2, f"المتوقع صورتين للرياضيات، وُجد {len(math_images)}"

    # تنظيف مجلدات الاختبار
    shutil.rmtree(test_storage)
    shutil.rmtree(test_img_dir)
    print("✓ نجح فحص وحدة إدارة الملفات بالكامل.\n")

def test_classifier_encoding():
    print("--- 3. فحص وحدة التصنيف وتجهيز الصور ---")
    test_img = Path("temp_test.png")
    img = Image.new("RGBA", (2000, 3000), color=(255, 255, 255, 255))
    img.save(test_img)

    encoded, media_type = classifier.encode_and_resize_image(str(test_img), max_dimension=1000)
    print(f"نوع الوسائط: {media_type}")
    print(f"طول نص Base64 المشفر: {len(encoded)} حرف")
    assert media_type == "image/png"
    assert len(encoded) > 0

    test_img.unlink()

    # 1. فحص سلوك الخطأ عند عدم وجود ملف الصورة
    try:
        classifier.classify_exam_image("non_existent.jpg", api_key="sk-test-dummy")
        print("تحذير: كان من المفترض رفع استثناء لعدم وجود ملف الصورة!")
    except classifier.ClassificationError as ce:
        print(f"الاستثناء المتوقع عند غياب ملف الصورة: {ce}")
        assert "لم يتم العثور على ملف الصورة" in str(ce)
        print("✓ تم التحقق بنجاح من معالجة غياب ملف الصورة.")

    # 2. فحص سلوك الخطأ عند عدم وجود مفتاح API مع وجود الصورة
    dummy_test_img = Path("dummy_for_key.jpg")
    Image.new("RGB", (100, 100), color=(255, 255, 255)).save(dummy_test_img)
    saved_env_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        classifier.classify_exam_image(str(dummy_test_img), api_key="", fallback_to_ocr=False)
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

    print("✓ نجح فحص وحدة التصنيف.\n")

def test_face_classifier():
    print("--- 4. فحص وحدة تصنيف الوجوه والتعرف عليها (Face Classifier) ---")
    import numpy as np
    import cv2
    import face_classifier

    sandbox = Path("test_sandbox_face")
    sandbox.mkdir(exist_ok=True)
    profile_path = sandbox / "test_face_profile.json"

    # 1. فحص استخراج تضمين الوجه من مصفوفة وجه اصطناعية
    mock_face = np.full((120, 120), 128, dtype=np.uint8)
    cv2.circle(mock_face, (40, 40), 10, 50, -1)  # عين يسرى
    cv2.circle(mock_face, (80, 40), 10, 50, -1)  # عين يمنى
    cv2.rectangle(mock_face, (45, 80), (75, 95), 40, -1)  # فم

    emb1 = face_classifier.extract_face_embedding(mock_face)
    assert emb1 is not None and len(emb1) == 512, "فشل استخراج التضمين أو طول المتجه ليس 512!"
    norm = np.linalg.norm(emb1)
    assert abs(norm - 1.0) < 1e-4, f"المتجه غير معياري: norm={norm}"
    print("✓ تم استخراج التضمين بنجاح بطول 512 وبمعيارية 1.0.")

    # 2. فحص تطابق الوجه مع نفسه
    sim_self = face_classifier.cosine_similarity(emb1, emb1)
    assert abs(sim_self - 1.0) < 1e-4, f"تشابه الوجه مع نفسه يجب أن يكون 1.0 ولكن وجد: {sim_self}"
    print("✓ تم التحقق من حساب جيب التمام بنجاح (تشابه تام = 1.0).")

    # 3. فحص إنشاء وحفظ وتحديث الملف الشخصي
    profile = face_classifier.build_and_save_profile([emb1, emb1], profile_path=profile_path)
    assert profile is not None and "mean_embedding" in profile
    assert profile_path.exists(), "لم يتم حفظ ملف البصمة!"
    loaded_profile = face_classifier.load_user_face_profile(profile_path=profile_path)
    assert loaded_profile is not None
    print("✓ تم حفظ وتحميل ملف البصمة بنجاح.")

    # تنظيف
    shutil.rmtree(sandbox)
    print("✓ نجح فحص وحدة تصنيف الوجوه بالكامل.\n")

def test_video_classifier():
    print("--- 5. فحص وحدة تصنيف الفيديوهات (Video Classifier) ---")
    import video_classifier

    # 1. فحص الكلمات المفتاحية لمسارات الفيديو
    cat1 = video_classifier.classify_video_locally("C:/Downloads/funny_cat_tiktok_reel.mp4")
    assert cat1 == "فيديوهات مضحكة", f"فشل تصنيف الفيديو المضحك: {cat1}"
    print(f"✓ فيديو مضحك: {cat1}")

    cat2 = video_classifier.classify_video_locally("D:/Study/CS50_Lecture_01_algorithms.mp4")
    assert cat2 == "محاضرات وتعلم", f"فشل تصنيف المحاضرة: {cat2}"
    print(f"✓ فيديو محاضرة: {cat2}")

    cat3 = video_classifier.classify_video_locally("E:/Movies/Inception.2010.1080p.mkv")
    assert cat3 == "أفلام ومسلسلات", f"فشل تصنيف الفيلم: {cat3}"
    print(f"✓ فيديو فيلم: {cat3}")

    cat4 = video_classifier.classify_video_locally("C:/Music/New_Official_Audio_Song.mp4")
    assert cat4 == "أغاني وأناشيد", f"فشل تصنيف الأغنية: {cat4}"
    print(f"✓ فيديو أغنية: {cat4}")

    print("✓ نجح فحص وحدة تصنيف الفيديوهات بالكامل.\n")

def test_media_scanner_and_rollback():
    print("--- 6. فحص النقل الآمن، السجل، والتراجع (Safety Move & Rollback) ---")
    sandbox = Path("test_sandbox_scanner")
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.mkdir(exist_ok=True)

    src_dir = sandbox / "source"
    dest_dir = sandbox / "dest"
    src_dir.mkdir()
    dest_dir.mkdir()

    # إنشاء ملفات تجريبية
    file1 = src_dir / "funny_memes.mp4"
    file1.write_bytes(b"TEST_VIDEO_DATA_FOR_VERIFICATION_BYTES_123456789")
    size_before = file1.stat().st_size

    # فحص النقل الآمن
    dest_path = file_manager.move_to_category(
        src_path=str(file1),
        category_name="فيديوهات مضحكة",
        base_path=dest_dir
    )

    assert not file1.exists(), "الملف المصدر لم يُحذف بعد التحقق من سلامة الوجهة!"
    dest_file = Path(dest_path)
    assert dest_file.exists(), "الملف النهائي غير موجود في الوجهة!"
    assert dest_file.stat().st_size == size_before, "حجم الملف في الوجهة لا يتطابق مع المصدر بالبايت!"
    print("✓ تم النقل بأمان مع التحقق الدقيق من الحجم بالبايت.")

    # فحص السجل والتراجع (Rollback)
    history = file_manager.get_transfer_history()
    assert len(history) > 0, "العملية لم تُسجل في transfer_history.json!"
    rec_id = history[0]["id"]

    undo_ok = file_manager.undo_transfer(rec_id)
    assert undo_ok, "فشلت عملية التراجع عن النقل!"
    assert file1.exists(), "الملف لم يعد إلى مكانه الأصلي بعد التراجع!"
    assert not dest_file.exists(), "الملف المنقول لم يُحذف من الوجهة بعد التراجع!"
    assert file1.stat().st_size == size_before, "حجم الملف المستعاد غير مطابق!"
    print(f"✓ تم التراجع بنجاح وإعادة الملف لمكانه الأصلي بدقة 100% (ID: {rec_id}).")

    # تنظيف
    shutil.rmtree(sandbox)
    print("✓ نجح فحص النقل الآمن والتراجع بالكامل.\n")

def test_service_watcher():
    print("--- 7. فحص خدمة المراقبة بالخلفية (Media Watcher Service) ---")
    from service import media_watcher_service
    import time

    media_watcher_service.stop_watcher_thread()
    assert not media_watcher_service.is_watcher_running(), "الخدمة يجب أن تكون متوقفة بعد الاستدعاء"
    media_watcher_service.start_watcher_thread(interval_seconds=1)
    assert media_watcher_service.is_watcher_running(), "فشل بدء ثريد الخدمة!"
    time.sleep(0.5)
    media_watcher_service.stop_watcher_thread()
    assert not media_watcher_service.is_watcher_running(), "فشل إيقاف ثريد الخدمة!"
    print("✓ تم بدء وإيقاف ثريد خدمة المراقبة بنجاح.\n")

if __name__ == "__main__":
    test_arabic_helper()
    test_file_manager()
    test_classifier_encoding()
    test_face_classifier()
    test_video_classifier()
    test_media_scanner_and_rollback()
    test_service_watcher()
    print("==================================================")
    print("  جميع الفحوصات الآلية للوحدات تمت بنجاح 100%!  ")
    print("==================================================")
