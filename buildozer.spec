[app]

# (str) Title of your application
title = Wasaet Dhakiyah

# (str) Package name
package.name = wasaetdhakiyah

# (str) Package domain (needed for android/ios packaging)
package.domain = com.wasaet.smart

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,otf,json,txt,sh

# (list) Inclusions
source.include_patterns = assets/*,assets/fonts/*,kv/*,screens/*,utils/*,service/*

# (list) Exclusions - keep APK size small
source.exclude_patterns = exam_sorter_prompt.md,exam_sorter_full_media_prompt.md,test_modules.py,pyrightconfig.json,.env.example,build_apk_wsl.sh
source.exclude_dirs = .git,.venv,.idea,__pycache__,test_media_input,ExamSorter,MediaSorter,temp,test_data,.github

# (str) Application versioning
version = 2.0.0

# ==============================================================
# REQUIREMENTS - All packages must have python-for-android recipes
# opencv = p4a built-in recipe (NOT opencv-python which is desktop only)
# numpy  = p4a built-in recipe
# pillow = p4a built-in recipe (PIL)
# plyer  = p4a built-in recipe
# python-dotenv, arabic-reshaper, python-bidi = pure Python, work as-is
# materialyoucolor, asynckivy = pure Python
# NO: onnxruntime, opencv-python, scikit-learn (no p4a recipe)
# ==============================================================
requirements = python3,kivy==2.3.0,kivymd==2.0.0,materialyoucolor,asynckivy,pillow,plyer,python-dotenv,arabic-reshaper,python-bidi,numpy,opencv

# (str) Presplash
presplash.filename = %(source.dir)s/assets/presplash.png

# (str) Icon
icon.filename = %(source.dir)s/assets/icon.png

# (list) Supported orientations
orientation = portrait

# (list) Services
services = MediaWatcher:service/media_watcher_service.py:foreground

#
# Android specific
#

# (list) Permissions
android.permissions = CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO,INTERNET,MANAGE_EXTERNAL_STORAGE,FOREGROUND_SERVICE,POST_NOTIFICATIONS

# (int) Target Android API
android.api = 34

# (int) Minimum API
android.minapi = 24

# (str) Android NDK version
android.ndk = 25b

# (int) Android application version code
android.numeric_version = 2

# (list) Android architectures - arm64 only for smaller APK (most phones are 64-bit)
android.archs = arm64-v8a

# (bool) Allow backup
android.allow_backup = True

# (bool) Enable AndroidX support. Required when using KivyMD.
android.enable_androidx = True

# (str) Release format
android.release_artifact = apk

# (str) Debug format
android.debug_artifact = apk

# (bool) Copy library instead of symlink
android.copy_libs = 1

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 0
