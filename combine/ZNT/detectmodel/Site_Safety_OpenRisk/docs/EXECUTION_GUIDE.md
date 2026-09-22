# Site Safety OpenRisk Training-Free：完整执行说明

## 1. 项目目标与边界

本工程只完成工地图像异常识别核心链路，输入为单张工地图像，输出为：

1. **异常定位输出**：SAM3实体Mask、异常主体Mask、危险源Mask、推算危险区域和叠加图；
2. **视觉核验输出**：多模态大模型根据原图和定位证据生成精简事实JSON；
3. **管理报告输出**：GLM-5.2根据视觉核验JSON与记忆库生成报告。

当前不包含自动安全评级、责任通知和后续Agent工具调用。规范或历史记忆只作为
GLM报告层的管理参考，不能改变视觉结论。

本方案使用预训练多模态大模型API与本地SAM3，不进行梯度训练。企业落地时可把云端MLLM适配器换成本地部署模型，而保持相同JSON协议。

---

## 2. 完整运行结构

```text
输入工地图像 I
       │
       ▼
A. 推理时异常暴露候选池
├─ 固定核心风险
├─ 无关干扰风险
└─ 开放异常发现指令
       │
       ▼
B. 第一次MLLM分析
├─ 全局场景理解
├─ 每项风险 present / absent / uncertain
├─ 可见事实与不确定信息
├─ 拆解风险主体、危险源、防护物和区域
├─ 生成SAM3短文本Prompt
├─ 生成空间关系检查任务
└─ 指定风险Mask构造策略
       │
       ▼
C. SAM3多实体分割
├─ 对每个task_id执行文本分割
├─ 输出一个或多个实例Mask
├─ 输出Box和Score
└─ 可选CLIP一致性复核
       │
       ▼
D. 无训练证据核验
├─ below_and_horizontal_overlap
├─ near
├─ inside
├─ overlap
├─ missing
└─ blocks_region
       │
       ▼
E. 多层级风险Mask构造
├─ entity_union
├─ subject_only
├─ object_only
├─ intersection
├─ projected_below
├─ missing_subject
└─ expanded_object_zone
       │
       ▼
F. 图像级背景抑制
├─ 保存异常叠加图
└─ 裁剪异常主体与必要上下文
       │
       ▼
G. 第二次MLLM证据复核
├─ 原始图像
├─ SAM3叠加图
├─ 异常局部裁剪
├─ SAM3分数
└─ 几何关系结果
       │
       ▼
精简visual_verification.json
       │
       ▼
H. GLM-5.2报告与记忆层
├─ 读取视觉核验JSON
├─ 检索风险目录与历史记忆
├─ 保持视觉结论不可变
└─ 输出final_report.json与summary.md
```

---

## 3. OpenRisk模块在训练自由系统中的对应关系

### 3.1 异常暴露

OpenRisk在训练中将真实类别与无关类别混合，或只使用无关类别，迫使模型依赖视觉证据。

本框架不训练模型，因此将其改为**推理时异常暴露**：

```text
核心风险 + 随机干扰风险 → MLLM逐项判断
```

其作用是：

- 防止只描述最显眼异常；
- 降低提示词诱导；
- 要求模型明确排除不存在风险；
- 可构造反幻觉压力测试。

对应配置：

```yaml
risk_catalog:
  include_all_core: true
  distractor_count: 3
  allow_open_discovery: true
```

### 3.2 多尺度语义投影器

最终系统以MLLM结构化风险描述、视觉定位和程序化证据核验形成无训练证据链：

```text
全图MLLM语义
+ SAM3实体与分数
+ 几何关系结果
+ 局部裁剪复核
+ 可选CLIP相似度
→ 最终风险结论
```

当前`evidence_score`只是便于调试的均值，不应直接作为正式安全评级。第二次MLLM负责综合视觉证据并保留不确定性；GLM仅负责报告组织。

### 3.3 背景Token压缩

API模型无法暴露内部视觉Token，无法直接复现反向注意力压缩。因此采用：

```text
全图发现 → SAM3定位 → 局部裁剪 → MLLM复核
```

局部裁剪必须保留风险关系所需上下文，例如人员、吊物以及两者之间的区域。

### 3.4 Multi-Level Mask Decoder

SAM3只输出可见实体Mask，风险区域可能还需要后处理：

- 未戴安全帽：使用工人头部或工人Mask，而不是“缺失安全帽Mask”；
- 吊物下方有人：使用人员Mask、吊物Mask和向下投影危险区域；
- 通道堵塞：使用障碍物与通道的交叠区域；
- 机械附近人员：使用机械扩张区域与人员证据。

---

## 4. 第一次MLLM输出协议

`FirstPassResponse`必须包含：

```json
{
  "scene_summary": "场景摘要",
  "has_possible_anomaly": true,
  "candidate_assessments": [
    {
      "risk_id": "worker_under_suspended_load",
      "risk_name_zh": "人员位于悬吊物下方",
      "status": "present",
      "confidence": 0.88,
      "observed_facts": ["可见事实"],
      "sam3_tasks": [
        {
          "task_id": "worker_01",
          "role": "subject",
          "prompt": "construction worker",
          "expected_count": 1
        }
      ],
      "relation_checks": [],
      "mask_strategy": "subject_only",
      "uncertainties": []
    }
  ],
  "open_discoveries": []
}
```

### SAM3 Prompt原则

使用可见的简短实体概念：

```text
construction worker
safety helmet
suspended construction load
excavator
smoke
construction passage
```

避免直接使用完整报告句子，也不要要求SAM3分割不存在的物体。

---

## 5. SAM3本地桥接协议

桥接文件：

```text
integrations/sam3_bridge_user.py
```

必须实现：

```python
class SAM3Bridge:
    def set_image(self, image: PIL.Image.Image) -> None:
        ...

    def segment(self, *, prompt, task_id, role, expected_count=None):
        return [
            {
                "mask": mask,                 # np.ndarray [H,W]
                "score": 0.91,
                "box_xyxy": [x1, y1, x2, y2]
            }
        ]
```

关键约束：

- Mask必须与原图宽高一致；
- Mask可为bool或0/1数组；
- 分数必须转换到0—1；
- 同一Prompt可以返回多个实例；
- 无结果时返回空列表，不要伪造空Mask实例。

---

## 6. CLIP可选支路

CLIP不决定主链结果，只用于检查：

> 当前图像或裁剪图与SAM3 Prompt是否存在基本语义一致性。

接口：

```python
score(image, texts) -> list[float]
```

适合用于：

- 检查SAM3是否因模糊Prompt分割到错误对象；
- 比较多个Prompt表达；
- 为低一致性结果增加人工复核标记。

不要把CLIP分数直接当作安全风险置信度。

---

## 7. 关系核验类型

### below_and_horizontal_overlap

用于人员位于吊物下方。条件：

- 人员中心纵坐标低于吊物中心；
- 两个Box在水平方向具有足够重叠。

### near

用于人员与机械距离过近。当前使用图像对角线归一化中心距离，是二维近似，不能代表真实物理距离。

### inside

用于主体是否进入区域。使用主体Mask落入区域Mask的比例。

### overlap / blocks_region

用于材料是否占用通道、对象是否发生交叠。

### missing

用于缺失型风险。当前保守逻辑：

```text
主体存在 AND 防护物未定位 → 缺失证据不确定，要求视觉复核或人工复核
```

只有显式启用`allow_missing_from_non_detection`时才允许把未检出作为缺失关系通过；
默认关闭，以避免小目标漏检造成误报。

---

## 8. 风险Mask策略

| 策略 | 用途 |
|---|---|
| `entity_union` | 合并全部相关实体 |
| `subject_only` | 只标记受威胁或违规主体 |
| `object_only` | 只标记危险源 |
| `intersection` | 标记主体与区域的交叠部分 |
| `projected_below` | 吊物向下投影形成危险区 |
| `missing_subject` | 缺失型异常标记主体 |
| `expanded_object_zone` | 机械或危险源周边扩张区域 |

当前这些区域是二维可解释近似，不应被表述为经过标定的真实安全距离。

---

## 9. 第二次MLLM视觉复核

输入：

- 原图；
- 每个风险叠加图；
- 每个风险局部裁剪；
- 第一次判断；
- SAM3实例、Score和Box；
- 关系核验结果；
- 可选CLIP一致性分数。

输出：

```json
{
  "overall_has_anomaly": true,
  "overall_summary": "总体结论",
  "final_risks": [
    {
      "risk_id": "...",
      "risk_name_zh": "...",
      "verified": true,
      "confidence": 0.91,
      "visible_evidence": ["..."],
      "risk_description": "...",
      "uncertainties": ["..."],
      "manual_review_required": true
    }
  ]
}
```

关键原则：

- 关键实体未定位：降低置信度或撤销；
- 关系核验失败：不得把关系型风险直接确认；
- 图像模糊或遮挡：保留不确定性；
- 单张图像无法确认设备运行状态或行为持续时间。
- 只输出简短视觉事实，不生成整改建议或长篇报告。

---

## 10. GLM-5.2报告与记忆层

输入为证据门控后的`visual_verification.json`和配置中声明的风险目录、术语或历史记忆，
不输入原图、叠加图或裁剪图。

硬约束：

- 不得改变`verified`、`confidence`和`manual_review_required`；
- 不得新增当前图像中的人员、设备、关系或异常事实；
- 记忆库只用于术语统一、管理建议和历史经验；
- GLM未启用时由确定性模板生成基础报告。

视觉处理完成后可以单独重跑报告：

```powershell
python generate_report.py `
  --visual-verification outputs\site_001\visual_verification.json `
  --config configs\default.yaml
```

---

## 11. 运行输出文件

```text
output_dir/
├─ mllm_first_raw.txt        # 第一次API原始文本
├─ first_pass.json           # 校验后的第一次输出
├─ entity_*.png              # SAM3实体Mask
├─ risk_mask_*.png           # 规则构造的风险Mask
├─ overlay_*.png             # 原图叠加定位结果
├─ crop_*.jpg                # 局部裁剪
├─ evidence.json             # 定位和关系证据
├─ mllm_second_raw.txt       # 第二次API原始文本
├─ visual_verification.json  # 多模态模型的最终视觉事实合同
├─ glm_report_raw.txt        # GLM原始输出，仅启用GLM时存在
├─ glm_report_error.txt      # GLM失败记录，仅失败回退时存在
├─ final_report.json         # GLM或确定性模板生成的管理报告
├─ summary.md                # 人类可读报告
└─ result.json               # 完整总结果
```

### 11.1 批次交付报告

批量输出目录可进一步整理为一份可交付Markdown：

```powershell
python generate_result_summary.py `
  --batch-dir outputs\examples_qwen `
  --output outputs\examples_qwen\FINAL_RESULT_SUMMARY.md
```

固定规则：

- `visual_verification.json`优先于GLM报告和文件名标签；
- 必须保留风险确认状态、置信度、不确定性和人工复核要求；
- 有文件时展示原图、`overlay_*.png`和`risk_mask_*.png`；
- 没有掩码时明确写出关键实体定位失败，不生成替代图；
- 同时统计“包含已确认风险的图像”和“包含人工复核项的图像”。

### 11.2 缺失型防护证据协议

对于安全带、安全绳、防护栏、踢脚板、洞口盖板和安全网：

1. SAM3的`subject`任务定位危险锚点或应检查区域；
2. `protective_item`任务搜索应存在的防护物；
3. `missing`关系必须携带`inspection_zone_visibility`和`required_item`；
4. 第一遍视觉模型只能将可见性标为`clear`、`partial`或`occluded`；
5. 第二遍视觉模型输出`confirmed_absent`、`not_observed`或`occluded`；
6. 仅当检查区域清晰、锚点已定位、防护物未定位且第二遍确认缺失时，
   缺失关系通过，置信度上限为`0.90`；
7. `not_observed`最高为`0.60`并转人工复核，`occluded`最高为`0.35`并撤销自动确认。

---

## 12. 推荐开发顺序

1. 运行Mock演示，确认完整文件链生成；
2. 对齐本地SAM3，只使用Mock MLLM测试分割接口；
3. 对齐多模态API，先关闭CLIP；
4. 建立20—50张工地测试集，检查JSON稳定性和级联漏检；
5. 加入CLIP一致性校验；
6. 增加固定检查查询、难负样本和干扰候选；
7. 再扩展至视频抽帧、SAM3跟踪和时序复核。

---

## 13. 评测建议

即使不训练，也必须评测：

- 风险发现召回率；
- 正常图像误报率；
- SAM3实体定位IoU或人工命中率；
- 关系核验准确率；
- 第二次复核撤销错误候选的比例；
- MLLM描述事实正确率；
- 幻觉率与人工复核率；
- 单图总延迟和API调用成本。

数据划分应按工地、摄像头或来源隔离，避免相邻帧造成虚高结果。
