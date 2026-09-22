# Site Safety OpenRisk 工作成果交付说明

## 1. 交付范围

本包包含两部分：

1. 异常识别模块：轻量模型触发接口、MLLM开放风险发现、RiskSpec结构化、CLIP一致性辅助、SAM3精细定位、空间关系核验和报告输出。
2. 原有Agent系统：风险推理、协同响应、工单、通知、复盘学习和演示前端。此次未修改其业务逻辑。

模型权重、数据集、`.env`密钥和大体积完整输出不放入压缩包。模型路径及版本见
[`MODELS_AND_TOOLS.md`](MODELS_AND_TOOLS.md)。

## 2. 输入接口

### 2.1 实时轻量检测器接口

启动独立检测服务：

```powershell
python detection_api.py --host 0.0.0.0 --port 8810 `
  --config configs/qwen_local_open_riskspec.yaml
```

接口：`POST /api/v1/detect/realtime`

JSON结构：

```json
{
  "image_base64": "原始图片Base64",
  "image_format": "jpeg",
  "screening": {
    "triggered": true,
    "anomaly_score": 0.78,
    "suspected_regions": [
      {
        "region_id": "coarse_1",
        "bbox_xyxy": [0.12, 0.18, 0.74, 0.86],
        "score": 0.78,
        "coordinate_space": "normalized_xyxy"
      }
    ],
    "suspected_concepts": [],
    "source_model": "realtime_yolo",
    "calibration_version": "v1"
  },
  "coarse_mask_base64": "可选的粗异常二值掩码Base64"
}
```

YOLO不需要识别具体风险类别，只需给出是否触发、异常分数以及粗区域或粗掩码。
如果上传掩码，程序会：

1. 保存`screening_mask.png`；
2. 自动计算粗区域框；
3. 生成`screening_overlay.jpg`；
4. 生成带上下文的外扩区域视图；
5. 把全图、掩码叠加图和区域视图送入MLLM核验。

上游区域只作为注意力提示，不作为风险证据。MLLM必须同时检查支持证据、反证和
不确定性，并在区域核验后回到全图做开放风险发现。

### 2.2 直接异常图片接口

接口：`POST /api/v1/detect/anomaly-image`

```json
{
  "image_base64": "疑似异常图片Base64",
  "image_format": "jpeg",
  "source": "safety_officer_upload"
}
```

该入口直接进入开放式异常审核。“人工认为疑似异常”仅用于路由，不会强迫MLLM输出异常。

### 2.3 Python直接调用

```python
result = inspector.inspect(
    image_path,
    output_dir,
    screening_trigger=screening_payload,
    screening_mask_path=coarse_mask_path,
)
```

### 2.4 命令行

```powershell
python run_inspection.py --image input.jpg `
  --screening-json trigger.json --screening-mask coarse_mask.png `
  --config configs/qwen_local_open_riskspec.yaml --output-dir outputs/run_001
```

实时目录交接模式仍可使用：

```powershell
python run_stream_inspection.py --source rtsp://... `
  --screening-dir runtime/screening --only-triggered
```

文件命名约定：`frame_00000001.json`和可选的`frame_00000001.mask.png`。

## 3. 输出

每次检测目录包括：

- `screening_trigger.json`：上游筛查信息；
- `screening_mask.png`、`screening_overlay.jpg`：上传粗掩码时生成；
- `first_pass.json`：MLLM RiskSpec；
- `evidence.json`：SAM3、CLIP和空间关系证据；
- `mask_*.png`、`overlay_*.png`、`crop_*.jpg`：风险定位结果；
- `visual_verification.json`：第二遍视觉核验；
- `final_report.json`：管理报告；
- `result.json`：完整机器可读结果。

## 4. 部署注意事项

- 本地Qwen的llama.cpp服务需先启动，当前配置连接`LOCAL_QWEN_BASE_URL`。
- 独立检测API使用单进程、单推理锁，适配当前SAM3和本地MLLM的可变状态；生产环境可通过多GPU、多进程或任务队列水平扩展。
- 不应让YOLO的`anomaly_score`直接决定最终风险；最终状态由MLLM、SAM3和关系核验共同形成。
- 必须保留周期性全图抽检旁路，避免YOLO漏检后重型模块永远看不到事件。
- API默认限制单张图片或掩码解码后不超过25 MiB。

## 5. 验证

交付前完整测试：`54 passed`。测试覆盖原Agent逻辑、检测编排、粗掩码生成叠加图、
异常触发协议、开放风险提示、JSON修复和两个API路由。
