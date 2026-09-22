# 软件设计蓝图：工作流、数据契约与页面布局

> 面向后续软件/前端开发的总设计文档。数据契约的字段级规范见
> [AGENT_PROTOCOL.md](AGENT_PROTOCOL.md)（本文只放核心摘要，避免两处维护）；
> 模块实现位置见 [AGENT_REGISTRY.md](AGENT_REGISTRY.md)。

---

## 1. 总体工作流与数据流

### 1.1 两种模式一张图

```mermaid
flowchart TD
    subgraph 输入层
        A1[固定摄像头/无人机<br>RTSP·RTMP流] --> W
        A2[视频文件] --> W
        A3[手机/离线图片批量上传] --> B
    end
    W[实时流worker<br>run_stream_inspection.py<br>按间隔抽帧] --> P
    B[批量检测入口<br>run_batch_inspection.py] --> P
    subgraph 检测核心（每帧/每图相同链路）
        P[第一遍MLLM分析<br>候选风险+干扰项+开放发现<br>可选:人员预检裁剪] --> S[SAM3多实体分割<br>+CLIP一致性校验]
        S --> R[几何关系核验<br>+风险Mask构造]
        R --> Q[第二遍MLLM证据复核]
        Q --> G[证据门控<br>撤销/降置信/转人工<br>唯一产生verified·confidence]
    end
    G --> E[事件构建 event_builder<br>→ DetectionEvent JSON]
    E --> RA[风险推理Agent<br>等级+规范条款+处置建议]
    RA --> CA[协同响应Agent]
    CA --> WO[WorkOrder 工单]
    CA --> CR[ConfirmationRequest 待复核]
    CA --> NT[通知网关<br>file/console/webhook]
    WO & CR --> UI[前端六页签]
    UI -- 确认/驳回 --> LA[复盘学习Agent<br>案例库+误报统计+交底]
    LA -- 阈值建议(人工审批) --> G
```

### 1.2 逐模块输入/输出表

| # | 模块 | 输入 | 输出 | 落盘产物 |
|---|---|---|---|---|
| 1a | 实时流worker | RTSP/视频 + interval + device信息 | 抽帧jpg | `frames/frame_*.jpg` |
| 1b | 批量入口 | 图片目录 + config | 逐图调用检测 | `batch_summary.json` |
| 2 | 第一遍MLLM | 原图(+人员裁剪图清单) + 候选风险池 | 逐项present/absent/uncertain + SAM3任务 + 关系检查 | `first_pass.json`、`mllm_first_raw.txt` |
| 3 | SAM3+CLIP | 图 + 文本任务 | 实体Mask/Box/Score + 一致性分 | `entity_*.png` |
| 4 | 关系核验+Mask构造 | Mask + 关系检查定义 | 关系通过/分数 + 风险Mask/叠加图/裁剪 | `evidence.json`、`risk_mask_*` `overlay_*` `crop_*` |
| 5 | 第二遍MLLM | 原图+叠加+裁剪+证据 | 精简视觉核验JSON | `visual_verification.json` |
| 6 | 证据门控 | 5的输出 + 4的证据 | 强制回写verified/confidence/absence_status/转人工 | （写回5的文件） |
| 7 | 事件构建 | 检测输出目录 + device/mode元信息 | **DetectionEvent** | `events.jsonl` |
| 8 | 风险推理Agent | DetectionEvent.risks | 回填risk_level/regulations/disposal_recommendations | （写回事件） |
| 9 | 协同响应Agent | 带等级的事件 | **WorkOrder** / **ConfirmationRequest** / 通知 | `work_orders.json`、`confirmation_requests.json`、`notifications.json`、`notify_outbox.jsonl` |
| 10 | 复盘学习Agent | 安全员裁决(verdict/reviewer/comment) | **CaseRecord** + 误报统计 + 阈值建议 + 交底 | `case_library.jsonl`、`briefing.md` |
| 11 | GLM报告层(可选) | visual_verification + 记忆库 | 管理报告(视觉结论只读) | `final_report.json`、`summary.md` |

**关键不变式**：`verified / confidence / manual_review_required` 只在第6步产生，第7步之后所有模块只读。

### 1.3 两种模式的差异

| | offline（批量/手机上传） | realtime（摄像头/无人机/视频流） |
|---|---|---|
| 入口 | 批量入口 / 未来的上传API | 实时流worker |
| `data_mode` | `"offline"` | `"realtime"` |
| `captured_at` | 可为null（拍摄时间未知） | 必填（帧时间戳） |
| `frame_id`/`stream_ref` | null | 必填 |
| device | `OFFLINE-UPLOAD`或`MOB-*` | `CAM-*`/`UAV-*` |
| 前端去向 | 批量分析/历史检索，不触发实时告警 | 实时告警页 + SLA倒计时 + 通知分发 |
| 节流 | 无 | interval抽帧；`processing_ms`记录单帧延迟 |

---

## 2. 标准化JSON结构（摘要）

五类对象，全部带 `schema_version:"1.0"`，字段只增不改。完整字段表和示例见
[AGENT_PROTOCOL.md](AGENT_PROTOCOL.md) §2–§5。

| 对象 | 主键 | 用户要求的固定字段落点 |
|---|---|---|
| **DetectionEvent** | `event_id` (EVT-) | 设备ID=`device.device_id`；时间戳=`time.captured_at/detected_at/reported_at`；掩码坐标=`risks[].geometry`（像素bbox+归一化bbox+多边形轮廓+掩码文件路径）；风险等级=`risks[].risk_level(_zh)`；置信度=`risks[].confidence`；规范条款ID=`risks[].regulation_ids`+反规范化`regulations`；工单ID=`risks[].work_order_id`回填；offline/realtime=`data_mode` |
| **WorkOrder** | `work_order_id` (WO-) | 状态机7态+SLA`due_at`+`disposal_recommendations`+`history`审计 |
| **ConfirmationRequest** | `request_id` (CR-) | 待复核队列条目：原因+凭证图路径 |
| **CaseRecord** | `case_id` (CASE-) | 模型结论vs人工裁决，案例库JSONL |
| **Notification** | `notification_id` (NT-) | 出站通知+`delivery`分发回执 |

pydantic源：`site_safety/agents/schemas.py`（可 `model_json_schema()` 导出JSON Schema
给前端生成TypeScript类型）。

---

## 3. 页面布局设计

### 3.0 信息架构

```text
① 检测入口（⬜待开发）──产生数据──▶ ②–⑦ 可视化与分析（✅演示系统已实现）
┌────────────────────────────────────────────────────────┐
│ ① 检测入口   摄像头画面/批量上传，系统的"起点"           │
│ ② 实时告警   verified风险卡片流（等级/SLA/规范/处置）    │
│ ③ 待复核     pending_review确认队列（人机协同入口）      │
│ ④ 工单管理   状态机表格+逾期高亮                        │
│ ⑤ 统计分析   等级/类型/工单分布+误报回流+阈值建议        │
│ ⑥ 班前交底   一键生成的Markdown材料                     │
│ ⑦ 系统配置   SLA/通知/规范检索/阈值                     │
└────────────────────────────────────────────────────────┘
```

### 3.1 ① 检测入口页（新增设计，前端开发目标）

```text
┌──────────────────────────────────────────────────────────────┐
│ 顶栏：站点选择▾  设备选择▾  [实时模式|离线模式] 切换          │
├───────────────────────────┬──────────────────────────────────┤
│  实时模式                  │  离线模式                        │
│ ┌───────────────────────┐ │ ┌──────────────────────────────┐ │
│ │                       │ │ │   ⇪ 拖拽图片/文件夹到此处      │ │
│ │   摄像头实时画面        │ │ │   或点击选择批量图片           │ │
│ │   (RTSP预览流)         │ │ │   支持jpg/png/webp            │ │
│ │                       │ │ └──────────────────────────────┘ │
│ └───────────────────────┘ │  已选 N 张 · [开始批量检测]       │
│ 抽帧间隔[10s▾]            │  ┌ 检测进度 ────────────────┐    │
│ [▶开始监测] [⏸暂停]       │  │ ████████░░ 8/12 (约3分钟) │    │
│                           │  └──────────────────────────┘    │
├───────────────────────────┴──────────────────────────────────┤
│ 最新检测结果流（缩略卡片：叠加图+风险名+等级色条，点击进②）      │
└──────────────────────────────────────────────────────────────┘
```

- 实时模式：选设备→预览→开始监测＝启动流worker（后端起子进程），卡片流实时追加；
- 离线模式：上传→批量检测（后端调批量入口）→进度条→完成后跳转统计页；
- **预留API**（待实现，命名与现有风格一致）：
  - `POST /api/detect/upload`（multipart图片→返回批次ID）
  - `POST /api/detect/batch/{batch_id}/start`、`GET /api/detect/batch/{batch_id}/progress`
  - `POST /api/stream/start` `{source, device_id, interval}` / `POST /api/stream/stop`
  - `GET /api/events?since=<ts>`（增量拉取，卡片流轮询用）

### 3.2 ② 实时告警页（已实现）

```text
┌ 卡片网格（按等级排序：重大→较大→一般）─────────────┐
│ ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│ │ 叠加图      │  │ …          │  │ …          │    │
│ │[重大][实时] │  └────────────┘  └────────────┘    │
│ │ 风险名      │   卡片内容：                        │
│ │ 事件/设备/  │   📖 规范条款引用（可多条）          │
│ │ 置信度/时间 │   🛠 处置建议                       │
│ │ 工单号+SLA  │   SLA剩余倒计时/逾期红字            │
│ └────────────┘                                    │
└──────────────────────────────────────────────────┘
数据源: GET /api/events 过滤 risks[].verified && risk_level∈{critical,major,general}
```

### 3.3 ③ 待复核页（已实现）

凭证图（叠加/裁剪）+ 不确定原因 + 备注输入 + **[✔确认属实] [✘驳回误报]**。
确认→自动生成工单并跳转④；驳回→写入案例库。
数据源: `GET /api/confirmations` (status=pending)；动作: `POST /api/confirmations/{id}/decide`。

### 3.4 ④ 工单管理页（已实现）

表格列：工单号｜等级｜风险(悬浮显示处置建议)｜状态｜负责人｜整改期限｜操作按钮（仅显示
状态机允许的下一步）。逾期行高亮。
数据源: `GET /api/work_orders` + `GET /api/transitions`；动作: `POST /api/work_orders/{id}/transition`。

### 3.5 ⑤ 统计分析页（已实现）

统计卡（事件总数/异常数/待复核/工单数）+ 四组条形图（等级分布/已确认风险类型/工单状态/
误报回流比例）+ 阈值调整建议条。数据源: `GET /api/stats`（实时聚合）。

### 3.6 ⑥ 班前交底页（已实现）

近期高发风险 + 典型案例回顾 + 今日重点提醒，Markdown渲染，可打印。
数据源: `GET /api/briefing`（由复盘学习Agent按案例库实时生成）。

### 3.7 ⑦ 系统配置页（已实现）

统计卡（规范条款数/通知渠道/降级阈值）+ SLA与通知对象表 + 规范知识库关键词检索。
数据源: `GET /api/config`、`GET /api/regulations?q=`。

### 3.8 视觉规范（沿用演示系统）

深色主题；等级色：重大`#ff5c5c`/较大`#ffab40`/一般`#ffe066`/待复核`#6ec6ff`/提示灰；
掩码绘制用 `geometry.bbox_xyxy_norm`（随容器缩放）或 `mask_polygons`（canvas半透明填充）。

---

## 4. 从演示系统到正式软件的差距清单

| 项 | 演示现状 | 正式软件需要 |
|---|---|---|
| 检测入口页 | 无（数据预生成） | §3.1整页 + 预留API |
| 后端 | 标准库HTTP单文件 | FastAPI/Flask + 任务队列（检测异步化） |
| 存储 | JSON文件为事实源 | SQLite/PostgreSQL（契约字段即表结构） |
| 实时刷新 | 60s轮询 | WebSocket/SSE推送 |
| 多用户 | 无鉴权 | 角色（安全员/工长/管理员）+登录 |
| 通知 | file底账+可选webhook | 企业微信/短信正式接入 |

契约（第2节）在迁移中保持不变——这是演示与正式软件之间的稳定接口。
