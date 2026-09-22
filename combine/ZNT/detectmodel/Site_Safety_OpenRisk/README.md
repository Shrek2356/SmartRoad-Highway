# 道路检测与复核后端

默认入口均使用 `configs/road_*.yaml`。标准产品工厂拒绝加载非道路配置；历史测试若需要工地兼容分支，必须在测试代码显式传 `allow_legacy=True`。

- `site_safety/pipeline/road_workflow.py`：观察与定位计划；
- `site_safety/prompting/road.py`：独立道路复核提示词；
- `site_safety/road_domain.py`：领域边界、风险优先级、岗位与内部响应目标；
- `site_safety/agents/road_knowledge.py`：法规导入、来源校验、有限范围检索与报告引用；
- `examples/road_knowledge/`：官方原始网页、相关原文与来源清单；
- `site_safety/agents/review_learning.py`：逐风险人工反馈与道路值班提示。

命令行使用已有检测 Python 执行 `run_inspection.py --help`、`build_events.py --help`。后者将检测目录转为业务事件并补入法规定向检索结果。默认知识库位于 `road_knowledge_base/`，不使用旧 `knowledge_base/`。

完整说明位于 `../../docs/道路领域全面迁移检查_20260921.md`。历史评估配置仅用于追溯，不是当前运行配置。
