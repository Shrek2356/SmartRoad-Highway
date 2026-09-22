"""风险推理Agent：风险等级评定 + 道路处置参考映射。

规则完全确定性，便于向评委和安全员解释：
1. 每个risk_id有基础严重度（critical/major/general）；
2. verified且置信度>=downgrade_threshold → 维持基础等级；
   verified但置信度不足 → 降一级（最低general）；
3. 未verified但需人工复核 → pending_review（进入待复核队列，不直接告警）；
4. 未verified且无需复核 → info（仅存档，不告警、不派单）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from site_safety.agents.schemas import RISK_LEVEL_ZH, RegulationRef, RiskFinding

# 基础严重度；open_*开放发现默认general
BASE_SEVERITY: Dict[str, str] = {
    "worker_under_suspended_load": "critical",
    "missing_fall_protection": "critical",
    "smoke_or_fire": "critical",
    "fallen_worker": "critical",
    "collapsed_scaffold": "critical",
    "missing_edge_protection": "major",
    "missing_helmet": "major",
    "machinery_proximity": "major",
    "blocked_passage": "general",
    "manual_report_critical": "critical",
    "manual_report_major": "major",
    "manual_report_general": "general",
}

_DOWNGRADE = {"critical": "major", "major": "general", "general": "general"}


class RiskReasoningAgent:
    def __init__(
        self,
        regulations_path: str | Path,
        *,
        downgrade_threshold: float = 0.70,
    ) -> None:
        payload = json.loads(Path(regulations_path).read_text(encoding="utf-8"))
        self.domain = payload.get("domain", "legacy")
        self.regulations: Dict[str, RegulationRef] = {
            item["regulation_id"]: RegulationRef.model_validate(item)
            for item in payload.get("regulations", [])
        }
        self.risk_regulation_map: Dict[str, List[str]] = payload.get("risk_regulation_map", {})
        self.disposal_actions: Dict[str, List[str]] = payload.get("disposal_actions", {})
        self.downgrade_threshold = downgrade_threshold

    def base_severity(self, risk_id: str) -> str:
        if self.domain == "road":
            from site_safety.road_domain import ROAD_PRIORITIES
            return ROAD_PRIORITIES.get(risk_id, "general")
        if risk_id in BASE_SEVERITY:
            return BASE_SEVERITY[risk_id]
        return "general"

    def assess_level(
        self,
        *,
        risk_id: str,
        verified: bool,
        confidence: float,
        manual_review_required: bool,
    ) -> str:
        if manual_review_required:
            return "pending_review"
        if verified:
            level = self.base_severity(risk_id)
            if confidence < self.downgrade_threshold:
                level = _DOWNGRADE[level]
            return level
        if manual_review_required:
            return "pending_review"
        return "info"

    def attach(self, finding: RiskFinding) -> RiskFinding:
        """回填risk_level与规范引用。"""
        level = self.assess_level(
            risk_id=finding.risk_id,
            verified=finding.verified,
            confidence=finding.confidence,
            manual_review_required=finding.manual_review_required,
        )
        if self.domain == "road" or finding.risk_id in {"pothole", "crack", "subsidence", "road_collapse", "water_accumulation", "rockfall_on_road", "slope_debris", "road_debris", "road_obstruction", "sediment_cover", "road_condition_anomaly"} or finding.risk_id.startswith("open_"):
            if finding.verified or finding.manual_review_required:
                level = "pending_review"
                finding.manual_review_required = True
        finding.risk_level = level
        finding.risk_level_zh = RISK_LEVEL_ZH[level]
        regulation_ids = self.risk_regulation_map.get(finding.risk_id, [])
        finding.regulation_ids = list(regulation_ids)
        finding.regulations = [
            self.regulations[reg_id] for reg_id in regulation_ids if reg_id in self.regulations
        ]
        if self.domain == "road":
            from site_safety.agents.road_knowledge import ensure_road_knowledge
            from site_safety.agents.knowledge_base import KnowledgeBase
            kb = KnowledgeBase(ensure_road_knowledge())
            finding.regulations = [reg for reg in finding.regulations
                                   if kb.sources.get(reg.source_file, {}).get("provenance_status") == "verified_checksum"
                                   and kb.sources[reg.source_file].get("sha256") == reg.source_sha256]
            finding.regulation_ids = [reg.regulation_id for reg in finding.regulations]
        finding.disposal_recommendations = self.disposal_for(finding.risk_id)
        return finding

    def disposal_for(self, risk_id: str) -> List[str]:
        """按risk_id取现场处置建议；无专项条目时用通用兜底。"""
        return list(self.disposal_actions.get(risk_id, self.disposal_actions.get("_default", [])))

    def search_regulations(self, query: str) -> List[RegulationRef]:
        """关键词检索规范条款（名称/条款号/要求全文匹配），供系统配置页使用。"""
        keyword = query.strip().lower()
        if not keyword:
            return list(self.regulations.values())
        return [
            reg
            for reg in self.regulations.values()
            if keyword in reg.name_zh.lower()
            or keyword in reg.clause.lower()
            or keyword in reg.requirement_zh.lower()
            or keyword in reg.regulation_id.lower()
        ]

    @property
    def retriever(self):
        """语义检索器（懒加载；优先本地语义向量模型，无则TF-IDF字符n-gram）。"""
        if getattr(self, "_retriever", None) is None:
            from site_safety.agents.regulation_retriever import RegulationRetriever

            self._retriever = RegulationRetriever(self.regulations, backend="tfidf" if self.domain == "road" else "auto")
        return self._retriever

    def hybrid_search(self, query: str, *, top_k: int = 8) -> List[dict]:
        """混合检索：精确关键词命中优先（score=1.0），语义检索补足其余名额。"""
        exact = self.search_regulations(query) if query.strip() else []
        results = [
            {"regulation": reg.model_dump(), "score": 1.0, "match": "exact"} for reg in exact
        ]
        seen = {reg.regulation_id for reg in exact}
        if query.strip():
            for reg, score in self.retriever.search(query, top_k=top_k):
                if reg.regulation_id not in seen and len(results) < top_k:
                    results.append(
                        {"regulation": reg.model_dump(), "score": score, "match": "semantic"}
                    )
        return results
