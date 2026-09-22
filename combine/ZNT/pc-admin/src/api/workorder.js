/**
 * 风险工单接口
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'
import { getMergedWorkOrders, patchWorkOrder, appendWorkOrderLog } from '@/utils/workOrderStore'
import { loadDetectWorkOrders, patchDetectWorkOrder } from '@/utils/detectWorkOrders'

function demoWorkOrders() {
  return loadDetectWorkOrders().filter((item) =>
    item.presentationAsset || item.sourceType === 'demo-run' || item.jobProfile === 'demo' || String(item.detectJobId || '').startsWith('MOCK-')
  ).map((item) => ({ ...item, presentationAsset: true, sourceType: 'demo-run' }))
}

function filterLocalOrders(list, params = {}) {
  return list.filter((item) => {
    const keyword = String(params.keyword || '').toLowerCase()
    if (keyword && ![item.id, item.title, item.area].some((value) => String(value || '').toLowerCase().includes(keyword))) return false
    if (params.level && item.level !== params.level) return false
    if (params.status && item.status !== params.status) return false
    if (params.type && item.type !== params.type) return false
    if (params.team && item.team !== params.team) return false
    return true
  })
}

function localOrder(id) {
  const item = loadDetectWorkOrders().find((candidate) => candidate.id === id)
  if (!item) return null
  const isDemo = item.presentationAsset || item.sourceType === 'demo-run' || item.jobProfile === 'demo' || String(item.detectJobId || '').startsWith('MOCK-')
  return isDemo ? { ...item, presentationAsset: true, sourceType: 'demo-run' } : item
}

/**
 * 工单列表（支持筛选）
 */
export function fetchWorkOrders(params = {}) {
  if (USE_MOCK) {
    let list = getMergedWorkOrders()
    if (params.keyword) {
      const kw = params.keyword.toLowerCase()
      list = list.filter(
        (w) =>
          w.id.toLowerCase().includes(kw) ||
          w.title.toLowerCase().includes(kw) ||
          (w.area || '').includes(kw)
      )
    }
    if (params.level) list = list.filter((w) => w.level === params.level)
    if (params.status) list = list.filter((w) => w.status === params.status)
    if (params.type) list = list.filter((w) => w.type === params.type)
    if (params.team) list = list.filter((w) => w.team === params.team)

    const page = params.page || 1
    const pageSize = params.pageSize || 10
    const start = (page - 1) * pageSize
    return mockDelay({
      list: list.slice(start, start + pageSize),
      total: list.length,
    })
  }
  return request.get('/workorder/list', { params: { ...params, page: 1, pageSize: 1000 } }).then((res) => {
    const remote = res.data.list || []
    const local = filterLocalOrders(demoWorkOrders(), params)
    const merged = [...local, ...remote]
    const page = Number(params.page || 1)
    const pageSize = Number(params.pageSize || 10)
    const start = (page - 1) * pageSize
    return { ...res, data: { ...res.data, list: merged.slice(start, start + pageSize), total: merged.length } }
  })
}

/**
 * 工单详情
 */
export function fetchWorkOrderDetail(id) {
  if (USE_MOCK) {
    const item = getMergedWorkOrders().find((w) => w.id === id)
    return mockDelay(item || null)
  }
  const local = localOrder(id)
  if (local?.presentationAsset || local?.sourceType === 'demo-run') return mockDelay(local, 80)
  return request.get(`/workorder/${id}`)
}

/**
 * 工单状态流转
 * accept / reject → 处理中；complete → 已完成
 */
export function updateWorkOrderStatus(data) {
  const local = localOrder(data.id)
  if (local?.presentationAsset || local?.sourceType === 'demo-run') {
    const statusMap = { accept: 'processing', reject: 'processing', complete: 'done', reopen: 'pending' }
    const rawStatusMap = { accept: 'rectifying', reject: 'rectifying', complete: 'closed', reopen: 'pending_confirmation' }
    const actionText = { accept: '演示工单已接单', reject: '演示工单已驳回重检', complete: '演示工单已复核关闭', reopen: '演示工单已重新打开' }
    const status = statusMap[data.action]
    const logs = [...(local.logs || []), { time: new Date().toTimeString().slice(0, 8), action: actionText[data.action] || data.action, user: '当前用户' }]
    patchDetectWorkOrder(data.id, { status, rawStatus: rawStatusMap[data.action], logs })
    return mockDelay({ success: true, ...data, status }, 80)
  }
  if (USE_MOCK) {
    const statusMap = {
      accept: 'processing',
      reject: 'processing',
      complete: 'done',
      reopen: 'pending',
    }
    const actionText = {
      accept: '道路值班员已接单，进入处理中',
      reject: '驳回重检，进入处理中',
      complete: '确认整改完成',
      reopen: '重新打开工单',
    }
    const nextStatus = statusMap[data.action]
    const id = data.id

    if (nextStatus && id) {
      // 检测工单仍写回 detect 存储（图片等字段）
      if (String(id).startsWith('WO-DET-')) {
        patchDetectWorkOrder(id, { status: nextStatus })
      }
      patchWorkOrder(id, { status: nextStatus })
      appendWorkOrderLog(id, {
        time: new Date().toTimeString().slice(0, 8),
        action: actionText[data.action] || data.action,
        user: '当前用户',
      })
    }
    return mockDelay({ success: true, ...data, status: nextStatus })
  }
  return request.post('/workorder/status', data)
}

export function uploadWorkOrderEvidence({ id, file, note = '' }) {
  const local = localOrder(id)
  if (local?.presentationAsset || local?.sourceType === 'demo-run') {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onerror = () => reject(new Error('整改证据读取失败'))
      reader.onload = () => {
        const evidenceImages = [...(local.evidenceImages || []), String(reader.result || '')]
        const logs = [...(local.logs || []), { time: new Date().toTimeString().slice(0, 8), action: note || '演示整改证据已上传', user: '当前用户' }]
        patchDetectWorkOrder(id, { evidenceImages, status: 'processing', rawStatus: 'rectified', logs })
        resolve({ code: 0, message: 'ok', data: { success: true, id } })
      }
      reader.readAsDataURL(file)
    })
  }
  const form = new FormData()
  form.append('id', id)
  form.append('note', note || 'PC端上传整改复核证据')
  form.append('file', file, file.name || 'rectification.jpg')
  return request.post('/workorder/evidence', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/**
 * 批量导出
 */
export function exportWorkOrders(data = {}) {
  if (USE_MOCK) {
    const all = getMergedWorkOrders()
    const list = data.ids?.length ? all.filter((w) => data.ids.includes(w.id)) : all
    return mockDelay(list)
  }
  return request.post('/workorder/export', data).then((res) => {
    const local = data.ids?.length ? demoWorkOrders().filter((item) => data.ids.includes(item.id)) : demoWorkOrders()
    return { ...res, data: [...local, ...(res.data || [])] }
  })
}

/** 状态统计（筛选 Tab 用） */
export function fetchWorkOrderStats() {
  if (USE_MOCK) {
    const all = getMergedWorkOrders()
    return mockDelay({
      all: all.length,
      pending: all.filter((w) => w.status === 'pending').length,
      processing: all.filter((w) => w.status === 'processing').length,
      done: all.filter((w) => w.status === 'done').length,
    })
  }
  return request.get('/workorder/stats').then((res) => {
    const local = demoWorkOrders()
    return {
      ...res,
      data: {
        all: Number(res.data.all || 0) + local.length,
        pending: Number(res.data.pending || 0) + local.filter((item) => item.status === 'pending').length,
        processing: Number(res.data.processing || 0) + local.filter((item) => item.status === 'processing').length,
        done: Number(res.data.done || 0) + local.filter((item) => item.status === 'done').length,
      },
    }
  })
}
