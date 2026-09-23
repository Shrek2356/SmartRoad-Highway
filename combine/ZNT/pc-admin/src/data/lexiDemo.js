/** Isolated presentation fixture. Never persist these records as detection jobs or work orders. */
export const corridor = Object.freeze({
  id: 'DEMO-LEXI', name: '乐西高速', section: '马边—雷波—美姑—昭觉',
  mode: 'demo', caption: '山区桥隧路段示意 · 非测绘模型',
  reference: 'https://lxgs.scgs.com.cn/2131/2/',
  referenceTitle: '四川乐西高速公路有限责任公司 · 项目信息',
  notice: '路线、地形、桩号、设备和路况均为演示构造，未接入现场数据。',
})

// Local scene coordinates, not longitude / latitude or engineering chainage.
export const routeNodes = [
  [-138, 6, 20], [-112, 9, -4], [-82, 13, -18], [-49, 18, 4],
  [-18, 22, 21], [15, 19, 8], [44, 15, -17], [73, 12, -8],
  [107, 8, 23], [140, 6, 12],
]
export const landmarks = [
  { name: '马边', t: 0.03 }, { name: '雷波', t: 0.33 },
  { name: '美姑', t: 0.66 }, { name: '昭觉', t: 0.97 },
]
export const structures = [
  { id: 'bridge', label: '山谷桥梁 · 示意', start: 0.34, end: 0.47 },
  { id: 'tunnel', label: '山岭隧道 · 示意', start: 0.61, end: 0.70 },
]
export const devices = [
  { id: 'DEMO-CAM-01', short: 'C01', name: '马边入口摄像机', type: '视频感知', t: 0.06, state: 'online', chainage: 'K008+200', detail: '双向车流与入口路面观察', spec: '400 万像素 / 25 fps', metric: '模拟延迟 86 ms' },
  { id: 'DEMO-CAM-02', short: 'C02', name: '弯道路段摄像机', type: '视频感知', t: 0.22, state: 'online', chainage: 'K032+600', detail: '弯道抛洒物与占道观察', spec: '400 万像素 / 25 fps', metric: '模拟延迟 102 ms' },
  { id: 'DEMO-WX-01', short: 'W01', name: '桥面气象监测站', type: '气象感知', t: 0.39, state: 'online', chainage: 'K058+400', detail: '温度、能见度和降水观察', spec: '多要素气象站', metric: '模拟气温 16°C / 小雨' },
  { id: 'DEMO-CAM-03', short: 'C03', name: '桥尾低洼段摄像机', type: '视频感知', t: 0.49, state: 'online', chainage: 'K073+100', detail: '低洼路段积水与行车道观察', spec: '800 万像素 / 25 fps', metric: '模拟延迟 94 ms' },
  { id: 'DEMO-RAD-01', short: 'R01', name: '隧道入口雷达', type: '交通感知', t: 0.59, state: 'offline', chainage: 'K088+500', detail: '车辆流量与速度观察', spec: '毫米波交通雷达', metric: '模拟离线 / 等待维护' },
  { id: 'DEMO-CAM-04', short: 'C04', name: '隧道出口摄像机', type: '视频感知', t: 0.72, state: 'online', chainage: 'K108+200', detail: '洞口落石与路障观察', spec: '400 万像素 / 25 fps', metric: '模拟延迟 112 ms' },
  { id: 'DEMO-SIGN-01', short: 'V01', name: '可变信息标志', type: '诱导发布', t: 0.81, state: 'maintenance', chainage: 'K122+600', detail: '交通提示显示设备', spec: '双行 LED 情报板', metric: '模拟检修 / 不发送指令' },
  { id: 'DEMO-CAM-05', short: 'C05', name: '昭觉出口摄像机', type: '视频感知', t: 0.93, state: 'online', chainage: 'K141+300', detail: '出口路况与标志观察', spec: '400 万像素 / 25 fps', metric: '模拟延迟 79 ms' },
]

export const reports = [
  { id: 'DEMO-E01', short: '01', title: '低洼路段积水淹没车道', severity: 'critical', t: 0.50, deviceId: 'DEMO-CAM-03', chainage: 'K074+000', time: '14:32', category: '路面积水',
    observation: '演示场景中连续水面覆盖右侧行车道，车道线局部被遮没，符合积水侵占车道的展示情形。',
    impact: '示例影响：右侧行车道通行受限；水深和通行能力未经现场核实。',
    action: '示例处置：人工核查积水范围，检查排水设施，按现场情况组织警示与交通引导。',
    boundary: '单纯下雨、湿润和反光不构成此类异常。', status: '待复核' },
  { id: 'DEMO-E02', short: '02', title: '隧道出口落石侵入车道', severity: 'critical', t: 0.735, deviceId: 'DEMO-CAM-04', chainage: 'K111+200', time: '14:26', category: '落石障碍',
    observation: '演示场景中数块落石由边坡延伸至右侧行车道，形成局部通行障碍。',
    impact: '示例影响：车辆可能避让；无法仅凭图像确认边坡后续稳定性。',
    action: '示例处置：核查现场，设置警示，组织清障并复查边坡。', boundary: '边坡岩石须与侵入道路的落石区分。', status: '待复核' },
  { id: 'DEMO-E03', short: '03', title: '弯道散落物占用车道', severity: 'warning', t: 0.235, deviceId: 'DEMO-CAM-02', chainage: 'K035+600', time: '14:18', category: '散落杂物',
    observation: '演示场景中散落物横跨车道局部区域；材质未作确定判断。',
    impact: '示例影响：弯道发现距离受限，需核实障碍尺寸和位置。',
    action: '示例处置：值班员复核画面，通知巡查清理，复查道路恢复情况。', boundary: '使用多个区域表示离散杂物，避免将整片路面当作掩码。', status: '待复核' },
  { id: 'DEMO-E04', short: '04', title: '出口交通标志疑似倾斜', severity: 'warning', t: 0.91, deviceId: 'DEMO-CAM-05', chainage: 'K138+800', time: '14:09', category: '设施异常',
    observation: '演示场景中路侧标志支撑结构倾斜，需结合其他视角核实。',
    impact: '示例影响：可能影响标志辨识；未认定倒伏或阻断。',
    action: '示例处置：核查标志安装状态和可读性，确认后安排维护。', boundary: '存在路牌属于正常设施，不能仅因检测到路牌就报警。', status: '待复核' },
]
export const normalSection = { t: 0.13, name: '湿润路面 · 正常示例', description: '路面湿润、车道线清晰，无可见积水侵占或障碍，不计入异常。' }
export const severityLabels = { critical: '严重', warning: '关注' }
export const deviceStateLabels = { online: '在线', offline: '离线', maintenance: '检修' }

export function demoSummary(deviceList = devices, reportList = reports) {
  return { devices: deviceList.length, online: deviceList.filter(d => d.state === 'online').length,
    critical: reportList.filter(r => r.severity === 'critical').length, reports: reportList.length }
}
export function selectReports(severity = 'all') {
  return reports.filter(r => severity === 'all' || r.severity === severity)
}
export function demoReportMarkdown(report) {
  const device = devices.find(d => d.id === report.deviceId)
  return `# 演示路况报告｜${report.title}\n\n> 虚构演示数据，不是实际检测结果，不用于现场处置。\n\n` +
    `- 报告编号：${report.id}\n- 路线：${corridor.name}（${corridor.section}）\n- 示意桩号：${report.chainage}\n` +
    `- 模拟时刻：${report.time}\n- 示例等级：${severityLabels[report.severity]}\n- 关联演示设备：${device?.name || '无'}\n- 状态：${report.status}（演示）\n\n` +
    `## 示例观察\n\n${report.observation}\n\n## 示例影响\n\n${report.impact}\n\n## 示例建议\n\n${report.action}\n\n` +
    `## 判定边界\n\n${report.boundary}\n\n无现场原图、掩码或模型推理记录。此报告不进入历史检测档案、学习库或业务工单。\n`
}
