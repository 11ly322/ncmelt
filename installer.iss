; ncmelt installer (Inno Setup 6)
#define AppName "ncmelt"
#define AppVersion "0.1.2alpha"
#define AppPublisher "11ly322"
#define AppURL "https://github.com/11ly322/ncmelt"

[Setup]
AppId={{65D5D881-DCD2-4E73-B26F-D97F2E04C59C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\ncmelt
DefaultGroupName=ncmelt
DisableDirPage=no
DisableProgramGroupPage=yes
AllowNoIcons=yes
LicenseFile=LICENSE
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=release
OutputBaseFilename=ncmelt-Setup-{#AppVersion}
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\ncmelt-gui.exe
UninstallDisplayName=ncmelt
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=0.1.2.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=ncmelt - NCM to MP3 converter
VersionInfoProductName=ncmelt
VersionInfoProductVersion=0.1.2.0
MinVersion=10.0

[Languages]
Name: "chinesesimplified"; MessagesFile: "installer\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked
Name: "addtopath"; Description: "将 ncmelt 添加到 PATH（在终端中直接使用 ncmelt 命令）"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
Source: "dist\ncmelt\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Icons]
Name: "{group}\ncmelt"; Filename: "{app}\ncmelt-gui.exe"; WorkingDir: "{app}"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
Name: "{autodesktop}\ncmelt"; Filename: "{app}\ncmelt-gui.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ncmelt-gui.exe"; Description: "启动 ncmelt"; Flags: nowait postinstall skipifsilent

[Code]
function PosEx(const SubStr, S: string; Offset: Integer): Integer;
var
  I: Integer;
begin
  Result := 0;
  for I := Offset to Length(S) - Length(SubStr) + 1 do
    if Copy(S, I, Length(SubStr)) = SubStr then
    begin
      Result := I;
      exit;
    end;
end;

function NeedsAddPath(Path: string): Boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Path) + ';',
    ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure RemoveFromPath(Path: string);
var
  OrigPath, NewPath, Part: string;
  P, I: Integer;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
    exit;
  NewPath := '';
  P := 1;
  while P <= Length(OrigPath) + 1 do
  begin
    I := PosEx(';', OrigPath + ';', P);
    Part := Copy(OrigPath, P, I - P);
    if (Part <> '') and (CompareText(Part, Path) <> 0) then
    begin
      if NewPath <> '' then
        NewPath := NewPath + ';';
      NewPath := NewPath + Part;
    end;
    P := I + 1;
  end;
  if NewPath <> OrigPath then
    RegWriteExpandStringValue(HKCU, 'Environment', 'Path', NewPath);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
end;
