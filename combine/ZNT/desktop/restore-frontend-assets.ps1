# Development only: restore public assets from the single packaged dist copy.
$ErrorActionPreference = 'Stop'
$frontend = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'dist\index.html'))) { throw '请将本脚本放在交付包 pc-admin 目录内执行' }
if (Test-Path -LiteralPath (Join-Path $frontend 'public')) { throw 'public 已存在；为避免覆盖，请自行合并素材' }
New-Item -ItemType Directory -Path (Join-Path $frontend 'public') | Out-Null
foreach ($entry in Get-ChildItem -LiteralPath (Join-Path $frontend 'dist')) {
    if ($entry.Name -notin @('assets','index.html')) {
        Copy-Item -LiteralPath $entry.FullName -Destination (Join-Path $frontend 'public') -Recurse
    }
}
Write-Output '素材已恢复。开发时安装 Node，再在 pc-admin 中运行 npm ci / npm run build。'
