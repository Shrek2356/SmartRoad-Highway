# 新设备模型部署指南 · v1.4.1

## 先明确要做什么

完整桌面包解压后打开 `SiteSafe-Sentinel.exe`，不要只复制 EXE，也不要在 ZIP 内直接运行。推荐解压到可写、较短的目录，例如 `D:\SiteSafe`。程序、前端和便携 Python 根据 EXE 所在位置查找，不要求原来的盘符。桌面包不需要 Node、node_modules 或重新构建前端。

Windows 10/11 x64 需要 [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)。缺少时通过官方安装入口补装。其他系统不能直接运行这个 Windows EXE。

| 目标 | 要准备的内容 |
|---|---|
| Demo 演示八个案例 | 随包基础 Python、前端和展示素材；无 GPU、权重、云端密钥要求 |
| Offline 本地检测 | 独立 GPU Python、Qwen GGUF + 配套 mmproj、llama.cpp、SAM3、项目 YOLO |
| Cloud 云端视觉 + 本地定位 | 云端多模态 API；本机仍需 GPU Python、SAM3 和项目 YOLO；不要求本地 Qwen |
| CLIP 辅助 | 默认关闭；仅启用时才准备相应文件和依赖 |

**前端入口：模型与规则 → 新设备部署。** 五步引导支持模式切换、组件来源、环境检查和后续操作入口；浏览不会执行安装或推理。终端也可运行 `部署助手.bat`。

## 第一步：准备独立推理环境

### 不要混淆三种 Python

1. 随包 `python-runtime/python.exe`：Demo 和基础业务使用，不安装 GPU 依赖到这里。
2. 新建 `env/Scripts/python.exe` 或已有外部环境：真实检测使用。
3. 系统 PATH 中的 `python` / `pip`：可能不是前两者。安装时应明确使用目标解释器的完整路径。

截至 2026-09-07，[SAM3 官方安装说明](https://github.com/facebookresearch/sam3#installation)要求 Python 3.12+、PyTorch 2.7+ 和支持 CUDA 的 GPU（官方列出 CUDA 12.6+）。新部署使用 **Python 3.12 x64** 起步。项目过往的 Python 3.10 记录对应历史适配环境，不能当作当前官方代码的通用安装方案。不要为此覆盖旧电脑已验证的环境。

本地 8B 模式建议 32 GB 以上内存、16 GB 以上 NVIDIA 显存，预留至少 35 GB 磁盘。12 GB 显存仅是需要单独验证的尝试条件；模型并发、上下文长度与分辨率都会增加占用。云端模式仍需满足本地 SAM3/YOLO 的显卡要求。这些是部署起点，不保证特定吞吐或推理效果。

1. 从 [Python Windows 官方页面](https://www.python.org/downloads/windows/)安装 Python 3.12 x64。
2. 打开 PowerShell，按实际应用位置创建环境（已有兼容环境可跳过）：

```powershell
py -3.12 -m venv 'D:\SiteSafe\env'
```

3. 使用 [PyTorch 官方安装选择器](https://pytorch.org/get-started/locally/)按驱动和显卡选择 **成套 torch + torchvision 的 CUDA 版**。将官方命令开头的 `pip` 改成：

```powershell
& 'D:\SiteSafe\env\Scripts\python.exe' -m pip
```

不要仅凭示例 CUDA 版本直接复制安装；不要误装 CPU 版。平台不替部署者自动猜测 CUDA wheel。然后：

```powershell
& 'D:\SiteSafe\env\Scripts\python.exe' -m pip install -r 'D:\SiteSafe\requirements\detect-full.txt'
```

前端会根据实际应用位置生成这些命令。已有外部环境时，请使用自己的目标 Python。可用 `requirements/setup_env.bat full` 为已建好的包内 env 安装依赖；缺少 CUDA PyTorch 时该脚本暂停并要求人工选择。

## 第二步：取得组件，按统一目录放置

以下均以 EXE 同级目录为基准；不必修改源码。

```text
SiteSafe/
├─ SiteSafe-Sentinel.exe
├─ python-runtime/                       # 保留随包基础环境
├─ env/                                  # 自建推理环境，不随迁移直接复制
├─ models/
│  ├─ qwen/Qwen3-VL-8B-Instruct-Q4_K_M.gguf
│  ├─ qwen/mmproj-BF16.gguf
│  ├─ sam3/sam3.pt
│  ├─ yolo/yolo26m_css_v28_baseline_best.pt
│  ├─ yolo/yolo26m_construction_site_best.pt
│  └─ clip/ViT-L-14.pt                    # 可选
└─ third_party/
   ├─ llama.cpp/llama-server.exe          # 同发行包 DLL 也要保留
   └─ sam3-main/                         # 代码仓库，而不只是权重
```

### Qwen 和 llama.cpp（仅本地模式必需）

- 从 [Qwen 官方 GGUF 仓库](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF)取得 Q4_K_M 文件和配套视觉投影 mmproj。
- 两个文件必须属于同一模型的匹配修订。名称、存在性检查不能证明兼容；最后仍需真实图片验证。
- 从 [llama.cpp 发行页](https://github.com/ggml-org/llama.cpp/releases)取得适合显卡的 Windows x64 CUDA 包，完整解压，保留同包 DLL。在前端选择 llama-server.exe；不强制修改系统 PATH。
- 默认 8192 上下文、单 slot 的历史设置是起点，不保证新显卡的延迟或容量。

### SAM3（本地和云端均需要）

从 [SAM3 官方仓库](https://github.com/facebookresearch/sam3)取得代码及其指引的 sam3.pt。权重可能需要授权访问，请依官方流程处理。代码与权重必须匹配，不默认升级成 SAM 3.1。

取得代码后使用目标环境安装：

```powershell
& 'D:\SiteSafe\env\Scripts\python.exe' -m pip install -e 'D:\SiteSafe\third_party\sam3-main'
```

只下载代码或放入 sam3.pt 不等于安装完成。Windows 上可能出现上游依赖或编译兼容问题，环境检查会展示导入错误；不要通过关闭检查来宣称部署成功。新的官方环境尚未在另一台实体电脑完成本项目全链路验收。

### 项目 YOLO 权重

两套项目权重的 **下载地址和 SHA-256 暂留空**。可由项目方直接提供，或后续上传 GitHub 后补入 `requirements/deployment-manifest.json` 中对应模型的 `download_url` 与 `sha256`。留空会明确显示“下载地址待补充”，不会伪装成已经下载或配置完成。此清单是前端和终端指引的共同来源。

该压缩包不带权重，不承诺已有可用下载地址；不要使用通用 YOLO 权重冒充项目训练产物。暂时没有 YOLO 时仍可看 Demo；已接通 VLM/SAM3 时可用人工／周期全面审计绕过实时初筛，但不能称实时监测链路完整。

### CLIP（可选）

默认关闭，无文件不阻断主链。启用后才检查对应权重及 OpenCLIP 依赖。参考 [OpenCLIP 仓库](https://github.com/mlfoundations/open_clip)。启用辅助模块需另行评估误报和耗时。

## 第三步：在前端保存环境与模型路径

1. 系统设置 → 桌面与连接：选择真实检测 Python。
2. 保存，正常关闭并重新打开软件，使业务后台和检测桥使用同一环境。
3. 模型与规则 → 模型部件与运行时：自动查找统一目录；未找到时点击“浏览…”。
4. 校验并保存，再点击“更新初始化配置”。仅在已确认路径后开启 Qwen 自动启动。
5. 包内模型以相对路径持久化，可以随整个目录移动；外部模型保留绝对路径，换电脑后重新选择。不要直接迁移旧虚拟环境。

桌面和 `部署助手.bat` 都以 `desktop-settings.json` 的 `backend_python` 为准；配置不存在或无效会明确报错，不静默改用其他 Python。浏览器开发模式没有桌面配置时使用正在运行检测桥的环境。

## 第四步：检查环境与连接

前端点击“检查当前模式环境”，或运行部署助手。检查有超时与防重复控制；Demo 不导入 CUDA 模块，所有模式都不加载权重、不调用视觉 API。

检查包括实际 Python、64 位、依赖可导入性、GPU/CUDA、llama-server 文件、模型路径和所需组件开关。桌面设置与当前检测桥 Python 不同会提示重启。项目下载地址未填写本身不是错误：本地已取得正确文件仍可继续。

检查通过只说明基础部署条件，不证明模型配对、云端密钥、许可、推理效果或长期稳定性。

- 本地：手动启动 Qwen，等待测试连接成功。
- 云端：在实时检测的云端设置填写 endpoint、模型名和 API key，并测试连接。检查器不会发起收费请求。
- SAM3/YOLO/CLIP：按任务懒加载，不需要独立服务启动按钮。

## 第五步：真实图片验收

先提交一张新图片，确认选择的是真实模式且生成新任务。核对风险描述、支持证据、疑问和可用的定位输出，再跑八个示例。已有的预编辑展示报告不等于当前机器刚跑出的结果。

没有掩码不自动判定识别失败；没有发现风险也不能视为安全保证。需要实时视频时再验证 YOLO 初筛、视频源和 30 分钟／2 小时全图审计接口。

## 常见问题与下一步

| 现象 | 处理 |
|---|---|
| 模型路径未找到 | 按推荐目录放置并自动查找，或浏览后保存；外部旧盘符需要重新选择 |
| 已安装依赖仍报缺失 | 核对报告中的实际 Python；使用那个 python.exe -m pip，不用随手输入 pip |
| 保存 Python 后结果不变 | 正常关闭并重新打开软件，再检查 |
| CUDA 不可用 | 检查驱动、GPU 支持及是否误装 CPU 版 torch；torchvision 必须配套 |
| SAM3 导入失败 | 检查 Python 版本、完整代码及 editable 安装；展开界面中的具体导入错误 |
| llama-server 无法运行 | 保留发行包 DLL，选择适配显卡的构建；文件存在并不等于加载成功 |
| CUDA 显存不足 | 关闭可选 CLIP、避免并发；调整上下文或换更大显存设备后重新验收 |
| 云端配置好仍失败 | 单独测试 endpoint、模型名、权限和密钥；环境检查不会验证这些 |
| 项目 YOLO 下载地址为空 | 暂由项目方提供文件；后续仅补清单地址，不需要改前端代码 |

本指南不安装驱动，不代替授权审批，不保证所有上游版本兼容，不修改现有业务记录或模型检测策略。
