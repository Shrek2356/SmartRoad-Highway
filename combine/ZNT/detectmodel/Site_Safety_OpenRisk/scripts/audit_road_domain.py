"""Reproducible source inventory plus active road-domain configuration checks."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]
sys.path.insert(0, str(ROOT))

from site_safety.road_domain import validate_road_config
from site_safety.utils.config import load_yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    names = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'], cwd=REPO).decode('utf-8').split('\0')
    rows = []
    pattern = re.compile(r'工地|施工安全|安全帽|吊装|塔吊|班组|JGJ|construction|SiteSafe|筑安', re.I)
    extensions = {'.py','.js','.mjs','.vue','.yaml','.yml','.json','.md','.txt','.bat','.cmd','.ps1','.iss','.html'}
    for name in sorted(set(names)):
        path = REPO / name
        if not name or not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if any(part in {'node_modules','python-runtime','node-runtime','.venv','build','dist','desktop-dist','outputs','road_app_data'} or part.startswith('build-') for part in path.parts):
            continue
        content = path.read_bytes()
        text = content.decode('utf-8-sig', errors='replace')
        lines = [i for i,line in enumerate(text.splitlines(),1) if pattern.search(line)]
        rows.append({'file':name,'sha256':hashlib.sha256(content).hexdigest(),'legacy_term_lines':lines})
    checks = []
    for name in ['road_demo','road_offline','road_standard']:
        config = load_yaml(ROOT/f'configs/{name}.yaml')
        assert config['domain'] == 'road'
        validate_road_config(config, ROOT)
        checks.append({'config':name,'domain':'road','guard_passed':True,'screening_enabled':config['screening']['enabled']})
    result = {'generated_at':datetime.now(timezone.utc).isoformat(), 'repository':str(REPO),
              'scope':'Git-tracked and non-ignored source/config/document files; excludes dependencies, binary assets, build products and runtime data.',
              'interpretation':'Legacy token hits are an inventory, not proof of an active construction behavior. Historical documents and explicitly gated compatibility code remain.',
              'file_count':len(rows),'files_with_legacy_terms':sum(bool(r['legacy_term_lines']) for r in rows),
              'project_instruction_files':[r['file'] for r in rows if Path(r['file']).name in {'AGENTS.md','SKILL.md'}],
              'active_config_checks':checks,'files':rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'files'},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
