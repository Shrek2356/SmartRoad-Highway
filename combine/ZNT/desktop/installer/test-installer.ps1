param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$TestParent,
    [switch]$Headless,
    [ValidateRange(1,120)][int]$HeadlessSeconds = 20,
    [string]$ApiProbe = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$installerPath = (Get-Item -LiteralPath $Installer).FullName
$appId = '{3AA70D20-370C-4CBA-BBB2-263596461A2D}'
$registration = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\${appId}_is1"
if (Test-Path -LiteralPath $registration) { throw '本用户已经安装正式版本，集成测试不会改动它；请在干净测试用户中运行' }
$defaultGroup = Join-Path ([Environment]::GetFolderPath('Programs')) '路安智巡 SmartRoad-Inspection'
if (Test-Path -LiteralPath $defaultGroup) { throw '开始菜单已有同名目录，测试不会覆盖既有快捷方式；请在干净测试用户中运行' }
$busyPorts = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -in 5173,8800,8810,8080)
if ($busyPorts.Count) { throw '平台端口已有服务，测试不会关闭它；请先正常关闭后重试' }
$testRoot = Join-Path ([IO.Path]::GetFullPath($TestParent)) ('qa-' + [guid]::NewGuid().ToString('N').Substring(0,12))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$installDirectory = Join-Path $testRoot '中文 空格\App'
$groupName = 'SmartRoad Installer QA ' + [IO.Path]::GetFileName($testRoot)
$checks = [Collections.Generic.List[object]]::new()
function Record-Check([string]$Name, [bool]$Passed) {
    $checks.Add([ordered]@{name=$Name; passed=$Passed})
    Write-Host "$Name : $Passed"
    if (-not $Passed) { throw "检查失败：$Name；测试资料保留在 $testRoot" }
}
function Run-Setup([string]$Name, [string]$Directory) {
    $arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',
        ('/DIR="' + $Directory + '"'), ('/GROUP="' + $groupName + '"'), '/TASKS=""', ('/LOG="' + (Join-Path $testRoot "$Name.log") + '"'))
    $process = Start-Process -FilePath $installerPath -ArgumentList $arguments -PassThru -WindowStyle Hidden
    $deadline = (Get-Date).AddMinutes(5)
    while (-not $process.WaitForExit(1000)) {
        if ((Get-Date) -gt $deadline) { throw "安装检查超时，保留当前进程 $($process.Id) 和测试目录供诊断" }
    }
    return $process.ExitCode
}
function Save-Fixture([string]$Relative, [string]$Content) {
    $target = Join-Path $installDirectory $Relative
    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
    [IO.File]::WriteAllText($target, $Content, [Text.UTF8Encoding]::new($false))
    return $target
}
try {
    $foreign = Join-Path $testRoot 'ForeignData'
    New-Item -ItemType Directory -Path $foreign | Out-Null
    [IO.File]::WriteAllText((Join-Path $foreign 'keep.txt'), 'unrelated test data')
    Record-Check '拒绝覆盖已有无关资料目录' ((Run-Setup 'reject-foreign' $foreign) -ne 0)
    Record-Check '无关资料没有改变' ((Get-Content -LiteralPath (Join-Path $foreign 'keep.txt') -Raw) -eq 'unrelated test data')

    $mutex = [Threading.Mutex]::new($false, 'Local\SmartRoadInspectionDesktop')
    try { Record-Check '应用运行标志存在时拒绝安装' ((Run-Setup 'reject-running' $installDirectory) -ne 0) }
    finally { $mutex.Dispose() }

    Record-Check '中文空格目录首次安装成功' ((Run-Setup 'fresh-install' $installDirectory) -eq 0)
    $registered = Get-ItemProperty -LiteralPath $registration
    Record-Check '已安装应用注册到正确位置' ($registered.InstallLocation.TrimEnd('\') -eq $installDirectory)
    # Inno uses DefaultGroupName when the group selection page is disabled.
    $group = Join-Path ([Environment]::GetFolderPath('Programs')) $registered.'Inno Setup: Icon Group'
    $shortcuts = @(Get-ChildItem -LiteralPath $group -Filter '*.lnk')
    Record-Check '开始菜单包含软件及辅助入口' ($shortcuts.Count -eq 4)
    $shellObject = New-Object -ComObject WScript.Shell
    $mainShortcut = $shellObject.CreateShortcut((Join-Path $group '路安智巡 SmartRoad-Inspection.lnk'))
    Record-Check '主快捷方式目标与工作目录正确' ($mainShortcut.TargetPath -eq (Join-Path $installDirectory 'SmartRoad-Inspection.exe') -and $mainShortcut.WorkingDirectory -eq $installDirectory)
    $manifest = Get-Content -LiteralPath (Join-Path $installDirectory 'release-manifest.json') -Raw -Encoding utf8 | ConvertFrom-Json
    $mismatches = @($manifest | Where-Object {
        $target = Join-Path $installDirectory $_.path
        -not (Test-Path -LiteralPath $target -PathType Leaf) -or (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $_.sha256
    })
    Record-Check '全部安装载荷逐项哈希一致' ($mismatches.Count -eq 0)

    $smokeArguments = if ($Headless) { "--profile demo --headless-smoke-seconds $HeadlessSeconds" } else { '--profile demo --smoke-test-seconds 45' }
    $appProcess = Start-Process -FilePath (Join-Path $installDirectory 'SmartRoad-Inspection.exe') -ArgumentList $smokeArguments -WorkingDirectory $installDirectory -WindowStyle Hidden -PassThru
    $services = @('http://127.0.0.1:5173/desktop-api/health', 'http://127.0.0.1:8800/api/health', 'http://127.0.0.1:8810/api/detect/health')
    $ready = $false
    $deadline = (Get-Date).AddSeconds(100)
    while ((Get-Date) -lt $deadline -and -not $appProcess.HasExited) {
        try {
            $responses = @($services | ForEach-Object { Invoke-RestMethod -Uri $_ -TimeoutSec 2 -NoProxy })
            $ready = ($responses.Count -eq 3 -and @($responses | Where-Object { $_.ok -ne $true }).Count -eq 0)
            if ($ready) { break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    Record-Check '安装版 EXE 带起前端业务后台检测桥' $ready
    Record-Check '登录页面可访问' ((Invoke-WebRequest -Uri 'http://127.0.0.1:5173/login' -NoProxy -TimeoutSec 5).StatusCode -eq 200)
    $health = Invoke-RestMethod -Uri $services[0] -NoProxy -TimeoutSec 5
    $installedVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $installDirectory 'SmartRoad-Inspection.exe')).ProductVersion
    Record-Check '运行服务与 EXE 版本一致' ($health.version -eq $installedVersion)
    $login = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/business-api/api/auth/login' -Method Post -ContentType 'application/json' -Body '{"username":"admin","password":"admin123"}' -NoProxy -TimeoutSec 5
    $knowledge = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/business-api/api/knowledge' -Headers @{Authorization=('Bearer ' + $login.token)} -NoProxy -TimeoutSec 10
    Record-Check '全新安装自动导入道路法规条款' ($knowledge.chunk_count -ge 10)
    if ($ApiProbe) {
        & (Join-Path $installDirectory 'python-runtime\python.exe') -B -X utf8 $ApiProbe --base-url 'http://127.0.0.1:5173' --app-root $installDirectory --record (Join-Path $testRoot 'road-api-probe.json')
        Record-Check '安装版道路接口与报告链路复验' ($LASTEXITCODE -eq 0)
    }
    $stopDeadline = (Get-Date).AddSeconds([math]::Max(55, $HeadlessSeconds + 15))
    while (-not $appProcess.WaitForExit(1000)) {
        if ((Get-Date) -gt $stopDeadline) { throw "应用定时烟测未正常结束：PID $($appProcess.Id)" }
    }
    Record-Check '安装程序服务烟测正常退出' ($appProcess.ExitCode -eq 0)
    if ($Headless) {
        $smokeRecord = Get-Content -LiteralPath (Join-Path $installDirectory 'runtime\desktop\headless-smoke.json') -Raw -Encoding utf8 | ConvertFrom-Json
        Record-Check '无窗口烟测完成记录有效' ($smokeRecord.ok -and $smokeRecord.mode -eq 'headless-services')
    }
    $remaining = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -in 5173,8800,8810,8080)
    Record-Check '退出后模型和平台端口无残留' ($remaining.Count -eq 0)

    $fixtures = [Collections.Generic.List[string]]::new()
    $settings = Get-Content -LiteralPath (Join-Path $installDirectory 'desktop-settings.json') -Raw -Encoding utf8 | ConvertFrom-Json
    $settings.window_width = 1360
    $fixtures.Add((Save-Fixture 'desktop-settings.json' ($settings | ConvertTo-Json)))
    $initialPath = 'detectmodel\Site_Safety_OpenRisk\configs\road_runtime_initial_settings.json'
    $initial = Get-Content -LiteralPath (Join-Path $installDirectory $initialPath) -Raw -Encoding utf8 | ConvertFrom-Json
    $initial.qwen_model_path = '../../models/user-selected-test.gguf'
    $fixtures.Add((Save-Fixture $initialPath ($initial | ConvertTo-Json)))
    foreach ($relative in @('detectmodel\Site_Safety_OpenRisk\road_knowledge_base\qa_keep.txt', 'detectmodel\Site_Safety_OpenRisk\road_app_data\qa_keep.txt',
        'detectmodel\Site_Safety_OpenRisk\outputs\qa_keep.txt', 'models\qa_keep.txt', 'env\qa_keep.txt', 'detectmodel\Site_Safety_OpenRisk\.env')) {
        $fixtures.Add((Save-Fixture $relative 'SITESAFE_INSTALLER_QA=keep'))
    }
    foreach ($database in (Get-ChildItem -LiteralPath (Join-Path $installDirectory 'detectmodel\Site_Safety_OpenRisk\road_app_data') -File -Recurse | Where-Object Extension -in '.db','.sqlite','.sqlite3')) {
        $fixtures.Add($database.FullName)
    }
    $before = @{}
    foreach ($file in $fixtures) { $before[$file] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash }
    $templatePath = Join-Path $installDirectory 'detectmodel\Site_Safety_OpenRisk\configs\road_demo.yaml'
    $templateHash = (Get-FileHash -LiteralPath $templatePath -Algorithm SHA256).Hash
    [IO.File]::AppendAllText($templatePath, "`n# installer QA: simulate an obsolete managed template`n")
    Record-Check '同版本重装成功' ((Run-Setup 'reinstall' $installDirectory) -eq 0)
    Record-Check '重装更新受版本管理的道路流程模板' ((Get-FileHash -LiteralPath $templatePath -Algorithm SHA256).Hash -eq $templateHash)
    Record-Check '重装保留个人配置与业务资料' (@($fixtures | Where-Object { (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash -ne $before[$_] }).Count -eq 0)
    $uninstaller = Join-Path $installDirectory 'unins000.exe'
    Record-Check '卸载器位于本次隔离安装目录' ((Test-Path -LiteralPath $uninstaller) -and [IO.Path]::GetFullPath($uninstaller).StartsWith($testRoot + '\', [StringComparison]::OrdinalIgnoreCase))
    $process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="' + (Join-Path $testRoot 'uninstall.log') + '"')) -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(55000)) { throw "卸载检查尚未结束：PID $($process.Id)" }
    Record-Check '卸载成功且程序注册清除' ($process.ExitCode -eq 0 -and -not (Test-Path -LiteralPath $registration))
    Record-Check '程序和开始菜单快捷方式已移除' (-not (Test-Path -LiteralPath (Join-Path $installDirectory 'SmartRoad-Inspection.exe')) -and -not (Test-Path -LiteralPath $group))
    Record-Check '卸载保留个人配置业务资料环境和模型目录' (@($fixtures | Where-Object { -not (Test-Path -LiteralPath $_) -or (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash -ne $before[$_] }).Count -eq 0)
    Record-Check '重装识别标记保留' (Test-Path -LiteralPath (Join-Path $installDirectory 'sitesafe-install.ini'))
} finally {
    [ordered]@{installer=$installerPath; sha256=(Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash;
        test_root=$testRoot; completed_at=(Get-Date).ToUniversalTime().ToString('o'); checks=@($checks.ToArray());
        models_executed=$false; native_window_tested=(-not $Headless); notes='Current Windows user; existing WebView2. Missing-runtime installation and physical new-device compatibility are not claimed.'
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $testRoot 'integration-result.json') -Encoding utf8
    Write-Host "测试记录：$testRoot\integration-result.json"
}
