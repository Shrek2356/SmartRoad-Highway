# 风险算子注册表

## 1. 目的

`configs/risk_operators.yaml`是异常检测链路的领域规则层。它把MLLM生成的
`RiskSpec`编译成三类可执行约束：

1. SAM3应该分割哪些正向实体；
2. 实体之间采用哪种空间或缺失关系核验；
3. 关系成立后用哪种策略构造最终风险Mask。

因此，MLLM负责开放语义发现与结构化描述，风险算子负责把描述变成稳定、可审计的视觉程序。
已知风险不再以Python条件分支写进`orchestrator.py`。

## 2. 执行位置

```text
MLLM RiskSpec
    ↓
RiskOperatorRegistry（加载并校验YAML）
    ├─ 补齐标准正向实体任务
    ├─ 绑定关系算子
    ├─ 绑定Mask策略
    └─ 应用可配置的召回保护规则
    ↓
SAM3分割 → RelationVerifier → RiskMaskBuilder → 证据门控
```

核心实现：

- `site_safety/risk_operators.py`：配置模型、启动校验、规则匹配与任务编译；
- `configs/risk_operators.yaml`：11类核心风险、开放发现映射、锚点重试规则；
- `site_safety/pipeline/orchestrator.py`：只调用注册表，不保存具体风险模板。

## 3. 算子字段

| 字段 | 作用 |
|---|---|
| `tasks` | SAM3正向实体提示、角色和预期数量 |
| `relation.type` | `near`、`overlap`、`missing_association`等关系核验 |
| `relation.task_scope` | 关系使用全部任务，或只使用注册表生成的标准任务 |
| `mask_strategy` | 风险Mask的合成方式 |
| `force_canonical_tasks` | MLLM已给任务时是否仍补充稳定的标准任务 |
| `promotion` | 关键可见线索出现时，把候选交给视觉与几何模块继续核验 |

所有角色、关系类型、Mask策略和数值范围均由Pydantic在系统启动时校验。错误配置会立即失败，
不会静默进入检测链路。

## 4. 新增风险示例

新增“工人吸烟”不需要修改Python，只需在`operators`下增加：

```yaml
smoking_worker:
  name_zh: 工人吸烟
  tasks:
    - {role: subject, prompt: construction worker, expected_count: 2}
    - {role: hazard_source, prompt: lit cigarette or visible smoking}
  relation:
    type: near
    task_scope: canonical
  mask_strategy: entity_union
  force_canonical_tasks: true
```

之后再把该风险加入候选目录，或由开放发现阶段生成相同`risk_id`。若风险需要新的关系逻辑，
才需要在`RelationVerifier`中新增通用关系算子；若只是新类别、提示词、数量和现有关系组合，
只修改YAML。

## 5. 技术价值

- **模型可替换**：Qwen、GLM或更强VLM只需输出同一RiskSpec，下游程序保持不变；
- **领域可扩展**：风险类别增长不再导致编排器条件分支持续膨胀；
- **结果可解释**：每个结论都能追溯到实体任务、关系算子和Mask策略；
- **便于消融**：可分别关闭标准任务、关系或召回保护，量化每个程序模块的贡献；
- **可治理**：规则变更集中在版本化配置中，适合安全人员审核。
