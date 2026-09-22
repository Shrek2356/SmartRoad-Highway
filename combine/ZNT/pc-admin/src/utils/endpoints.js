import { validateEndpoint } from './endpointValidation.js'
const BUSINESS_KEY = 'znt_business_api'
const DETECT_KEY = 'znt_detect_api'

export const DEFAULT_BUSINESS_API = import.meta.env.VITE_API_BASE || '/business-api/api'
export const DEFAULT_DETECT_API = import.meta.env.VITE_DETECT_API || '/detect-api'

function clean(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

export function normalizeBusinessApi(value) {
  const base = clean(value) || DEFAULT_BUSINESS_API
  if (base.endsWith('/api') || base.endsWith('/business-api/api')) return base
  return `${base}/api`
}

export function normalizeDetectApi(value) {
  return clean(value) || DEFAULT_DETECT_API
}

export function getBusinessApiBase() {
  return normalizeBusinessApi(localStorage.getItem(BUSINESS_KEY) || DEFAULT_BUSINESS_API)
}

export function getDetectApiBase() {
  return normalizeDetectApi(localStorage.getItem(DETECT_KEY) || DEFAULT_DETECT_API)
}

export function getEndpointSettings() {
  return { businessApi: getBusinessApiBase(), detectApi: getDetectApiBase() }
}

export function saveEndpointSettings({ businessApi, detectApi }) {
  const normalized = {
    businessApi: normalizeBusinessApi(businessApi),
    detectApi: normalizeDetectApi(detectApi),
  }
  validateEndpoint(normalized.businessApi)
  validateEndpoint(normalized.detectApi)
  localStorage.setItem(BUSINESS_KEY, normalized.businessApi)
  localStorage.setItem(DETECT_KEY, normalized.detectApi)
  return normalized
}

export function resetEndpointSettings() {
  localStorage.removeItem(BUSINESS_KEY)
  localStorage.removeItem(DETECT_KEY)
  return getEndpointSettings()
}

export function joinEndpoint(base, path = '') {
  const root = clean(base)
  const suffix = String(path || '').replace(/^\/+/, '')
  return suffix ? `${root}/${suffix}` : root
}

export function resolveBusinessMediaUrl(url = '') {
  if (!url || /^(https?:|blob:|data:)/i.test(url)) return url
  const base = getBusinessApiBase()
  if (url.startsWith('/business-api/api/')) {
    return joinEndpoint(base, url.slice('/business-api/api/'.length))
  }
  if (url.startsWith('/api/')) {
    return joinEndpoint(base, url.slice('/api/'.length))
  }
  return url
}

export function resolveDetectMediaUrl(url = '') {
  if (!url || /^(https?:|blob:|data:)/i.test(url)) return url
  const base = getDetectApiBase()
  if (url.startsWith('/detect-api/')) return joinEndpoint(base, url.slice('/detect-api/'.length))
  if (url.startsWith('/api/detect/')) return joinEndpoint(base, url.slice(1))
  return url.startsWith('/') ? url : joinEndpoint(base, url)
}
