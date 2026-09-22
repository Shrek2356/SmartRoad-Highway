/**
 * 浏览器端 uni API 兼容层（原 UniApp 页面可直接调用）
 */
import router from './router'

function toast(title) {
  const el = document.createElement('div')
  el.className = 'uni-toast'
  el.textContent = title
  document.body.appendChild(el)
  setTimeout(() => el.remove(), 1600)
}

function pathFromUniUrl(url = '') {
  const clean = url.split('?')[0]
  const map = {
    '/pages/index/index': '/',
    '/pages/workorder/index': '/workorder',
    '/pages/case/index': '/case',
    '/pages/report/index': '/report',
    '/pages/alarm/index': '/alarm',
  }
  return map[clean] || '/'
}

const uni = {
  showToast({ title } = {}) {
    toast(title || '完成')
  },
  switchTab({ url } = {}) {
    router.push(pathFromUniUrl(url))
  },
  navigateTo({ url } = {}) {
    router.push(pathFromUniUrl(url))
  },
  reLaunch({ url } = {}) {
    router.replace(pathFromUniUrl(url))
  },
  chooseImage({ count = 1, success } = {}) {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.multiple = count > 1
    input.onchange = () => {
      const files = Array.from(input.files || []).slice(0, count)
      const tempFilePaths = files.map((f) => URL.createObjectURL(f))
      success?.({ tempFilePaths, tempFiles: files })
    }
    input.click()
  },
  getStorageSync(key) {
    return localStorage.getItem(key) || ''
  },
  setStorageSync(key, value) {
    localStorage.setItem(key, value)
  },
  removeStorageSync(key) {
    localStorage.removeItem(key)
  },
  request({ url, method = 'GET', data, header = {}, success, fail } = {}) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json', ...header },
    }
    let finalUrl = url
    if (method === 'GET' && data && Object.keys(data).length) {
      const qs = new URLSearchParams(data).toString()
      finalUrl += (url.includes('?') ? '&' : '?') + qs
    } else if (method !== 'GET' && data) {
      opts.body = JSON.stringify(data)
    }
    fetch(finalUrl, opts)
      .then(async (response) => {
        const text = await response.text()
        let body = null
        try { body = text ? JSON.parse(text) : null } catch { body = { detail: text } }
        success?.({ data: body, statusCode: response.status, header: response.headers })
      })
      .catch((err) => fail?.(err))
  },
}

export function installUni() {
  if (typeof window !== 'undefined') {
    window.uni = uni
  }
  return uni
}

export default uni
