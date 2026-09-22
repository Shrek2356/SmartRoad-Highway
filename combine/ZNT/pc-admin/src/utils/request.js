/**
 * HTTP 请求封装
 * -------------------------------------------------------
 * 作用：统一 axios 实例，后续对接真实后端时，只需改 baseURL
 * 【后续修改入口】BASE_URL、拦截器中的 Token 注入
 * -------------------------------------------------------
 */
import axios from 'axios'
import { message } from 'ant-design-vue'
import { getBusinessApiBase } from '@/utils/endpoints'

/** 是否使用本地 Mock（true=本地模拟，false=真实接口） */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

const service = axios.create({
  timeout: 30000,
})

/** 请求拦截：预留 Token 注入 */
service.interceptors.request.use(
  (config) => {
    // 每次请求动态读取登录页保存的地址，网页版无需重新构建即可切换服务。
    config.baseURL = getBusinessApiBase()
    const token = localStorage.getItem('znt_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

/** 响应拦截：统一错误处理 */
service.interceptors.response.use(
  (response) => {
    const res = response.data
    // 约定：code === 0 为成功（对接时可按后端规范调整）
    if (res.code !== undefined && res.code !== 0) {
      message.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message || '请求失败'))
    }
    // 正式 FastAPI 返回业务对象；旧 Mock 返回 {code,data}。统一成前端既有契约。
    return res?.code !== undefined ? res : { code: 0, message: 'ok', data: res }
  },
  (error) => {
    if (error?.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem('znt_token')
      localStorage.removeItem('znt_user')
      window.location.replace('/login?expired=1')
      // 页面即将卸载；保持当前请求挂起，避免各页面 mounted/watch
      // 在重定向前收到一次无意义的未处理 Promise 拒绝。
      return new Promise(() => {})
    }
    message.error(error.message || '网络异常')
    return Promise.reject(error)
  }
)

export default service

/**
 * Mock 延迟模拟，让本地开发更接近真实接口体验
 * @param {any} data 返回数据
 * @param {number} delay 延迟毫秒
 */
export function mockDelay(data, delay = 300) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({ code: 0, message: 'ok', data })
    }, delay)
  })
}
