import json
import uuid
from pathlib import Path

import pytest

from site_safety.agents import (
    CollaborativeResponseAgent,
    ReviewLearningAgent,
    RiskReasoningAgent,
)
from site_safety.agents.schemas import (
    DetectionEvent,
    DeviceInfo,
    GeometryInfo,
    MediaInfo,
    RiskFinding,
    TimeInfo,
)

ROOT = Path(__file__).resolve().parents[1]


def _reasoning() -> RiskReasoningAgent:
    return RiskReasoningAgent(ROOT / "examples" / "regulations.json")


def _finding(risk_id: str, *, verified: bool, confidence: float, review: bool = False) -> RiskFinding:
    return RiskFinding(
        risk_id=risk_id,
        risk_name_zh=risk_id,
        verified=verified,
        confidence=confidence,
        risk_level="info",
        risk_level_zh="提示信息",
        geometry=GeometryInfo(),
        manual_review_required=review,
    )


def _event(findings) -> DetectionEvent:
    return DetectionEvent(
        event_id="EVT-TEST-" + uuid.uuid4().hex,
        data_mode="offline",
        device=DeviceInfo(),
        time=TimeInfo(detected_at="2026-07-26T12:00:00+08:00", reported_at="2026-07-26T12:00:01+08:00"),
        media=MediaInfo(image_path="test.jpg", image_width=100, image_height=100),
        overall_has_anomaly=any(f.verified for f in findings),
        risks=findings,
    )


def test_risk_level_rules() -> None:
    reasoning = _reasoning()
    critical = reasoning.attach(_finding("worker_under_suspended_load", verified=True, confidence=0.9))
    assert critical.risk_level == "critical"
    downgraded = reasoning.attach(_finding("worker_under_suspended_load", verified=True, confidence=0.5))
    assert downgraded.risk_level == "major"
    pending = reasoning.attach(_finding("missing_helmet", verified=False, confidence=0.6, review=True))
    assert pending.risk_level == "pending_review"
    info = reasoning.attach(_finding("missing_helmet", verified=False, confidence=0.1))
    assert info.risk_level == "info"


def test_regulation_mapping_attached() -> None:
    finding = _reasoning().attach(_finding("missing_helmet", verified=True, confidence=0.9))
    assert "JGJ59-2011-HELMET" in finding.regulation_ids
    assert finding.regulations[0].name_zh.startswith("建筑施工安全检查标准")


def test_work_order_created_only_for_verified() -> None:
    reasoning = _reasoning()
    findings = [
        reasoning.attach(_finding("missing_helmet", verified=True, confidence=0.9)),
        reasoning.attach(_finding("missing_edge_protection", verified=False, confidence=0.5, review=True)),
    ]
    event = _event(findings)
    agent = CollaborativeResponseAgent(domain="legacy")
    orders, confirmations = agent.process_event(event)
    assert len(orders) == 1
    assert orders[0].risk_id == "missing_helmet"
    assert findings[0].work_order_id == orders[0].work_order_id
    assert len(confirmations) == 1
    assert confirmations[0].risk_id == "missing_edge_protection"
    assert confirmations[0].model_verified is False
    assert confirmations[0].model_confidence == 0.5
    assert confirmations[0].absence_status == "not_applicable"
    assert len(agent.notifications) == 1


def test_work_order_state_machine_rejects_illegal_transition() -> None:
    reasoning = _reasoning()
    event = _event([reasoning.attach(_finding("missing_helmet", verified=True, confidence=0.9))])
    agent = CollaborativeResponseAgent(domain="legacy")
    orders, _ = agent.process_event(event)
    order = orders[0]
    agent.transition(order, "confirmed", by="safety_officer")
    agent.transition(order, "assigned", by="safety_officer", assignee="foreman_wang")
    assert order.assignee == "foreman_wang"
    with pytest.raises(ValueError):
        agent.transition(order, "closed", by="safety_officer")
    assert len(order.history) == 3


def test_review_learning_case_library_and_stats(tmp_path: Path) -> None:
    reasoning = _reasoning()
    learning = ReviewLearningAgent(tmp_path / "case_library.jsonl", domain="legacy")
    for verdict in ["confirmed", "rejected", "rejected"]:
        event = _event([reasoning.attach(_finding("missing_helmet", verified=True, confidence=0.9))])
        learning.ingest_confirmation(event, "missing_helmet", verdict, reviewer="tester")
        assert event.review.status == verdict
    stats = learning.false_alarm_stats()
    assert stats["missing_helmet"]["model_verified_count"] == 3
    assert stats["missing_helmet"]["human_rejected_count"] == 2
    briefing = learning.generate_briefing([])
    assert "班前安全交底" in briefing


def test_event_json_roundtrip() -> None:
    reasoning = _reasoning()
    event = _event([reasoning.attach(_finding("smoke_or_fire", verified=True, confidence=0.95))])
    payload = json.loads(json.dumps(event.model_dump(), ensure_ascii=False))
    restored = DetectionEvent.model_validate(payload)
    assert restored.risks[0].risk_level == "critical"
    assert restored.schema_version == "1.0"


def test_disposal_recommendations_attached_and_copied_to_order() -> None:
    reasoning = _reasoning()
    finding = reasoning.attach(_finding("missing_fall_protection", verified=True, confidence=0.9))
    assert finding.disposal_recommendations
    assert any("安全带" in x for x in finding.disposal_recommendations)
    event = _event([finding])
    orders, _ = CollaborativeResponseAgent(domain="legacy").process_event(event)
    assert orders[0].disposal_recommendations == finding.disposal_recommendations


def test_disposal_falls_back_to_default_for_unknown_risk() -> None:
    reasoning = _reasoning()
    finding = reasoning.attach(_finding("open_discovery_1", verified=True, confidence=0.9))
    assert finding.disposal_recommendations  # _default兜底


def test_regulation_search() -> None:
    reasoning = _reasoning()
    hits = reasoning.search_regulations("洞口")
    assert hits and all("洞口" in (h.requirement_zh + h.clause) for h in hits)
    assert len(reasoning.search_regulations("")) == len(reasoning.regulations)
    assert reasoning.search_regulations("不存在的关键词xyz") == []


def test_notify_gateway_file_channel(tmp_path: Path) -> None:
    from site_safety.agents.notify_gateway import NotificationGateway

    gateway = NotificationGateway(outbox_path=tmp_path / "outbox.jsonl")
    assert gateway.channels == ["file"]  # 未配置webhook时不发外部请求
    record = gateway.dispatch({"notification_id": "NT-x", "title": "测试", "body": "b"})
    assert record["delivery"]["channels"] == ["file"]
    lines = (tmp_path / "outbox.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["notification_id"] == "NT-x"


def test_response_agent_dispatches_via_gateway(tmp_path: Path) -> None:
    from site_safety.agents.notify_gateway import NotificationGateway

    reasoning = _reasoning()
    gateway = NotificationGateway(outbox_path=tmp_path / "outbox.jsonl")
    agent = CollaborativeResponseAgent(gateway=gateway, domain="legacy")
    event = _event([reasoning.attach(_finding("missing_helmet", verified=True, confidence=0.9))])
    agent.process_event(event)
    assert agent.notifications[0]["delivery"]["channels"] == ["file"]
    assert "首要处置" in agent.notifications[0]["body"]
    assert (tmp_path / "outbox.jsonl").is_file()


def test_threshold_proposals_from_rejected_cases(tmp_path: Path) -> None:
    reasoning = _reasoning()
    learning = ReviewLearningAgent(tmp_path / "case_library.jsonl", domain="legacy")
    confs = [(0.90, "rejected"), (0.85, "rejected"), (0.92, "confirmed"), (0.88, "confirmed"), (0.95, "rejected")]
    for conf, verdict in confs:
        event = _event([reasoning.attach(_finding("missing_helmet", verified=True, confidence=conf))])
        learning.ingest_confirmation(event, "missing_helmet", verdict, reviewer="t")
    proposals = learning.build_threshold_proposals()
    assert len(proposals) == 1
    p = proposals[0]
    assert p.risk_id == "missing_helmet"
    assert p.status == "pending"
    # 最高被驳回置信度0.95 + 0.05，封顶0.95
    assert p.proposed_min_verified_confidence == 0.95
    # 排除集生效
    assert learning.build_threshold_proposals(exclude_risk_ids={"missing_helmet"}) == []


def test_regulation_semantic_retrieval() -> None:
    reasoning = _reasoning()
    # "高空坠落防护"无精确词面（库内用"高处/坠落"），语义检索应命中安全带/临边条款
    results = reasoning.hybrid_search("高空坠落防护", top_k=5)
    assert results, "语义检索应返回结果"
    ids = [r["regulation"]["regulation_id"] for r in results]
    assert any("HARNESS" in i or "EDGE" in i or "80-2016" in i for i in ids)
    # 精确命中优先且score=1.0
    exact = reasoning.hybrid_search("洞口")
    assert exact[0]["match"] == "exact" and exact[0]["score"] == 1.0
    # 检索器后端已初始化（无语义模型时回退TF-IDF）
    assert reasoning.retriever.backend in {"sentence_transformers", "tfidf_char_ngram"}


def test_knowledge_base_ingest_and_search(tmp_path: Path) -> None:
    from site_safety.agents.knowledge_base import KnowledgeBase

    doc = tmp_path / "规程.md"
    doc.write_text(
        "# 吊装作业规程\n\n## 第一条 警戒\n\n吊装作业前必须设置警戒区，吊物下方严禁站人。\n\n"
        "## 第二条 指挥\n\n必须由持证信号工统一指挥，视线不清时停止作业。\n",
        encoding="utf-8",
    )
    kb = KnowledgeBase(tmp_path)
    summary = kb.summary()
    assert summary["file_count"] == 1 and summary["chunk_count"] >= 2
    hits = kb.search("吊物下面能不能站人")
    assert hits and hits[0]["source_file"] == "规程.md"
    assert "严禁站人" in hits[0]["text"]
    # 新增文件自动重建索引
    (tmp_path / "补充.txt").write_text("第一条 夜间施工必须保证照明充足。", encoding="utf-8")
    assert kb.summary()["file_count"] == 2
    assert kb.search("夜间照明")


def test_user_database_management(tmp_path: Path) -> None:
    from app_server import Database

    db = Database(tmp_path / "t.db")
    db.seed_users()
    assert db.verify_user("admin", "admin123") == "admin"
    assert db.verify_user("admin", "wrong") is None
    db.create_user("foreman", "secret66", "safety_officer")
    assert db.verify_user("foreman", "secret66") == "safety_officer"
    with pytest.raises(ValueError):
        db.create_user("foreman", "secret66", "safety_officer")  # 重名
    with pytest.raises(ValueError):
        db.create_user("x", "123", "viewer")  # 密码太短
    db.set_password("foreman", "newpass8")
    assert db.verify_user("foreman", "secret66") is None
    assert db.verify_user("foreman", "newpass8") == "safety_officer"
    db.set_role("foreman", "admin")
    assert db.verify_user("foreman", "newpass8") == "admin"
    with pytest.raises(KeyError):
        db.set_password("ghost", "whatever8")
