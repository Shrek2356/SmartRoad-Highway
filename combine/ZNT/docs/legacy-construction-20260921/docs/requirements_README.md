# 环境与依赖说明

本目录是环境准备入口。请先区分 **完整桌面交付包** 和 **GitHub 源码**，不要把二者的安装步骤混用。

## 先选使用方式

| 使用方式 | 基础环境 | 是否需要模型 |
|----------|----------|--------------|
| v1.4.1 完整桌面包，仅演示 | 随包 Python、业务依赖与前端构建；无需系统 Node | 不需要 |
| GitHub 源码开发 | 自备 Python／Node，安装开发与业务依赖 | 只做 Demo 时不需要 |
| 本地离线／云端视觉加本地定位 | 完整检测环境，按显卡配置 CUDA PyTorch 与其他依赖 | 需要对应外部模型；云端还需 API 配置 |

完整包的 Windows 独立窗口需要 WebView2 Runtime。GitHub 跟踪了部分基础 Python 文件，但不包含完整 site-packages、EXE 或前端构建产物；看到 `python-runtime/` 不代表源码已经可以免安装运行。

## 文件索引

| 文件 | 用途 |
|------|------|
| [detect-bridge.txt](./detect-bridge.txt) | Demo、业务／检测桥与 RAG 规范导入依赖 |
| [detect-full.txt](./detect-full.txt) | 完整检测依赖；CUDA PyTorch 需另行选择 |
| [requirements.txt](../requirements.txt) | 应用根目录完整依赖转发入口 |
| [setup_env.bat](./setup_env.bat) | 在应用目录创建／补充 `env/`，支持 `demo` 和 `full` |
| [preflight_check.py](./preflight_check.py) | 环境、GPU、模型路径自检 |
| [check_weights.bat](./check_weights.bat) | 模型文件检查 |
| [deployment-manifest.json](./deployment-manifest.json) | 可机读环境与模型清单 |
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | 详细部署、权重与验收流程 |
| [TESTED_ENVIRONMENT.md](./TESTED_ENVIRONMENT.md) | 分场景的已验证环境记录 |
| [test.txt](./test.txt) | 自动回归所需依赖 |

## 完整桌面包：先展示，再接模型

1. 完整解压到较短的目录，关闭旧版，再打开根目录 `SiteSafe-Sentinel.exe`。
2. 登录并查看“检测结果汇总”的八个案例；Demo 不需要重新安装基础 Python 或 Node。
3. 要检测新图片，先打开“模型与规则 → 新设备部署”，按五步引导操作；`部署助手.bat` 是终端检查入口。
4. 在“系统设置 → 桌面与连接”设置后台 Python，在“模型规则配置”设置模型、推理引擎与 API。
5. 保存并按提示重启，完成环境检查后，用新图片验证真实结果。

`setup_env.bat full` 创建独立 `env/`，不修改随包 Demo 运行时。环境缺少匹配的 CUDA PyTorch 时会暂停并提示，不会猜测显卡环境自动安装。

## GitHub 源码：需要安装开发环境

桌面构建／回归使用 Python 3.12；前端 Vite 要求 Node `^20.19.0 || >=22.12.0`，仓库 CI 配置为 Node 22。这里描述项目已配置的版本条件，不代表所有更高版本均已验收。

在 `combine/ZNT/` 执行：

```powershell
.\requirements\setup_env.bat demo
```

再进入 `pc-admin/` 执行 `npm ci`、`npm test` 与 `npm run build`。新建的业务 Python 位于 `env/Scripts/python.exe`。要运行桌面版，请在本地 `desktop-settings.json` 中将 `backend_python` 指向这个环境，具体构建步骤见[桌面说明](../desktop/README.md)。

这些步骤仅用于源码开发；已经拿到完整运行包的体验者不用执行。

## 模型与展示数据边界

权重不包含在代码／演示包里；按部署指南取得匹配的 Qwen GGUF 与 mmproj、SAM3、项目 YOLO，以及可选 CLIP。云端视觉服务不替代所有本地定位依赖。

预置案例、检测框、掩码和报告用于展示既有成果，不代表对新上传图片进行了真实推理。运行时可在“系统设置 → 工作台与展示”隐藏预置素材；构建时可设置 `VITE_ENABLE_PRESENTATION_ASSETS=false`。开关不删除文件，也不改动真实数据库。

## 更换环境时

- 新机使用独立 Python 3.12 GPU 环境，PyTorch、torchvision 与 CUDA 整组匹配；随包 Demo Python 不含推理依赖。历史 3.10 是适配环境，不可直接混装当前官方 SAM3。
- `desktop-settings.json` 的 `backend_python` 是桌面后台选择；部署助手现在读取同一配置，不再优先选择旧 conda 或另一个便携环境。
- 已有 conda／其他环境可以直接填写其 Python 路径，不必重复创建环境。
- 不把模型、密钥、个人环境或运行日志作为 Git 源码同步；模型与环境改动后重新进行功能和效果验收。
