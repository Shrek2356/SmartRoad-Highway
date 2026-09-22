import { getBusinessApiBase } from '@/utils/endpoints'
import { notifyModules } from '@/utils/moduleBus'

let socket = null
let retryTimer = null
let stopped = true

function socketUrl() {
  const token = localStorage.getItem('znt_token') || ''
  const base = getBusinessApiBase()
  const absolute = new URL(base, window.location.origin)
  const path = absolute.pathname.replace(/\/api\/?$/, '')
  const protocol = absolute.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${absolute.host}${path}/ws?token=${encodeURIComponent(token)}`
}

function connect() {
  retryTimer = null
  if (stopped || !localStorage.getItem('znt_token')) return
  socket = new WebSocket(socketUrl())
  socket.onopen = () => socket?.send('ping')
  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload.type === 'ready' || payload.type === 'pong') return
      notifyModules({
        ...payload,
        type: payload.type === 'work_order' ? 'workorders' : 'detect-results',
        backendType: payload.type,
      })
    } catch {
      // Ignore malformed optional push messages; HTTP remains the source of truth.
    }
  }
  socket.onclose = () => {
    socket = null
    if (!stopped) retryTimer = window.setTimeout(connect, 3000)
  }
  socket.onerror = () => socket?.close()
}

export function startBusinessSocket() {
  stopped = false
  if (!socket && !retryTimer) connect()
}

export function stopBusinessSocket() {
  stopped = true
  if (retryTimer) window.clearTimeout(retryTimer)
  retryTimer = null
  socket?.close()
  socket = null
}
