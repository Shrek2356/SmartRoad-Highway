/**
 * 工单数据汇总：Mock 种子 + 实时检测工单 + 状态覆盖（localStorage）
 */
import { workOrders as mockSeed } from '@/mock'
import { loadDetectWorkOrders } from './detectWorkOrders'

const OVERRIDE_KEY = 'znt_workorder_overrides'

function loadOverrides() {
  try {
    return JSON.parse(localStorage.getItem(OVERRIDE_KEY) || '{}')
  } catch {
    return {}
  }
}

function saveOverrides(map) {
  localStorage.setItem(OVERRIDE_KEY, JSON.stringify(map))
}

function applyOverride(order) {
  const patch = loadOverrides()[order.id]
  if (!patch) return order
  return {
    ...order,
    ...patch,
    logs: patch.logs || order.logs,
  }
}

/** 合并全部工单（检测工单在前） */
export function getMergedWorkOrders() {
  const detect = loadDetectWorkOrders().map(applyOverride)
  const mock = mockSeed.map(applyOverride)
  return [...detect, ...mock]
}

/** 各状态数量 */
export function countWorkOrdersByStatus() {
  const all = getMergedWorkOrders()
  return {
    all: all.length,
    pending: all.filter((w) => w.status === 'pending').length,
    processing: all.filter((w) => w.status === 'processing').length,
    done: all.filter((w) => w.status === 'done').length,
  }
}

/** 更新任意工单字段并持久化 */
export function patchWorkOrder(id, patch) {
  const overrides = loadOverrides()
  const prev = overrides[id] || {}
  overrides[id] = {
    ...prev,
    ...patch,
    logs: patch.logs !== undefined ? patch.logs : prev.logs,
  }
  saveOverrides(overrides)
  try {
    // 延迟导入避免循环依赖
    import('./moduleBus').then(({ notifyModules }) => {
      notifyModules({ type: 'workorders', id })
    })
  } catch {
    // ignore
  }
  return applyOverride(
    getMergedWorkOrders().find((w) => w.id === id) || { id, ...patch }
  )
}

/** 追加流转日志 */
export function appendWorkOrderLog(id, log) {
  const order = getMergedWorkOrders().find((w) => w.id === id)
  if (!order) return null
  const logs = [...(order.logs || []), log]
  return patchWorkOrder(id, { logs })
}
