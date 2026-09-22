/**
 * 风险等级展示工具
 */
export function levelText(level) {
  return { red: '高危', orange: '中危', yellow: '低危' }[level] || level
}

export function levelColor(level) {
  return { red: '#ff4d4f', orange: '#fa8c16', yellow: '#d4b106' }[level] || '#8c8c8c'
}

export function statusText(status) {
  return { pending: '待处理', processing: '处理中', done: '已完成' }[status] || status
}
