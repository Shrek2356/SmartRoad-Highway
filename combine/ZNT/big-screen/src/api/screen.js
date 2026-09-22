/**
 * 大屏数据接口
 * -------------------------------------------------------
 * 入参：{ projectId?: string }
 * 出参：{ alerts, stats, cases, teamRank }
 * 默认读取业务后台；VITE_USE_MOCK=true 时才使用独立演示数据。
 * -------------------------------------------------------
 */
import axios from 'axios'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'
const TOKEN_KEY = 'znt_screen_token'
const TOKEN_BASE_KEY = 'znt_screen_token_base'

function delay(data, ms = 200) {
  return new Promise((resolve) => setTimeout(() => resolve({ code: 0, data }), ms))
}

function screenBaseUrl() {
  const queryBase = new URLSearchParams(window.location.search).get('api')
  const baseURL = (queryBase || localStorage.getItem('znt_screen_api') || import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8800').replace(/\/$/, '')
  if (queryBase) localStorage.setItem('znt_screen_api', queryBase)
  return baseURL
}

async function screenToken(baseURL, force = false) {
  const cached = localStorage.getItem(TOKEN_KEY)
  const cachedBase = localStorage.getItem(TOKEN_BASE_KEY)
  if (!force && cached && cachedBase === baseURL) return cached
  const username = import.meta.env.VITE_SCREEN_USERNAME || 'viewer'
  const password = import.meta.env.VITE_SCREEN_PASSWORD || 'viewer123'
  const response = await axios.post(`${baseURL}/api/auth/login`, { username, password })
  const token = response.data?.token
  if (!token) throw new Error('大屏只读账号登录失败')
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(TOKEN_BASE_KEY, baseURL)
  return token
}

async function loadRealScreen(params = {}, retry = true) {
  const baseURL = screenBaseUrl()
  const token = await screenToken(baseURL)
  try {
    const response = await axios.get(`${baseURL}/api/screen/overview`, {
      params,
      headers: { Authorization: `Bearer ${token}` },
    })
    response.data.cases = (response.data.cases || []).map((item) => ({
      ...item,
      image: item.image?.startsWith('/') ? `${baseURL}${item.image}` : item.image,
    }))
    return response
  } catch (error) {
    if (retry && error?.response?.status === 401) {
      await screenToken(baseURL, true)
      return loadRealScreen(params, false)
    }
    throw error
  }
}

export function fetchScreenData(params = {}) {
  if (USE_MOCK) {
    return delay({
      alerts: alertScroll,
      stats: todayStats,
      cases: violationCases,
      teamRank,
      projectId: params.projectId || 'proj-001',
    })
  }
  return loadRealScreen(params)
}
