# 路安智巡 · SmartRoad-Highway

面向高速公路建设与管理的道路风险检测实验室原型。当前版本 **1.4.4**，服务器端采用 Qwen 观察与复核、SAM3 多概念定位、道路法规检索、问题报告和人工反馈流程。端侧实时模型暂缓训练。

- [应用源码及使用说明](combine/ZNT/README.md)
- [环境部署说明](combine/ZNT/requirements/README.md)
- [1.4.4 测试与验证摘要](docs/validation/v1.4.4/README.md)
- [道路领域迁移检查](combine/ZNT/docs/道路领域全面迁移检查_20260921.md)

## 当前能力与边界

区分普通湿润路面与可见积聚水体，支持同图多种风险和多个分割实例。正常场景显示绿色道路框，路牌作为蓝色场景对象标注。报告按风险 ID 关联原图、掩码和复核结论。可检测的候选包括路面破损、积水淹没、散落物、阻塞、塌方、火情及交通设施异常；不能以掩码存在代替精准检测或人工确认。

真实 Qwen/SAM3 开发测试已完成 15 张图，仍存在误分、漏分和边界不准。这是小试开发结果，不是独立数据集准确率或真实高速试点结论。

## 源码开发

本仓库包含项目源码、道路配置模板、法规出处与校验记录、测试、构建脚本和验证摘要。Python、Node、GPU 环境、模型权重、数据集、个人配置、业务数据库和安装构建产物在本地管理。历史兼容模块保留，但产品入口采用道路配置。

在 `combine/ZNT` 中安装所需依赖；前端位于 `pc-admin`，执行 `npm ci`、`npm test`、`npm run build`。基础服务依赖见 `requirements/detect-bridge.txt`，完整检测环境见 `requirements/DEPLOYMENT_GUIDE.md`，自动回归依赖见 `requirements/test.txt`。复制 `desktop-settings.example.json` 为 `desktop-settings.json`，将 `backend_python` 指向本机已安装依赖的 Python；个人桌面配置不提交 Git。

道路后端入口位于 `combine/ZNT/detectmodel/Site_Safety_OpenRisk`，真实本地检测选择 `configs/road_offline.yaml`，模拟联调选择 `configs/road_demo.yaml`。构建桌面 EXE 前先构建前端并准备桌面依赖，见 `combine/ZNT/desktop/README.md`。

## 同步与发布

此仓库是从 2026-09-22 的当前工作区整理出的道路版源码基线，旧仓库和原始本地工作区保留。后续开发在本仓库提交并推送至 `main`。安装程序通过 GitHub Release 单独提供，不放入 Git 文件历史。

项目与第三方许可见 [LICENSE](LICENSE)、[THIRD_PARTY_NOTICE.md](THIRD_PARTY_NOTICE.md) 和 [COMPETITION_SUBMISSION_NOTICE.md](COMPETITION_SUBMISSION_NOTICE.md)。
