[app]

# (str) Title of your application
title = وسائط ذكية

# (str) Package name
package.name = wasaetdhakiyah

# (str) Package domain (needed for android/ios packaging)
package.domain = com.wasaet.smart

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,otf,json,txt

# (list) List of inclusions using pattern matching
source.include_patterns = assets/*,assets/fonts/*,kv/*,screens/*,utils/*,service/*

# (list) Source files to exclude (dev-only files)
source.exclude_patterns = exam_sorter_prompt.md,exam_sorter_full_media_prompt.md,test_modules.py,pyrightconfig.json,.env.example,امثلة*/*
source.exclude_dirs = .git,.venv,.idea,__pycache__,test_media_input,ExamSorter,MediaSorter,temp

# (str) Application versioning (method 1)
version = 2.0.0

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3,kivy==2.3.0,kivymd==2.0.0,materialyoucolor,asynckivy,pillow,plyer,python-dotenv,arabic-reshaper,python-bidi,numpy,opencv

# (str) Presplash of the application
presplash.filename = %(source.dir)s/assets/presplash.png

# (str) Icon of the application
icon.filename = %(source.dir)s/assets/icon.png

# (list) Supported orientations
# Valid values are: landscape, sensorLandscape, portrait or all
orientation = portrait

# (list) List of services to declare
services = MediaWatcher:service/media_watcher_service.py:foreground

#
# Android specific
#

# (list) Permissions
android.permissions = CAMERA, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES, READ_MEDIA_VIDEO, INTERNET, MANAGE_EXTERNAL_STORAGE, FOREGROUND_SERVICE, POST_NOTIFICATIONS

# (int) Target Android API, should be as high as possible.
android.api = 34

# (int) Minimum API your APK / AAB will support.
android.minapi = 21

# (str) Android NDK version to use
android.ndk = 25b

# (int) Android application number to use for version code
android.numeric_version = 1

# (list) Android architectures to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = arm64-v8a, armeabi-v7a, x86_64

# (bool) Allow backup
android.allow_backup = True

# (bool) Enable AndroidX support. Required when using KivyMD.
android.enable_androidx = True

# (str) The format used to package the app for release mode (aab or apk or aar).
android.release_artifact = apk

# (str) The format used to package the app for debug mode (apk or aar).
android.debug_artifact = apk

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
