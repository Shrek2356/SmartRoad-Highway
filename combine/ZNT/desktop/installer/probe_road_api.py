"""Probe only an isolated installed demo instance; no model calls or notifications."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--app-root', type=Path, required=True)
    parser.add_argument('--record', type=Path, required=True)
    args = parser.parse_args()
    if args.record.exists():
        raise ValueError('Use a new evidence file')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    checks = []
    record = {'mode':'installed-demo-api', 'real_models_executed':False, 'checks':checks}

    def check(name, passed):
        checks.append({'name':name, 'passed':bool(passed)})
        if not passed:
            raise AssertionError(name)

    def request(route, *, data=None, headers=None, method=None, json_body=None):
        headers = dict(headers or {})
        if json_body is not None:
            data = json.dumps(json_body).encode()
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(args.base_url+route, data=data, headers=headers, method=method)
        try:
            with opener.open(req, timeout=15) as response:
                raw = response.read()
                return response.status, json.loads(raw) if 'application/json' in response.headers.get('Content-Type','') else raw
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, json.loads(raw)

    def upload(profile, raw):
        boundary = 'SmartRoadPackageVerification'
        data = b''
        for key,value in {'profile':profile,'device_id':'PACKAGE-QA','site_id':'ROAD-LAB','data_mode':'offline'}.items():
            data += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        data += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="qa.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+raw+f'\r\n--{boundary}--\r\n'.encode()
        return request('/detect-api/api/detect/upload', data=data, headers={'Content-Type':'multipart/form-data; boundary='+boundary})

    try:
        code, login = request('/business-api/api/auth/login', json_body={'username':'admin','password':'admin123'})
        check('实验室账号实际登录', code == 200 and bool(login.get('token')))
        auth = {'Authorization':'Bearer '+login['token']}
        _, config = request('/business-api/api/model/config', headers=auth)
        keys = [item['key'] for item in config['thresholds']]
        check('活动风险规则为道路领域', 'pothole' in keys and not set(keys) & {'missing_helmet','missing_safety_harness','unsafe_lifting'})
        record['road_risk_keys'] = keys
        code, _ = request('/business-api/api/model/threshold', method='PUT', headers=auth, json_body={'key':'missing_helmet','value':.8})
        check('拒绝旧工地风险阈值写入', code == 422)
        _, kb = request('/detect-api/api/detect/knowledge')
        check('首次安装仅有十条法规种子', kb['chunk_count'] == 10)
        _, found = request('/detect-api/api/detect/knowledge/search?'+urllib.parse.urlencode({'q':'道路出现坍塌、坑漕、水毁、隆起等损毁','top_k':1}))
        hit = found['hits'][0]
        check('法规检索命中第三十条且来源校验通过', hit['section']=='第三十条' and hit['provenance_status']=='verified_checksum')
        record['law_hit'] = hit
        _, before = request('/business-api/api/events', headers=auth)
        raw = io.BytesIO(); Image.new('RGB',(96,64),'gray').save(raw,format='PNG'); image = raw.getvalue()
        code, queued = upload('demo', image)
        check('明确演示档位可提交图片', code == 200 and bool(queued.get('job_id')))
        job_id = queued['job_id']; record['job_id'] = job_id
        for _ in range(100):
            _, job = request('/detect-api/api/detect/jobs/'+job_id)
            if job['status'] in {'done','error','cancelled'}:
                break
            time.sleep(.2)
        check('演示检测流程完整结束', job['status']=='done')
        check('演示结论明确标注模拟', '模拟' in json.dumps(job['result'], ensure_ascii=False))
        check('演示任务不写入真实事件', job['business_sync'].get('skipped') is True)
        code, summary = request(f'/detect-api/api/detect/jobs/{job_id}/media/summary.md')
        check('自动生成的演示报告可以下载', code == 200 and '模拟' in summary.decode('utf-8'))
        args.record.with_suffix('.summary.md').write_bytes(summary)
        report_path = args.app_root/'detectmodel/Site_Safety_OpenRisk/outputs/road_bridge_jobs'/job_id/'summary.md'
        check('下载报告与安装目录原文件一致', report_path.read_bytes() == summary)
        record['summary_sha256'] = hashlib.sha256(summary).hexdigest()
        code, returned_image = request(f'/detect-api/api/detect/jobs/{job_id}/media/{job["image_name"]}')
        check('图像证据下载字节一致', code == 200 and returned_image == image)
        code, failed = upload('offline', image)
        check('缺少真实模型明确拒绝而非演示降级', code in {409,503} and not failed.get('job_id'))
        record['offline_failure'] = {'status':code, 'response':failed}
        code, _ = upload('demo', b'not an image')
        check('拒绝伪图片', code in {400,422})
        _, after = request('/business-api/api/events', headers=auth)
        check('演示和失败请求均未制造业务事件', before == after)
        record['ok'] = True
    except Exception as exc:
        record.update(ok=False, error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'ok':record.get('ok'), 'checks':len(checks), 'record':str(args.record)},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
