export const DETECTION_PROFILES = ['demo', 'offline', 'standard']
export function normalizeDetectionProfile(value, fallback='offline') {
  return DETECTION_PROFILES.includes(value) ? value : fallback
}
export function detectionBlockReason(profile, health) {
  if (profile === 'demo') return ''
  if (!health.online) return '检测桥未连接。请先恢复连接；系统不会将真实检测自动切换成演示。'
  const p = health.profiles?.find(p => p.id === profile)
  const ready = profile === 'offline' && p?.runtime_ready !== undefined ? p.runtime_ready : p?.ready
  return ready ? '' : '当前模式尚未就绪，请配置模型与服务后重试。'
}
