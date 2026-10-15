#!/usr/bin/env bash
# Genera PoliReport.apk: una app Android que abre tu sitio de Render (URL en android-url.txt)
set -euo pipefail
URL="$(tr -d '[:space:]' < android-url.txt)"
case "$URL" in https://*.*) ;; *) echo "Pon tu URL https://... en android-url.txt"; exit 1;; esac
case "$URL" in *CAMBIA-ESTO*) echo "Falta cambiar la URL en android-url.txt"; exit 1;; esac

rm -rf build-android && mkdir build-android && cd build-android
npm init -y >/dev/null
npm i @capacitor/core@7 @capacitor/cli@7 @capacitor/android@7
mkdir www && echo '<!doctype html><meta charset="utf-8"><title>PoliReport</title>' > www/index.html
cat > capacitor.config.json <<JSON
{ "appId": "com.polireport.app", "appName": "PoliReport", "webDir": "www",
  "server": { "url": "$URL", "cleartext": false } }
JSON
npx cap add android

# cámara para adjuntar fotos
sed -i 's#</manifest>#    <uses-permission android:name="android.permission.CAMERA" />\n    <uses-feature android:name="android.hardware.camera" android:required="false" />\n</manifest>#' \
  android/app/src/main/AndroidManifest.xml

# ícono propio
pip install -q pillow
python3 - <<'PY'
from PIL import Image
import shutil
src = Image.open("../static/icon-512.png").convert("RGBA")
res = "android/app/src/main/res"
shutil.rmtree(f"{res}/mipmap-anydpi-v26", ignore_errors=True)
for d, s in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
    im = src.resize((s, s), Image.LANCZOS)
    for n in ("ic_launcher.png", "ic_launcher_round.png"):
        im.save(f"{res}/mipmap-{d}/{n}")
PY

cd android
chmod +x gradlew
./gradlew assembleDebug --no-daemon
cp app/build/outputs/apk/debug/app-debug.apk ../../PoliReport.apk
echo "Listo: PoliReport.apk"
