[app]
title = Novel Reader
package.name = novelreader
package.domain = org.qinyangaaa
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db,json
source.exclude_dirs = .git,__pycache__,.kivy,data
version = 0.1.0
requirements = python3,flet,requests,beautifulsoup4
orientation = portrait
fullscreen = 0





android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
p4a.extra_index_url = https://kivy.org/downloads/simple/

android.accept_sdk_license = True
android.meta_data = android.hardware.vulkan.level:0
android.features = android.hardware.touchscreen
android.arch = arm64-v8a

presplash.filename =
icon.filename =

[buildozer]
log_level = 2
warn_on_root = 1
