/**
 * 首页数字驾驶舱接口
 * -------------------------------------------------------
 * 【入参/出参】见各函数 JSDoc
 * 【后续对接】将 USE_MOCK 分支改为真实 request 调用即可
 * -------------------------------------------------------
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'
import { getDashboardByProject } from '@/mock'
import { getMergedWorkOrders } from '@/utils/workOrderStore'

// 比赛展示默认保留预编辑视觉资产；换成真实摄像头后，后端返回的非空
// 点位/视频会自动优先。可用 VITE_ENABLE_PRESENTATION_ASSETS=false 关闭。
import { presentationEnabled } from '@/utils/preferences'

function withPresentationAssets(real, projectId) {
  const normalizedReal = { ...real, metrics: normalizeMetrics(real.metrics) }
  if (!presentationEnabled()) return normalizedReal
  const pack = getDashboardByProject(projectId)
  const visual = (items = []) => items.map((item) => ({ ...item, presentationAsset: true }))
  const presentationGroups = []
  const sitePoints = real.sitePoints?.length
    ? real.sitePoints
    : (presentationGroups.push('sitePoints'), visual(pack.sitePoints))
  const highRiskVideos = real.highRiskVideos?.length
    ? real.highRiskVideos
    : (presentationGroups.push('highRiskVideos'), visual(pack.highRiskVideos))
  const hasTrend = real.riskTrendHours?.values?.some((value) => Number(value) > 0)
  const riskTrendHours = hasTrend
    ? real.riskTrendHours
    : (presentationGroups.push('riskTrendHours'), { ...pack.riskTrendHours, presentationAsset: true })
  const hazardTypes = real.hazardTypes?.length > 0
    ? real.hazardTypes
    : (presentationGroups.push('hazardTypes'), visual(pack.hazardTypes))
  const teamRank = real.teamRank?.length > 0
    ? real.teamRank
    : (presentationGroups.push('teamRank'), visual(pack.teamRank))
  const topHazards = real.topHazards?.length > 0
    ? real.topHazards
    : (presentationGroups.push('topHazards'), visual(pack.topHazards))
  return {
    ...normalizedReal,
    sitePoints,
    highRiskVideos,
    riskTrendHours,
    hazardTypes,
    teamRank,
    topHazards,
    presentationAssetsEnabled: presentationGroups.length > 0,
    presentationAssetGroups: presentationGroups,
  }
}

function normalizeMetrics(metrics = []) {
  return metrics.map((metric) => {
    if (metric.key !== 'highRisk') return metric
    return {
      ...metric,
      label: '待处置高危',
      trend: '当前待跟进',
      trendPrefix: '',
    }
  })
}

/**
 * 获取驾驶舱全部数据
 * @param {{ projectId?: string }} params
 * @returns {Promise<{code:number,data:object}>}
 */
export function fetchDashboardData(params = {}) {
  if (USE_MOCK) {
    const projectId = params.projectId || 'proj-001'
    const pack = getDashboardByProject(projectId)
    const orders = getMergedWorkOrders()
    const pending = orders.filter((w) => w.status === 'pending').length
    const highRisk = orders.filter((w) => w.level === 'red' && w.status !== 'done').length
    const metrics = normalizeMetrics(pack.metrics.map((m) => {
      if (m.key === 'pending') return { ...m, value: pending }
      if (m.key === 'highRisk') return { ...m, value: highRisk }
      return { ...m }
    }))
    return mockDelay({
      projectId,
      projectName: pack.shortName,
      projectAddress: pack.address,
      metrics,
      sitePoints: pack.sitePoints.map((item) => ({ ...item, presentationAsset: true })),
      highRiskVideos: pack.highRiskVideos.map((item) => ({ ...item, presentationAsset: true })),
      riskTrendHours: { ...pack.riskTrendHours, presentationAsset: true },
      hazardTypes: pack.hazardTypes.map((item) => ({ ...item, presentationAsset: true })),
      teamRank: pack.teamRank.map((item) => ({ ...item, presentationAsset: true })),
      topHazards: pack.topHazards.map((item) => ({ ...item, presentationAsset: true })),
      presentationAssetsEnabled: true,
      presentationAssetGroups: [
        'sitePoints',
        'highRiskVideos',
        'riskTrendHours',
        'hazardTypes',
        'teamRank',
        'topHazards',
      ],
    })
  }
  return request.get('/dashboard/overview', { params }).then((response) => ({
    ...response,
    data: withPresentationAssets(response.data, params.projectId || 'proj-001'),
  }))
}
