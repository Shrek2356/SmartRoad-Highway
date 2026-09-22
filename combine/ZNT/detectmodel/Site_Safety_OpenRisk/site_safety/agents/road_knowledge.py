"""Road RAG bootstrap and bounded citations. Retrieval never changes vision."""
import hashlib
import json
import threading
import os
from pathlib import Path

from site_safety.agents.knowledge_base import KnowledgeBase
from site_safety.road_domain import ROOT

_LOCK = threading.RLock()


def ensure_road_knowledge(kb_dir=None, bundle_dir=None):
    target = Path(kb_dir or ROOT / 'road_knowledge_base')
    bundle = Path(bundle_dir or ROOT / 'examples/road_knowledge')
    marker = target / '.road_seed_v1.json'
    with _LOCK:
        if marker.exists():
            return target  # Respect later deletion/replacement through the UI.
        sources = json.loads((bundle / 'sources.json').read_text(encoding='utf-8'))
        target.mkdir(parents=True, exist_ok=True)
        meta_path = target / 'sources.json'
        existing = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
        kb = KnowledgeBase(target)
        for filename, meta in sources.items():
            content = (bundle / filename).read_bytes()
            if hashlib.sha256(content).hexdigest() != meta['sha256']:
                raise ValueError('Bundled road regulation checksum mismatch: ' + filename)
            if not (target / filename).exists():
                kb.import_document(filename, content)
            if hashlib.sha256((target / filename).read_bytes()).hexdigest() == meta['sha256']:
                existing[filename] = meta
        temp = target / f'sources.{os.getpid()}.{threading.get_ident()}.tmp'
        temp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(meta_path)
        marker.write_text(json.dumps(list(sources), ensure_ascii=False), encoding='utf-8')
    return target


def attach_road_references(event, output_dir, kb=None):
    kb = kb or KnowledgeBase(ensure_road_knowledge())
    for risk in event.risks:
        scope = {(reg.source_file, reg.clause) for reg in risk.regulations if reg.source_file}
        query = ' '.join([risk.risk_name_zh, risk.risk_description, *risk.visible_evidence])
        hits = kb.search(query, top_k=3, min_score=0, allowed_sections=scope, verified_only=True) if scope else []
        for hit in hits:
            hit['retrieval_method'] = 'curated_risk_scope_then_tfidf'
            hit['usage'] = '待人工核查适用条件的处置参考；检索分数不是违法概率或风险置信度。'
        risk.knowledge_references = hits
        # Never retain a statutory-looking attachment if the source was deleted or changed.
        supported = {hit.get('regulation_id') for hit in hits}
        risk.regulations = [reg for reg in risk.regulations if reg.regulation_id in supported]
        risk.regulation_ids = [reg.regulation_id for reg in risk.regulations]
    write_reference_report(event, output_dir)


def write_reference_report(event, output_dir):
    output_dir = Path(output_dir)
    references = {r.risk_id:r.knowledge_references for r in event.risks}
    payload = {'scope': '处置参考，不构成违法认定，不改变视觉结论', 'references': references}
    ref_file = output_dir / 'regulatory_references.json'
    ref_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    report_json = output_dir / 'issue_report.json'
    if report_json.exists():
        data = json.loads(report_json.read_text(encoding='utf-8'))
        data['regulatory_references'] = payload
        data.setdefault('artifact_sha256', {})[ref_file.name] = hashlib.sha256(ref_file.read_bytes()).hexdigest()
        if ref_file.name not in data.setdefault('source_artifacts', []):
            data['source_artifacts'].append(ref_file.name)
        report_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    report_md = output_dir / 'issue_report.md'
    if report_md.exists():
        marker = '\n\n<!-- road-regulatory-references -->'
        text = report_md.read_text(encoding='utf-8').split(marker)[0]
        lines = ['## 法规处置参考', '', payload['scope'] + '。未匹配条款时不生成法律依据。']
        for risk in event.risks:
            lines += ['', '### ' + risk.risk_name_zh]
            if not risk.knowledge_references:
                lines += ['暂无经过来源校验且在该风险检索范围内的条款。']
            for hit in risk.knowledge_references:
                lines += ['', f"- [{hit.get('title', hit['source_file'])} {hit['section']}]({hit.get('source_url', '')})；{hit.get('version', '')}",
                          '  适用条件：' + hit.get('applicability', '需人工核查'),
                          '  原文：' + hit['text'].replace('\n', ' ')]
        report_md.write_text(text + marker + '\n' + '\n'.join(lines) + '\n', encoding='utf-8')
