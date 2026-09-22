/**
 * 嘉然队形象资源（JR）
 * 队名：道路检测 · 实验室小试
 *
 * 工单状态表情约定：
 * - yes.png      → 待处理
 * - emergent.png → 紧急事项
 * - no.png       → 正常
 */
export const TEAM_NAME = '道路检测 · 实验室小试'

export const JR = {
  mascot1: '/jr/1.png',
  mascot2: '/jr/2.png',
  yes: '/jr/yes.png',
  emergent: '/jr/emergent.png',
  no: '/jr/no.png',
}

/**
 * 根据工单等级与状态返回对应表情
 * @param {{ level?: string, status?: string }} record
 */
export function workOrderMood(record = {}) {
  if (record.status === 'done') {
    return { key: 'no', src: JR.no, label: '正常', tip: '工单已完成' }
  }
  if (record.level === 'red') {
    return { key: 'emergent', src: JR.emergent, label: '紧急事项', tip: '高危工单，请优先处置' }
  }
  return { key: 'yes', src: JR.yes, label: '待处理', tip: '请及时处置本工单' }
}

/** 首页指标卡可附带的小表情 */
export function metricMood(metricKey) {
  if (metricKey === 'highRisk') return { src: JR.emergent, tip: '紧急事项' }
  if (metricKey === 'pending') return { src: JR.yes, tip: '待处理' }
  if (metricKey === 'fixedRate') return { src: JR.no, tip: '正常' }
  return null
}
