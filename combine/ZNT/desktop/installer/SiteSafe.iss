; Build through build-installer.ps1: payload entries are generated from the verified release manifest.
#ifndef PayloadRoot
  #error PayloadRoot is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#define ProductGuid "{3AA70D20-370C-4CBA-BBB2-263596461A2D}"
#define ProductName "路安智巡 · SmartRoad-Inspection"

[Setup]
AppId={{3AA70D20-370C-4CBA-BBB2-263596461A2D}
AppName={#ProductName}
AppVersion={#AppVersion}
AppVerName={#ProductName} {#AppVersion}
AppPublisher=SmartRoad-Inspection 项目团队
AppPublisherURL=https://github.com/Shrek2356/SmartRoad-Highway
AppSupportURL=https://github.com/Shrek2356/SmartRoad-Highway
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription=SmartRoad-Inspection 桌面软件安装程序
DefaultDirName={localappdata}\Programs\SmartRoad-Inspection
DefaultGroupName=路安智巡 SmartRoad-Inspection
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UsePreviousAppDir=yes
UsePreviousTasks=yes
DisableDirPage=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
WizardStyle=modern dynamic
WizardSizePercent=110
SetupIconFile={#PayloadRoot}\desktop\assets\sitesafe.ico
UninstallDisplayIcon={app}\SmartRoad-Inspection.exe
UninstallDisplayName={#ProductName}
LicenseFile={#PayloadRoot}\LICENSE
InfoBeforeFile={#SourcePath}\安装前须知.txt
OutputDir={#OutputRoot}
OutputBaseFilename=SmartRoad-Inspection_Setup_v{#AppVersion}_x64
Compression=lzma2/normal
SolidCompression=yes
AppMutex=Local\SmartRoadInspectionDesktop
CloseApplications=no
RestartApplications=no
SetupLogging=yes
UninstallLogging=yes

[Languages]
Name: "zhcn"; MessagesFile: "compiler:Default.isl,{#SourcePath}\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "在桌面创建快捷方式"; GroupDescription: "快捷方式："

[Files]
; Offline prerequisite is extracted only if the shared Microsoft runtime is absent.
Source: "{#WebViewInstaller}"; Flags: dontcopy noencryption nocompression
#include PayloadInclude
Source: "{#SourcePath}\安装版使用说明.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourcePath}\安装前须知.txt"; DestDir: "{app}"; Flags: ignoreversion

[INI]
; Intentionally retained to identify a data-preserving reinstall destination.
Filename: "{app}\sitesafe-install.ini"; Section: "Setup"; Key: "AppId"; String: "{{3AA70D20-370C-4CBA-BBB2-263596461A2D}"
Filename: "{app}\sitesafe-install.ini"; Section: "Setup"; Key: "Version"; String: "{#AppVersion}"

[Icons]
Name: "{group}\路安智巡 SmartRoad-Inspection"; Filename: "{app}\SmartRoad-Inspection.exe"; WorkingDir: "{app}"; Comment: "道路风险识别、人工复核与处置记录"
Name: "{group}\模型部署助手"; Filename: "{app}\部署助手.bat"; WorkingDir: "{app}"
Name: "{group}\打开软件目录与使用说明"; Filename: "{app}"; WorkingDir: "{app}"
Name: "{group}\卸载路安智巡"; Filename: "{uninstallexe}"
Name: "{userdesktop}\路安智巡 SmartRoad-Inspection"; Filename: "{app}\SmartRoad-Inspection.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\SmartRoad-Inspection.exe"; Description: "立即打开路安智巡（首次默认演示模式，不启动大模型）"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
const
  RuntimeKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  AppGuid = '{#ProductGuid}';

function RuntimeVersionAt(Root: Integer): Boolean;
var Version: String;
begin
  Result := RegQueryStringValue(Root, RuntimeKey, 'pv', Version) and
    (Version <> '') and (Version <> '0.0.0.0');
end;

function HasWebView2(): Boolean;
begin
  Result := RuntimeVersionAt(HKCU) or RuntimeVersionAt(HKLM32);
end;

function DirectoryHasEntries(const Folder: String): Boolean;
var Entry: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Folder) + '*', Entry) then begin
    try
      repeat
        if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
          Result := True;
          Break;
        end;
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

function DirectoryProblem(): String;
var Target, Marker: String;
begin
  Result := '';
  Target := RemoveBackslashUnlessRoot(ExpandFileName(WizardDirValue));
  if (Length(Target) <= 3) or (Copy(Target, 1, 2) = '\\') then begin
    Result := '请选择本机磁盘上的专用软件子目录，不能安装到磁盘根目录或网络共享。';
    Exit;
  end;
  if FileExists(Target) then begin
    Result := '安装位置是一个文件，请选择专用软件文件夹。';
    Exit;
  end;
  Marker := AddBackslash(Target) + 'sitesafe-install.ini';
  if DirectoryHasEntries(Target) and (GetIniString('Setup', 'AppId', '', Marker) <> AppGuid) then
    Result := '该目录已有其他文件，且不是本安装程序管理的版本。为避免覆盖资料，请选择新的空子目录。旧版资料可在软件内通过备份与恢复迁移。';
end;

function DataServicesProblem(const Folder: String): String;
var PythonPath, HelperPath, BackendPath, Arguments: String; ResultCode: Integer;
begin
  Result := '';
  PythonPath := AddBackslash(Folder) + 'python-runtime\python.exe';
  HelperPath := AddBackslash(Folder) + 'desktop';
  BackendPath := AddBackslash(Folder) + 'detectmodel\Site_Safety_OpenRisk';
  if not FileExists(PythonPath) then Exit;
  Arguments := '-I -c "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);' +
    'from environment_check import assert_data_services_stopped;' +
    'assert_data_services_stopped(Path(sys.executable),Path(sys.argv[2]))" "' +
    HelperPath + '" "' + BackendPath + '"';
  if not Exec(PythonPath, Arguments, Folder, SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := '无法检查此目录的后台服务。请先关闭软件及其后台服务，再重试。'
  else if ResultCode <> 0 then
    Result := '此目录仍有业务后台或检测服务运行，或环境检查失败。请先正常关闭软件；必要时运行该目录的 stop-platform.bat，再重试。安装程序不会强制终止模型。';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var Problem: String;
begin
  Result := True;
  // Silent installs receive the same validation in PrepareToInstall, which exits with an error code.
  if (CurPageID = wpSelectDir) and not WizardSilent then begin
    Problem := DirectoryProblem();
    Result := Problem = '';
    if not Result then MsgBox(Problem, mbError, MB_OK);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ProbePath, Target: String; ResultCode: Integer;
begin
  Result := DirectoryProblem();
  if Result <> '' then Exit;
  Target := ExpandConstant('{app}');
  Result := DataServicesProblem(Target);
  if Result <> '' then Exit;
  if not ForceDirectories(Target) then begin
    Result := '无法创建安装目录。请使用默认的当前用户目录，或选择有写入权限的专用目录。';
    Exit;
  end;
  ProbePath := AddBackslash(Target) + '.sitesafe-setup-write-probe.tmp';
  if FileExists(ProbePath) then begin
    Result := '目录内存在未完成安装的写入检查文件 .sitesafe-setup-write-probe.tmp，请确认没有其他安装进程后移走该文件，再重试。';
    Exit;
  end;
  if not SaveStringToFile(ProbePath, 'SiteSafe setup write check', False) then begin
    Result := '此目录没有写入权限，软件将无法保存配置。请改用默认安装目录。';
    Exit;
  end;
  DeleteFile(ProbePath);
  if HasWebView2() then begin
    Log('WebView2 is already installed; the shared runtime is unchanged.');
    Exit;
  end;
  WizardForm.StatusLabel.Caption := '正在安装 Microsoft WebView2 窗口运行环境，请稍候……';
  ExtractTemporaryFile('MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'),
      '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
    Result := 'WebView2 安装程序无法启动。请检查系统限制与安全软件提示，然后重试；不要关闭系统安全保护。';
    Exit;
  end;
  Log('WebView2 installer exit code: ' + IntToStr(ResultCode));
  if not HasWebView2() then begin
    Result := 'WebView2 未安装成功（返回码 ' + IntToStr(ResultCode) + '）。请检查 Microsoft EdgeUpdate 安装日志，或请管理员安装 WebView2 后重试。';
    Exit;
  end;
  if (ResultCode <> 0) and (ResultCode <> 3010) then begin
    Result := 'WebView2 返回异常状态 ' + IntToStr(ResultCode) + '，本次不继续安装。请检查运行环境后重试。';
    Exit;
  end;
  if ResultCode = 3010 then begin
    NeedsRestart := True;
    Result := 'WebView2 要求重新启动 Windows。请先重启，再重新运行本安装包。';
  end;
end;

function InitializeUninstall(): Boolean;
var Problem: String;
begin
  Problem := DataServicesProblem(ExpandConstant('{app}'));
  Result := Problem = '';
  if not Result then SuppressibleMsgBox(Problem, mbError, MB_OK, IDOK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    MsgBox('程序和快捷方式已卸载。模型、已导入规范、业务记录和个人配置不会自动删除，仍保留在原目录：' + #13#10 +
      ExpandConstant('{app}') + #13#10#13#10 + '确认不再需要后，可自行备份或清理。', mbInformation, MB_OK);
end;
