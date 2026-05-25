[app]

title = Novel Reader
package.name = novelreader
package.domain = org.qinyangaaa

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,txt,md,json
source.exclude_dirs = .git,__pycache__,.kivy,data

version = 0.1.0

requirements = python3,kivy,requests,beautifulsoup4

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True

presplash.filename =
icon.filename =

log_level = 2
warn_on_root = 1

[buildozer]

log_level = 2
