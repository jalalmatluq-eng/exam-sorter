#!/bin/bash
# =============================================================
# سكريبت بناء APK عبر WSL لتطبيق وسائط ذكية
# كيفية التشغيل:
#   wsl bash /mnt/d/exam-sorter/build_apk_wsl.sh
# =============================================================

set -e

PROJECT_WIN="d:/exam-sorter"
PROJECT_LINUX="/mnt/d/exam-sorter"

echo "=========================================="
echo "  بناء APK - وسائط ذكية v2.0.0"
echo "=========================================="

# 1. تحديث النظام وتثبيت المتطلبات
echo "[1/5] تثبيت متطلبات النظام..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    git zip unzip curl wget \
    openjdk-17-jdk \
    autoconf libtool pkg-config \
    zlib1g-dev libncurses5-dev libncursesw5-dev \
    cmake libffi-dev libssl-dev build-essential \
    ccache python3-pip python3-dev python3-venv

# 2. تثبيت Buildozer
echo "[2/5] تثبيت Buildozer..."
pip3 install --upgrade pip wheel --quiet
pip3 install buildozer==1.5.0 cython==0.29.36 --quiet

# 3. الانتقال لمجلد المشروع
echo "[3/5] الانتقال لمجلد المشروع..."
cd "$PROJECT_LINUX"

# 4. تنظيف بناء قديم إن وجد (اختياري)
if [ "$1" == "--clean" ]; then
    echo "تنظيف مخبأ البناء السابق..."
    buildozer android clean
fi

# 5. بناء APK
echo "[4/5] بدء بناء APK (يستغرق 15-40 دقيقة في المرة الأولى)..."
buildozer -v android debug

echo "[5/5] اكتمل البناء!"
echo ""
echo "مكان الـ APK:"
ls -lh bin/*.apk 2>/dev/null && echo "bin/$(ls bin/*.apk | head -1 | xargs basename)"
echo ""
echo "لنسخ APK لسطح المكتب Windows:"
echo "  cp bin/*.apk /mnt/c/Users/$USER/Desktop/"
