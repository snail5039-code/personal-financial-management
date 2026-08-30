# PyInstaller spec - Kurima.exe(app.py, 대화형 CLI)와 KurimaTray.exe(tray_app.py, 백그라운드
# 트레이 앱)를 하나의 폴더(dist/Kurima)에 같이 담는다. MERGE로 겹치는 의존성은 한 번만 담는다.
#
# 빌드: pyinstaller kurima.spec

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# 네이티브 바이너리/데이터 파일이 있어서 표준 임포트 스캔만으로는 빠지기 쉬운 패키지들.
for pkg in (
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "sounddevice",
    "pystray",
    "winotify",
    "pycaw",
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += ["win32timezone", "win32com", "win32com.client"]

block_cipher = None

app_a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    excludes=[],
    noarchive=False,
)

tray_a = Analysis(
    ["tray_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    excludes=[],
    noarchive=False,
)

MERGE((app_a, "app", "Kurima"), (tray_a, "tray_app", "KurimaTray"))

app_pyz = PYZ(app_a.pure, app_a.zipped_data, cipher=block_cipher)
app_exe = EXE(
    app_pyz,
    app_a.scripts,
    [],
    exclude_binaries=True,
    name="Kurima",
    console=True,
    icon="kurima.ico",
)

tray_pyz = PYZ(tray_a.pure, tray_a.zipped_data, cipher=block_cipher)
tray_exe = EXE(
    tray_pyz,
    tray_a.scripts,
    [],
    exclude_binaries=True,
    name="KurimaTray",
    console=False,
    icon="kurima.ico",
)

coll = COLLECT(
    app_exe,
    app_a.binaries,
    app_a.zipfiles,
    app_a.datas,
    tray_exe,
    tray_a.binaries,
    tray_a.zipfiles,
    tray_a.datas,
    name="Kurima",
)
