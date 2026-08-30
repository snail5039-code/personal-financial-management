; 커리마 설치 파일. dist/Kurima(kurima.spec으로 PyInstaller 빌드한 결과물)를 그대로 담아
; 관리자 권한 없이 사용자 폴더(%LOCALAPPDATA%\Programs\Kurima)에 설치한다.
;
; 빌드: "C:\Users\snail\AppData\Local\Programs\Inno Setup 6\ISCC.exe" kurima_setup.iss
; (미리 dist\Kurima에 kurima.spec으로 빌드해둔 실행 파일이 있어야 함)

#define MyAppName "커리마"
#define MyAppVersion "1.0"
#define MyAppExeName "Kurima.exe"
#define MyTrayExeName "KurimaTray.exe"

[Setup]
AppId={{9F1C7D2E-6C7A-4C46-9C0E-3B9C2C6D6E11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\Kurima
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=KurimaSetup
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "autostart"; Description: "Windows 시작 시 커리마를 백그라운드로 자동 실행 (트레이 앱)"; Flags: unchecked
Name: "desktopicon"; Description: "바탕화면에 아이콘 만들기"; Flags: unchecked

[Files]
; dist\Kurima 폴더 전체(exe + _internal)를 그대로 설치 - .env/credentials.json/data는
; 사용자 개인 설정/데이터라 설치 파일에 안 담고, 최초 실행 시 앱이 직접 물어보거나
; 사용자가 직접 넣는다.
Source: "dist\Kurima\Kurima.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\Kurima\KurimaTray.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\Kurima\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 메인 아이콘은 트레이 앱(KurimaTray.exe)이다 - 켜두면 백그라운드에서 상주하면서
; 알림·음성 웨이크워드가 동작하고, 트레이 아이콘 우클릭 "커리마 열기"로 대화형 CLI를
; 그때그때 연다. CLI(Kurima.exe)만 바로 열고 싶을 때를 위한 아이콘도 따로 둔다.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyTrayExeName}"
Name: "{group}\{#MyAppName} (대화창 바로 열기)"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyTrayExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyTrayExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyTrayExeName}"; Description: "설치 후 커리마 실행 (트레이 앱)"; Flags: postinstall nowait skipifsilent unchecked
