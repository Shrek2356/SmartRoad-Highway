/**
 * 实时视频监控接口
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'
import { deviceTree, cameraList, realtimeAlarms } from '@/mock'

import { presentationEnabled } from '@/utils/preferences'

function presentationCameras() {
  return cameraList.map((camera) => ({ ...camera, presentationAsset: true }))
}

/**
 * 获取设备树
 * @returns {Promise<{code:number,data:Array}>}
 */
export function fetchDeviceTree() {
  if (USE_MOCK) return mockDelay(deviceTree)
  return request.get('/monitor/device-tree').then((response) => {
    if (!presentationEnabled()) return response
    const demoTree = deviceTree.map((root) => ({
      ...root,
      key: `presentation-${root.key}`,
      title: `${root.title} · 展示点位`,
      presentationAsset: true,
    }))
    return { ...response, data: [...demoTree, ...(response.data || [])] }
  })
}

/**
 * 获取摄像头详情（含流地址与风险掩码）
 * @param {{ ids?: string[] }} params 摄像头 id 列表，空则返回全部
 * @returns {Promise<{code:number,data:Array}>}
 *
 * 出参单项:
 * { id, name, streamUrl, online, masks: [{level,x,y,w,h,label}] }
 * 坐标为画面百分比 0-100
 */
export function fetchCameras(params = {}) {
  if (USE_MOCK) {
    let list = cameraList
    if (params.ids?.length) {
      list = cameraList.filter((c) => params.ids.includes(c.id))
    }
    return mockDelay(list)
  }
  return request.get('/monitor/cameras', { params }).then((response) => {
    if (!presentationEnabled()) return response
    const real = response.data || []
    const known = new Set(real.map((camera) => camera.id))
    const demo = presentationCameras().filter((camera) => !known.has(camera.id))
    // 有真实在线流时优先展示；当前尚未接流时先保留预编辑检测框。
    const merged = real.some((camera) => camera.online) ? [...real, ...demo] : [...demo, ...real]
    const filtered = params.ids?.length ? merged.filter((camera) => params.ids.includes(camera.id)) : merged
    return { ...response, data: filtered }
  })
}

/**
 * 获取实时告警
 * @returns {Promise<{code:number,data:Array}>}
 */
export function fetchRealtimeAlarms() {
  if (USE_MOCK) return mockDelay(realtimeAlarms)
  return request.get('/monitor/alarms')
}

export function fetchStreamSources() {
  return request.get('/monitor/sources')
}

export function saveStreamSource(data) {
  return request.post('/monitor/sources', data)
}

export function startStreamSource(id) {
  return request.post(`/monitor/sources/${encodeURIComponent(id)}/start`)
}

export function stopStreamSource(id) {
  return request.post(`/monitor/sources/${encodeURIComponent(id)}/stop`)
}

export function deleteStreamSource(id) {
  return request.delete(`/monitor/sources/${encodeURIComponent(id)}`)
}

export function fetchStreamSourceLog(id, lines = 120) {
  return request.get(`/monitor/sources/${encodeURIComponent(id)}/log`, { params: { lines } })
}
