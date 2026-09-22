# 模型分工与成本控制笔记

## 最终职责边界

```text
多模态大模型
├─ 第一次看原图：发现候选风险并生成SAM3任务
└─ 第二次看证据图：输出精简视觉核验JSON

本地视觉模块
├─ SAM3：实体与区域分割
├─ OpenAI ViT-L/14：图文一致性校验
├─ 几何规则：空间关系核验
└─ 证据门控：撤销定位或关系不成立的结论

GLM-5.2
├─ 读取visual_verification.json
├─ 检索风险目录、历史案例和术语记忆
├─ 生成管理报告和统一格式
└─ 汇总统计、人工复核项与后续动作
```

## 不可跨越的边界

- GLM不读取图片，不新增视觉事实。
- GLM不得修改`verified`、`confidence`、可见证据或人工复核要求。
- 记忆库只能提供术语、历史经验和管理建议，不能证明当前图像存在某风险。
- 第二次多模态调用只做视觉核验，不承担长篇报告生成。

## 成本控制

- 多模态模型输出保持短JSON，减少输出Token。
- 报告修改或格式调整只重跑`generate_report.py`。
- SAM3与CLIP结果保存到磁盘，报告阶段不重新加载视觉模型。
- GLM未配置或调用失败时，可由确定性模板生成基础报告。

## 核心文件

```text
site_safety/prompting/first_pass.py     第一次视觉分析
site_safety/prompting/second_pass.py    第二次视觉核验
site_safety/prompting/report.py         GLM报告提示
generate_report.py                      独立报告生成入口
visual_verification.json                视觉层事实合同
final_report.json                       管理层报告
```
