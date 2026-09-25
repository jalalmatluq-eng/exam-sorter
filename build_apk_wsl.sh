#!/bin/bash
# =============================================================
# Build APK via WSL for Wasaet Dhakiyah v2.0.0
# =============================================================
set -e

cd /mnt/d/exam-sorter

echo "=========================================="
echo "  بدء بناء APK لتطبيق وسائط ذكية v2.0.0"
echo "=========================================="

# Build APK and pipe output to log file
buildozer -v android debug 2>&1 | tee build_wsl.log

echo "=========================================="
echo "  فحص ملف الـ APK الناتج:"
echo "=========================================="
if ls bin/*.apk 1> /dev/null 2>&1; then
    echo "تم إنشاء الـ APK بنجاح!"
    ls -lh bin/*.apk
    # نسخ الـ APK إلى المجلد الرئيسي ليسهل على المستخدم سحبه
    cp bin/*.apk /mnt/d/exam-sorter/ 2>/dev/null || true
    echo "تم نسخ الـ APK إلى: d:\exam-sorter\"
else
    echo "لم يتم العثور على APK بعد"
fi
