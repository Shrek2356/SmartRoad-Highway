# 筑安智巡——面向开放施工风险的多模态安全监管智能体
## SiteSafe-Sentinel 嘉然今天也在守护工地
An open-risk visual detection and multi-agent safety management platform for construction sites.

当前源码版本 **v1.4.1**：新增前端五步模型部署引导，统一新机路径和 Python 检查，预留项目权重下载地址；保留工作空间备份、双主题、全部展示案例与嘉然动画。[新设备模型部署说明](./combine/ZNT/docs/桌面版v1.4.1模型部署说明.md)。旧版压缩包不会自动包含这些更新。

<p align="center">
  <a href="./combine/ZNT/video/%E5%80%99%E6%9C%BA%E5%8A%A8%E7%94%BB.mp4" title="点击观看原始高清视频">
    <img src="./assets/readme/sitesafe-sentinel-intro.gif" width="720" alt="嘉然正在检查工地安全系统各模块" />
  </a>
</p>

<p align="center"><em>点击动画可查看原始高清视频</em></p>

## v1.3.0 · 更清晰的安全工作台

这次更新聚焦 **PC 管理后台与 Windows 桌面体验**，不改变异常识别策略，不增加大模型调用，也没有重新计算检测效果。

- **统一明暗主题**：雾白与石墨蓝底色，青绿表达操作和选中，红／橙／黄表达风险。
- **清楚的视觉层次**：优化侧栏、项目切换、文字、卡片、表格、滑杆、图表与状态标签；小高度窗口使用紧凑导航。
- **随时找到下一步**：保留功能搜索 `Ctrl + K`、本页指南、首次使用引导和连接诊断。
- **展示内容完整保留**：嘉然动画、八张关键案例、原图、检测框、掩码与报告；预置素材始终标注来源。
- **保持真实状态**：检测桥在线不等于模型已加载；连接失败不会把真实检测自动改为 Mock。

[版本变更记录](./CHANGELOG.md) · [新版使用指南](./combine/ZNT/docs/桌面版v1.3视觉升级与使用指南.md) · [验证与交付记录](./combine/ZNT/docs/v1.3视觉验收记录.md)

## 如何开始

### Windows 安装版：像普通软件一样安装

项目方提供的 **`SiteSafe-Sentinel_Setup_v1.4.1_x64.exe`** 可选择安装位置，创建桌面/开始菜单快捷方式，并在 Windows“已安装的应用”提供卸载入口。默认当前用户安装；包含原有演示内容和离线 WebView2，不包含模型权重，模型仍从软件内的部署引导接入。

升级保留已有配置，卸载不主动清理业务资料或外置模型。这里的“注册”指 Windows 软件管理登记，不是账号注册或联网激活。[安装与迁移说明](./combine/ZNT/desktop/installer/安装版使用说明.md) · [安装包构建说明](./combine/ZNT/desktop/installer/README.md)。安装包和便携包是两种分发方式，软件本体同为 v1.4.1，GitHub 源码下载不包含这些运行包。

### 直接体验：完整桌面交付包

使用项目方提供的 `SiteSafe-Sentinel_Desktop_v1.4.1_deployment_final.zip`，完整解压后双击根目录 **`SiteSafe-Sentinel.exe`**。若旧版仍在运行，请先正常退出旧版。接入模型请从“模型与规则 → 新设备部署”开始；项目 YOLO 下载地址暂留空，不影响通过选择文件配置已有权重。

- 环境：Windows 10/11 64 位，Microsoft Edge WebView2 Runtime。
- 随包提供基础 Python 与已构建前端；演示不要求系统 Node、GPU、API 密钥或大模型权重。
- 软件使用独立窗口，自动启动业务后台与检测桥；关闭时只停止由该窗口启动的服务，不强关原有共享服务。
- 不要只拷贝 EXE，它需要同目录的运行时、前端和后台文件。

**GitHub 的“Download ZIP”下载的是源码，不是这个完整运行包。** 当前仓库不跟踪桌面应用 `SiteSafe-Sentinel.exe` 与前端 `dist`；代码同步不等于上传了桌面压缩包。完整交付包的文件名、体积和校验值见[交付记录](./combine/ZNT/docs/v1.3视觉验收记录.md)。

默认演示账号：

| 角色 | 账号 | 密码 |
|------|------|------|
| 管理员 | `admin` | `admin123` |
| 安全员 | `safety` | `safety123` |
| 只读总监 | `viewer` | `viewer123` |

真实账号权限由后台决定，正式使用应更改默认凭据。

### 看八个案例，还是检测新图片？

| 目的 | 操作入口 | 所需条件 |
|------|----------|----------|
| 查看已有作品 | 检测结果汇总 → 预置展示案例 | 不需要模型；展示既有证据 |
| 体验操作流程 | 实时检测 → 演示模式 | Mock 结果，不用于安全判定 |
| 检测新图片 | 模型规则配置 → 配置运行时与模型 → 实时检测 | 完整环境、本地模型，或云端视觉 API 加本地定位模型 |
| 排查连接 | 使用与支持 → 连接诊断 | 可分别检查业务后台与检测桥 |
| 导入规范 | 模型规则配置 → 安全知识库管理 | 业务与 RAG 依赖就绪，导入后可检索验证 |

右上角按钮切换明暗主题；用户菜单可切换“工作台／展示视图”。**外观模式与预置素材开关彼此独立**，隐藏展示素材不会删除文件，也不会改变真实事件数据库。

### 接入真实检测

在“系统设置 → 桌面与连接”选择完整 Python 环境；在“模型规则配置 → 模型部件与运行时”配置推理引擎和模型路径，在对应配置入口填写云端服务信息。

YOLO、Qwen、SAM3 与可选 CLIP 的权重不在代码／演示包内。不要照抄开发者电脑的盘符或缓存路径。按 [部署指南](./combine/ZNT/requirements/DEPLOYMENT_GUIDE.md)、[依赖说明](./combine/ZNT/requirements/README.md) 和[已验证环境记录](./combine/ZNT/requirements/TESTED_ENVIRONMENT.md)准备自己的环境，再用新图片验收。

保留实时监测初筛、定期全图检查与直接图片输入入口。风险描述、定位证据和人工复核各有用途，不能仅凭掩码有无判断整条链路成功与否。

## 从源码开发

主要应用目录是 `combine/ZNT/`。源码开发需要自行准备 Python、Node 和依赖；本地虚拟环境与模型不通过 Git 同步。

前端依赖与构建：

```powershell
cd combine/ZNT/pc-admin
npm ci
npm test
npm run build
```

开发预览使用 `npm run dev`，它不是桌面一键启动器，也不负责启动后台。业务环境、桌面 EXE 构建及首次启动的配置步骤见[桌面开发说明](./combine/ZNT/desktop/README.md)。

源码中的 `combine/ZNT/start-platform.bat` 保留浏览器兼容启动方式；完整桌面交付包中的同名入口用于打开 EXE。两者不要混淆。

## 项目目录

```text
SiteSafe-Sentinel/
├── README.md
├── CHANGELOG.md
├── LICENSE
├── assets/readme/                     # GitHub 首页动画
└── combine/ZNT/
    ├── desktop/                      # 独立窗口、服务生命周期与 EXE 构建
    ├── desktop-settings.json         # 运行档位、Python 路径与端口
    ├── pc-admin/
    │   ├── src/                      # 主工作台代码
    │   ├── public/                   # 动画、案例与预编辑展示素材
    │   └── tests/                    # 前端回归
    ├── detectmodel/Site_Safety_OpenRisk/ # 检测、业务、Agent 与接口
    ├── requirements/                 # 环境、模型和部署说明
    ├── example/                      # 示例图片
    ├── big-screen/                   # 大屏端源码
    ├── mobile/                       # 移动端源码
    └── docs/                         # 使用、接口、汇报与版本记录
```

`desktop-dist/`、`pc-admin/dist/` 与完整 Python 环境由构建或交付阶段准备。**v1.3 的视觉改版范围是 PC／桌面端，不包含移动端和大屏端重新设计**；完整桌面包也不等于自动启动三端。

## 验证范围

2026-09-07 的 v1.3 记录：

- 前端 17 项、后端与桌面 145 项回归通过；前端和 EXE 构建成功。
- 与 v1.2 比对的 55 个前端静态文件未变，八个预置案例保留。
- 解压后的 5,524 项清单文件校验一致。
- 当时旧版占用全局单实例，新 EXE 尚未完成独立窗口启动验收；页面视觉检查不能替代这项检查。
- 没有重新测试模型召回率、误报率或推理速度；色板对比度测试不是完整可访问性或生产认证。

这些是已记录的本地结果，**不是对当前 GitHub Actions 运行状态的声明**。仓库提供[自动回归工作流](./.github/workflows/regression.yml)，实际执行结果请查看仓库 Actions。

## 文档导航

- [v1.3 视觉与使用指南](./combine/ZNT/docs/桌面版v1.3视觉升级与使用指南.md)
- [v1.3 验证与交付记录](./combine/ZNT/docs/v1.3视觉验收记录.md)
- [v1.2 产品引导与功能说明](./combine/ZNT/docs/桌面版v1.2产品体验与使用指南.md)
- [桌面构建与打包](./combine/ZNT/desktop/README.md)
- [环境与模型部署](./combine/ZNT/requirements/README.md)
- [接口对接指南](./combine/ZNT/docs/对接指南.md)
- [YOLO－VLM－前端接口整合](./combine/ZNT/docs/YOLO-VLM-前端接口整合说明.md)
- [作品演示脚本](./combine/ZNT/docs/两分钟作品演示-画面字幕配音脚本.md)

## License / 授权说明

本项目为**源码可见的专有软件，并非开源软件**。版权归 SiteSafe-Sentinel 项目作者及依法享有权利的贡献者所有。

获得私有仓库访问权限，仅代表可以为非商业评估、比赛评审或内部测试查看和运行项目；未经著作权人事先书面许可，不得公开、再分发、商用、用于生产部署、训练模型、开发竞品或删除作者信息。

完整条款见 [LICENSE](./LICENSE)。第三方软件、模型、数据、字体、图片、角色素材和商标仍适用各自权利人的许可，本项目不对其主张独占权利。
