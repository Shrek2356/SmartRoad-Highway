param(
    [string]$Destination = 'E:\work\智慧交通\软件包',
    [string]$Name = 'SmartRoad-Inspection_Desktop_v1.4.5_road'
)
$ErrorActionPreference = 'Stop'
$appSource = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $Destination $Name))
$destinationRoot = [IO.Path]::GetFullPath($Destination).TrimEnd('\') + '\'
if (-not $releaseRoot.StartsWith($destinationRoot, [StringComparison]::OrdinalIgnoreCase)) { throw '交付路径越界' }
if (Test-Path -LiteralPath $releaseRoot) { throw "目标已存在，请选择新的交付目录：$releaseRoot" }
$zip = Join-Path $Destination "$Name.zip"
if (Test-Path -LiteralPath $zip) { throw "压缩包已存在：$zip" }
foreach ($required in @('desktop-dist\SmartRoad-Inspection.exe','pc-admin\dist\index.html','python-runtime\python.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $appSource $required))) { throw "缺少构建产物 $required" }
}
$frontendVersion = (Get-Content -LiteralPath (Join-Path $appSource 'pc-admin\package.json') -Raw | ConvertFrom-Json).version
$exeVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $appSource 'desktop-dist\SmartRoad-Inspection.exe')).ProductVersion
if ($frontendVersion -ne $exeVersion) { throw "EXE 与前端源码版本不一致，请先重新构建两者：$exeVersion / $frontendVersion" }
& (Join-Path $appSource 'python-runtime\python.exe') -B -I -c 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from environment_check import check_python; check_python(Path(sys.executable))' (Join-Path $appSource 'desktop')
if ($LASTEXITCODE -ne 0) { throw '随包 Python 基础依赖检查失败，未生成交付目录' }
New-Item -ItemType Directory -Path $releaseRoot | Out-Null
# Exclude inactive construction assets by absolute path; backend examples/road_knowledge stays bundled.
$excludedPaths = @(
    (Join-Path $appSource 'desktop\dist'),
    (Join-Path $appSource 'detectmodel\Site_Safety_OpenRisk\knowledge_base'),
    (Join-Path $appSource 'docs\legacy-construction-20260921')
)
foreach ($base in @('pc-admin\public', 'pc-admin\dist')) {
    foreach ($folder in @('examples', 'outcomes', 'results', 'media')) {
        $excludedPaths += Join-Path $appSource "$base\$folder"
    }
}
function Copy-Tree([string]$relative) {
    $from = Join-Path $appSource $relative
    if (-not (Test-Path -LiteralPath $from)) { return }
    $to = Join-Path $releaseRoot $relative
    & robocopy $from $to /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD __pycache__ .pytest_cache .venv node_modules app_data road_app_data outputs road_knowledge_base runtime build 'build-*' desktop-dist .git @excludedPaths /XF .env '*.log' '*.pyc' '*.pyo' '*.spec' '*.db' '*.sqlite*' '*.pt' '*.pth' '*.gguf' '*.safetensors' 'runtime_initial_settings.json' 'threshold_overrides.json' 'road_local_qwen.yaml' 'road_notify_targets.json' | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "复制失败：$relative" }
}
# Runtime node_modules is not required; precompiled frontend needs no Node.
Copy-Tree 'python-runtime'
Copy-Tree 'pc-admin\dist'
Copy-Tree 'pc-admin\public'
Copy-Tree 'pc-admin\src'
Copy-Tree 'pc-admin\tests'
Copy-Tree 'detectmodel\Site_Safety_OpenRisk'
Copy-Tree 'desktop'
Copy-Tree 'requirements'
Copy-Tree 'docs'
$historyGuide = Join-Path $appSource '..\..\docs\DETECTION_HISTORY.md'
if (Test-Path -LiteralPath $historyGuide) {
    Copy-Item -LiteralPath $historyGuide -Destination (Join-Path $releaseRoot 'docs\DETECTION_HISTORY.md')
}
foreach ($file in @('requirements.txt','LICENSE','THIRD_PARTY_NOTICE.md','COMPETITION_SUBMISSION_NOTICE.md','部署助手.bat','start-local-qwen.bat','stop-platform.bat')) {
    $path = Join-Path $appSource $file
    if (-not (Test-Path -LiteralPath $path) -and $file -in @('LICENSE','THIRD_PARTY_NOTICE.md','COMPETITION_SUBMISSION_NOTICE.md')) {
        $path = Join-Path $appSource "..\..\$file"
    }
    if (Test-Path -LiteralPath $path) { Copy-Item -LiteralPath $path -Destination (Join-Path $releaseRoot $file) }
}
# A developer-selected absolute Python path must never leak into a portable release.
[ordered]@{ profile='demo'; backend_python='python-runtime/python.exe'; business_port=8800; bridge_port=8810; frontend_port=5173; window_width=1440; window_height=900; confirm_close=$true } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $releaseRoot 'desktop-settings.json') -Encoding utf8
foreach ($file in @('package.json','package-lock.json','vite.config.js','index.html')) {
    Copy-Item -LiteralPath (Join-Path $appSource "pc-admin\$file") -Destination (Join-Path $releaseRoot "pc-admin\$file")
}
Copy-Item -LiteralPath (Join-Path $appSource 'desktop-dist\SmartRoad-Inspection.exe') -Destination (Join-Path $releaseRoot 'SmartRoad-Inspection.exe')
Copy-Item -LiteralPath (Join-Path $appSource 'desktop\installer\安装版使用说明.md') -Destination (Join-Path $releaseRoot 'README.md')
# A fresh delivery uses only documented in-package locations, never the developer's model paths.
[ordered]@{
    qwen_enabled=$true; qwen_autostart=$false; yolo_enabled=$false; sam3_enabled=$true; clip_enabled=$false
    llama_server_path='../../third_party/llama.cpp/llama-server.exe'
    qwen_model_path='../../models/qwen/Qwen3-VL-8B-Instruct-Q4_K_M.gguf'
    qwen_mmproj_path='../../models/qwen/mmproj-BF16.gguf'
    qwen_base_url='http://127.0.0.1:8080/v1/chat/completions'
    sam3_repo_path='../../third_party/sam3-main'; sam3_checkpoint_path='../../models/sam3/sam3.pt'
    clip_checkpoint_path='../../models/clip/ViT-L-14.pt'
    yolo_css_weights_path=''
    yolo_construction_weights_path=''
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $releaseRoot 'detectmodel\Site_Safety_OpenRisk\configs\road_runtime_initial_settings.json') -Encoding utf8
[ordered]@{ risk_overrides=@{}; history=@() } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $releaseRoot 'detectmodel\Site_Safety_OpenRisk\configs\road_threshold_overrides.json') -Encoding utf8
Copy-Item -LiteralPath (Join-Path $appSource 'desktop\start-desktop.bat') -Destination (Join-Path $releaseRoot 'start-platform.bat')
# Retain source public/ assets alongside the compiled app for full development handoff.
Copy-Item -LiteralPath (Join-Path $appSource 'desktop\restore-frontend-assets.ps1') -Destination (Join-Path $releaseRoot 'pc-admin\restore-frontend-assets.ps1')
# Verify the copied interpreter, not just the developer copy, before sealing the manifest.
& (Join-Path $releaseRoot 'python-runtime\python.exe') -B -I -c 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from environment_check import check_python; check_python(Path(sys.executable))' (Join-Path $releaseRoot 'desktop')
if ($LASTEXITCODE -ne 0) { throw '交付目录中的 Python 基础依赖检查失败，未生成 ZIP' }
& (Join-Path $releaseRoot 'python-runtime\python.exe') -B -I -c 'import sys; from pathlib import Path; root=Path(sys.argv[1]); sys.path.insert(0,str(root/"desktop/installer")); from payload_manifest import assert_release_file; [assert_release_file(p.relative_to(root).as_posix()) for p in root.rglob("*") if p.is_file()]' $releaseRoot
if ($LASTEXITCODE -ne 0) { throw '交付文件边界检查失败，未生成 ZIP' }
$files = Get-ChildItem -LiteralPath $releaseRoot -File -Recurse
$manifest = foreach ($file in $files) {
    [ordered]@{ path=$file.FullName.Substring($releaseRoot.Length+1); bytes=$file.Length; sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $releaseRoot 'release-manifest.json') -Encoding utf8
$zip = Join-Path $Destination "$Name.zip"
if (Test-Path -LiteralPath $zip) { throw "压缩包已存在：$zip" }
Compress-Archive -LiteralPath $releaseRoot -DestinationPath $zip -CompressionLevel Optimal
$archive = Get-Item -LiteralPath $zip
[pscustomobject]@{ Folder=$releaseRoot; Zip=$zip; Bytes=$archive.Length; MiB=[math]::Round($archive.Length/1MB,2); SHA256=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash } | ConvertTo-Json
