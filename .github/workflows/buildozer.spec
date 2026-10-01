[app]
title = Rocket League 3D
package.name = rocketleague3d
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.0
requirements = python3,kivy

# QUESTA RIGA DICE A BUILDOZER DI USARE LA TUA ICONA:
icon.filename = %(source.dir)s/icon.png

orientation = landscape
fullscreen = 1
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
