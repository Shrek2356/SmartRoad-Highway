"""Deterministic, evidence-linked road issue report; no invented site metadata."""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def write_road_issue_report(image_path, output_dir, first, report, config):
    output_dir = Path(output_dir)
    quality = report.assessment_quality
    version=quality.get('workflow_version','road-observe-plan-review-v4')
    original_name='input_image'+Path(image_path).suffix.lower()
    if Path(image_path).resolve() != (output_dir/original_name).resolve():
        shutil.copy2(image_path,output_dir/original_name)
    metadata = dict(workflow_version=version,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    image_path=str(image_path), image_sha256=hashlib.sha256(Path(image_path).read_bytes()).hexdigest(),
                    captured_at=None, road_location=None,
                    assessment_quality=quality,
                    findings=[r.model_dump() for r in report.final_risks],
                    source_artifacts=['first_prompt.txt','mllm_first_raw.txt','planning_prompt.txt',
                                      'planning_raw.txt','localization_plan.json','evidence.json','visual_verification.json'])
    metadata['source_artifacts'] = [p for p in metadata['source_artifacts'] if (output_dir/p).exists()]
    metadata['pipeline_config'] = config.get('pipeline', {})
    metadata['model'] = os.environ.get(config.get('mllm', {}).get('model_env', ''), 'not_recorded')
    metadata['code_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                              [Path(__file__),Path(__file__).with_name('road_workflow.py'),Path(__file__).with_name('road_evidence.py')]}
    metadata['artifact_sha256'] = {p:hashlib.sha256((output_dir/p).read_bytes()).hexdigest() for p in metadata['source_artifacts']}
    metadata['source_artifacts'] += [p.name for p in output_dir.glob('review_prompt_*.txt')]
    (output_dir/'issue_report.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 道路图像问题报告','',report.overall_summary,'',
           '拍摄时间、道路名称、方向和桩号：未提供。报告生成时间不代表现场拍摄时间。',
           f'输入文件：{image_path}',f'输入SHA256：{metadata["image_sha256"]}',
           '流程版本：'+version,'', '## 原始图像','',f'![原始图像]({original_name})','', '## 画面可判断范围','',
           '可见性：'+str(quality.get('visibility','未评估'))]
    lines += ['- '+x for x in quality.get('issues',[])]
    if (output_dir/'scene_annotation.png').exists():
        lines += ['', '## 场景标注','', '绿色道路框表示本图未见可见异常；蓝框是路牌、护栏等场景对象，不表示损坏。','',
                  '![场景标注](scene_annotation.png)']
    if not report.final_risks:
        lines += ['', '无保留风险候选；有画面限制时需补充图像，不能写成道路安全。']
    for risk in report.final_risks:
        lines += ['',f'## {risk.risk_name_zh} · {"自动证据支持，待业务复核" if risk.verified else "待核实"}','',
                  '以下为模型观察，尚非人工确认事实：']
        lines += ['- '+f for f in risk.visible_evidence]
        if risk.counter_evidence: lines += ['','反证与其他解释：']+['- '+f for f in risk.counter_evidence]
        if risk.uncertainties: lines += ['','复核原因与不确定事项：']+['- '+f for f in risk.uncertainties]
        lines += ['', '定位状态：'+str(risk.evidence_state.get('localization','未知')),
                  '道路影响：'+str(risk.evidence_state.get('road_impact','undetermined')),
                  '建议：核对原图与道路边界；必要时补充更清晰图像、邻近视频帧或现场复核记录。']
        for prefix in ['overlay_','risk_mask_','review_region_']:
            name=prefix+risk.risk_id+'.png'
            if (output_dir/name).exists():
                lines += ['',f'![{risk.risk_name_zh} 实际模型定位]({name})',''] if prefix=='overlay_' else [f'证据附件：[{name}]({name})']
        if not (output_dir/('overlay_'+risk.risk_id+'.png')).exists():
            lines += ['', '本项没有生成异常目标叠加图，原图观察保留待核实。']
    if quality.get('dismissed_observations'):
        lines += ['', '## 排除的候选（不作为异常告警）','']
        for item in quality['dismissed_observations']:
            lines += ['- '+str(item.get('risk_name_zh',item.get('risk_id')))+'：'+
                      ('；'.join(item.get('counter_evidence',[])) or item.get('reason','复核未支持'))]
    lines += ['', '## 原始分析记录','']+[f'- [{p}]({p})' for p in metadata['source_artifacts']]
    lines += ['', '本报告不判断水深、承载能力、车辆能否通行，也不自动给出封路或工程验收结论。']
    (output_dir/'issue_report.md').write_text('\n'.join(lines),encoding='utf-8')
