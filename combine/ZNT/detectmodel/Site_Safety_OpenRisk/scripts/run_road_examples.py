"""Run real local Qwen/SAM3 on selected images and preserve every outcome."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from site_safety.utils.config import load_yaml
from site_safety.factory import build_inspector
from site_safety.qwen_service import QwenServiceManager
from site_safety.agents.event_builder import build_event_from_output_dir
from site_safety.agents.risk_reasoning import RiskReasoningAgent


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--run-name',default='baseline')
    p.add_argument('--ids',nargs='*')
    args=p.parse_args()
    run=args.workspace/args.run_name
    run.mkdir(exist_ok=True)
    if (run/'summary.json').exists():raise RuntimeError('Use a new run-name; existing outcomes must be retained')
    settings=dict(qwen_base_url='http://127.0.0.1:8091/v1/chat/completions',
        qwen_model_path='E:/model/Qwen3-VL-8B-Instruct-Q4_K_M.gguf',qwen_mmproj_path='E:/model/mmproj-BF16.gguf',
        llama_server_path='C:/Users/SYS03/AppData/Local/Microsoft/WinGet/Packages/ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe/llama-server.exe')
    cfg=load_yaml(ROOT/'configs/road_offline.yaml')
    cfg['sam3']['init_kwargs'].update(repo_path='E:/SAM3_MAIN/sam3-main',checkpoint='E:/SAM3_MAIN/SAM3/sam3.pt')
    cfg['mllm'].update(trust_env=False,max_retries=0,timeout_seconds=240)
    cfg['mllm']['payload_extra']={'max_tokens':4096,'seed':42}
    os.environ.update(LOCAL_QWEN_BASE_URL=settings['qwen_base_url'],LOCAL_QWEN_API_KEY='local-no-key',LOCAL_QWEN_MODEL='Qwen3-VL-8B-Instruct')
    summary=dict(purpose='real-model diagnostic examples, not benchmark evaluation',config=cfg,
        domain_sources={str(p.relative_to(ROOT)):p.read_text(encoding='utf-8') for p in
                        [ROOT/cfg['risk_operators']['path'],ROOT/cfg['risk_catalog']['path']]},
        python=sys.executable,code_root=str(ROOT),started_at=time.strftime('%Y-%m-%d %H:%M:%S'),
        model_files={k:{'path':v,'size':Path(v).stat().st_size} for k,v in settings.items() if k.endswith('_path')},
        code_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (ROOT/'site_safety').rglob('*.py')},items=[])
    def save():
        (run/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    manager=QwenServiceManager(run/'service')
    owned=False
    try:
        status=manager.start(settings)
        owned=bool(status.get('managed'))
        if not owned:raise RuntimeError('Dedicated model port is in use; refusing to reuse an unidentified model')
        for _ in range(180):
            if manager.status(settings).get('reachable'):break
            time.sleep(1)
        else:raise RuntimeError('Qwen readiness timeout')
        print('Qwen ready; loading SAM3',flush=True)
        inspector=build_inspector(cfg,ROOT)
        print('Real adapters built',flush=True)
        entries=json.loads((args.workspace/'manifest.json').read_text(encoding='utf-8'))['items']
        for entry in entries:
            sid=entry['sample_id']
            if args.ids and sid not in args.ids:continue
            item=dict(sample_id=sid,status='running');summary['items'].append(item);save()
            started=time.monotonic()
            try:
                result=inspector.inspect(args.workspace/entry['input'],run/sid)
                event=build_event_from_output_dir(run/sid,RiskReasoningAgent(ROOT/'examples/road_regulations.json'),config_name='road_offline.yaml')
                if event:
                    (run/sid/'detection_event.json').write_text(event.model_dump_json(indent=2),encoding='utf-8')
                visual=result.visual_verification or result.final_report
                item.update(status='ok',visual=visual.model_dump() if visual else None,
                            report=result.management_report.model_dump() if result.management_report else None)
            except Exception as exc:
                item.update(status='error',error=f'{type(exc).__name__}: {exc}')
                (run/f'{sid}_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            item['seconds']=round(time.monotonic()-started,2)
            save();print(json.dumps(item,ensure_ascii=False),flush=True)
        summary['completed_at']=time.strftime('%Y-%m-%d %H:%M:%S');save()
    except Exception as exc:
        summary['fatal_error']=f'{type(exc).__name__}: {exc}';save();raise
    finally:
        if owned:manager.stop(settings)

if __name__=='__main__':main()
