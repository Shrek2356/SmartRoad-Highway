# Site Safety OpenRisk 检测与Agent模块

本模块实现工地安全开放风险识别、风险定位、证据核验和Agent闭环。

## 主链

1. YOLO对摄像头帧进行低成本注意力初筛；
2. MLLM根据完整图像与候选区域输出结构化RiskSpec；
3. SAM3定位风险实体并生成Mask、Bounding Box与Presence Score；
4. 程序化规则核验空间关系、缺失型风险、支持证据与反证；
5. Agent生成工单、人工复核请求、通知、规范依据和复盘材料。

## 生产配置

- 配置：`configs/qwen_local_production.yaml`
- 检测桥：`detect_bridge.py`
- 业务服务：`app_server.py`
- 本地模型服务：`scripts/run_local_qwen_server.py`
- 运行路径由设置页或部署助手维护，模型权重不随比赛包分发。

## 验证

```powershell
python -m pytest -q
```

比赛包保留测试代码和八张展示案例，不包含历史推理批次与逐轮模型日志。
