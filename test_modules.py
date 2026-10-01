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

try:
    import cv2
except Exception:
    cv2 = None  # type: ignore
import numpy as np
from PIL import Image

import classifier
import face_classifier
import file_manager
import storage_backend
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


def test_export_logs() -> None:
    print("--- 9. فحص تصدير سجل التشخيص (Export Diagnostic Logs) ---")
    from utils.export_logs import get_private_log_file, export_diagnostic_log
    log_p = get_private_log_file()
    assert log_p.exists(), "ملف السجل الداخلي يجب أن يكون موجوداً أو تم إنشاؤه!"
    ok, msg = export_diagnostic_log()
    assert ok, f"فشل تصدير سجل التشخيص: {msg}"
    print(f"✓ تم تصدير السجل بنجاح إلى: {msg}")
    print("✓ نجح فحص تصدير سجل التشخيص بالكامل.\n")


def test_unified_storage_backend() -> None:
    print("--- 10. فحص طبقة التخزين الموحدة وهجرة المجلدات والنسخ الآمن ---")

    # 1. فحص استكشاف مواقع التخزين
    locations = storage_backend.detect_storage_locations()
    assert "internal" in locations, "يجب اكتشاف الذاكرة الداخلية دائماً!"
    assert "sdcard" in locations, "يجب تحديد حالة بطاقة SD دائماً!"
    internal_loc = locations["internal"]
    assert internal_loc.readable is True
    print(f"✓ موقع التخزين الداخلي: {internal_loc.name}, متاح={internal_loc.detected}")

    # 2. فحص توحيد أسماء التصنيفات
    assert storage_backend.normalize_category_name("محاضرات وتعلم") == "محاضرات ودروس"
    assert storage_backend.normalize_category_name("محاضرات_وتعلم") == "محاضرات ودروس"
    assert storage_backend.normalize_category_name("صور_الاختبارات") == "صور الاختبارات"
    assert storage_backend.normalize_category_name("افلام ومسلسلات") == "أفلام ومسلسلات"
    print("✓ تم التحقق من توحيد أسماء التصنيفات القديمة بدقة.")

    # 3. فحص هجرة المجلدات القديمة تلقائياً
    test_root = Path("test_data_migration")
    test_root.mkdir(parents=True, exist_ok=True)
    old_folder = test_root / "محاضرات وتعلم"
    old_folder.mkdir(parents=True, exist_ok=True)
    test_file = old_folder / "lecture_01.mp4"
    test_file.write_text("dummy lecture content", encoding="utf-8")

    migrated_count = storage_backend.migrate_legacy_folders(test_root)
    assert migrated_count >= 1, "يجب هجرة الملفات من المجلد القديم!"
    new_file = test_root / "محاضرات ودروس" / "lecture_01.mp4"
    assert new_file.exists(), "الملف المهاجر يجب أن يتواجد في المجلد القياسي الموحد!"
    assert not old_folder.exists(), "المجلد القديم الفارغ يجب أن يحذف بعد الهجرة!"
    print(f"✓ تمت هجرة المجلد القديم بنجاح ({migrated_count} ملف).")

    # 4. فحص النسخ الذري مع التحقق من الحجم
    src_test = test_root / "source_atomic.bin"
    src_test.write_bytes(b"HELLO STREAMING STORAGE " * 500)
    dest_test = test_root / "dest_atomic.bin"
    ok = storage_backend.copy_path_to_path(src_test, dest_test)
    assert ok is True
    assert dest_test.exists()
    assert dest_test.stat().st_size == src_test.stat().st_size
    print("✓ نجح النسخ الذري عبر دفق آمن مع التحقق من الحجم بالبايت.")

    # 5. فحص حذف MediaItem
    media_item = storage_backend.MediaItem(
        id=str(dest_test),
        source_type="path",
        path=str(dest_test),
        display_name="dest_atomic.bin",
        size_bytes=dest_test.stat().st_size,
    )
    assert media_item.name == "dest_atomic.bin"
    assert media_item.exists() is True
    del_ok = storage_backend.delete_media_item(media_item)
    assert del_ok is True
    assert not dest_test.exists()
    print("✓ نجح التعامل مع MediaItem والتحقق من الحذف الآمن.")

    # 6. فحص وجهات التخزين في file_manager
    dests = file_manager.get_available_storage_destinations()
    assert "internal" in dests
    assert "sdcard" in dests
    assert "is_writable" in dests["internal"]
    assert "requires_saf" in dests["sdcard"]
    print("✓ تم التحقق من واجهة وجهات التخزين وتوافقها مع SAF.")

    # تنظيف
    shutil.rmtree(test_root, ignore_errors=True)
    print("✓ نجح فحص طبقة التخزين الموحدة بالكامل.\n")


def test_saf_and_target_location_simulations() -> None:
    """
    الفحص الآلي الشامل لسيناريوهات SAF ومحاكاة بطاقة SD وحالات الأعطال الثمانية:
    1. internal -> internal
    2. SD SAF -> internal
    3. internal -> SD SAF
    4. both -> SD SAF
    5. فصل SD أثناء الفرز ومنع الـ Fallback الصامت
    6. فقدان URI permission والتوقف الآمن
    7. التراجع Undo لوجهة content:// / SAF URI
    8. نمط Move مع فشل حذف المصدر (التحويل لنسخ آمن وحماية الأصل)
    """
    print("--- 11. فحص محاكاة مسارات SAF والذاكرة الخارجية وسيناريوهات الأمان الثمانية ---")
    import storage_backend
    import file_manager

    sim_root = Path("test_sim_saf_env").resolve()
    shutil.rmtree(sim_root, ignore_errors=True)
    sim_root.mkdir(parents=True, exist_ok=True)

    internal_src_dir = sim_root / "internal_storage"
    internal_dest_dir = sim_root / "internal_dest"
    sd_mount_dir = sim_root / "sd_card_mount"

    internal_src_dir.mkdir(parents=True, exist_ok=True)
    internal_dest_dir.mkdir(parents=True, exist_ok=True)
    sd_mount_dir.mkdir(parents=True, exist_ok=True)

    # 1. اختبار internal -> internal
    f_int1 = internal_src_dir / "doc_exam_01.jpg"
    f_int1.write_bytes(b"INTERNAL EXAM CONTENT " * 200)
    int_loc = storage_backend.TargetLocation(
        storage_type="internal",
        is_saf=False,
        path=internal_dest_dir,
        display_name="الذاكرة الداخلية",
        is_valid=True,
    )
    dest1 = file_manager.copy_to_category(f_int1, "محاضرات ودروس", target_location=int_loc)
    assert isinstance(dest1, Path)
    assert dest1.exists()
    assert dest1.stat().st_size == f_int1.stat().st_size
    print("  [1/8] ✓ internal -> internal: نجح النسخ مع تطابق الحجم بدقة.")

    # 2. اختبار SD SAF -> internal
    sd_tree_uri = f"mock_saf://{sd_mount_dir}"
    sd_file_mock = sd_mount_dir / "external_video.mp4"
    sd_file_mock.write_bytes(b"MOCK EXTERNAL SD VIDEO DATA " * 300)
    sd_item = storage_backend.MediaItem(
        id=f"mock_doc://{sd_file_mock}",
        source_type="content_uri",
        path="",
        uri=f"mock_doc://{sd_file_mock}",
        display_name="external_video.mp4",
        size_bytes=sd_file_mock.stat().st_size,
        storage_id="sdcard",
    )
    dest2 = file_manager.copy_to_category(sd_item, "فيديوهات مضحكة", target_location=int_loc)
    assert isinstance(dest2, Path)
    assert dest2.exists()
    assert dest2.stat().st_size == sd_item.size_bytes
    print("  [2/8] ✓ SD SAF -> internal: نجح دفق الوسائط من SAF إلى الذاكرة الداخلية.")

    # 3. اختبار internal -> SD SAF
    sd_loc = storage_backend.TargetLocation(
        storage_type="sdcard",
        is_saf=True,
        tree_uri=sd_tree_uri,
        display_name="بطاقة الذاكرة الخارجية SAF",
        is_valid=True,
    )
    f_int2 = internal_src_dir / "lecture_photo.jpg"
    f_int2.write_bytes(b"LECTURE PHOTO STREAM DATA " * 150)
    dest3_uri = file_manager.copy_to_category(f_int2, "محاضرات ودروس", target_location=sd_loc)
    assert isinstance(dest3_uri, str)
    assert dest3_uri.startswith("mock_doc://")
    created_sd_file = Path(dest3_uri.replace("mock_doc://", ""))
    assert created_sd_file.exists()
    assert created_sd_file.stat().st_size == f_int2.stat().st_size
    print("  [3/8] ✓ internal -> SD SAF: نجح إنشاء وتدفق الملف إلى مجلد SAF بالبطاقة.")

    # 4. اختبار both -> SD SAF
    # تجهيز ملفين أحدهما من الداخلية والآخر من SAF
    dest4_a = file_manager.copy_to_category(f_int1, "صوري", target_location=sd_loc)
    dest4_b = file_manager.copy_to_category(sd_item, "أفلام ومسلسلات", target_location=sd_loc)
    assert str(dest4_a).startswith("mock_doc://")
    assert str(dest4_b).startswith("mock_doc://")
    print("  [4/8] ✓ both -> SD SAF: تم دمج ومعالجة المصدرين وحفظهما بالبطاقة دون إسقاط أي منهما.")

    # 5. اختبار فصل SD أثناء الفرز ومنع الـ Fallback الصامت
    # محاكاة فصل البطاقة بإزالة مجلد التخزين
    shutil.rmtree(sd_mount_dir, ignore_errors=True)
    disconnected_loc = storage_backend.TargetLocation(
        storage_type="sdcard",
        is_saf=True,
        tree_uri=sd_tree_uri,
        display_name="بطاقة مفصولة",
        is_valid=False,
        error_message="البطاقة تم فصلها",
    )
    caught_disconnect = False
    try:
        file_manager.copy_to_category(f_int1, "محاضرات ودروس", target_location=disconnected_loc)
    except OSError:
        caught_disconnect = True
    assert caught_disconnect is True, "يجب التوقف وإلقاء خطأ عند فصل البطاقة وعدم التحويل الصامت للداخلية!"
    assert f_int1.exists(), "الملف الأصلي يجب أن يظل سليماً دون أي مساس!"
    print("  [5/8] ✓ فصل SD أثناء الفرز: توقف الفرز بأمان مع حماية الأصل ومنع الـ Fallback الصامت.")

    # إعادة تهيئة مجلد الـ SD
    sd_mount_dir.mkdir(parents=True, exist_ok=True)

    # 6. اختبار فقدان URI permission
    storage_backend.save_saf_persisted_uri("")
    loc_no_perm = storage_backend.get_active_target_location("sdcard")
    assert loc_no_perm.is_valid is False
    assert ("SAF" in loc_no_perm.error_message or "غير متوفرة" in loc_no_perm.error_message)
    print("  [6/8] ✓ فقدان URI permission: تم كشف غياب الإذن بدقة ومطالبة المستخدم به.")

    # 7. اختبار Undo لوجهة content:// / SAF URI
    history_before = file_manager.get_transfer_history(base_path=internal_dest_dir)
    # نسجل عملية نسخ إلى SAF
    f_undo_src = internal_src_dir / "undo_test.jpg"
    f_undo_src.write_bytes(b"TEST UNDO CONTENT")
    dest_undo_uri = file_manager.copy_to_category(f_undo_src, "صوري", target_location=sd_loc, base_path=internal_dest_dir)
    undo_file_path = Path(str(dest_undo_uri).replace("mock_doc://", ""))
    assert undo_file_path.exists()
    latest_history = file_manager.get_transfer_history(base_path=internal_dest_dir)
    assert len(latest_history) > 0
    record_id = int(latest_history[0]["id"])
    undo_ok = file_manager.undo_transfer(record_id, base_path=internal_dest_dir)
    assert undo_ok is True
    assert not undo_file_path.exists(), "يجب حذف الملف من SAF الوجهة عند التراجع!"
    assert f_undo_src.exists(), "الملف المصدر يجب أن يظل موجوداً!"
    print("  [7/8] ✓ Undo لوجهة SAF URI: تم حذف الملف من الوجهة بدقة مع بقاء الأصل.")

    # 8. اختبار Move مع فشل حذف المصدر (التحويل لنسخ آمن وحماية الأصل)
    f_move_src = internal_src_dir / "safe_move_test.jpg"
    f_move_src.write_bytes(b"IMPORTANT DATA NEVER LOSE")

    # محاكاة فشل الحذف
    original_delete = storage_backend.delete_media_item
    storage_backend.delete_media_item = lambda item: False
    try:
        dest_moved = file_manager.move_to_category(
            f_move_src, "محاضرات ودروس", target_location=int_loc, base_path=internal_dest_dir, copy_only=False
        )
        assert isinstance(dest_moved, Path) and dest_moved.exists()
        assert f_move_src.exists(), "عند فشل حذف المصدر يجب ألا يُفقد الملف ويُعتبر نسخاً آمناً!"
        # التحقق من أن السجل تم تحويله إلى is_copy = True
        hist = file_manager.get_transfer_history(base_path=internal_dest_dir)
        assert len(hist) > 0
        assert hist[0].get("is_copy") is True
        print("  [8/8] ✓ Move مع فشل حذف المصدر: تم حفظ الوجهة والاحتفاظ بالأصل وتحويل العملية لنسخ آمن.")
    finally:
        storage_backend.delete_media_item = original_delete

    # تنظيف
    shutil.rmtree(sim_root, ignore_errors=True)
    print("✓ نجحت جميع اختبارات محاكاة SAF والسيناريوهات الثمانية بنسبة 100%!\n")


if __name__ == "__main__":
    test_arabic_helper()
    test_file_manager()
    test_classifier_encoding()
    test_face_classifier()
    test_video_classifier()
    test_media_scanner_and_rollback()
    test_service_watcher()
    test_poison_files_and_pending_scan()
    test_export_logs()
    test_unified_storage_backend()
    test_saf_and_target_location_simulations()
    print("==================================================")
    print("  جميع الفحوصات الآلية للوحدات تمت بنجاح 100%!  ")
    print("==================================================")

