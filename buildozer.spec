[app]
title = Novel Reader
package.name = novelreader
package.domain = org.qinyangaaa
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db,json
source.exclude_dirs = .git,__pycache__,.kivy,data
version = 0.1.0
requirements = python3==3.11.9,kivy==2.2.1,requests,beautifulsoup4,trafilatura
orientation = portrait
fullscreen = 0





android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24

android.accept_sdk_license = True
android.meta_data = android.hardware.vulkan.level:0
android.features = android.hardware.touchscreen
android.arch = arm64-v8a

presplash.filename =
icon.filename =

[buildozer]
log_level = 2
warn_on_root = 1
