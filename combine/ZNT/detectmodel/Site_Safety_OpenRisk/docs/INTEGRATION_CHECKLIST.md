# 本地模型对齐检查表

## SAM3

- [ ] `set_image`只在每张新图开始时调用一次
- [ ] 同一图片可连续执行多个文本Prompt
- [ ] 返回Mask尺寸与原图一致
- [ ] 多实例输出未被错误合并
- [ ] Box坐标使用`[x1,y1,x2,y2]`
- [ ] Score转换到0—1
- [ ] 空结果返回`[]`
- [ ] CPU/GPU Tensor在返回前转为NumPy

## CLIP（可选）

- [ ] 图像预处理与本地权重匹配
- [ ] 文本编码模板固定
- [ ] 图像和文本特征完成L2归一化
- [ ] 输出被规范化为0—1
- [ ] CLIP只作为一致性证据，不直接替代风险判断

## 多模态API

- [ ] `.env.qwen.example`已复制为`.env`且仅在本地填写API Key
- [ ] 百炼兼容地址以`/compatible-mode/v1/chat/completions`结尾
- [ ] 模型能够读取图片
- [ ] 支持一次上传原图和多张证据图
- [ ] 输出严格JSON
- [ ] JSON错误有重试或人工记录
- [ ] Prompt禁止推测设备运行状态和人员权限
- [ ] API日志不保存敏感图片，或已符合比赛数据要求

## GLM报告与记忆层

- [ ] GLM只接收`visual_verification.json`和声明的记忆库内容
- [ ] GLM不接收图片，也不新增视觉事实
- [ ] `verified`、`confidence`和人工复核标记由程序强制回写
- [ ] 报告格式调整可通过`generate_report.py`独立重跑
- [ ] GLM不可用时可回退到确定性报告模板

## 端到端

- [ ] 正常图像可输出无异常
- [ ] MLLM提出的每个task_id都可追踪到Mask
- [ ] 关系检查引用的task_id真实存在
- [ ] 缺失型风险没有要求分割不存在物体
- [ ] 第二次MLLM能够撤销证据不足的风险
- [ ] `visual_verification.json`、`final_report.json`、`summary.md`和叠加图均能生成
