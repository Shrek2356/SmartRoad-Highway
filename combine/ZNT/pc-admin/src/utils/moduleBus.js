/**
 * 模块间互通总线
 * 检测完成 / 工单变更后通知各页刷新（同页 CustomEvent + 跨页 storage）
 */
const CHANNEL = 'znt_module_sync'
const EVENT = 'znt-module-sync'

export function notifyModules(payload = {}) {
  const detail = {
    ...payload,
    at: Date.now(),
  }
  try {
    window.dispatchEvent(new CustomEvent(EVENT, { detail }))
    localStorage.setItem(CHANNEL, JSON.stringify(detail))
  } catch {
    // ignore quota / private mode
  }
}

/**
 * @param {(detail: object) => void} handler
 * @returns {() => void} unsubscribe
 */
export function subscribeModules(handler) {
  const onCustom = (e) => handler(e.detail || {})
  const onStorage = (e) => {
    if (e.key !== CHANNEL || !e.newValue) return
    try {
      handler(JSON.parse(e.newValue))
    } catch {
      // ignore
    }
  }
  window.addEventListener(EVENT, onCustom)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener(EVENT, onCustom)
    window.removeEventListener('storage', onStorage)
  }
}
