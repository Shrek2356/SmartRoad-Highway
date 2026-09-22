/**
 * 智能复盘分析接口
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'
import { analysisTrend, areaHeat, teamViolation } from '@/mock'
import dayjs from 'dayjs'

import { presentationEnabled } from '@/utils/preferences'

function pad(n) {
  return String(n).padStart(2, '0')
}

/** 按日期区间生成可查询的复盘数据（Mock） */
function buildAnalysisByRange(startDate, endDate) {
  const end = endDate ? dayjs(endDate) : dayjs()
  const start = startDate ? dayjs(startDate) : end.subtract(6, 'day')
  const days = Math.max(1, end.diff(start, 'day') + 1)
  const dayCount = Math.min(days, 31)

  const dates = []
  const red = []
  const orange = []
  const yellow = []
  for (let i = 0; i < dayCount; i++) {
    const d = start.add(i, 'day')
    dates.push(`${pad(d.month() + 1)}-${pad(d.date())}`)
    // 用日期种子做稳定伪随机，保证同一区间结果可复现
    const seed = d.year() * 10000 + (d.month() + 1) * 100 + d.date()
    red.push(1 + (seed % 5))
    orange.push(2 + ((seed * 3) % 7))
    yellow.push(4 + ((seed * 7) % 9))
  }

  const heatScale = 0.7 + (dayCount / 31) * 0.6
  const heat = areaHeat.map((item, idx) => ({
    name: item.name,
    value: Math.max(1, Math.round(item.value * heatScale * (0.85 + ((idx + dayCount) % 5) * 0.06))),
  }))

  const team = teamViolation.map((item, idx) => ({
    name: item.name,
    count: Math.max(1, Math.round(item.count * heatScale * (0.8 + ((idx + dayCount) % 4) * 0.08))),
  }))

  return {
    trend: { dates, red, orange, yellow },
    areaHeat: heat,
    teamViolation: team,
    range: {
      start: start.format('YYYY-MM-DD'),
      end: end.format('YYYY-MM-DD'),
      days: dayCount,
    },
  }
}

/**
 * 获取复盘统计数据
 * @param {{ startDate?: string, endDate?: string, projectId?: string }} params
 */
export function fetchAnalysisData(params = {}) {
  if (USE_MOCK) {
    const data = buildAnalysisByRange(params.startDate, params.endDate)
    // 无日期时回落默认近7天样例，便于首屏
    if (!params.startDate && !params.endDate) {
      return mockDelay({
        trend: analysisTrend,
        areaHeat,
        teamViolation,
        range: {
          start: dayjs().subtract(6, 'day').format('YYYY-MM-DD'),
          end: dayjs().format('YYYY-MM-DD'),
          days: 7,
        },
      })
    }
    return mockDelay(data)
  }
  return request.get('/analysis/overview', { params }).then((response) => {
    const real = response.data || {}
    const total = [
      ...(real.trend?.red || []),
      ...(real.trend?.orange || []),
      ...(real.trend?.yellow || []),
      ...(real.areaHeat || []).map((item) => item.value),
      ...(real.teamViolation || []).map((item) => item.count),
    ].reduce((sum, value) => sum + (Number(value) || 0), 0)
    if (total > 0 || !presentationEnabled()) {
      return { ...response, data: { ...real, presentationAsset: false } }
    }
    const presentation = buildAnalysisByRange(params.startDate, params.endDate)
    return {
      ...response,
      data: {
        ...presentation,
        presentationAsset: true,
        realDataEmpty: true,
        realRange: real.range || null,
        sourceNote: '所选区间暂无真实检测事件，当前图表使用固定规则生成的演示复盘数据，不写入业务统计。',
      },
    }
  })
}

/**
 * 导出复盘报告元数据（实际 PDF 由页面截图生成）
 */
export function exportAnalysisReport(data = {}) {
  if (USE_MOCK) {
    return mockDelay({
      success: true,
      message: '报告数据已就绪',
      ...data,
    })
  }
  return request.post('/analysis/export', data)
}

export { buildAnalysisByRange }
