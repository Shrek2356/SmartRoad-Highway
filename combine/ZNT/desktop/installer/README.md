# Windows 安装器构建与验收

应用本体仍是 v1.4.1；安装器将已验证的便携包封装为可安装、可卸载的 EXE。不是把所有模型压进程序，也没有添加付费授权/账号注册服务。

## 构建

需要 Windows、源码中可用的 `python-runtime/python.exe`、Inno Setup 6.5+（本次编译器 6.7.3）。编译器只用于开发构建，安装后的用户不需要它。首次构建从 Microsoft 官方地址下载 WebView2 离线 x64 安装程序到被 Git 忽略的 `build/cache/`，并强制验证 Microsoft 发布者签名。后续可缓存或通过参数提供离线文件。

在本目录打开 PowerShell：

```powershell
.\build-installer.ps1 -PortableZip '完整便携包.zip' -OutputDirectory '输出目录' -ExpectedZipSha256 '便携包的SHA256'
```

可选 `-Compiler 'ISCC.exe完整路径'`、`-WebViewInstaller 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe完整路径'`。输出包括安装 EXE、构建收据与使用说明。脚本拒绝覆盖已有同名安装包；修改源码后请用新的输出目录，验收后再归档。

构建器必须读取原始 ZIP，不能递归复制已运行过的软件目录。ZIP 必须单根目录，且每个文件均在 `release-manifest.json` 中声明；逐项验证 SHA-256 和大小，拒绝额外文件、路径越界、重复路径及业务/推理/密钥/权重数据。安装清单由通过校验的文件逐项生成，不用通配符抓取工作目录。

`SiteSafe.iss` 的 AppId 是稳定产品标识，后续升级不得随意更改。默认安装到当前用户 `%LOCALAPPDATA%\Programs\SiteSafe-Sentinel`；应用当前仍在安装目录存放工作空间，因此不默认 Program Files，不全局修改 PATH。

## 数据保留契约

- `desktop-settings.json`、检测后端 `configs/`、规范种子 `knowledge_base/`：首次安装写入，重装不覆盖，卸载不删除。
- 运行生成的 `runtime/`、`app_data/`、`outputs/`、用户 `.env` 及自行准备的 `models/`、`env/`、`third_party/`：不属于程序文件清单，卸载不递归清空。
- 程序代码、静态前端和基础 Python：随版本更新，由安装器卸载。
- `sitesafe-install.ini`：保留用于辨认可重装的资料目录，不作为联网标识。

未来升级如果需要改变旧配置的默认值或结构，必须增加显式迁移，不得通过覆盖用户配置完成。默认配置保留也意味着新版本默认值不会自动应用到老用户。跨大版本、降级及异机恢复应先独立验证。

## 测试

纯逻辑检查（开发 Python）：

```powershell
..\.venv\Scripts\python.exe -m unittest -v test_payload_manifest.py
```

真实安装/重装/卸载测试会暂时在当前 Windows 用户注册本产品，然后卸载隔离测试副本。如果用户已安装该 AppId 或平台端口占用，脚本拒绝运行，不覆盖已有安装。

```powershell
.\test-installer.ps1 -Installer '安装包.exe' -TestParent '专用测试目录'
```

覆盖非空目录拒绝、进程互斥、中文空格路径、注册表、开始菜单目标、全载荷哈希、独立窗口三个服务健康、退出清理、重装配置保留、卸载数据保留。测试不创建用户桌面快捷方式，不运行大模型；故障时保留精确目录和日志便于诊断，不自动删除测试资料。

还需干净 Windows 10/11 设备验收：缺少 WebView2 的首次补齐、标准用户权限、组织策略、安全软件、异机模型配置与驱动。已有 WebView2 的本机测试不能代替缺失分支实装。

发布前应按实际用途核实 [Inno Setup](https://jrsoftware.org/isdl.php) 的许可；本次使用现有非商业编译环境。对外商用同时需要项目和第三方授权、发布者代码签名与新机验收。没有签名的构建应明确标记，不承诺没有 SmartScreen 提示。
