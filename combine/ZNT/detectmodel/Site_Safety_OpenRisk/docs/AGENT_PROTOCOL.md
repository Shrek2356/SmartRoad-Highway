# Agent层数据契约（前端对接文档）v1.0

本协议定义检测系统 → 前端/软件层的全部数据结构。所有对象带`schema_version`，
字段只增不改，保证前端向后兼容。数据源代码：`site_safety/agents/schemas.py`
（pydantic模型，可直接`model_json_schema()`导出JSON Schema给前端做类型生成）。

## 1. 数据流总览

```text
摄像头/无人机/手机(realtime) ─┐
                              ├─ 视觉流水线 → DetectionEvent ─┬─ 实时告警页（level≠info/pending_review）
离线图片批量上传(offline)    ─┘                              ├─ 待复核队列（ConfirmationRequest）
                                                             ├─ 工单管理页（WorkOrder状态机）
                                                             ├─ 统计分析页（dashboard_stats聚合）
                                                             └─ 复盘学习（CaseRecord案例库 + briefing.md）
```

生成工具：`python build_events.py --batch-dir <检测输出目录> --output-dir <前端数据目录>`
产物：`events.jsonl`、`work_orders.json`、`confirmation_requests.json`、
`notifications.json`、`dashboard_stats.json`、`briefing.md`、`case_library.jsonl`。

## 2. DetectionEvent（检测事件，核心对象）

```json
{
  "schema_version": "1.0",
  "event_id": "EVT-20260726-a1b2c3d4",
  "data_mode": "realtime",
  "device": {
    "device_id": "CAM-A3-007",
    "device_type": "fixed_camera",
    "site_id": "SITE-01",
    "location_desc": "3号楼东侧塔吊区"
  },
  "time": {
    "captured_at": "2026-07-26T14:03:21+08:00",
    "detected_at": "2026-07-26T14:03:24+08:00",
    "reported_at": "2026-07-26T14:03:25+08:00",
    "processing_ms": 2870
  },
  "media": {
    "image_path": "outputs/site_001/frame_000123.jpg",
    "image_width": 1920,
    "image_height": 1080,
    "frame_id": "000123",
    "stream_ref": "rtsp://.../cam007"
  },
  "scene_summary": "塔吊正在吊装钢筋，下方有工人通行。",
  "overall_has_anomaly": true,
  "risks": [
    {
      "risk_id": "worker_under_suspended_load",
      "risk_name_zh": "人员位于悬吊物下方",
      "verified": true,
      "confidence": 0.88,
      "absence_status": "not_applicable",
      "risk_level": "critical",
      "risk_level_zh": "重大风险",
      "regulation_ids": ["GB6067-LIFTING"],
      "regulations": [
        {
          "regulation_id": "GB6067-LIFTING",
          "name_zh": "起重机械安全规程 GB/T 6067.1",
          "clause": "吊装作业",
          "requirement_zh": "起重臂和吊物下方严禁站人、通行或作业。"
        }
      ],
      "geometry": {
        "bbox_xyxy": [412.0, 236.5, 980.3, 1044.0],
        "bbox_xyxy_norm": [0.2146, 0.219, 0.5106, 0.9667],
        "mask_polygons": [[[430, 250], [960, 250], [955, 1040], [425, 1030]]],
        "mask_path": ".../risk_mask_worker_under_suspended_load.png",
        "overlay_path": ".../overlay_worker_under_suspended_load.png",
        "crop_path": ".../crop_worker_under_suspended_load.jpg"
      },
      "visible_evidence": ["吊物正下方站有一名工人"],
      "risk_description": "工人处于吊物垂直投影区域内。",
      "uncertainties": [],
      "manual_review_required": false,
      "disposal_recommendations": [
        "立即指挥吊物下方人员撤离，暂停起重作业",
        "设置吊装警戒区围挡，安排信号指挥与专人监护"
      ],
      "work_order_id": "WO-20260726-9f3e2a1b"
    }
  ],
  "pipeline": {
    "config_name": "qwen_visual",
    "mllm_model": "qwen-vl",
    "output_dir": "outputs/site_001",
    "evidence_path": ".../evidence.json",
    "visual_verification_path": ".../visual_verification.json"
  },
  "review": {"status": "pending", "reviewer": null, "reviewed_at": null, "comment": ""}
}
```

### 2.1 offline与realtime的区别

| 字段 | realtime | offline |
|---|---|---|
| `data_mode` | `"realtime"` | `"offline"` |
| `device.device_id` | 真实设备编号（CAM-/UAV-/MOB-前缀） | `"OFFLINE-UPLOAD"`或上传者标识 |
| `device.device_type` | `fixed_camera` / `drone` / `mobile` | `offline_upload` |
| `time.captured_at` | 必填（帧时间戳） | 可为`null`（拍摄时间未知） |
| `media.frame_id` / `stream_ref` | 必填 | `null` |
| 前端处理 | 进实时告警页，按SLA倒计时 | 进批量分析/历史检索页，不触发实时告警 |

### 2.2 坐标约定

- `bbox_xyxy`：像素坐标`[x1,y1,x2,y2]`，原点在图像左上角；
- `bbox_xyxy_norm`：除以图宽/图高的归一化坐标（0–1），前端按显示尺寸缩放即可；
- `mask_polygons`：风险区域掩码的外轮廓多边形数组（像素坐标，已Douglas-Peucker简化，
  最多8个连通域），前端可直接用canvas/SVG绘制半透明高亮；
- `mask_path`/`overlay_path`/`crop_path`：原始PNG/JPG文件路径，用于详情页。

### 2.3 风险等级 `risk_level`

| 值 | 中文 | 来源规则 | 前端行为 |
|---|---|---|---|
| `critical` | 重大风险 | verified且基础严重度critical（吊物下方有人、无安全带高处作业、烟火、倒地、脚手架坍塌） | 红色告警+弹窗+声音，SLA 2小时 |
| `major` | 较大风险 | verified且基础严重度major（未戴帽、临边缺护栏、人机过近）| 橙色告警，SLA 24小时 |
| `general` | 一般风险 | verified且基础严重度general，或verified但置信度<0.70降一级 | 黄色告警，SLA 72小时 |
| `pending_review` | 待人工复核 | 未verified但`manual_review_required=true` | 进待复核队列，不告警 |
| `info` | 提示信息 | 未verified且无需复核 | 仅存档可查询 |

等级规则实现于`site_safety/agents/risk_reasoning.py`（确定性规则，可解释）。
`confidence`与`verified`来自视觉层，任何下游模块不得修改（守卫强制）。

## 3. WorkOrder（工单）

```json
{
  "schema_version": "1.0",
  "work_order_id": "WO-20260726-9f3e2a1b",
  "event_id": "EVT-20260726-a1b2c3d4",
  "risk_id": "worker_under_suspended_load",
  "risk_name_zh": "人员位于悬吊物下方",
  "risk_level": "critical",
  "risk_level_zh": "重大风险",
  "status": "pending_confirmation",
  "created_at": "2026-07-26T14:03:25+08:00",
  "due_at": "2026-07-26T16:03:25+08:00",
  "site_id": "SITE-01",
  "device_id": "CAM-A3-007",
  "assignee": null,
  "notify_targets": ["safety_director", "site_manager", "area_foreman"],
  "disposal_recommendations": ["立即指挥吊物下方人员撤离，暂停起重作业", "..."],
  "rectification_note": "",
  "history": [
    {"at": "...", "from_status": null, "to_status": "pending_confirmation", "by": "system", "note": "系统自动创建"}
  ]
}
```

### 3.1 工单状态机

```text
pending_confirmation ──confirmed──▶ assigned ──▶ rectifying ──▶ rectified ──▶ closed
        │                                              ▲              │
        └──rejected_false_alarm（终态，回流案例库）      └──复验不通过───┘
```

非法迁移会被`CollaborativeResponseAgent.transition()`拒绝（ValueError）。
`due_at`按等级SLA自动计算；前端逾期高亮用`now > due_at 且 status未到rectified`。

### 3.2 创建规则

- verified风险（critical/major/general）→ 自动建单，初始`pending_confirmation`，
  附带按risk_id生成的`disposal_recommendations`（处置动作库：`examples/regulations.json`
  的`disposal_actions`，未命中时用`_default`兜底）；
- `pending_review`风险→ 先生成ConfirmationRequest，安全员确认后再建单；
- 通知统一写入`notifications.json`出站队列（title/body/targets）。

### 3.3 通知网关

`site_safety/agents/notify_gateway.py`，渠道可插拔：

| 渠道 | 启用条件 | 说明 |
|---|---|---|
| `file` | 始终 | 追加写`notify_outbox.jsonl`审计底账 |
| `console` | 构造参数`console=True` | 调试打印 |
| `webhook` | 设置环境变量`SAFETY_WEBHOOK_URL` | 企业微信群机器人markdown格式POST；未配置则不发任何外部请求 |

发送结果写回通知记录`delivery`字段；失败不阻塞主流程。

## 4. ConfirmationRequest（待复核队列条目）

字段：`request_id`(CR-前缀)、`event_id`、`risk_id`、`reason`（不确定性说明）、
`crop_path`/`overlay_path`（复核凭证图）、`status`(`pending/confirmed/rejected`)。
前端"待复核"页展示凭证图+原因，安全员一键确认/驳回。

## 5. CaseRecord（案例库，复盘学习Agent）

人工确认/驳回结果由`ReviewLearningAgent.ingest_confirmation()`写入
`case_library.jsonl`（每行一条）。字段含模型结论(`model_verified/model_confidence`)
与人工裁决(`human_verdict`)，用于：

- 误报统计：`false_alarm_stats()`按risk_id输出误报率；
- 阈值建议：`threshold_suggestions()`（只建议，人工确认后改配置生效）;
- 班前交底：`generate_briefing()`输出Markdown（近期高发风险+典型案例+重点提醒）。

## 6. dashboard_stats.json（统计分析页聚合）

```json
{
  "total_events": 50,
  "events_with_anomaly": 11,
  "risk_level_distribution": {"critical": 1, "major": 8, "general": 2, "pending_review": 9, "info": 30},
  "verified_risk_distribution": {"施工人员未佩戴安全帽": 6},
  "work_orders_created": 11,
  "pending_confirmations": 9,
  "notifications_enqueued": 11
}
```

## 7. 系统配置页对接点

| 配置项 | 数据位置 |
|---|---|
| 风险目录/干扰项 | `examples/risk_catalog.json` |
| 规范知识库+处置动作库 | `examples/regulations.json`（`regulations`/`risk_regulation_map`/`disposal_actions`） |
| 等级SLA与通知对象 | `site_safety/agents/response.py`（`SLA_HOURS`/`notify_targets`，可注入） |
| 通知webhook | 环境变量`SAFETY_WEBHOOK_URL` |
| 门控阈值 | `configs/*.yaml`的`pipeline.relation_defaults` |
| 小目标两阶段感知 | `configs/*.yaml`的`pipeline.person_precheck`（enabled/prompt/min_score/max_crops） |
| 等级降级阈值 | `RiskReasoningAgent(downgrade_threshold=0.70)` |

演示服务对应端点：`GET /api/config`（当前生效配置）、`GET /api/regulations?q=关键词`（规范检索）。

## 7.1 实时流接入

```bash
python run_stream_inspection.py --source rtsp://... --device-id CAM-A3-007 \
    --config configs/qwen_visual.yaml --output-root outputs/stream_cam007 \
    --frontend-dir outputs/eval_v1/frontend --interval-seconds 10
```

worker按间隔抽帧→逐帧检测→以`data_mode=realtime`把事件/工单/确认/通知**追加**进frontend
数据目录，前端刷新即见。支持视频文件（按帧快进）与RTSP/RTMP（按墙钟节流）；单帧失败
写error.txt不中断流。

## 8. 不变式（前端可依赖）

1. `event_id`/`work_order_id`/`request_id`/`case_id`全局唯一且带类型前缀；
2. `verified/confidence/manual_review_required`由视觉层门控产生，下游只读；
3. 工单一定关联到存在的`event_id`+`risk_id`；`risks[].work_order_id`双向可查；
4. 时间统一ISO 8601带时区；
5. `risk_level=info`的风险不会出现在工单和告警中。
