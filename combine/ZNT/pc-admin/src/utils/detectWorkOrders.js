/**
 * 实时检测结果 → 工单处置（本地汇总）
 * 检测桥接与工单 Mock 原本不通，用本模块把已确认风险写入本地工单池。
 */
import { notifyModules } from './moduleBus'

const STORAGE_KEY = 'znt_detect_workorders'

function nowText() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function mapLevel(risk = {}) {
  const raw = String(risk.level || risk.level_zh || '').toLowerCase()
  if (raw.includes('red') || raw.includes('高') || raw.includes('重大') || raw.includes('critical')) return 'red'
  if (raw.includes('yellow') || raw.includes('低') || raw.includes('一般') || raw.includes('minor')) return 'yellow'
  if (raw.includes('orange') || raw.includes('中') || raw.includes('较大') || raw.includes('major')) return 'orange'
  const conf = Number(risk.confidence || 0)
  if (conf >= 0.85) return 'red'
  if (conf >= 0.6) return 'orange'
  return 'yellow'
}

function pickImages(result = {}, risk = {}, index = 0) {
  const snapUrl = result.input_image || ''
  const overlayUrl =
    risk.overlay ||
    (result.overlays || [])[index] ||
    (result.overlays || [])[0] ||
    ''
  const maskUrl =
    risk.mask ||
    (result.masks || [])[index] ||
    (result.masks || [])[0] ||
    overlayUrl ||
    ''
  return { snapUrl, maskUrl, overlayUrl }
}

export function loadDetectWorkOrders() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

function saveDetectWorkOrders(list) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  notifyModules({ type: 'workorders' })
}

/**
 * 将一次检测任务的风险写入工单池（幂等：同一 job + risk 不重复；会回填缺失图片）
 * @returns {{ created: number, updated: number, orders: Array }}
 */
export function syncDetectJobToWorkOrders(job) {
  if (!job || job.status !== 'done') return { created: 0, updated: 0, orders: [] }
  const result = job.result || {}
  const risks = (result.risks || []).filter((r) => r && (r.verified !== false || r.manual_review))
  if (!risks.length && (result.input_image || result.overlays?.length)) {
    // 无结构化风险时，仍保留一张总览工单，方便查看抓拍/标注
    risks.push({
      name: '检测结果待复核',
      verified: true,
      manual_review: true,
      confidence: 0.5,
      level: 'orange',
      description: result.report_summary || '检测已完成，请人工复核',
    })
  }
  if (!risks.length) return { created: 0, updated: 0, orders: [] }

  const existing = loadDetectWorkOrders()
  const touched = []
  let created = 0
  let updated = 0
  const stamp = nowText()
  const presentationAsset = Boolean(job.mock || job.profile === 'demo')

  risks.forEach((risk, index) => {
    const riskKey = risk.risk_id || risk.name || `risk-${index}`
    const id = `WO-DET-${String(job.job_id || 'JOB').replace(/[^A-Za-z0-9]/g, '').slice(-18)}-${index + 1}`
    const images = pickImages(result, risk, index)
    const found = existing.find(
      (w) => w.id === id || (w.detectJobId === job.job_id && w.detectRiskKey === riskKey)
    )

    if (found) {
      let changed = false
      if (!found.snapUrl && images.snapUrl) {
        found.snapUrl = images.snapUrl
        changed = true
      }
      if (!found.maskUrl && (images.maskUrl || images.overlayUrl)) {
        found.maskUrl = images.maskUrl || images.overlayUrl
        changed = true
      }
      if (!found.overlayUrl && images.overlayUrl) {
        found.overlayUrl = images.overlayUrl
        changed = true
      }
      // 已有工单但图片路径未带代理前缀时补齐
      if (found.snapUrl && found.snapUrl.startsWith('/api/detect/')) {
        found.snapUrl = `/detect-api${found.snapUrl}`
        changed = true
      }
      if (found.maskUrl && found.maskUrl.startsWith('/api/detect/')) {
        found.maskUrl = `/detect-api${found.maskUrl}`
        changed = true
      }
      if (changed) {
        updated += 1
        touched.push(found)
      }
      return
    }

    const order = {
      id,
      title: risk.name || '现场检测风险',
      level: mapLevel(risk),
      type: risk.name || '实时检测',
      area: job.device_id || job.site_id || '实时检测',
      team: '待指派',
      status: 'pending',
      rawStatus: 'pending_confirmation',
      assignee: '待指派',
      createTime: stamp,
      deadline: stamp,
      snapUrl: images.snapUrl,
      maskUrl: images.maskUrl || images.overlayUrl,
      overlayUrl: images.overlayUrl,
      regulation: risk.description || result.report_summary || '见检测报告与规范映射',
      suggestions: risk.suggestions || [],
      detectJobId: job.job_id,
      jobProfile: job.profile || '',
      businessEventId: job.event?.event_id || '',
      detectRiskKey: riskKey,
      source: 'realtime-detect',
      presentationAsset,
      sourceType: presentationAsset ? 'demo-run' : 'pending-sync',
      logs: [
        { time: stamp.slice(11), action: '实时检测自动生成工单', user: 'AI检测引擎' },
        {
          time: stamp.slice(11),
          action: `来源任务 ${job.job_id} · 模式 ${job.profile || '-'}`,
          user: '系统',
        },
      ],
    }
    existing.unshift(order)
    touched.push(order)
    created += 1
  })

  if (created || updated) {
    saveDetectWorkOrders(existing)
  }
  return { created, updated, orders: touched }
}

export function patchDetectWorkOrder(id, patch) {
  const list = loadDetectWorkOrders()
  const idx = list.findIndex((w) => w.id === id)
  if (idx < 0) return null
  list[idx] = { ...list[idx], ...patch }
  saveDetectWorkOrders(list)
  return list[idx]
}
