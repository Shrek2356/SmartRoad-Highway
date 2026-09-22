/**
 * 视觉大模型对接位
 * -------------------------------------------------------
 * 【对接服务】目标检测 / 分割视觉大模型（YOLO / 自研视觉模型等）
 * 【修改入口】VISION_API_URL、parseVisionResult
 * -------------------------------------------------------
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'

/** 视觉大模型服务地址（对接时修改） */
export const VISION_API_URL = import.meta.env.VITE_VISION_API || '/ai/vision/detect'

/**
 * 接收风险检测结果
 * -------------------------------------------------------
 * 入参 payload:
 * {
 *   cameraId: string,          // 摄像头ID
 *   frameId?: string,          // 帧ID / 时间戳
 *   imageBase64?: string,      // 可选：推送单帧图片
 *   // 若由后端推送结果，前端也可直接传入 detections
 *   detections?: Array<{
 *     className: string,       // 类别：road_debris / water_accumulation ...
 *     confidence: number,      // 0~1
 *     bbox: { x, y, w, h }     // 像素或归一化坐标，需与后端约定
 *   }>
 * }
 *
 * 出参 data:
 * {
 *   cameraId: string,
 *   risks: Array<{
 *     type: string,
 *     label: string,
 *     confidence: number,
 *     level: 'red'|'orange'|'yellow',
 *     mask: { x, y, w, h }     // 统一为画面百分比 0-100
 *   }>
 * }
 */
export async function receiveRiskDetection(payload) {
  if (USE_MOCK) {
    // Mock：模拟视觉模型返回
    return mockDelay({
      cameraId: payload.cameraId,
      risks: payload.detections
        ? payload.detections.map((d) => normalizeDetection(d))
        : [],
      source: 'vision-model-mock',
    })
  }
  // 真实对接：调用视觉大模型或后端代理接口
  return request.post(VISION_API_URL, payload)
}

/** 将原始检测框规范化为前端掩码格式（百分比） */
function normalizeDetection(d) {
  const levelMap = {
    road_debris: 'red',
    water_accumulation: 'orange',
    road_obstruction: 'orange',
    fire: 'red',
  }
  const labelMap = {
    road_debris: '路面散落物',
    water_accumulation: '路面积水',
    road_obstruction: '道路阻塞',
    fire: '车辆或路侧火情',
  }
  return {
    type: d.className,
    label: labelMap[d.className] || d.className,
    confidence: d.confidence,
    level: levelMap[d.className] || 'yellow',
    // 若后端给归一化 0-1，乘以 100；若已是百分比则原样
    mask: {
      x: d.bbox.x <= 1 ? d.bbox.x * 100 : d.bbox.x,
      y: d.bbox.y <= 1 ? d.bbox.y * 100 : d.bbox.y,
      w: d.bbox.w <= 1 ? d.bbox.w * 100 : d.bbox.w,
      h: d.bbox.h <= 1 ? d.bbox.h * 100 : d.bbox.h,
    },
  }
}
