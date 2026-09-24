import request from '@/utils/request'

export const learningOverview = () => request.get('/learning/overview')
export const auditSamples = () => request.get('/learning/audit-samples')
export const correctionContext = (id) => request.get(`/learning/context/${encodeURIComponent(id)}`)
export const submitCorrection = (data) => request.post('/learning/cases', data)
export const reviewCase = (id, data) => request.post(`/learning/cases/${encodeURIComponent(id)}/review`, data)
export const buildMemory = () => request.post('/learning/versions')
export const startReplay = (data) => request.post('/learning/runs', data)
export const cancelReplay = (id) => request.post(`/learning/runs/${encodeURIComponent(id)}/cancel`)
export const activateMemory = (id) => request.post(`/learning/runs/${encodeURIComponent(id)}/activate`)
export const rollbackMemory = () => request.post('/learning/rollback')
export const exportCases = (partition) => request.get(`/learning/export/${partition}`, { responseType: 'blob', timeout: 120000 })
export const learningError = (error) => error?.response?.data?.detail || error?.message || '操作未完成'
