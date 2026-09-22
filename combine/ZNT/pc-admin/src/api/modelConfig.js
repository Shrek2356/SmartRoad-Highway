/**
 * 模型规则配置接口
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'
import { modelConfig } from '@/mock'

/**
 * 获取模型配置全量数据
 */
export function fetchModelConfig() {
  if (USE_MOCK) return mockDelay(modelConfig)
  return request.get('/model/config')
}

/**
 * 更新检测阈值
 * @param {{ key: string, value: number }} data
 */
export function updateThreshold(data) {
  if (USE_MOCK) return mockDelay({ success: true, ...data })
  return request.put('/model/threshold', data)
}

/**
 * 更新告警推送规则
 * @param {object} data 规则对象
 */
export function updatePushRule(data) {
  if (USE_MOCK) return mockDelay({ success: true, ...data })
  return request.put('/model/push-rule', data)
}
