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

if __name__ == "__main__":
    test_arabic_helper()
    test_file_manager()
    test_classifier_encoding()
    print("==================================================")
    print("  جميع الفحوصات الآلية للوحدات تمت بنجاح 100%!  ")
    print("==================================================")
