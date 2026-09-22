import request from '@/utils/request'

export const fetchConfirmations = () => request.get('/confirmations')
export const decideConfirmation = (id, data) => request.post(`/confirmations/${encodeURIComponent(id)}/decide`, data)
export const fetchProposals = () => request.get('/proposals')
export const decideProposal = (id, data) => request.post(`/proposals/${encodeURIComponent(id)}/decide`, data)
export const fetchOverrides = () => request.get('/overrides')
export const fetchNotifications = () => request.get('/notifications')
export const fetchBriefing = () => request.get('/briefing')
export const fetchUsers = () => request.get('/users')
export const createUser = (data) => request.post('/users', data)
export const updateUserRole = (username, role) => request.post(`/users/${encodeURIComponent(username)}/role`, { role })
export const updateUserPassword = (username, password) => request.post(`/users/${encodeURIComponent(username)}/password`, { password })
export const createBackup = () => request.post('/admin/backup')
