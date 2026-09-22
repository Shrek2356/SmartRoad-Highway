"""Run a frozen image sample using installed road code and existing local models."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
import traceback
from datetime import datetime, timezone


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--settings-source', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8091)
    parser.add_argument('--run-name', default='run')
    args = parser.parse_args()
    root = args.code_root.resolve()
    if Path(args.run_name).name != args.run_name or args.run_name in {'.','..'}:
        raise ValueError('run-name must be one directory name')
    run = args.workspace / args.run_name
    run.mkdir()  # Do not replace or merge earlier evidence.
    entries = json.loads((args.workspace/'manifest.json').read_text(encoding='utf-8'))['items']
    assert 1 <= len(entries) <= 32
    settings_source = json.loads(args.settings_source.read_text(encoding='utf-8-sig'))
    settings = {k:settings_source[k] for k in ('llama_server_path','qwen_model_path','qwen_mmproj_path')}
    settings['qwen_base_url'] = f'http://127.0.0.1:{args.port}/v1/chat/completions'
    with socket.socket() as probe:
        probe.settimeout(.5)
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            raise RuntimeError('Dedicated model port is occupied; no existing service will be changed')
    os.environ.update(LOCAL_QWEN_BASE_URL=settings['qwen_base_url'], LOCAL_QWEN_API_KEY='local-no-key',
                      LOCAL_QWEN_MODEL='Qwen3-VL-8B-Instruct', NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1')
    sys.path.insert(0, str(root))
    from site_safety.utils.config import load_yaml
    from site_safety.factory import build_inspector
    from site_safety.qwen_service import QwenServiceManager
    from site_safety.agents.event_builder import build_event_from_output_dir
    from site_safety.agents.risk_reasoning import RiskReasoningAgent
    from site_safety.agents import road_knowledge

    cfg = load_yaml(root/'configs/road_offline.yaml')
    cfg['sam3']['init_kwargs'].update(repo_path=settings_source['sam3_repo_path'], checkpoint=settings_source['sam3_checkpoint_path'])
    assert cfg['domain']=='road' and cfg['mllm']['backend']=='openai_compatible' and cfg['sam3']['backend']=='bridge'
    assert cfg['report_llm']['enabled'] is False and cfg['screening']['enabled'] is False
    # Public regulation seeds are isolated; no live application knowledge or business data is written.
    kb_runtime = run/'knowledge_runtime'
    road_knowledge.ensure_road_knowledge(kb_runtime/'road_knowledge_base', root/'examples/road_knowledge')
    road_knowledge.ROOT = kb_runtime
    summary = {'purpose':f'{len(entries)}-image development diagnostic sample; not a benchmark or accuracy claim',
               'status':'initializing','mock':False,'code_root':str(root),'python':sys.executable,
               'started_at':datetime.now(timezone.utc).isoformat(), 'config':cfg,
               'settings':settings, 'sample_manifest_sha256':digest(args.workspace/'manifest.json'),
               'code_sha256':{str(p.relative_to(root)):digest(p) for p in (root/'site_safety').rglob('*.py')},
               'model_files':{},'items':[]}
    def save():
        temporary = run/'summary.tmp'
        temporary.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(run/'summary.json')
    save()
    print('Checking fixed model files',flush=True)
    for label,path in {**{k:v for k,v in settings.items() if k.endswith('_path')},'sam3_checkpoint':settings_source['sam3_checkpoint_path']}.items():
        p=Path(path)
        summary['model_files'][label]={'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p)}
    save()
    manager = QwenServiceManager(run/'service')
    started=False
    try:
        status=manager.start(settings)
        started=bool(status.get('managed'))
        if not started: raise RuntimeError('Could not establish ownership of dedicated Qwen process')
        summary['qwen_pid']=status['pid'];save()
        for _ in range(180):
            if manager.status(settings).get('reachable'): break
            time.sleep(1)
        else: raise RuntimeError('Qwen loading timeout')
        print('Owned Qwen ready; loading real SAM3',flush=True)
        inspector=build_inspector(cfg,root)
        summary.update(status='running',adapters={'mllm':type(inspector.mllm).__name__,'sam3':type(inspector.sam3).__name__})
        save()
        for entry in entries:
            sid=entry['sample_id']; image=args.workspace/entry['input']
            assert digest(image)==entry['sha256'], 'Selected input bytes changed'
            item={'sample_id':sid,'status':'running','started_at':datetime.now(timezone.utc).isoformat()}
            summary['items'].append(item);save()
            start=time.monotonic()
            def progress(stage,status,message):
                item['stage']={'id':stage,'status':status,'message':message};save()
                print(json.dumps({'sample_id':sid,'stage':stage,'status':status},ensure_ascii=False),flush=True)
            try:
                output=run/sid
                result=inspector.inspect(image,output,progress_callback=progress)
                event=build_event_from_output_dir(output,RiskReasoningAgent(root/'examples/road_regulations.json'),
                    config_name='road_offline.yaml',mllm_model='Qwen3-VL-8B-Instruct')
                if event:
                    (output/'detection_event.json').write_text(event.model_dump_json(indent=2),encoding='utf-8')
                visual=result.visual_verification or result.final_report
                item.update(status='ok',visual=visual.model_dump() if visual else None,
                            report_generated=(output/'issue_report.md').is_file(),event_generated=event is not None,
                            artifacts={str(p.relative_to(output)):digest(p) for p in output.iterdir() if p.is_file()})
            except Exception as exc:
                item.update(status='error',error=f'{type(exc).__name__}: {exc}')
                (run/f'{sid}_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            item['seconds']=round(time.monotonic()-start,2);save()
            print(json.dumps({'sample_id':sid,'status':item['status'],'seconds':item['seconds'],'error':item.get('error')},ensure_ascii=False),flush=True)
        summary.update(status='completed',completed_at=datetime.now(timezone.utc).isoformat());save()
    except Exception as exc:
        summary.update(status='failed',fatal_error=f'{type(exc).__name__}: {exc}');save();raise
    finally:
        if started:
            manager.stop(settings)
            summary['owned_qwen_stopped']=not manager.status(settings).get('managed')
            save()


if __name__=='__main__':
    main()
