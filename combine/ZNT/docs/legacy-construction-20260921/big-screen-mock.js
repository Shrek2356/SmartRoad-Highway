/**
 * 大屏 Mock 数据
 * 【后续对接】改为 api/screen.js 真实请求
 */

/** 高危告警滚动 */
export const alertScroll = [
  { id: 1, text: '【高危】脚手架C区发现未戴安全帽，已生成工单 WO-20260726001', level: 'red' },
  { id: 2, text: '【高危】塔吊A区吊物下方站人，请立即疏散', level: 'red' },
  { id: 3, text: '【中危】基坑B区临边防护缺失，责令2小时内整改', level: 'orange' },
  { id: 4, text: '【中危】主体结构3层未系安全带，安全员已接单', level: 'orange' },
  { id: 5, text: '【低危】材料堆场侵占通道，已通知班组长清理', level: 'yellow' },
]

/** 今日核心指标 */
export const todayStats = {
  hazardTotal: 28,
  fixedRate: 86.5,
  highRisk: 3,
  pending: 9,
}

/** 违规案例循环（封面用占位色块） */
export const violationCases = [
  { id: 'c1', title: '未戴安全帽', area: '脚手架C区', time: '14:32', level: 'red' },
  { id: 'c2', title: '吊物下方站人', area: '塔吊A区', time: '14:28', level: 'red' },
  { id: 'c3', title: '临边防护缺失', area: '基坑B区', time: '14:15', level: 'orange' },
  { id: 'c4', title: '未系安全带', area: '主体3层', time: '13:40', level: 'orange' },
]

/** 班组整改排名 */
export const teamRank = [
  { name: '钢筋一班', rate: 90, fixed: 18, total: 20 },
  { name: '木工二班', rate: 87.5, fixed: 14, total: 16 },
  { name: '水电四班', rate: 75, fixed: 9, total: 12 },
  { name: '架子三班', rate: 73.3, fixed: 11, total: 15 },
  { name: '土建五班', rate: 70, fixed: 7, total: 10 },
]
