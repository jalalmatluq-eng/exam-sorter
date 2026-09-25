#!/bin/bash
# =============================================================
# Build APK via WSL Native Linux (ext4) for Wasaet Dhakiyah v2.0.0
# =============================================================
set -e

echo "=========================================="
echo "  بدء بناء APK لتطبيق وسائط ذكية v2.0.0"
echo "=========================================="

export ax_cv_c_float_words_bigendian=no

BUILD_DIR="/root/build_wasaet"
mkdir -p "$BUILD_DIR"

echo "تحديث ملفات المشروع إلى بيئة لينكس الأصلية السريعة..."
rsync -a \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='temp' \
  --exclude='test_data' \
  --exclude='MediaSorter' \
  --exclude='test_media_input' \
  --exclude='.buildozer' \
  --exclude='bin' \
  --exclude='امثلة*' \
  /mnt/d/exam-sorter/ "$BUILD_DIR/"

cd "$BUILD_DIR"

echo "تأكيد توافق إصدار بايثون 3.11 مع حزم المشروع..."
python3 /mnt/d/exam-sorter/patch_p4a.py

echo "تشغيل Buildozer في بيئة ext4..."
buildozer -v android debug 2>&1 | tee /mnt/d/exam-sorter/build_wsl.log

echo "=========================================="
echo "  فحص ملف الـ APK الناتج:"
echo "=========================================="
mkdir -p /mnt/d/exam-sorter/bin
if ls bin/*.apk 1> /dev/null 2>&1; then
    echo "تم إنشاء الـ APK بنجاح!"
    ls -lh bin/*.apk
    cp bin/*.apk /mnt/d/exam-sorter/bin/ 2>/dev/null || true
    cp bin/*.apk /mnt/d/exam-sorter/ 2>/dev/null || true
    echo "تم نسخ الـ APK إلى: d:/exam-sorter/"
else
    echo "لم يتم العثور على APK بعد"
fi
