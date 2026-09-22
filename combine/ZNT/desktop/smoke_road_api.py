"""One real-model upload through the desktop gateway; no native window required."""
import argparse
import json
from pathlib import Path
import time
import urllib.request
from desktop_app import DesktopRuntime,load_config

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--record',type=Path,required=True)
    args=parser.parse_args()
    runtime=DesktopRuntime(load_config())
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    record={'input':str(args.image),'mode':'offline','mock':False}
    def request(route,data=None,headers=None):
        req=urllib.request.Request('http://127.0.0.1:5273'+route,data=data,headers=headers or {})
        with opener.open(req,timeout=30) as response:return json.load(response)
    try:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        if args.record.exists(): raise RuntimeError('Use a new record path; prior test evidence must be retained')
        runtime.start_services()
        request('/detect-api/api/detect/qwen-service/start',b'')
        for _ in range(90):
            if request('/detect-api/api/detect/qwen-service').get('reachable'):break
            time.sleep(2)
        else:raise RuntimeError('Qwen readiness timeout')
        boundary='RoadExampleBoundary'
        body=b''
        for key,value in {'profile':'offline','device_id':f'ROAD-{args.image.stem}-EXAMPLE','site_id':'ROAD-LAB','data_mode':'offline'}.items():
            body+=f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        body+=f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{args.image.name}"\r\nContent-Type: image/png\r\n\r\n'.encode()+args.image.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
        queued=request('/detect-api/api/detect/upload',body,{'Content-Type':'multipart/form-data; boundary='+boundary})
        record['job_id']=queued['job_id']; print('submitted',queued,flush=True)
        for _ in range(300):
            job=request('/detect-api/api/detect/jobs/'+queued['job_id'])
            if job['status'] in ['done','error','cancelled']:break
            time.sleep(2)
        else:raise RuntimeError('Job timeout')
        record.update(status=job['status'],error=job.get('error'),business_sync=job.get('business_sync'),result=job.get('result'),stages=job.get('stages'))
        if job['status']!='done':raise RuntimeError('Real-model job did not complete')
        login=request('/business-api/api/auth/login',json.dumps({'username':'admin','password':'admin123'}).encode(),{'Content-Type':'application/json'})
        auth_headers={'Authorization':'Bearer '+login['token']}
        knowledge=request('/business-api/api/knowledge',headers=auth_headers)
        assert knowledge['chunk_count'] >= 10
        record['knowledge_summary']=knowledge
        config=request('/business-api/api/model/config',headers=auth_headers)
        assert all(r['key'] != 'missing_helmet' for r in config['thresholds'])
        record['road_operator_count']=len(config['thresholds'])
        events=request('/business-api/api/events',headers=auth_headers)
        matching=[e for e in events if e.get('pipeline',{}).get('job_id')==queued['job_id']]
        record['persisted_event_count']=len(matching)
        assert len(matching)==1,'Detection must reach the business database exactly once'
        if job['result'].get('assessment_quality'):
            assert matching[0].get('assessment_quality') == job['result']['assessment_quality']
            report_url=job['result'].get('issue_report')
            assert report_url, 'Road report link must be exposed'
            with opener.open('http://127.0.0.1:5273/detect-api'+report_url,timeout=30) as response:
                report_text=response.read().decode('utf-8')
            assert '道路图像问题报告' in report_text
            record['report_download_ok']=True
            record['quality_persisted']=True
        record['risk_references']={r['risk_id']:r.get('knowledge_references',[]) for r in matching[0]['risks']}
        record['event_id']=matching[0]['event_id'];record['ok']=True
    except Exception as exc:
        record.update(ok=False,error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        args.record.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        try:request('/detect-api/api/detect/qwen-service/stop',b'')
        except Exception:pass
        runtime.stop()
    print(json.dumps({k:v for k,v in record.items() if k not in ['result','stages']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
