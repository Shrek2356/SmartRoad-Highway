/**
 * 处置智能体对接位
 * -------------------------------------------------------
 * 【对接服务】工单自动生成 / 告警推送智能体
 * 【职责】根据推理结果创建工单、触发多通道推送
 * 【修改入口】ACTION_API_URL
 * -------------------------------------------------------
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'

export const ACTION_API_URL = import.meta.env.VITE_ACTION_API || '/ai/action/create-order'

/**
 * 工单自动生成
 *
 * 入参:
 * {
 *   reasonResult: object,      // analyzeRisk 出参
 *   visionResult: object,      // receiveRiskDetection 出参
 *   context: {
 *     cameraId, area, team?, assignee?
 *   }
 * }
 *
 * 出参:
 * {
 *   workOrderId: string,
 *   status: 'created',
 *   pushChannels: string[]
 * }
 */
export async function autoCreateWorkOrder(payload) {
  if (USE_MOCK) {
    return mockDelay({ workOrderId: null, status: 'pending_review', pushChannels: [], source: 'road-mock-no-order' })
  }
  return request.post(ACTION_API_URL, payload)
}

/**
 * 完整 AI 处置链路（视觉 → 推理 → 工单）
 * 页面或 WebSocket 回调中可直接调用此编排函数
 */
export async function runAiPipeline(payload) {
  const { receiveRiskDetection } = await import('./vision')
  const { analyzeRisk } = await import('./reason')

  const visionRes = await receiveRiskDetection(payload)
  const visionData = visionRes.data

  const reasonRes = await analyzeRisk({
    risks: visionData.risks,
    context: payload.context || { cameraId: payload.cameraId },
  })
  const reasonData = reasonRes.data

  let orderData = null
  if (reasonData.needWorkOrder) {
    const orderRes = await autoCreateWorkOrder({
      reasonResult: reasonData,
      visionResult: visionData,
      context: payload.context || { cameraId: payload.cameraId },
    })
    orderData = orderRes.data
  }

  return {
    code: 0,
    data: {
      vision: visionData,
      reason: reasonData,
      workOrder: orderData,
    },
  }
}
