# 实时筛查模型到异常识别模块的触发协议

轻量模型只负责高召回筛查和路由，MLLM + CLIP + SAM3仍负责风险发现、定位、
证据核验与报告。上游输出不能被当作视觉真值。

## 输入契约

参考 [`examples/screening_trigger.example.json`](../examples/screening_trigger.example.json)：

```json
{
  "triggered": true,
  "anomaly_score": 0.81,
  "suspected_regions": [
    {
      "region_id": "region_1",
      "bbox_xyxy": [420, 180, 610, 720],
      "score": 0.86,
      "label": "person_without_clear_ppe",
      "coordinate_space": "pixel_xyxy"
    }
  ],
  "suspected_concepts": ["person", "helmet", "fall_protection"],
  "source_model": "edge_screening_model",
  "calibration_version": "v1"
}
```

`anomaly_score`和每个区域的`score`必须在0到1之间，`bbox_xyxy`必须满足
`x2>x1`、`y2>y1`。`suspected_concepts`可以为空，以支持类别无关异常筛查。

如果轻量检测器与异常识别模块运行在同一进程，也可以直接传递对象：

```python
result = inspector.inspect(
    frame_path,
    output_dir,
    screening_trigger=detector_payload,
)
```

## 调用方式

单图：

```powershell
python run_inspection.py --image sample.jpg `
  --config configs/qwen_local_open_riskspec.yaml `
  --screening-json examples/screening_trigger.example.json `
  --output-dir outputs/triggered_sample
```

批量：在目录中为每张图片准备同名JSON，例如`images/a.jpg`对应
`triggers/a.json`，然后传入`--screening-dir triggers`。

实时流：轻量检测器把`frame_00000001.json`写入交接目录；流worker使用：

```powershell
python run_stream_inspection.py --source rtsp://... `
  --screening-dir runtime/screening_triggers --only-triggered
```

未使用`--only-triggered`时，没有触发文件的帧仍按原流程抽检；使用后，仅
`triggered=true`的帧进入重型异常识别链路。

## 输出与安全边界

每次运行会保存`screening_trigger.json`，并在`result.json`中返回：

- `screening_consistency`: `supported | unsupported | uncertain | not_provided`
- `overall_status`: `confirmed_anomaly | suspected_anomaly | no_visible_anomaly | not_evaluated`

提示词明确规定：触发只表示“值得审核”，不是异常成立证据；MLLM仍可输出无
可见异常或不确定。生产环境还应保留定时关键帧旁路，避免轻量模型漏检后整个
重型链路没有机会审核。
