#!/bin/bash
# Build APK via WSL - Usage: wsl bash /mnt/d/exam-sorter/build_apk_wsl.sh
set -e
cd /mnt/d/exam-sorter
echo Building APK...
sudo apt-get update -qq
sudo apt-get install -y git zip unzip openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev libncurses5-dev cmake libffi-dev libssl-dev build-essential ccache python3-pip python3-dev python3-venv 2>/dev/null
pip3 install --upgrade pip wheel --quiet
pip3 install cython==0.29.37 --quiet
pip3 install buildozer==1.5.0 --quiet
buildozer -v android debug
find bin/ -name "*.apk" 2>/dev/null && echo "APK ready!" || echo "No APK found"
