# YOLO—VLM—前端接口整合说明

## 1. 当前完整数据链

```text
图片上传 / 摄像头截帧
        │
        ▼
detect_bridge.py（8810）
        │
        ├─ 内置两套 YOLO26 推理
        │    ├─ CSS v28：安全帽、口罩、反光衣、人员、机械、车辆
        │    └─ ConstructionSite：人员、挖掘机、钢筋、四类规则违规
        │
        ▼
ScreeningTrigger
  ├─ triggered
  ├─ anomaly_score
  ├─ suspected_regions（像素粗框）
  ├─ suspected_concepts
  └─ source_model / reason
        │
        ├─ 摄像头未触发：跳过重型模型，等待后续帧
        ├─ 每30分钟/2小时：周期性全图直检，避免未知异常永远无法进入VLM
        └─ 上传/人工强制：无论YOLO是否触发都进入VLM
        ▼
Qwen3-VL → SAM3 → 证据/空间关系 → Agent → 报告
        │
        ▼
PC前端阶段进度、YOLO粗框、SAM3掩码、风险和工单
```

YOLO结果只决定实时调度和视觉注意区域，不作为最终风险事实。最终异常类型、置信度和报告由VLM、SAM3、规则核验与Agent共同形成。

## 2. 内置模型路径

| 模块 | 路径 |
|---|---|
| Python统一环境 | `E:\work\competition\combine\env\python.exe` |
| YOLO CSS | `combine\yolo_site_workspace_portable\weights\yolo26m_css_v28_baseline_best.pt` |
| YOLO ConstructionSite | `combine\yolo_site_workspace_portable\weights\yolo26m_construction_site_best.pt` |
| Qwen3-VL | `E:\model\Qwen3-VL-8B-Instruct-Q4_K_M.gguf` |
| Qwen视觉投影 | `E:\model\mmproj-BF16.gguf` |
| SAM3代码 | `E:\SAM3_MAIN\sam3-main` |
| SAM3权重 | `E:\SAM3_MAIN\SAM3\sam3.pt` |
| CLIP（云端配置保留） | `C:\Users\SYS03\.cache\clip\ViT-L-14.pt` |

## 3. 前端接口

### 3.1 图片上传

`POST /api/detect/upload`，`multipart/form-data`：

| 字段 | 默认值 | 含义 |
|---|---|---|
| `file` | 必填 | 输入图片 |
| `profile` | 当前档位 | `offline` / `standard` / `demo` |
| `force_inspection` | `true` | 上传图片即使YOLO未触发也进入VLM |
| `screening_json` | 空 | 可选的外部实时模型结果 |

### 3.2 摄像头帧

`POST /api/detect/camera-frame`：

```json
{
  "image_base64": "...",
  "device_id": "CAM-01",
  "profile": "offline",
  "force_inspection": false,
  "force_full_audit": false,
  "audit_interval_minutes": 30,
  "screening": null
}
```

`screening=null`时桥接调用内置YOLO；生产实时服务也可直接填入外部`ScreeningTrigger`，桥接将跳过内置YOLO并使用外部粗框。

### 3.3 定时/人工全面检测

`POST /api/detect/full-audit`使用与摄像头帧相同的JSON结构。该接口强制绕过YOLO、粗框、粗掩码和候选提示，直接把完整图像交给VLM开放发现，再进入SAM3、证据核验与报告链。调度器可以每30分钟或2小时调用；普通`camera-frame`也会按同一设备的`audit_interval_minutes`自动判断周期。

### 3.4 返回结果新增字段

```json
{
  "screening": {},
  "screening_overlay": "/api/detect/jobs/.../media/screening_overlay.jpg",
  "screening_mask": "/api/detect/jobs/.../media/screening_coarse_mask.png",
  "routed_to_vlm": true,
  "full_audit": false,
  "audit_mode": "screened"
}
```

任务目录同时保存：

- `yolo_detections.json`：两套YOLO全部原始框；
- `screening_trigger.json`：交给VLM的标准路由协议；
- `screening_overlay.jpg`：YOLO注意力框；
- `screening_coarse_mask.png`：交给VLM的粗区域掩码；
- 原有`first_pass.json`、`evidence.json`、SAM3 Mask及最终报告。

## 4. 实时门控策略

1. `NO-Hardhat`、`NO-Mask`、`NO-Safety-Vest`和四类`rule_*_violation`可以触发VLM。
2. 人员、机械、车辆等中性类别本身不是异常，只作为注意区域。
3. 人员与机械粗框距离过近时产生`person_near_machinery`候选，最终仍由VLM/SAM3核验。
4. YOLO推理失败时采用故障开放策略，帧进入VLM，避免因轻模型故障漏掉风险。
5. 摄像头按设备默认每30分钟全图直检一次，也可设为每2小时；人工/API可随时触发。
6. 全面检测不使用YOLO类别或ROI作为提示，因此可发现吸烟、倒地、电线、临边防护等未训练类别。

门限位于三个业务配置的`screening`段，可以现场标定，但不应把YOLO置信度直接当最终风险置信度。

## 5. 已完成验证

- Python完整测试：86项通过；
- PC前端生产构建通过；
- 两套真实YOLO权重加载及推理通过；
- 示例上传：YOLO → ScreeningTrigger → Mock VLM → 前端结果契约通过；
- 空白摄像头帧：YOLO未触发 → 跳过VLM通过；
- 本地SAM3和CLIP在统一环境中的真实推理已通过。
- 单一Qwen进程下的七张示例组合链验证完成：7/7任务成功、6/7输出至少一个风险、5/7命中图片标题指定主风险；总耗时324.44秒，平均46.35秒/张。
- 第5张材料/通道堵塞和第6张脚手架结构隐患是本轮主风险漏检边界；详细结果见`outputs/combined_seven_20260809_003157/SUMMARY.md`。
