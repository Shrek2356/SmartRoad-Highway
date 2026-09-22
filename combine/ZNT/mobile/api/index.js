/**
 * 移动端接口统一封装
 * -------------------------------------------------------
 * 每个函数标注入参/出参，后续替换 Mock 只需改本目录
 * 默认连接业务后台与检测桥；VITE_USE_MOCK=true 时才使用独立演示数据。
 * -------------------------------------------------------
 */
import {
  homeReminders,
  latestAlarm,
  workOrders,
  cases,
} from '../mock/index.js'

/** true=本地Mock，false=真实接口 */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export const DETECT_PROFILE_OPTIONS = Object.freeze([
  { value: 'standard', label: '云端检测' },
  { value: 'offline', label: '本地离线' },
  { value: 'demo', label: '演示模式' },
])

const RUNTIME_DEFAULTS = Object.freeze({
  businessApi: import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8800',
  detectApi: import.meta.env.VITE_DETECT_API || 'http://127.0.0.1:8810',
  username: import.meta.env.VITE_MOBILE_USERNAME || 'safety',
  password: import.meta.env.VITE_MOBILE_PASSWORD || 'safety123',
  profile: import.meta.env.VITE_DETECT_PROFILE || 'offline',
})

const STORAGE_KEYS = Object.freeze({
  businessApi: 'znt_mobile_api',
  detectApi: 'znt_detect_api',
  username: 'znt_mobile_username',
  password: 'znt_mobile_password',
  profile: 'znt_detect_profile',
})

let queryConfigApplied = false

function normalizeServiceUrl(value, fallback) {
  const clean = String(value || fallback || '').trim().replace(/\/+$/, '')
  return clean.replace(/\/api$/i, '')
}

function isKnownProfile(value) {
  return DETECT_PROFILE_OPTIONS.some((option) => option.value === value)
}

function readStoredConfig() {
  return {
    businessApi: normalizeServiceUrl(uni.getStorageSync(STORAGE_KEYS.businessApi), RUNTIME_DEFAULTS.businessApi),
    detectApi: normalizeServiceUrl(uni.getStorageSync(STORAGE_KEYS.detectApi), RUNTIME_DEFAULTS.detectApi),
    username: uni.getStorageSync(STORAGE_KEYS.username) || RUNTIME_DEFAULTS.username,
    password: uni.getStorageSync(STORAGE_KEYS.password) || RUNTIME_DEFAULTS.password,
    profile: isKnownProfile(uni.getStorageSync(STORAGE_KEYS.profile))
      ? uni.getStorageSync(STORAGE_KEYS.profile)
      : RUNTIME_DEFAULTS.profile,
  }
}

function applyQueryConfig() {
  if (queryConfigApplied || typeof window === 'undefined') return
  queryConfigApplied = true
  const query = new URLSearchParams(window.location.search)
  const patch = {
    businessApi: query.get('api'),
    detectApi: query.get('detect'),
    username: query.get('username') || query.get('user'),
    password: query.get('password'),
    profile: query.get('profile'),
  }
  if (Object.values(patch).some((value) => value !== null && value !== '')) {
    saveRuntimeConfig({ ...readStoredConfig(), ...Object.fromEntries(
      Object.entries(patch).filter(([, value]) => value !== null && value !== '')
    ) })
  }
}

/**
 * 获取移动端运行配置。优先级：URL 查询参数 > 本地保存 > 构建环境变量 > 演示默认值。
 * 支持查询参数：api、detect、username（或 user）、password、profile。
 */
export function getRuntimeConfig() {
  applyQueryConfig()
  return readStoredConfig()
}

export function saveRuntimeConfig(nextConfig = {}) {
  const previous = readStoredConfig()
  const valueOf = (field) => Object.prototype.hasOwnProperty.call(nextConfig, field)
    ? nextConfig[field]
    : previous[field]
  const profile = isKnownProfile(nextConfig.profile) ? nextConfig.profile : previous.profile
  const config = {
    businessApi: normalizeServiceUrl(valueOf('businessApi'), ''),
    detectApi: normalizeServiceUrl(valueOf('detectApi'), ''),
    username: String(valueOf('username') ?? '').trim(),
    password: String(valueOf('password') ?? ''),
    profile,
  }
  if (!config.businessApi || !config.detectApi || !config.username || !config.password) {
    throw new Error('业务地址、检测地址、登录账号和密码均不能为空')
  }
  Object.entries(STORAGE_KEYS).forEach(([field, key]) => uni.setStorageSync(key, config[field]))
  const authChanged = ['businessApi', 'username', 'password']
    .some((field) => config[field] !== previous[field])
  if (authChanged) {
    uni.removeStorageSync('znt_token')
    uni.removeStorageSync('znt_user')
  }
  return config
}

export function resetRuntimeConfig() {
  Object.values(STORAGE_KEYS).forEach((key) => uni.removeStorageSync(key))
  uni.removeStorageSync('znt_token')
  uni.removeStorageSync('znt_user')
  queryConfigApplied = true
  return readStoredConfig()
}

/** 真实后端地址 */
export function getBaseUrl() {
  return getRuntimeConfig().businessApi + '/api'
}

function mockDelay(data, ms = 250) {
  return new Promise((resolve) => {
    setTimeout(() => resolve({ code: 0, message: 'ok', data }), ms)
  })
}

/**
 * 首页工单提醒
 * 入参：无
 * 出参：Array<{id,title,level,time,status}>
 */
export function fetchHomeReminders() {
  if (USE_MOCK) return mockDelay(homeReminders)
  return uniRequest('/mobile/reminders')
}

/**
 * 最新告警（用于弹窗）
 * 出参：{ id, level, title, area, camera, time, snapTip, regulation }
 */
export function fetchLatestAlarm() {
  if (USE_MOCK) return mockDelay(latestAlarm)
  return uniRequest('/mobile/alarm/latest')
}

/**
 * 告警处置
 * 入参：{ alarmId, action: 'accept'|'ignore'|'escalate', remark? }
 */
export function handleAlarm(data) {
  if (USE_MOCK) return mockDelay({ success: true, ...data })
  return uniRequest('/mobile/alarm/handle', 'POST', data)
}

/**
 * 工单列表
 * 入参：{ status? }
 */
export function fetchWorkOrders(params = {}) {
  if (USE_MOCK) {
    let list = [...workOrders]
    if (params.status) list = list.filter((w) => w.status === params.status)
    return mockDelay(list)
  }
  return uniRequest('/mobile/workorder/list', 'GET', params)
}

/**
 * 工单闭环推进
 * 入参：{ id, action: 'next'|'photo'|'close', photoPath? }
 */
export function advanceWorkOrder(data) {
  if (USE_MOCK) return mockDelay({ success: true, ...data })
  return uniRequest('/mobile/workorder/advance', 'POST', data)
}

export function uploadWorkOrderEvidence({ id, image, note = '' }) {
  return ensureLogin().then(async () => {
    const form = new FormData()
    form.append('id', id)
    form.append('note', note || '移动端现场拍照复核')
    form.append('file', image.file, image.file.name || 'rectification.jpg')
    const response = await fetch(getBaseUrl() + '/mobile/workorder/evidence', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + (uni.getStorageSync('znt_token') || '') },
      body: form,
    })
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail || '复核照片上传失败')
    return { code: 0, message: 'ok', data: body }
  })
}

/**
 * 案例查询
 * 入参：{ keyword? }
 */
export function fetchCases(params = {}) {
  if (USE_MOCK) {
    let list = [...cases]
    if (params.keyword) {
      list = list.filter(
        (c) => c.title.includes(params.keyword) || c.summary.includes(params.keyword)
      )
    }
    return mockDelay(list)
  }
  return uniRequest('/mobile/case/list', 'GET', params)
}

/**
 * 人工上报
 * 入参：{ title, level, area, desc, images? }
 * 图片 AI 辅助分类由 detectImage 调用检测桥完成。
 */
export function submitReport(data) {
  if (USE_MOCK) {
    return mockDelay({
      success: true,
      reportId: 'RP-' + Date.now(),
      message: '上报成功（Mock）',
      ...data,
    })
  }
  return ensureLogin().then(async () => {
    const form = new FormData()
    form.append('title', data.title || '')
    form.append('level', data.level || 'orange')
    form.append('area', data.area || '现场')
    form.append('desc', data.desc || '')
    form.append('site_id', data.site_id || 'SITE-DEFAULT')
    for (const image of data.images || []) {
      if (image?.file) form.append('files', image.file, image.file.name || 'report.jpg')
    }
    const response = await fetch(getBaseUrl() + '/mobile/report', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + (uni.getStorageSync('znt_token') || '') },
      body: form,
    })
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail || '人工上报失败')
    return { code: 0, message: 'ok', data: body }
  })
}

/** uni.request 封装（真实对接时使用） */
function uniRequest(url, method = 'GET', data = {}) {
  return ensureLogin().then(() => requestOnce(url, method, data, true))
}

function requestOnce(url, method, data, mayRelogin) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: getBaseUrl() + url,
      method,
      data,
      header: {
        Authorization: 'Bearer ' + (uni.getStorageSync('znt_token') || ''),
      },
      success: async (res) => {
        const body = res.data
        if (res.statusCode === 401 && mayRelogin) {
          uni.setStorageSync('znt_token', '')
          try {
            await ensureLogin()
            resolve(await requestOnce(url, method, data, false))
          } catch (error) { reject(error) }
          return
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(body?.detail || body?.message || `请求失败（HTTP ${res.statusCode}）`))
          return
        }
        resolve(body?.code !== undefined ? body : { code: 0, message: 'ok', data: body })
      },
      fail: reject,
    })
  })
}

export async function ensureLogin() {
  if (uni.getStorageSync('znt_token')) return
  const config = getRuntimeConfig()
  const response = await fetch(getBaseUrl() + '/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: config.username, password: config.password }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || '移动端无法登录业务后台，请检查连接设置与账号')
  }
  const body = await response.json()
  uni.setStorageSync('znt_token', body.token)
  uni.setStorageSync('znt_user', JSON.stringify(body.user))
}

export async function detectImage(imagePath) {
  await ensureLogin()
  const config = getRuntimeConfig()
  const detectBase = config.detectApi
  const blob = await fetch(imagePath).then((response) => response.blob())
  const form = new FormData(); form.append('file', blob, 'mobile-report.jpg'); form.append('profile', config.profile); form.append('device_id', 'MOBILE-REPORT'); form.append('site_id', 'SITE-DEFAULT'); form.append('force_inspection', 'true')
  const createdResponse = await fetch(detectBase + '/api/detect/upload', { method: 'POST', body: form })
  const created = await createdResponse.json().catch(() => ({}))
  if (!createdResponse.ok) throw new Error(created.detail || `检测任务创建失败（HTTP ${createdResponse.status}）`)
  if (!created.job_id) throw new Error(created.detail || '检测任务创建失败')
  for (let index = 0; index < 180; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1000))
    const jobResponse = await fetch(`${detectBase}/api/detect/jobs/${created.job_id}`)
    const job = await jobResponse.json().catch(() => ({}))
    if (!jobResponse.ok) throw new Error(job.detail || `检测状态查询失败（HTTP ${jobResponse.status}）`)
    if (job.status === 'done') return job
    if (job.status === 'error') throw new Error(job.error || '检测失败')
  }
  throw new Error('检测超时，请到PC端查看任务状态')
}
