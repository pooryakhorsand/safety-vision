; Inno Setup 6 script. Compile with build_installer.ps1 (it passes the values below).
;   /DAppName="Safety Vision" /DShortName=SafetyVision /DAppVersion=1.0.0 /DVariant=gpu|cpu

#ifndef AppName
  #error AppName is not defined (use build_installer.ps1)
#endif

[Setup]
AppId={{87E150F3-62D9-456A-B7E9-0CDF57B7B02B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#ShortName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename={#ShortName}-{#AppVersion}-{#Variant}-setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\app\desktop\assets\app.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
#if Variant == "gpu"
; GitHub release files must stay below 2 GiB: the GPU installer is split into slices if it gets that large.
DiskSpanning=yes
DiskSliceSize=1900000000
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Shortcuts:"
Name: "autostart"; Description: "Start {#AppName} when Windows starts"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Dirs]
; Data folder: settings, database, snapshots, logs and model files. Normal users may write to it.
Name: "{commonappdata}\{#ShortName}"; Permissions: users-modify
Name: "{commonappdata}\{#ShortName}\models"; Permissions: users-modify

[Files]
Source: "..\stage\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: VCRedistNeeded
Source: "redist\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: WebView2Needed

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\runtime\web\pythonw.exe"; Parameters: "-m desktop.launcher"; WorkingDir: "{app}\app"; IconFilename: "{app}\app\desktop\assets\app.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\runtime\web\pythonw.exe"; Parameters: "-m desktop.launcher"; WorkingDir: "{app}\app"; IconFilename: "{app}\app\desktop\assets\app.ico"; Tasks: desktopicon
Name: "{commonstartup}\{#AppName}"; Filename: "{app}\runtime\web\pythonw.exe"; Parameters: "-m desktop.launcher"; WorkingDir: "{app}\app"; IconFilename: "{app}\app\desktop\assets\app.ico"; Tasks: autostart

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Microsoft Visual C++ runtime..."; Check: VCRedistNeeded; Flags: waituntilterminated
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2..."; Check: WebView2Needed; Flags: waituntilterminated
Filename: "{app}\runtime\web\pythonw.exe"; Parameters: "-m desktop.launcher"; WorkingDir: "{app}\app"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function VCRedistNeeded: Boolean;
var
  Installed: Cardinal;
begin
  Result := not (RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) and (Installed = 1));
end;

function WebView2Needed: Boolean;
var
  Version: String;
begin
  Result := not (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> ''));
end;

function NvidiaDriverFound: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{sys}\cmd.exe'), '/C nvidia-smi', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function InitializeSetup: Boolean;
var
  ErrorCode: Integer;
begin
  Result := True;
#if Variant == "gpu"
  if not NvidiaDriverFound then
  begin
    if MsgBox('No NVIDIA graphics driver was found.' + #13#10 + #13#10 +
              '{#AppName} still works without it, but video analysis will be slow.' + #13#10 +
              'Open the NVIDIA driver download page now?', mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://www.nvidia.com/Download/index.aspx', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
  end;
#endif
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('Also delete the settings, database, snapshots and logs of {#AppName}?' + #13#10 + #13#10 +
              'Choose No to keep them (for example before installing a newer version).', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{commonappdata}\{#ShortName}'), True, True, True);
  end;
end;
