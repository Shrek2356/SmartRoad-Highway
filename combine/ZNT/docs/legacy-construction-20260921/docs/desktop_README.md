# SiteSafe-Sentinel 独立桌面版

当前源码版本 **1.4.1**。保留桌面导出、工作空间备份恢复，新增新机模型部署向导和 Windows 安装包构建。见[模型部署说明](../docs/桌面版v1.4.1模型部署说明.md)、[安装版说明](installer/安装版使用说明.md)与[版本记录](../../../CHANGELOG.md)。

## 用户启动

完整交付包的入口在包根目录；源码构建产物位于应用目录的 `desktop-dist/SiteSafe-Sentinel.exe`。以下相对命令以 `combine/ZNT/` 为当前目录。它会：

1. 显示原生桌面窗口和启动页，不弹出浏览器。
2. 启动内嵌PC前端、8800业务后台和8810检测桥。
3. 默认使用Demo档，不需大模型权重。
4. 关闭窗口时停止由EXE启动的子服务和本地Qwen。

不会接管或关闭原先已运行的共享服务。修改 Python、模式或端口可在“系统设置 → 桌面与连接”完成，保存后重启。普通模型路径与 Qwen 启停仍在“模型规则配置”。

EXE 不内置大模型或可变业务数据。分发时把 EXE 放到完整包根目录，与以下目录／配置同级；源码的 `desktop-dist/` 子目录启动会向上定位应用目录：

- `python-runtime/`
- `pc-admin/dist/`
- `detectmodel/Site_Safety_OpenRisk/`
- `desktop-settings.json`

系统不再依赖用户的 Chrome/Firefox 窗口，但 Windows 需有 Microsoft Edge WebView2 Runtime；请通过部署助手检查实际设备。

## 运行档位

编辑根目录`desktop-settings.json`：

- `demo`：Mock检测，无权重。
- `offline`：本地YOLO + Qwen + SAM3/CLIP。
- `standard`：云端视觉API + 本地SAM3/CLIP。

真实检测时，将`backend_python`改为已安装CUDA/PyTorch和完整检测依赖的Python路径。模型路径仍可在前端“模型规则配置”中修改。

## 从 GitHub 源码准备

GitHub 的源码 ZIP 不等于完整桌面运行包。EXE、`pc-admin/dist/` 和完整业务依赖需要自行构建／准备。先安装 Python 3.12 与满足 Vite 条件的 Node，再执行：

```powershell
# 当前目录：combine/ZNT/
.\requirements\setup_env.bat demo
cd pc-admin
npm ci
npm test
npm run build
cd ..
.\desktop\build-desktop-exe.bat
```

`setup_env.bat demo` 准备业务环境 `env/`；桌面构建脚本另建 `desktop/.venv/`，两者不要混用。首次从源码运行前，在本地 `desktop-settings.json` 将 `backend_python` 改为 `env/Scripts/python.exe`，保留其他字段。已有完整包的使用者无需重新执行这些安装步骤。

## 开发调试

```powershell
desktop\.venv\Scripts\python.exe desktop\desktop_app.py --profile demo
```

## 重新构建

双击`desktop/build-desktop-exe.bat`。构建环境与业务运行环境分离，生成文件位于`desktop-dist/SiteSafe-Sentinel.exe`。构建会写入产品名称、版本号和应用图标；对外正式分发时如需消除 Windows SmartScreen 的“未知发布者”提示，还需要使用团队自己的代码签名证书签名。

先验证便携目录版，再使用 [installer/build-installer.ps1](installer/build-installer.ps1) 将已核验的便携 ZIP 封装成单个安装 EXE。模型权重始终外置，便于更新和不同 GPU 配置；安装包注册 Windows 软件信息，不新增联网激活。

## 生成便携交付包

构建前端与 EXE 后，执行 `desktop/pack-release.ps1 -Destination <输出目录>`；脚本拒绝覆盖已有交付目录，并生成 SHA256 文件清单。本版包含源码、完整 `public` 素材及 `dist` 构建产物，不再以压缩包大小为优先约束。修改前端时在 `pc-admin` 安装开发依赖后构建；普通使用者无需这些操作。旧版精简包仍可用 `restore-frontend-assets.ps1` 恢复公共素材。

打包前须准备完整 `python-runtime/` 及其 Demo／RAG 依赖，并检查交付配置的 `backend_python` 指向 `python-runtime/python.exe`。脚本不会把开发用 `env/` 或 `desktop/.venv/` 一起分发；不能仅凭 EXE 构建成功就宣称解压即用。最后从独立解压目录验收。
