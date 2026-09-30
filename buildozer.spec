[app]

title = CosmoSort
package.name = cosmosort
package.domain = com.cosmosort.ai
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,otf,json,txt
source.include_patterns = assets/*,assets/fonts/*,kv/*,screens/*,utils/*,service/*
source.exclude_patterns = exam_sorter_prompt.md,exam_sorter_full_media_prompt.md,test_modules.py,pyrightconfig.json,basedpyrightconfig.json,.env.example,build_apk_wsl.sh,*.apk,build_wsl.log,patch_p4a.py,*.pyc
source.exclude_dirs = .git,.venv,.idea,__pycache__,test_media_input,ExamSorter,MediaSorter,temp,test_data,.github,الملفات المنظمة,docs,bin,tools,.buildozer
version = 2.0.0
requirements = python3,kivy==2.3.1,kivymd==2.0.0,materialyoucolor==3.0.4,asynckivy,asyncgui,pillow,plyer,python-dotenv,arabic-reshaper==2.1.4,python-bidi==0.4.2,numpy,opencv
presplash.filename = %(source.dir)s/assets/presplash.png
icon.filename = %(source.dir)s/assets/icon.png
orientation = portrait
services = MediaWatcher:service/media_watcher_service.py:foreground:foregroundServiceType=dataSync

# Android specific settings
android.permissions = CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO,INTERNET,MANAGE_EXTERNAL_STORAGE,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,POST_NOTIFICATIONS
android.api = 34
android.minapi = 24
android.ndk = 28c
android.numeric_version = 2
android.archs = arm64-v8a
android.allow_backup = True
android.enable_androidx = True
android.accept_sdk_license = True
android.release_artifact = apk
android.debug_artifact = apk
android.copy_libs = 1

[buildozer]
log_level = 2
warn_on_root = 0
