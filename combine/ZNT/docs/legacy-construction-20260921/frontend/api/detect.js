/**
 * 实时检测接口（对接 detectmodel/Site_Safety_OpenRisk detect_bridge.py）
 * -------------------------------------------------------
 * 【后续修改入口】
 * - 开发环境经 Vite 代理：/detect-api → http://127.0.0.1:8810
 * - 生产可设 VITE_DETECT_API
 * - 桥接未启动时，前端页面可降级使用本地 Mock 演示
 * -------------------------------------------------------
 */
import axios from 'axios'
import { mockDelay } from '@/utils/request'
import { getDetectApiBase, resolveDetectMediaUrl } from '@/utils/endpoints'

export async function fetchTaskPage(params = {}) {
  const { data } = await detectHttp.get('/api/detect/recent', { params, timeout: 10000 })
  if (!Array.isArray(data?.items)) throw new Error('任务接口返回格式错误')
  return data.items
}
export async function cancelDetectJob(id) {
  return (await detectHttp.post(`/api/detect/jobs/${encodeURIComponent(id)}/cancel`)).data
}
export async function retryDetectJob(id) {
  return (await detectHttp.post(`/api/detect/jobs/${encodeURIComponent(id)}/retry`)).data
}

/** 检测桥接根地址 */
const detectHttp = axios.create({
  timeout: 120000,
})

detectHttp.interceptors.request.use((config) => {
  config.baseURL = getDetectApiBase()
  return config
})

/**
 * 健康检查
 * 出参：{ ok, service, default_profile, profiles[], config, code_root }
 */
export async function checkDetectHealth() {
  try {
    const { data } = await detectHttp.get('/api/detect/health', { timeout: 5000 })
    if (data?.ok !== true || data?.service !== 'site-OpenRisk-detect-bridge') throw new Error('服务地址未返回有效的检测桥信息')
    return { ...data, online: true }
  } catch {
    return { online: false, ok: false, profiles: [], default_profile: 'demo' }
  }
}

/** 读取检测桥运行时模型路径及 CLIP 可选开关（不会返回任何 API Key）。 */
export async function fetchRuntimeSettings() {
  const { data } = await detectHttp.get('/api/detect/runtime-settings')
  return data
}

export async function fetchDeploymentGuide() {
  return (await detectHttp.get('/api/detect/deployment', { timeout: 10000 })).data
}

export async function checkDeploymentEnvironment(mode) {
  return (await detectHttp.post('/api/detect/deployment/check', null, { params: { mode }, timeout: 100000 })).data
}

/** 让后端在已知便携目录和本机模型目录中查找模型部件。 */
export async function discoverRuntimeSettings(settings = {}) {
  const { data } = await detectHttp.post('/api/detect/runtime-settings/discover', { settings })
  return data
}

/** 保存到后端 runtime JSON；只影响之后新建的检测任务。 */
export async function saveRuntimeSettings(settings) {
  const { data } = await detectHttp.put('/api/detect/runtime-settings', { settings })
  return data
}

/** 将当前配置保存为后续首次运行/恢复时使用的初始化预设。 */
export async function saveInitialRuntimeSettings(settings) {
  const { data } = await detectHttp.put('/api/detect/runtime-settings/initial', { settings })
  return data
}

/** 使用已保存的初始化预设覆盖当前运行时配置。 */
export async function resetRuntimeSettingsToInitial() {
  const { data } = await detectHttp.post('/api/detect/runtime-settings/reset-initial')
  return data
}

/** 请求本地桥打开 Windows 文件/目录选择窗口。取消时 path 为空。 */
export async function pickRuntimePath(field, current = '') {
  const { data } = await detectHttp.post(
    '/api/detect/runtime-settings/pick-path',
    { field, current },
    { timeout: 310000 },
  )
  return data
}

export async function fetchQwenServiceStatus() {
  const { data } = await detectHttp.get('/api/detect/qwen-service')
  return data
}

export async function startQwenService() {
  const { data } = await detectHttp.post('/api/detect/qwen-service/start')
  return data
}

export async function stopQwenService() {
  const { data } = await detectHttp.post('/api/detect/qwen-service/stop')
  return data
}

export async function fetchKnowledgeBase() {
  const { data } = await detectHttp.get('/api/detect/knowledge')
  return data
}

export async function uploadKnowledgeDocument(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await detectHttp.post('/api/detect/knowledge/upload', form, { timeout: 120000 })
  return data
}

export async function deleteKnowledgeDocument(filename) {
  const { data } = await detectHttp.delete(`/api/detect/knowledge/${encodeURIComponent(filename)}`)
  return data
}

export async function searchKnowledgeBase(query) {
  const { data } = await detectHttp.get('/api/detect/knowledge/search', { params: { q: query } })
  return data
}

/**
 * 写入云端检测 API Key（写入进程环境变量，并可持久化到桥接目录 .env）
 * 入参：{ apiKey, persist? }
 */
export async function saveDetectCloudKey({ apiKey, persist = true } = {}) {
  const { data } = await detectHttp.post('/api/detect/cloud-key', {
    api_key: apiKey,
    persist,
  })
  return data
}

/**
 * 上传线下图片发起检测
 * 入参：File, { deviceId?, siteId?, dataMode?, profile? }
 * 出参：{ job_id, status, profile }
 */
export async function uploadDetectImage(file, options = {}) {
  const form = new FormData()
  form.append('file', file)
  form.append('device_id', options.deviceId || 'OFFLINE-UPLOAD')
  form.append('site_id', options.siteId || 'SITE-DEFAULT')
  form.append('data_mode', options.dataMode || 'offline')
  if (options.profile) form.append('profile', options.profile)
  if (options.screening) form.append('screening_json', JSON.stringify(options.screening))
  form.append('force_inspection', String(options.forceInspection ?? true))
  const { data } = await detectHttp.post('/api/detect/upload', form)
  return data
}

/**
 * 摄像头截帧检测
 * 入参：{ imageBase64, deviceId?, streamRef?, siteId?, profile? }
 */
export async function detectCameraFrame(payload) {
  const { data } = await detectHttp.post('/api/detect/camera-frame', {
    image_base64: payload.imageBase64,
    device_id: payload.deviceId || 'CAM-WEB-01',
    stream_ref: payload.streamRef || '',
    site_id: payload.siteId || 'SITE-DEFAULT',
    profile: payload.profile || '',
    screening: payload.screening || null,
    force_inspection: payload.forceInspection ?? false,
    force_full_audit: payload.forceFullAudit ?? false,
    audit_interval_minutes: payload.auditIntervalMinutes ?? 30,
  })
  return data
}

/** 调度器/人工立即执行一次绕过YOLO提示的完整图像审计。 */
export async function detectFullAudit(payload) {
  const { data } = await detectHttp.post('/api/detect/full-audit', {
    image_base64: payload.imageBase64,
    device_id: payload.deviceId || 'CAM-WEB-01',
    stream_ref: payload.streamRef || '',
    site_id: payload.siteId || 'SITE-DEFAULT',
    profile: payload.profile || '',
    audit_interval_minutes: payload.auditIntervalMinutes ?? 30,
  })
  return data
}

/**
 * 查询任务（含各阶段状态与结果）
 * 出参：{ job_id, status, stages[], result, event, error }
 */
export async function fetchDetectJob(jobId) {
  const { data } = await detectHttp.get(`/api/detect/jobs/${jobId}`)
  // 媒体路径转成可访问的绝对代理路径
  if (data?.result) {
    data.result = rewriteMediaUrls(data.result)
  }
  return data
}

export async function fetchRecentJobs(limit = 10) {
  try {
    const { data } = await detectHttp.get('/api/detect/recent', { params: { limit } })
    return data.items || []
  } catch {
    return []
  }
}

function rewriteMediaUrls(result) {
  const fix = (url) => {
    return resolveDetectMediaUrl(url)
  }
  return {
    ...result,
    input_image: fix(result.input_image),
    overlays: (result.overlays || []).map(fix),
    masks: (result.masks || []).map(fix),
    crops: (result.crops || []).map(fix),
    screening_overlay: fix(result.screening_overlay),
    screening_mask: fix(result.screening_mask),
    risks: (result.risks || []).map((r) => ({
      ...r,
      overlay: fix(r.overlay),
      mask: fix(r.mask),
    })),
  }
}

/**
 * 本地 Mock 检测（桥接离线时的演示降级）
 * 模拟各阶段协同；若传入 exampleId / previewUrl，结论与测试图对应
 */
export async function mockDetectPipeline({
  source = 'upload',
  fileName = 'demo.jpg',
  exampleId = null,
  previewUrl = '',
} = {}) {
  const stages = [
    { id: 'ingest', name: '接收图像', agent: '接入层' },
    { id: 'screen', name: '实时视觉注意力初筛', agent: 'YOLO轻量模型' },
    { id: 'first_pass', name: '视觉初检·候选发现', agent: '视觉大模型' },
    { id: 'segment', name: '实体定位与风险掩码', agent: 'SAM3/分割' },
    { id: 'verify', name: '证据核验与门控', agent: '空间关系/规则门控' },
    { id: 'second_pass', name: '二次视觉确认', agent: '视觉大模型' },
    { id: 'reason', name: '风险推理与规范映射', agent: '推理智能体' },
    { id: 'report', name: '生成处置建议', agent: '处置/报告' },
  ].map((s) => ({ ...s, status: 'pending', message: '' }))

  const jobId = 'MOCK-' + Date.now()
  const job = {
    job_id: jobId,
    status: 'running',
    source,
    fileName,
    exampleId,
    previewUrl,
    stages,
    result: null,
    error: null,
    mock: true,
  }

  return mockDelay(job, 50)
}

/** Mock 推进一个阶段（页面轮询时调用） */
export function advanceMockJob(job) {
  const next = JSON.parse(JSON.stringify(job))
  const pending = next.stages.find((s) => s.status === 'pending')
  const running = next.stages.find((s) => s.status === 'running')
  if (running) {
    running.status = 'done'
    running.message = '完成'
  } else if (pending) {
    pending.status = 'running'
    pending.message = '处理中…'
  } else if (next.status !== 'done') {
    next.status = 'done'
    next.result = buildMockResult(next)
    next.event = {
      event_id: next.job_id,
      data_mode: sourceMode(next),
      overall_has_anomaly: next.result.overall_has_anomaly,
      scene_summary: next.result.report_summary,
      risks: next.result.risks,
    }
  }
  return next
}

function buildMockResult(job) {
  const ex = getExampleMeta(job.exampleId)
  const input = job.previewUrl || ex?.src || '/outcomes/case3_overlay.png'
  const overlay = ex?.outcome || '/outcomes/case3_overlay.png'
  const name = ex?.resultName || '临边防护缺失'
  const conf = ex?.confidence ?? 0.88
  const level = ex?.level || 'major'
  const levelZh = ex?.level_zh || '较大风险'
  const review = !!ex?.manual_review || conf < 0.7
  return {
    overall_has_anomaly: true,
    risk_count: 1,
    report_summary: `（演示）${ex?.title || name}：${ex?.risk || '现场异常'}。证据核验后给出处置建议，请结合现场复核。`,
    input_image: input,
    overlays: [overlay],
    masks: [],
    crops: [],
    risks: [
      {
        name,
        verified: !review || conf >= 0.85,
        confidence: conf,
        level,
        level_zh: levelZh,
        manual_review: review,
        description: ex?.risk || name,
        suggestions: ['立即现场处置', '安全员复核确认', '整改完成后关闭工单'],
        overlay,
      },
    ],
    artifacts: {
      first_pass: true,
      evidence: true,
      visual_verification: true,
      final_report: true,
      result: true,
    },
  }
}

function getExampleMeta(id) {
  if (!id) return null
  // 轻量内联，避免 mock 循环依赖；与 mock/examples.js 保持一致
  const map = {
    1: {
      src: '/examples/case1.png',
      title: '高处作业未佩戴安全带',
      risk: '坠落风险',
      outcome: '/outcomes/case1_overlay.png',
      resultName: '高处作业未佩戴安全带/安全绳',
      level: 'critical',
      level_zh: '重大风险',
      confidence: 0.9,
    },
    2: {
      src: '/examples/case2.png',
      title: '吊装作业下方有人',
      risk: '起重伤害风险',
      outcome: '/outcomes/case2_overlay.png',
      resultName: '人员位于悬吊物下方',
      level: 'critical',
      level_zh: '重大风险',
      confidence: 0.92,
    },
    3: {
      src: '/examples/case3.png',
      title: '临边洞口未防护',
      risk: '坠落风险',
      outcome: '/outcomes/case3_overlay.png',
      resultName: '临边防护缺失',
      level: 'major',
      level_zh: '较大风险',
      confidence: 0.88,
    },
    4: {
      src: '/examples/case4.png',
      title: '电气线路裸露违规用电',
      risk: '触电风险',
      outcome: '/outcomes/case4_overlay.png',
      resultName: '电缆浸水/违规用电',
      level: 'critical',
      level_zh: '重大风险',
      confidence: 0.85,
    },
    5: {
      src: '/examples/case5.png',
      title: '材料堆放违规·通道堵塞',
      risk: '管理风险',
      outcome: '/outcomes/case5_overlay.png',
      resultName: '通道被材料堵塞',
      level: 'general',
      level_zh: '一般风险',
      confidence: 0.8,
    },
    6: {
      src: '/examples/case6.png',
      title: '脚手架安全隐患',
      risk: '坍塌跌落风险',
      outcome: '/results/case6_original.jpg',
      resultName: '脚手架安全隐患（实体定位不足，建议复核）',
      level: 'major',
      level_zh: '较大风险',
      confidence: 0.55,
      manual_review: true,
    },
    7: {
      src: '/examples/case7.png',
      title: '未佩戴安全帽',
      risk: '个人防护缺失',
      outcome: '/outcomes/case7_overlay.png',
      resultName: '施工人员未佩戴安全帽',
      level: 'major',
      level_zh: '较大风险',
      confidence: 0.98,
    },
    8: {
      src: '/examples/case8.png',
      title: '工人独自昏倒',
      risk: '紧急安全事故',
      outcome: '/outcomes/case8_overlay.png',
      resultName: '人员异常倒地',
      level: 'critical',
      level_zh: '重大风险',
      confidence: 0.95,
    },
  }
  return map[Number(id)] || null
}

function sourceMode(job) {
  return job.source === 'camera' ? 'realtime' : 'offline'
}
