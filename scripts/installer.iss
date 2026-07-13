; Inno Setup script for Speakr-Setup.exe — built by .github/workflows/release.yml
; from the PyInstaller onedir output in dist\Speakr. Per-user install
; (PrivilegesRequired=lowest): no admin/UAC prompt, lands in
; %LOCALAPPDATA%\Programs\Speakr, Start Menu shortcut always, desktop
; shortcut optional, offers to launch Speakr when the wizard finishes.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7C1E5A90-52F3-4B8A-9C1D-1A6B33F0E2D4}
AppName=Speakr
AppVersion={#AppVersion}
AppPublisher=Speakr
DefaultDirName={localappdata}\Programs\Speakr
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..
OutputBaseFilename=Speakr-Setup
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\Speakr.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\Speakr\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: desktopicon; Description: "Create a &desktop shortcut"

[Icons]
Name: "{autoprograms}\Speakr"; Filename: "{app}\Speakr.exe"
Name: "{autodesktop}\Speakr"; Filename: "{app}\Speakr.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Speakr.exe"; Description: "Launch Speakr now"; Flags: nowait postinstall skipifsilent
