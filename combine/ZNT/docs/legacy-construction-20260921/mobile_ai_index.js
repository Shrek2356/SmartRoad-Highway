/**
 * 移动端 AI 对接预留
 * -------------------------------------------------------
 * 与 PC 端 ai/ 目录对应，便于统一后端智能体
 *
 * 1. 视觉大模型：上报图片辅助识别
 * 2. 推理智能体：风险定级与条文匹配
 * 3. 处置智能体：自动生成/关联工单
 * -------------------------------------------------------
 */

const USE_MOCK_AI = true

/**
 * 【视觉大模型对接位】识别上报图片中的隐患
 * 入参：{ imagePath: string }
 * 出参：{ type, label, confidence, level }
 */
export function visionDetectFromImage(payload) {
  if (USE_MOCK_AI) {
    return Promise.resolve({
      code: 0,
      data: {
        type: 'helmet_missing',
        label: '未戴安全帽',
        confidence: 0.88,
        level: 'red',
        source: 'vision-model-mock',
      },
    })
  }
  // return uni.request({ url: 'https://ai-host/vision', ... })
  return Promise.resolve({ code: -1, message: '未配置视觉服务' })
}

/**
 * 【推理智能体对接位】
 */
export function reasonAnalyze(payload) {
  if (USE_MOCK_AI) {
    return Promise.resolve({
      code: 0,
      data: {
        level: payload.level || 'orange',
        suggestion: '请立即现场核查并督促整改',
        regulation: '相关安全规范条文（Mock）',
        source: 'reason-agent-mock',
      },
    })
  }
  return Promise.resolve({ code: -1 })
}

/**
 * 【处置智能体对接位】人工上报后自动建单
 */
export function actionCreateOrder(payload) {
  if (USE_MOCK_AI) {
    return Promise.resolve({
      code: 0,
      data: {
        workOrderId: 'WO-MOB-' + Date.now(),
        status: 'created',
        source: 'action-agent-mock',
        ...payload,
      },
    })
  }
  return Promise.resolve({ code: -1 })
}
