# Agent功能与模块分类登记表

按方案架构对系统内全部智能体与支撑模块分类登记。每次新增/修改Agent或模块后同步更新本表。
状态标记：✅已实现并有测试 ｜ 🔶已实现待加强 ｜ ⬜规划中。

## 0. 总览：方案架构 ↔ 代码模块映射

```text
工地摄像头/无人机/手机
  ▼
[A] 视觉感知与Token压缩 ──────────── 感知模块（非Agent）          ✅
  ▼
[B] MLLM驱动的开放风险识别 ─────── 感知模块 + 证据门控模块       ✅
  ▼
[C] 风险推理Agent ────────────────── RiskReasoningAgent           ✅(等级+规范+处置+检索)
  ▼
[D] 协同响应Agent ────────────────── CollaborativeResponseAgent   ✅(工单+通知网关)
  ▼
[E] 复盘学习Agent ────────────────── ReviewLearningAgent          ✅(阈值自动化⬜)
  ═
[F] 应用层（演示系统/前端契约）────── serve_demo + demo_ui         ✅
```

---

## 1. 决策型Agent（有自主判断逻辑，产出决策性输出）

### 1.1 风险推理Agent `RiskReasoningAgent` ✅

- **模块**：`site_safety/agents/risk_reasoning.py`
- **类别**：决策型 / 规则推理
- **职责**：风险等级评定（基础严重度×verified×置信度降级规则）；施工规范条款映射；现场处置建议附带；规范关键词检索（`search_regulations`）
- **输入**：RiskFinding（视觉层结论，只读）
- **输出**：回填 `risk_level`、`risk_level_zh`、`regulation_ids`、`regulations`、`disposal_recommendations`
- **知识库**：`examples/regulations.json`——20条规范条款（JGJ 59-2011 / JGJ 80-2016 / JGJ 46-2005 / JGJ 130-2011 / JGJ 33-2012 / GB 6067 / GB 50720 / GB 2811 / GB 6095 / GB/T 29639）+ 10类风险处置动作库（`disposal_actions`，`_default`兜底）
- **边界**：不得修改 verified/confidence；等级规则确定性可解释，不调用LLM
- **测试**：`tests/test_agents.py::test_risk_level_rules / test_regulation_mapping_attached`

### 1.2 协同响应Agent `CollaborativeResponseAgent` ✅

- **模块**：`site_safety/agents/response.py`
- **类别**：决策型 / 流程编排
- **职责**：verified风险自动建单（SLA：critical 2h / major 24h / general 72h，附处置建议）；pending_review风险生成安全员确认请求；工单状态机管理（非法迁移拒绝）；通知经NotificationGateway分发
- **输入**：DetectionEvent
- **输出**：WorkOrder（含`disposal_recommendations`）、ConfirmationRequest、notifications（含delivery结果）；回填 `risks[].work_order_id`
- **状态机**：pending_confirmation→confirmed→assigned→rectifying→rectified→closed；rejected_false_alarm终态
- **子模块**：通知网关 `site_safety/agents/notify_gateway.py`（file审计底账始终开启；webhook仅在`SAFETY_WEBHOOK_URL`配置时启用，企业微信机器人格式；失败不阻塞主流程）
- **边界**：不修改视觉结论
- **测试**：`tests/test_agents.py::test_work_order_created_only_for_verified / test_work_order_state_machine_rejects_illegal_transition`

### 1.3 复盘学习Agent `ReviewLearningAgent` ✅（阈值自动生效⬜）

- **模块**：`site_safety/agents/review_learning.py`
- **类别**：决策型 / 学习反馈
- **职责**：人工确认/驳回回流案例库（case_library.jsonl）；按risk_id统计误报率；阈值调整建议；班前安全交底Markdown生成
- **输入**：DetectionEvent + 安全员裁决（verdict/reviewer/comment）
- **输出**：CaseRecord、false_alarm_stats、threshold_suggestions、briefing.md
- **边界**：只写案例库与建议，**不自动修改任何阈值或视觉结论**（建议需人工改配置生效）
- **测试**：`tests/test_agents.py::test_review_learning_case_library_and_stats`

---

## 2. 感知与证据模块（非Agent：确定性流水线，无自主决策）

| 模块 | 路径 | 职责 | 状态 |
|---|---|---|---|
| 流水线编排器 | `site_safety/pipeline/orchestrator.py` | 两遍MLLM+SAM3+CLIP全链路调度；`_apply_evidence_guards`证据门控（撤销/降置信/转人工） | ✅ |
| 第一遍视觉分析 | `site_safety/prompting/first_pass.py` | 候选风险池+干扰项+开放发现→结构化JSON+SAM3任务；支持人员裁剪图清单 | ✅ |
| 小目标两阶段感知 | `orchestrator._build_first_pass_images` | SAM3人员预检→逐人放大裁剪随全景送第一遍（`pipeline.person_precheck`配置开关） | ✅ |
| 第二遍证据复核 | `site_safety/prompting/second_pass.py` | 原图+叠加图+裁剪图→visual_verification.json | ✅ |
| 关系核验器 | `site_safety/pipeline/relation.py` | below/near/inside/overlap/missing/blocks_region几何核验；缺失型分级协议 | ✅ |
| 风险Mask构造 | `site_safety/pipeline/mask_builder.py` | 7种mask策略（entity_union/projected_below等） | ✅ |
| 模型适配器 | `site_safety/adapters/`、`integrations/` | Qwen视觉API、GLM、本地SAM3桥接、CLIP ViT-L/14桥接、Mock | ✅ |
| GLM报告层 | `site_safety/prompting/report.py` | 记忆库检索+管理报告（视觉结论只读，守卫强制） | ✅ |

**关键边界（全系统不变式）**：`verified / confidence / manual_review_required` 只能由证据门控产生，
风险推理/协同响应/复盘学习/GLM报告一律只读。

---

## 3. 数据契约与转换模块

| 模块 | 路径 | 职责 | 状态 |
|---|---|---|---|
| 标准化Schema | `site_safety/agents/schemas.py` | DetectionEvent/WorkOrder/ConfirmationRequest/CaseRecord v1.0；offline/realtime区分 | ✅ |
| 事件构建器 | `site_safety/agents/event_builder.py` | 检测输出目录→DetectionEvent（掩码多边形提取、归一化bbox） | ✅ |
| 批量转换CLI | `build_events.py` | 批量输出→events.jsonl/work_orders/confirmations/stats/briefing | ✅ |
| 前端对接文档 | `docs/AGENT_PROTOCOL.md` | 全字段规范+状态机+页面对接点 | ✅ |

## 4. 应用层（演示系统）

| 模块 | 路径 | 职责 | 状态 |
|---|---|---|---|
| 演示服务端 | `serve_demo.py` | 标准库HTTP API；确认/驳回与工单流转动作落盘（复用三个Agent） | ✅ |
| 演示前端 | `demo_ui/index.html` | 五页签SPA：实时告警/待复核/工单管理/统计分析/班前交底 | ✅ |
| 启动配置 | `.claude/launch.json`(`safety-demo`) | 端口8765，数据源outputs/eval_v1/frontend | ✅ |

## 5. 评测与实验模块

| 模块 | 路径 | 职责 | 状态 |
|---|---|---|---|
| 评测子集构建 | `eval_data/build_eval_subset.py` | Roboflow CSS+SHD抽样50张，ground_truth.json | ✅ |
| 评分脚本 | `eval_data/score_eval.py` | 召回/误报/含转人工口径/absence分布 | ✅ |
| 实验记录 | `docs/EXPERIMENT_LOG.md` | 全部评测与工程记录（随做随更新） | ✅ |

## 6. 实时流接入 ✅

| 模块 | 路径 | 职责 | 状态 |
|---|---|---|---|
| 流worker | `run_stream_inspection.py` | 视频文件/RTSP按间隔抽帧→逐帧检测→realtime事件追加frontend目录；单帧失败不中断 | ✅(合成视频实测) |

## 7. 增强模块（原规划项，已全部落地 ✅）

| 模块 | 路径 | 职责 | 状态 |
|---|---|---|---|
| 阈值审批流 | `review_learning.build_threshold_proposals` + `orchestrator._load_threshold_overrides` + serve_demo/app_server审批端点 | 误报统计→提案→人工批准→`configs/threshold_overrides.json`→门控即刻生效 | ✅ E2E实测 |
| 语义检索器 | `site_safety/agents/regulation_retriever.py` | 可插拔：sentence-transformers优先，TF-IDF字符n-gram兜底；hybrid_search精确+语义 | ✅ |
| 多站点聚合 | serve_demo/app_server `sites()` | 站点×设备×工单聚合+前端筛选 | ✅ |
| 正式后端 | `app_server.py`（端口8800） | FastAPI+SQLite文档存储+WebSocket推送+三级角色鉴权+ingest接口；demo_ui双后端兼容 | ✅ E2E实测 |

## 8. 收官三项（✅）

| 模块 | 路径 | 职责 | 状态 |
|---|---|---|---|
| RAG知识库 | `site_safety/agents/knowledge_base.py` + `knowledge_base/`目录 | 任意规程文件(.md/.txt/.pdf/.docx)自动条款级切块入库检索，混入`/api/regulations`结果 | ✅ E2E |
| 用户管理 | app_server `Database.create_user/set_password/set_role` + `/api/users*` | admin增改密改角色（盐化SHA256，密码≥6位），配置页管理区块 | ✅ E2E |
| 部署硬化 | app_server ssl参数+备份 + `docs/DEPLOYMENT.md` | HTTPS、启动/手动在线备份（留20份）、上线检查清单 | ✅ |

## 9. 规划中（⬜）

- 知识库升级语义向量后端（bge，接口已留位）与条款引用回填到风险发现
- 多项目/多租户隔离（当前单库多站点）
