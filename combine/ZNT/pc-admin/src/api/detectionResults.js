/**
 * 检测结果汇总接口
 * 出参：{ summary, cases, origin }
 * 合并：现场样例 Mock + 实时检测写入的本地结果
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'
import { detectionSummary, detectionCases, resultOrigin } from '@/mock/detectionResults'
import { loadDetectResultCases } from '@/utils/detectResults'
import { resolveBusinessMediaUrl } from '@/utils/endpoints'

import { presentationEnabled } from '@/utils/preferences'

function presentationCases() {
  if (!presentationEnabled()) return []
  return detectionCases.map((item) => ({
    ...item,
    id: `example-${item.id}`,
    exampleId: item.id,
    live: false,
    presentationAsset: true,
    sourceType: 'presentation',
  }))
}

function resolveCaseMedia(item) {
  return {
    ...item,
    cover: resolveBusinessMediaUrl(item.cover),
    images: item.images ? Object.fromEntries(
      Object.entries(item.images).map(([key, value]) => [key, resolveBusinessMediaUrl(value)]),
    ) : item.images,
  }
}

function buildSummary(cases) {
  const realCases = cases.filter((c) => !c.presentationAsset)
  const presentationCount = cases.length - realCases.length
  const demoRunCount = cases.filter((c) => c.sourceType === 'demo-run').length
  const presetCount = cases.filter((c) => c.sourceType === 'presentation').length
  const pendingSyncCount = realCases.filter((c) => c.sourceType === 'pending-sync').length
  const persistedCount = realCases.length - pendingSyncCount
  const autoConfirmed = realCases.filter((c) => c.autoConfirm).length
  const humanReview = realCases.filter((c) => c.humanReview).length
  const highConfidenceNoReview = realCases.filter((c) => c.confidence >= 0.9 && !c.humanReview).length
  const liveCount = realCases.filter((c) => c.live).length
  return {
    total: cases.length,
    realCount: realCases.length,
    presentationCount,
    autoConfirmed,
    humanReview,
    highConfidenceNoReview,
    liveCount,
    demoRunCount,
    presetCount,
    pendingSyncCount,
    persistedCount,
    conclusion:
      `当前展示 ${persistedCount} 条真实持久化风险记录` +
      `${pendingSyncCount ? `，${pendingSyncCount} 条真实检测待后台同步` : ''}` +
      `${liveCount ? `（其中 ${liveCount} 条实时检测）` : ''}` +
      `${demoRunCount ? `，${demoRunCount} 条本次浏览器演示结果` : ''}` +
      `${presetCount ? `，并保留 ${presetCount} 张预设关键案例` : ''}。` +
      '各类数据已明确标注，不会互相冒充。',
  }
}

export function fetchDetectionResults(params = {}) {
  if (USE_MOCK) {
    const live = loadDetectResultCases()
    const seed = presentationCases()
    // 实时结果在前；若带 job 则优先置顶匹配项
    let cases = [...live, ...seed].filter(c => presentationEnabled() || !(c.presentationAsset || c.profile === 'demo' || String(c.detectJobId || '').startsWith('MOCK-')))
    const jobId = params.job || params.job_id
    if (jobId) {
      const hit = cases.find((c) => c.detectJobId === jobId || c.id === `live-${jobId}`)
      if (hit) {
        cases = [hit, ...cases.filter((c) => c !== hit)]
      }
    }
    if (params.case) {
      const id = String(params.case)
      const hit = cases.find((c) => String(c.id) === id || String(c.exampleId) === id)
      if (hit) cases = [hit, ...cases.filter((c) => c !== hit)]
    }
    return mockDelay({
      summary: buildSummary(cases),
      cases,
      origin: resultOrigin,
      batchId: params.batchId || (live[0]?.detectJobId ? `live-${live[0].detectJobId}` : 'example-batch-001'),
    })
  }
  return request.get('/detection/final-summary', { params }).then((res) => {
    const real = (res.data.cases || []).map((item) => ({
      ...resolveCaseMedia(item),
      presentationAsset: false,
      sourceType: item.live ? 'live' : 'persisted',
    }))
    const persistedJobs = new Set(real.map((item) => item.detectJobId).filter(Boolean))
    const local = loadDetectResultCases()
      .filter((item) => item.presentationAsset || item.profile === 'demo' || String(item.detectJobId || '').startsWith('MOCK-') || !persistedJobs.has(item.detectJobId))
      .map((item) => {
        const isDemo = Boolean(item.presentationAsset || item.profile === 'demo' || String(item.detectJobId || '').startsWith('MOCK-'))
        return {
          ...item,
          presentationAsset: isDemo,
          sourceType: isDemo ? 'demo-run' : 'pending-sync',
        }
      })
    let cases = [...local, ...real, ...presentationCases()].filter(c => presentationEnabled() || !c.presentationAsset)
    const jobId = params.job || params.job_id
    if (jobId) {
      const hit = cases.find((item) => item.detectJobId === jobId || item.id === `live-${jobId}`)
      if (hit) cases = [hit, ...cases.filter((item) => item !== hit)]
    }
    if (params.case) {
      const id = String(params.case)
      const hit = cases.find((item) => String(item.id) === id || String(item.exampleId) === id)
      if (hit) cases = [hit, ...cases.filter((item) => item !== hit)]
    }
    return {
      ...res,
      data: {
        ...res.data,
        cases,
        summary: buildSummary(cases),
        origin: res.data.origin || resultOrigin,
        presentationAssetsEnabled: presentationEnabled(),
      },
    }
  })
}
