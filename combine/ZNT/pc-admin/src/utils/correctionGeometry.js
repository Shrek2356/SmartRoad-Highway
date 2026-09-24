export function normalizedPoint(event, rect) {
  if (!rect.width || !rect.height) return null
  return [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
    Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))]
}
export function normalizedBox(start, end) {
  if (!start || !end) return null
  const box = [Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.max(start[0], end[0]), Math.max(start[1], end[1])]
  return box[2] - box[0] >= .005 && box[3] - box[1] >= .005 ? box.map(n => Math.round(n * 10000) / 10000) : null
}
export const correctionKinds = [
  { value: 'false_positive', label: '误报：实际不存在' }, { value: 'false_negative', label: '漏检：应有未报' },
  { value: 'wrong_category', label: '类别判断错误' }, { value: 'localization', label: '定位范围错误' },
  { value: 'novel_class', label: '新类别候选' }, { value: 'normal', label: '整图正常复查' }, { value: 'uncertain', label: '暂时无法判断' },
]
export const partitions = [{ value: 'train', label: '经验 / 训练集' }, { value: 'validation', label: '开发验证集' }, { value: 'holdout', label: '保留测试集' }]
