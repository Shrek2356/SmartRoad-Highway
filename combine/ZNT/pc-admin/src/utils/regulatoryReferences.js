// Only display saved evidence. Opening this view must never run a new KB search.
export function referenceGroups(result = {}) {
  return (Array.isArray(result.risks) ? result.risks : []).map((risk, index) => ({
    id: risk.risk_id || `risk-${index}`,
    name: risk.name || risk.risk_name_zh || risk.risk_id || '未命名观察',
    description: risk.description || risk.risk_description || '',
    references: (Array.isArray(risk.knowledge_references) ? risk.knowledge_references : [])
      .filter(ref => ref && typeof ref === 'object' && !Array.isArray(ref)),
    trace: risk.knowledge_retrieval && typeof risk.knowledge_retrieval === 'object' ? risk.knowledge_retrieval : {},
  }))
}

export function referenceCount(result) {
  return referenceGroups(result).reduce((count, group) => count + group.references.length, 0)
}

export function safeSourceUrl(value) {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''
  } catch { return '' }
}

export function scoreLabel(score) {
  return typeof score === 'number' && Number.isFinite(score) ? score.toFixed(4) : '未记录'
}

export function emptyReferenceMessage(result, group) {
  if (group?.trace.status === 'not_configured') return '此类观察尚未配置条款检索范围，本次未执行规范检索。'
  if (group?.trace.status === 'no_verified_match') return '已检索，未找到在该风险范围内且来源校验通过的条款。'
  if (result?.reference_record_status === 'invalid') return '保存的规范记录无法读取；请核查档案文件。'
  if (!referenceGroups(result).length && result?.assessment_quality?.result_status === 'no_visible_anomaly') {
    return '本次图像未见可见异常，没有异常关联的规范引用。'
  }
  if (result?.reference_record_status === 'recorded') return '该检测档案未保存匹配条款。'
  return '此任务未保存规范检索记录，不能据此判断当时是否检索过。'
}
