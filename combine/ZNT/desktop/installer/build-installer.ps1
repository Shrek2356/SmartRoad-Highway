param(
    [Parameter(Mandatory=$true)][string]$PortableZip,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$ExpectedZipSha256 = '',
    [string]$Compiler = '',
    [string]$WebViewInstaller = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$appSource = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $appSource 'python-runtime\python.exe'
$archive = (Get-Item -LiteralPath $PortableZip).FullName
$archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
if ($ExpectedZipSha256 -and $archiveHash -ne $ExpectedZipSha256) { throw '便携包 SHA-256 与指定值不一致' }
if (-not $Compiler) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    $Compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $Compiler -or -not (Test-Path -LiteralPath $Compiler -PathType Leaf)) { throw '请安装 Inno Setup 6.5+ 或通过 -Compiler 指定 ISCC.exe' }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw '构建需要源码目录的便携 Python' }
$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$buildRoot = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
$stage = Join-Path $buildRoot ('stage-' + [guid]::NewGuid().ToString('N'))
Write-Host '正在逐项核验便携包并创建干净安装载荷…'
& $python -I -X utf8 (Join-Path $PSScriptRoot 'payload_manifest.py') $archive $stage | Out-Null
if ($LASTEXITCODE -ne 0) { throw '便携包验证失败，不生成安装程序' }
$payloadInfo = Get-Content -LiteralPath (Join-Path $stage 'payload-info.json') -Raw -Encoding utf8 | ConvertFrom-Json
$version = $payloadInfo.version
$exeVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $payloadInfo.payload 'SmartRoad-Inspection.exe')).ProductVersion
if ($exeVersion -ne $version) { throw "载荷中的 EXE/前端版本不一致：$exeVersion / $version" }
$outputExe = Join-Path $outputRoot "SmartRoad-Inspection_Setup_v${version}_x64.exe"
if (Test-Path -LiteralPath $outputExe) { throw "不覆盖已有交付包，请使用新的输出目录：$outputExe" }
if (-not $WebViewInstaller) {
    $cache = Join-Path $buildRoot 'cache'
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $WebViewInstaller = Join-Path $cache 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
    if (-not (Test-Path -LiteralPath $WebViewInstaller -PathType Leaf)) {
        Write-Host '首次构建：从 Microsoft 下载离线 WebView2（客户端安装不再下载）…'
        Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124701' -OutFile $WebViewInstaller
    }
}
$WebViewInstaller = (Get-Item -LiteralPath $WebViewInstaller).FullName
if ([IO.Path]::GetFileName($WebViewInstaller) -ne 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe') { throw 'WebView2 离线安装文件名不匹配' }
$signature = Get-AuthenticodeSignature -LiteralPath $WebViewInstaller
if ($signature.Status.ToString() -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=Microsoft Corporation(,|$)') {
    throw 'WebView2 文件没有有效 Microsoft 发布者签名，拒绝打包'
}
$vendorHash = (Get-FileHash -LiteralPath $WebViewInstaller -Algorithm SHA256).Hash
# Encode only the generated compiler inputs as UTF-8 BOM for Inno 6.x language detection.
$compilerSources = Join-Path $stage 'installer-source'
New-Item -ItemType Directory -Path $compilerSources | Out-Null
foreach ($name in @('SiteSafe.iss','ChineseSimplified.isl','安装前须知.txt','安装版使用说明.md')) {
    [IO.File]::WriteAllText((Join-Path $compilerSources $name),
        [IO.File]::ReadAllText((Join-Path $PSScriptRoot $name)), [Text.UTF8Encoding]::new($true))
}
$arguments = @('/Q', "/DPayloadRoot=$($payloadInfo.payload)", "/DAppVersion=$version", "/DOutputRoot=$outputRoot",
    "/DWebViewInstaller=$WebViewInstaller", "/DPayloadInclude=$($payloadInfo.include)", (Join-Path $compilerSources 'SiteSafe.iss'))
Write-Host "正在构建安装版 $version（已核验 $($payloadInfo.verified_manifest_files) 个载荷文件）…"
& $Compiler @arguments 2>&1 | Tee-Object -FilePath (Join-Path $stage 'compiler.log') | Out-Host
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputExe)) { throw "安装器编译失败，日志：$stage\compiler.log" }
$artifact = Get-Item -LiteralPath $outputExe
$receipt = [ordered]@{
    product='SmartRoad-Inspection'; version=$version; built_at=(Get-Date).ToUniversalTime().ToString('o')
    installer=$artifact.Name; bytes=$artifact.Length; sha256=(Get-FileHash -LiteralPath $outputExe -Algorithm SHA256).Hash
    installer_signature=(Get-AuthenticodeSignature -LiteralPath $outputExe).Status.ToString()
    app_id='{3AA70D20-370C-4CBA-BBB2-263596461A2D}'; install_scope='current Windows user'
    portable_zip=[IO.Path]::GetFileName($archive); portable_zip_sha256=$archiveHash
    verified_manifest_files=$payloadInfo.verified_manifest_files; unpacked_bytes=$payloadInfo.unpacked_bytes
    webview2=@{sha256=$vendorHash; bytes=(Get-Item -LiteralPath $WebViewInstaller).Length;
        signature=$signature.Status.ToString(); signer=$signature.SignerCertificate.Subject;
        source='https://go.microsoft.com/fwlink/p/?LinkId=2124701'; bundled_offline=$true}
    models_bundled=$false; preserved_seed_files=$payloadInfo.preserved_seed_files
}
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $outputRoot 'installer-build-receipt.json') -Encoding utf8
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '安装版使用说明.md') -Destination (Join-Path $outputRoot '安装版使用说明.md')
Write-Host "完成：$outputExe"
Write-Host "大小：$([math]::Round($artifact.Length/1MB,2)) MiB"
Write-Host "SHA-256：$($receipt.sha256)"
