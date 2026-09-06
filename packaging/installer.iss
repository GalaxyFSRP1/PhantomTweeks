; Phantom Tweeks installer — Inno Setup 6
#define AppName        "Phantom Tweeks"
#define AppVersion     "0.2.4"
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

[Dirs]
; Create the per-user data tree during installation rather than lazily on
; first run. If a folder cannot be created later (locked-down profile, roaming
; profile quirk) the app would fail at the worst moment - when the user is
; trying to back something up. Creating it here surfaces the problem while the
; installer is still on screen.
; Note {localappdata} here is the INSTALLING user's profile. Other users get
; their own tree on first run; see EnsureUserData in [Code].
Name: "{localappdata}\PhantomTweeks";           Flags: uninsneveruninstall
Name: "{localappdata}\PhantomTweeks\backups";  Flags: uninsneveruninstall
Name: "{localappdata}\PhantomTweeks\logs";     Flags: uninsneveruninstall
Name: "{localappdata}\PhantomTweeks\logs\crash"; Flags: uninsneveruninstall
Name: "{localappdata}\PhantomTweeks\profiles"; Flags: uninsneveruninstall
Name: "{localappdata}\PhantomTweeks\snapshots"; Flags: uninsneveruninstall
Name: "{localappdata}\PhantomTweeks\updates";  Flags: uninsneveruninstall

[Files]
Source: "..\dist\PhantomTweeks.exe";          DestDir: "{app}"; Flags: ignoreversion
; Update.exe is installed alongside the app. It cannot live inside it:
; Windows locks a running executable, so the updater must be separate.
Source: "..\dist\Update.exe";                 DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\docs\*";                          DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs
Source: "..\assets\phantom.ico";              DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Check for Updates";  Filename: "{app}\Update.exe"
; Inno generates unins000.exe automatically. Giving it a plainly named
; shortcut means users can find it without hunting through Add/Remove.
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{group}\Self-Test";          Filename: "{app}\{#AppExeName}"; Parameters: "doctor"
Name: "{group}\Restore Everything"; Filename: "{app}\{#AppExeName}"; Parameters: "restore --all"
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"
Name: "{group}\Privacy Policy";       Filename: "{app}\docs\PRIVACY.md"
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
; Write the default settings file if the user does not already have one.
; Every value here is the safe default: nothing automatic is enabled.
Filename: "{app}\{#AppExeName}"; Parameters: "config --init"; \
    Flags: runhidden waituntilterminated; StatusMsg: "Preparing your settings..."

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

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: string;
begin
  if CurStep = ssPostInstall then
  begin
    DataDir := ExpandConstant('{localappdata}\PhantomTweeks');
    if not DirExists(DataDir) then
    begin
      { Do not fail the install over this - the app recreates the tree on
        first run. But say so now rather than letting it surprise the user
        later, when they are trying to take a backup. }
      MsgBox('Phantom Tweeks could not create its data folder:' + #13#10 +
             DataDir + #13#10#13#10 +
             'The app will try again on first launch. If backups do not ' +
             'work, check the permissions on that folder.',
             mbInformation, MB_OK);
    end;
  end;
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
