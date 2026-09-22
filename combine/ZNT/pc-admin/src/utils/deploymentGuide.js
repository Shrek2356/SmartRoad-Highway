export const DEPLOYMENT_MODES = [
  { id:'demo', title:'先看演示', description:'无需 GPU、模型、系统 Python 或 Node；仅用于道路软件流程联调。' },
  { id:'offline', title:'本地离线检测', description:'Qwen 在本机识图和报告，SAM3 定位。' },
  { id:'cloud', title:'云端视觉 + 本地定位', description:'视觉模型使用 API；SAM3 仍需本地 GPU 环境。' },
]

export function modelItems(manifest, mode, checks = {}) {
  if (mode === 'demo') return []
  return Object.entries(manifest?.models || {})
    .filter(([key, spec]) => spec.required_for?.includes(mode) || key === 'clip_checkpoint_path')
    .map(([key, spec]) => ({ key, ...spec, required: spec.required_for?.includes(mode), check: checks[key] }))
}

export function safeSource(value) {
  try { const url = new URL(value); return ['https:','http:'].includes(url.protocol) && !url.username && !url.password ? url.href : '' } catch { return '' }
}

export function reportSummary(report) {
  if (!report) return { type:'info', title:'尚未执行环境检查', detail:'选择目标模式后点击检查。进入本页不会启动任何模型。' }
  if (report.error) return { type:'error', title:'环境检查未完成', detail:report.error }
  return {
    type: report.ready ? 'success' : 'warning',
    title: report.ready ? '环境检查通过，仍需真实图片验收' : '还有部署条件需要处理',
    detail: report.scope || '检查不验证云端密钥、GGUF/mmproj 配对或实际推理效果。',
  }
}

// Quote displayed commands for PowerShell; never execute user paths in the UI.
export function psQuote(value) { return "'" + String(value).replaceAll("'", "''") + "'" }
export function installCommands(root, python) {
  const base = String(root || '').replace(/[\\/]+$/, '')
  const target = python && !/[\\/]python-runtime[\\/]/i.test(python) ? python : `${base}/env/Scripts/python.exe`
  return {
    create: `py -3.12 -m venv ${psQuote(`${base}/env`)}`,
    dependencies: `& ${psQuote(target)} -m pip install -r ${psQuote(`${base}/requirements/detect-full.txt`)}`,
    sam3: `& ${psQuote(target)} -m pip install -e ${psQuote(`${base}/third_party/sam3-main`)}`,
  }
}
