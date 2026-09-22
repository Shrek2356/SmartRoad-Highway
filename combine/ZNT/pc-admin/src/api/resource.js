/**
 * 基础资源管理接口（设备 / 组织 / 项目）
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'
import { devices, orgTree, projectList, currentProject } from '@/mock'

/**
 * 设备列表
 * @param {{ status?: string, keyword?: string }} params
 */
export function fetchDevices(params = {}) {
  if (USE_MOCK) {
    let list = [...devices]
    if (params.status) list = list.filter((d) => d.status === params.status)
    if (params.keyword) {
      list = list.filter(
        (d) => d.name.includes(params.keyword) || d.area.includes(params.keyword)
      )
    }
    return mockDelay(list)
  }
  return request.get('/resource/devices', { params })
}

/**
 * 组织架构树
 */
export function fetchOrgTree() {
  if (USE_MOCK) return mockDelay(orgTree)
  return request.get('/resource/org-tree')
}

/**
 * 项目列表
 */
export function fetchProjects() {
  if (USE_MOCK) return mockDelay(projectList)
  return request.get('/resource/projects')
}

/**
 * 切换当前项目
 * @param {{ projectId: string }} data
 */
export function switchProject(data) {
  if (USE_MOCK) {
    const project = projectList.find((p) => p.id === data.projectId) || currentProject
    return mockDelay(project)
  }
  return request.post('/resource/switch-project', data)
}
