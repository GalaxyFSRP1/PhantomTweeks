; Phantom Tweeks installer — Inno Setup 6
#define AppName        "Phantom Tweeks"
#define AppVersion     "0.1.2"
#define AppPublisher   "Phantom Tweeks"
#define AppURL         "https://phantomtweeks.example"
#define AppExeName     "PhantomTweeks.exe"

[Setup]
AppId={{8F2C4A61-9D3E-4B7A-A5C2-7E1D6B0F3A94}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/support
AppUpdatesURL={#AppURL}/download
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\docs\EULA.txt
InfoBeforeFile=..\docs\INSTALL_NOTES.txt
OutputDir=..\dist
OutputBaseFilename=PhantomTweeks-Setup
SetupIconFile=..\assets\phantom.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-machine install requires elevation; the app itself does not.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "addtopath";   Description: "Add Phantom Tweeks to PATH (enables the CLI)"; GroupDescription: "Advanced:"; Flags: unchecked

[Files]
Source: "..\dist\PhantomTweeks.exe";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\*";                          DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs
Source: "..\assets\phantom.ico";              DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"
Name: "{group}\Privacy Policy";       Filename: "{app}\docs\PRIVACY.md"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only removes application files. User data and backups are deliberately kept
; so a user who uninstalls can still restore their previous configuration.
Type: filesandordirs; Name: "{app}\docs"

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    MsgBox('Phantom Tweeks has been removed.' + #13#10#13#10 +
           'Your backups and optimization history were kept in:' + #13#10 +
           ExpandConstant('{localappdata}\PhantomTweeks') + #13#10#13#10 +
           'If you want to revert Phantom Tweeks'' changes, reinstall and use ' +
           'RESTORE EVERYTHING before deleting that folder.',
           mbInformation, MB_OK);
end;
