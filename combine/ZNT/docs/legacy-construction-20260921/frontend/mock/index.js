/**
 * Mock 数据总入口
 * -------------------------------------------------------
 * 所有页面模拟数据集中于此，真实对接后可逐步删除本目录
 * 【后续修改入口】对接后端时，api/ 层改为真实请求，本文件可废弃
 * -------------------------------------------------------
 */

/** 当前项目信息 */
export const currentProject = {
  id: 'proj-001',
  name: '智慧城建·滨江一期工地',
  address: '杭州市滨江区江南大道188号',
}

/** 项目列表（多项目切换） */
export const projectList = [
  currentProject,
  { id: 'proj-002', name: '城东轨道枢纽项目', address: '杭州市上城区秋涛路66号' },
  { id: 'proj-003', name: '钱塘新区保障房工程', address: '杭州市钱塘区下沙路99号' },
]

/**
 * 首页顶部指标
 * link: 点击跳转路径（query 用于目标页筛选）
 */
export const dashboardMetrics = [
  {
    key: 'todayRisk',
    label: '今日隐患',
    value: 28,
    unit: '件',
    trend: '+12%',
    type: 'danger',
    link: '/detection-results',
    linkQuery: { filter: 'all' },
    tip: '点击查看检测样例明细',
  },
  {
    key: 'pending',
    label: '待整改工单',
    value: 9,
    unit: '件',
    trend: '-3%',
    type: 'warning',
    link: '/workorder',
    linkQuery: { status: 'pending' },
    tip: '点击查看待整改工单',
  },
  {
    key: 'fixedRate',
    label: '整改完成率',
    value: 86.5,
    unit: '%',
    trend: '+2.1%',
    type: 'success',
    link: '/workorder',
    linkQuery: { status: 'done' },
    tip: '点击查看已完成工单',
  },
  {
    key: 'onlineCam',
    label: '在线摄像头',
    value: 42,
    unit: '路',
    trend: '100%',
    type: 'primary',
    link: '/monitor',
    linkQuery: {},
    tip: '点击进入实时监控',
  },
  {
    key: 'highRisk',
    label: '高危告警',
    value: 3,
    unit: '件',
    trend: '实时',
    type: 'danger',
    link: '/workorder',
    linkQuery: { level: 'red' },
    tip: '点击查看高危工单',
  },
]

/** 工地点位（2D平面图坐标，百分比定位） */
export const sitePoints = [
  { id: 'p1', name: '塔吊A区', x: 22, y: 28, riskLevel: 'red', cameraId: 'cam-01', riskCount: 3 },
  { id: 'p2', name: '基坑B区', x: 48, y: 42, riskLevel: 'orange', cameraId: 'cam-02', riskCount: 2 },
  { id: 'p3', name: '材料堆场', x: 70, y: 35, riskLevel: 'yellow', cameraId: 'cam-03', riskCount: 1 },
  { id: 'p4', name: '脚手架C区', x: 35, y: 65, riskLevel: 'red', cameraId: 'cam-04', riskCount: 4 },
  { id: 'p5', name: '钢筋加工棚', x: 78, y: 68, riskLevel: 'yellow', cameraId: 'cam-05', riskCount: 1 },
  { id: 'p6', name: '出入口岗亭', x: 12, y: 80, riskLevel: 'green', cameraId: 'cam-06', riskCount: 0 },
]

/**
 * 高风险轮播
 * 当前用成果标注图展示；streamUrl 预留真实视频流对接
 * 【后续对接】填入 flv/hls 地址后，前端可优先播流，失败再回退 cover
 */
export const highRiskVideos = [
  {
    id: 'v1',
    title: '未佩戴安全帽',
    cameraName: '现场样例-07',
    riskLevel: 'red',
    cover: '/outcomes/case7_overlay.png',
    streamUrl: '',
    time: '2026-07-26 14:32:10',
    caseId: 7,
  },
  {
    id: 'v2',
    title: '吊物下方站人',
    cameraName: '现场样例-02',
    riskLevel: 'red',
    cover: '/outcomes/case2_overlay.png',
    streamUrl: '',
    time: '2026-07-26 14:28:05',
    caseId: 2,
  },
  {
    id: 'v3',
    title: '临边防护缺失',
    cameraName: '现场样例-03',
    riskLevel: 'orange',
    cover: '/outcomes/case3_overlay.png',
    streamUrl: '',
    time: '2026-07-26 14:15:42',
    caseId: 3,
  },
  {
    id: 'v4',
    title: '电缆浸水违规用电',
    cameraName: '现场样例-04',
    riskLevel: 'red',
    cover: '/outcomes/case4_overlay.png',
    streamUrl: '',
    time: '2026-07-26 13:50:22',
    caseId: 4,
  },
]

/** 风险时段折线 */
export const riskTrendHours = {
  hours: ['08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00'],
  values: [2, 4, 6, 8, 3, 5, 9, 7, 4, 2],
}

/** 隐患类型饼图 */
export const hazardTypes = [
  { name: '未戴安全帽', value: 12 },
  { name: '未系安全带', value: 8 },
  { name: '临边防护', value: 5 },
  { name: '烟火违规', value: 3 },
  { name: '其他', value: 4 },
]

/** 班组整改排行 */
export const teamRank = [
  { name: '钢筋一班', fixed: 18, total: 20, rate: 90 },
  { name: '木工二班', fixed: 14, total: 16, rate: 87.5 },
  { name: '架子三班', fixed: 11, total: 15, rate: 73.3 },
  { name: '水电四班', fixed: 9, total: 12, rate: 75 },
  { name: '土建五班', fixed: 7, total: 10, rate: 70 },
]

/** 高频隐患 TOP5 */
export const topHazards = [
  { name: '未正确佩戴安全帽', count: 12 },
  { name: '高处作业未系安全带', count: 8 },
  { name: '临边洞口防护不到位', count: 5 },
  { name: '施工区域烟火违规', count: 3 },
  { name: '材料堆放侵占通道', count: 2 },
]

/**
 * 按项目区分的驾驶舱数据（切换项目时首页随之变化）
 * 未列出的字段会回落到上方默认导出
 */
function cloneMetrics(overrides) {
  return dashboardMetrics.map((m) => ({ ...m, ...(overrides[m.key] || {}) }))
}

export const dashboardByProject = {
  'proj-001': {
    shortName: '滨江一期',
    address: '杭州市滨江区江南大道188号',
    metrics: dashboardMetrics,
    sitePoints,
    highRiskVideos,
    riskTrendHours,
    hazardTypes,
    teamRank,
    topHazards,
  },
  'proj-002': {
    shortName: '城东枢纽',
    address: '杭州市上城区秋涛路66号',
    metrics: cloneMetrics({
      todayRisk: { value: 41, trend: '+18%' },
      pending: { value: 16, trend: '+5%' },
      fixedRate: { value: 74.8, trend: '-1.2%' },
      onlineCam: { value: 58, trend: '96%' },
      highRisk: { value: 6, trend: '实时' },
    }),
    sitePoints: [
      { id: 'p1', name: '盾构始发井', x: 18, y: 32, riskLevel: 'red', cameraId: 'cam-01', riskCount: 5 },
      { id: 'p2', name: '站厅作业区', x: 42, y: 38, riskLevel: 'orange', cameraId: 'cam-02', riskCount: 3 },
      { id: 'p3', name: '轨行区通道', x: 68, y: 30, riskLevel: 'red', cameraId: 'cam-03', riskCount: 4 },
      { id: 'p4', name: '出土口', x: 55, y: 62, riskLevel: 'orange', cameraId: 'cam-04', riskCount: 2 },
      { id: 'p5', name: '临电配电间', x: 80, y: 70, riskLevel: 'yellow', cameraId: 'cam-05', riskCount: 1 },
      { id: 'p6', name: '材料转运口', x: 14, y: 78, riskLevel: 'yellow', cameraId: 'cam-06', riskCount: 1 },
    ],
    highRiskVideos: [
      { ...highRiskVideos[1], id: 'v1', title: '轨行区闯入', cameraName: '枢纽样例-轨行区', time: '2026-08-04 09:18:22' },
      { ...highRiskVideos[3], id: 'v2', title: '临电乱拉浸水', cameraName: '枢纽样例-配电', time: '2026-08-04 10:05:11' },
      { ...highRiskVideos[2], id: 'v3', title: '洞口防护缺失', cameraName: '枢纽样例-站厅', time: '2026-08-04 11:42:08' },
      { ...highRiskVideos[0], id: 'v4', title: '出土口未戴安全帽', cameraName: '枢纽样例-出土口', time: '2026-08-04 13:26:40' },
    ],
    riskTrendHours: {
      hours: ['08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00'],
      values: [5, 8, 11, 9, 4, 7, 12, 10, 6, 3],
    },
    hazardTypes: [
      { name: '轨行区闯入', value: 14 },
      { name: '临电违规', value: 11 },
      { name: '洞口防护', value: 8 },
      { name: '未戴安全帽', value: 6 },
      { name: '其他', value: 5 },
    ],
    teamRank: [
      { name: '盾构一班', fixed: 22, total: 28, rate: 78.6 },
      { name: '轨通二班', fixed: 15, total: 20, rate: 75 },
      { name: '机电三班', fixed: 12, total: 18, rate: 66.7 },
      { name: '土建四班', fixed: 10, total: 14, rate: 71.4 },
      { name: '吊装五班', fixed: 8, total: 13, rate: 61.5 },
    ],
    topHazards: [
      { name: '轨行区未授权进入', count: 14 },
      { name: '临时用电私拉乱接', count: 11 },
      { name: '竖井洞口防护不到位', count: 8 },
      { name: '出土口未戴安全帽', count: 6 },
      { name: '吊装作业指挥缺失', count: 4 },
    ],
  },
  'proj-003': {
    shortName: '钱塘保障房',
    address: '杭州市钱塘区下沙路99号',
    metrics: cloneMetrics({
      todayRisk: { value: 17, trend: '-8%' },
      pending: { value: 5, trend: '-12%' },
      fixedRate: { value: 92.4, trend: '+3.6%' },
      onlineCam: { value: 31, trend: '100%' },
      highRisk: { value: 1, trend: '实时' },
    }),
    sitePoints: [
      { id: 'p1', name: '1#楼主体', x: 28, y: 30, riskLevel: 'yellow', cameraId: 'cam-01', riskCount: 1 },
      { id: 'p2', name: '2#楼外架', x: 52, y: 26, riskLevel: 'orange', cameraId: 'cam-02', riskCount: 2 },
      { id: 'p3', name: '地下室临边', x: 40, y: 55, riskLevel: 'red', cameraId: 'cam-03', riskCount: 2 },
      { id: 'p4', name: '塔吊覆盖区', x: 72, y: 40, riskLevel: 'yellow', cameraId: 'cam-04', riskCount: 1 },
      { id: 'p5', name: '砌筑材料区', x: 18, y: 68, riskLevel: 'green', cameraId: 'cam-05', riskCount: 0 },
      { id: 'p6', name: '生活区出入口', x: 82, y: 78, riskLevel: 'green', cameraId: 'cam-06', riskCount: 0 },
    ],
    highRiskVideos: [
      { ...highRiskVideos[2], id: 'v1', title: '外架临边防护不足', cameraName: '保障房-2#楼', time: '2026-08-04 08:55:03' },
      { ...highRiskVideos[0], id: 'v2', title: '地下室未戴安全帽', cameraName: '保障房-地下室', time: '2026-08-04 10:20:17' },
      { ...highRiskVideos[1], id: 'v3', title: '塔吊下站人', cameraName: '保障房-塔吊区', time: '2026-08-04 14:08:55' },
      { ...highRiskVideos[3], id: 'v4', title: '临电箱积水', cameraName: '保障房-临电', time: '2026-08-04 15:33:29' },
    ],
    riskTrendHours: {
      hours: ['08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00'],
      values: [1, 2, 3, 4, 2, 2, 5, 3, 2, 1],
    },
    hazardTypes: [
      { name: '外架防护', value: 7 },
      { name: '未戴安全帽', value: 5 },
      { name: '洞口盖板', value: 3 },
      { name: '材料堆放', value: 2 },
      { name: '其他', value: 2 },
    ],
    teamRank: [
      { name: '砌筑一班', fixed: 16, total: 17, rate: 94.1 },
      { name: '粉刷二班', fixed: 13, total: 14, rate: 92.9 },
      { name: '架子三班', fixed: 11, total: 12, rate: 91.7 },
      { name: '水电四班', fixed: 9, total: 10, rate: 90 },
      { name: '土建五班', fixed: 8, total: 9, rate: 88.9 },
    ],
    topHazards: [
      { name: '外架临边防护不到位', count: 7 },
      { name: '地下室未戴安全帽', count: 5 },
      { name: '预留洞口盖板缺失', count: 3 },
      { name: '砌块堆放侵占通道', count: 2 },
      { name: '临电箱周边积水', count: 1 },
    ],
  },
}

/** 按项目 ID 取驾驶舱数据包 */
export function getDashboardByProject(projectId = 'proj-001') {
  return dashboardByProject[projectId] || dashboardByProject['proj-001']
}

/** 设备树（视频监控页） */
export const deviceTree = [
  {
    title: '滨江一期工地',
    key: 'site-1',
    children: [
      {
        title: '塔吊监控',
        key: 'group-1',
        children: [
          { title: 'CAM-01 塔吊A区', key: 'cam-01', isLeaf: true, online: true },
          { title: 'CAM-07 塔吊B区', key: 'cam-07', isLeaf: true, online: true },
        ],
      },
      {
        title: '基坑监控',
        key: 'group-2',
        children: [
          { title: 'CAM-02 基坑B区', key: 'cam-02', isLeaf: true, online: true },
          { title: 'CAM-08 降水井', key: 'cam-08', isLeaf: true, online: false },
        ],
      },
      {
        title: '主体结构',
        key: 'group-3',
        children: [
          { title: 'CAM-03 材料堆场', key: 'cam-03', isLeaf: true, online: true },
          { title: 'CAM-04 脚手架C区', key: 'cam-04', isLeaf: true, online: true },
          { title: 'CAM-05 钢筋加工棚', key: 'cam-05', isLeaf: true, online: true },
          { title: 'CAM-06 出入口岗亭', key: 'cam-06', isLeaf: true, online: true },
        ],
      },
    ],
  },
]

/**
 * 视频通道列表
 * streamUrl 为空时 VideoPlayer 显示占位画面
 * 【后续对接】填入真实 flv/hls 地址即可播放
 */
export const cameraList = [
  {
    id: 'cam-01',
    name: '塔吊A区',
    streamUrl: '',
    online: true,
    masks: [
      { level: 'red', x: 30, y: 20, w: 18, h: 35, label: '吊物下方站人' },
    ],
  },
  {
    id: 'cam-02',
    name: '基坑B区',
    streamUrl: '',
    online: true,
    masks: [
      { level: 'orange', x: 45, y: 40, w: 25, h: 20, label: '临边防护缺失' },
    ],
  },
  {
    id: 'cam-03',
    name: '材料堆场',
    streamUrl: '',
    online: true,
    masks: [
      { level: 'yellow', x: 55, y: 50, w: 20, h: 18, label: '堆放侵占通道' },
    ],
  },
  {
    id: 'cam-04',
    name: '脚手架C区',
    streamUrl: '',
    online: true,
    masks: [
      { level: 'red', x: 40, y: 25, w: 15, h: 30, label: '未戴安全帽' },
      { level: 'orange', x: 60, y: 45, w: 12, h: 25, label: '未系安全带' },
    ],
  },
  { id: 'cam-05', name: '钢筋加工棚', streamUrl: '', online: true, masks: [] },
  { id: 'cam-06', name: '出入口岗亭', streamUrl: '', online: true, masks: [] },
  { id: 'cam-07', name: '塔吊B区', streamUrl: '', online: true, masks: [] },
  { id: 'cam-08', name: '降水井', streamUrl: '', online: false, masks: [] },
  { id: 'cam-09', name: '宿舍区', streamUrl: '', online: true, masks: [] },
]

/** 实时告警列表 */
export const realtimeAlarms = [
  { id: 'a1', level: 'red', title: '未戴安全帽', camera: 'CAM-04', time: '14:32:10', status: 'pending' },
  { id: 'a2', level: 'red', title: '吊物下方站人', camera: 'CAM-01', time: '14:28:05', status: 'pending' },
  { id: 'a3', level: 'orange', title: '临边防护缺失', camera: 'CAM-02', time: '14:15:42', status: 'processing' },
  { id: 'a4', level: 'yellow', title: '材料侵占通道', camera: 'CAM-03', time: '13:58:20', status: 'done' },
  { id: 'a5', level: 'orange', title: '未系安全带', camera: 'CAM-04', time: '13:40:11', status: 'pending' },
]

/** 工单列表 */
export const workOrders = [
  {
    id: 'WO-20260726001',
    title: '脚手架C区未戴安全帽',
    level: 'red',
    type: '未戴安全帽',
    area: '脚手架C区',
    team: '架子三班',
    status: 'pending',
    assignee: '张安全',
    createTime: '2026-07-26 14:32:10',
    deadline: '2026-07-26 16:30:00',
    snapUrl: '',
    maskUrl: '',
    regulation: '《建筑施工安全检查标准》JGJ59-2011 第3.1.3条：进入施工现场的人员必须正确佩戴安全帽。',
    logs: [
      { time: '14:32:10', action: '系统自动生成工单', user: 'AI检测引擎' },
      { time: '14:33:00', action: '已推送至安全员', user: '系统' },
    ],
  },
  {
    id: 'WO-20260726002',
    title: '塔吊A区吊物下方站人',
    level: 'red',
    type: '吊装违规',
    area: '塔吊A区',
    team: '土建五班',
    status: 'processing',
    assignee: '李安全',
    createTime: '2026-07-26 14:28:05',
    deadline: '2026-07-26 15:30:00',
    snapUrl: '',
    maskUrl: '',
    regulation: '《起重机械安全规程》GB6067：吊运重物时，严禁下方站人。',
    logs: [
      { time: '14:28:05', action: '系统自动生成工单', user: 'AI检测引擎' },
      { time: '14:29:00', action: '安全员已接单', user: '李安全' },
      { time: '14:35:00', action: '现场正在疏散人员', user: '李安全' },
    ],
  },
  {
    id: 'WO-20260726003',
    title: '基坑B区临边防护缺失',
    level: 'orange',
    type: '临边防护',
    area: '基坑B区',
    team: '木工二班',
    status: 'pending',
    assignee: '王安全',
    createTime: '2026-07-26 14:15:42',
    deadline: '2026-07-26 18:00:00',
    snapUrl: '',
    maskUrl: '',
    regulation: '《建筑施工高处作业安全技术规范》JGJ80：临边作业应设置防护栏杆。',
    logs: [
      { time: '14:15:42', action: '系统自动生成工单', user: 'AI检测引擎' },
    ],
  },
  {
    id: 'WO-20260725008',
    title: '材料堆场侵占消防通道',
    level: 'yellow',
    type: '材料堆放',
    area: '材料堆场',
    team: '水电四班',
    status: 'done',
    assignee: '张安全',
    createTime: '2026-07-25 16:20:00',
    deadline: '2026-07-26 10:00:00',
    snapUrl: '',
    maskUrl: '',
    regulation: '《施工现场消防安全技术规范》GB50720：消防通道应保持畅通。',
    logs: [
      { time: '16:20:00', action: '系统自动生成工单', user: 'AI检测引擎' },
      { time: '17:00:00', action: '已整改完成', user: '张安全' },
      { time: '17:30:00', action: '总监复核通过', user: '赵总监' },
    ],
  },
  {
    id: 'WO-20260725005',
    title: '高处作业未系安全带',
    level: 'orange',
    type: '未系安全带',
    area: '主体结构3层',
    team: '架子三班',
    status: 'done',
    assignee: '李安全',
    createTime: '2026-07-25 11:10:00',
    deadline: '2026-07-25 14:00:00',
    snapUrl: '',
    maskUrl: '',
    regulation: '《建筑施工高处作业安全技术规范》JGJ80：高处作业人员必须系安全带。',
    logs: [
      { time: '11:10:00', action: '系统自动生成工单', user: 'AI检测引擎' },
      { time: '12:00:00', action: '已督促佩戴并拍照复核', user: '李安全' },
    ],
  },
]

/** 复盘分析 - 隐患趋势（近7天） */
export const analysisTrend = {
  dates: ['07-20', '07-21', '07-22', '07-23', '07-24', '07-25', '07-26'],
  red: [3, 2, 4, 1, 3, 2, 3],
  orange: [5, 6, 4, 7, 5, 4, 5],
  yellow: [8, 7, 9, 6, 8, 10, 7],
}

/** 区域热力 */
export const areaHeat = [
  { name: '脚手架C区', value: 18 },
  { name: '塔吊A区', value: 12 },
  { name: '基坑B区', value: 9 },
  { name: '材料堆场', value: 6 },
  { name: '钢筋加工棚', value: 4 },
  { name: '出入口', value: 1 },
]

/** 班组违规统计 */
export const teamViolation = [
  { name: '架子三班', count: 15 },
  { name: '土建五班', count: 10 },
  { name: '木工二班', count: 8 },
  { name: '水电四班', count: 6 },
  { name: '钢筋一班', count: 4 },
]

/** 模型规则配置 */
export const modelConfig = {
  thresholds: [
    { key: 'helmet', label: '未戴安全帽', value: 0.75, desc: '置信度阈值，越高越严格' },
    { key: 'harness', label: '未系安全带', value: 0.8, desc: '置信度阈值' },
    { key: 'edge', label: '临边防护', value: 0.7, desc: '置信度阈值' },
    { key: 'fire', label: '烟火检测', value: 0.85, desc: '置信度阈值' },
  ],
  knowledgeBase: [
    { id: 'kb1', title: '安全帽佩戴规范', category: '个体防护', updateTime: '2026-07-01' },
    { id: 'kb2', title: '高处作业安全带要求', category: '高处作业', updateTime: '2026-07-05' },
    { id: 'kb3', title: '临边洞口防护标准', category: '防护设施', updateTime: '2026-07-10' },
    { id: 'kb4', title: '施工现场烟火管理', category: '消防安全', updateTime: '2026-07-12' },
  ],
  pushRules: [
    { id: 'pr1', level: 'red', channels: ['短信', '小程序', 'PC弹窗'], delayMin: 0 },
    { id: 'pr2', level: 'orange', channels: ['小程序', 'PC弹窗'], delayMin: 1 },
    { id: 'pr3', level: 'yellow', channels: ['PC弹窗'], delayMin: 5 },
  ],
  trainProgress: {
    modelName: '道路安全视觉模型',
    progress: 72,
    epoch: '36/50',
    status: 'training',
    eta: '约2小时',
  },
}

/** 安全案例库 */
export const caseList = [
  {
    id: 'case-001',
    title: '未戴安全帽导致坠落伤害典型案例',
    type: '未戴安全帽',
    level: 'red',
    tags: ['个体防护', '高处作业'],
    date: '2026-06-15',
    summary: '工人未佩戴安全帽攀爬脚手架，坠落时头部受创。',
    mediaType: 'video',
  },
  {
    id: 'case-002',
    title: '吊装作业下方站人险情复盘',
    type: '吊装违规',
    level: 'red',
    tags: ['起重机械', '人员管控'],
    date: '2026-05-20',
    summary: '塔吊吊运钢筋时下方有人穿行，险些造成砸伤。',
    mediaType: 'image',
  },
  {
    id: 'case-003',
    title: '临边防护缺失整改前后对比',
    type: '临边防护',
    level: 'orange',
    tags: ['防护设施'],
    date: '2026-04-08',
    summary: '基坑临边栏杆缺失，经整改后恢复封闭防护。',
    mediaType: 'image',
  },
  {
    id: 'case-004',
    title: '电焊作业未设灭火器培训素材',
    type: '烟火违规',
    level: 'orange',
    tags: ['消防安全', '培训'],
    date: '2026-03-22',
    summary: '用于班前教育的烟火违规警示视频素材。',
    mediaType: 'video',
  },
]

/** 历史培训素材 */
export const trainingMaterials = [
  { id: 'tm1', title: '安全帽佩戴培训短视频', type: '视频', createTime: '2026-07-10', size: '12MB' },
  { id: 'tm2', title: '高处作业十条禁令海报', type: '图片', createTime: '2026-07-08', size: '2MB' },
  { id: 'tm3', title: '临边防护周检清单', type: '文档', createTime: '2026-07-01', size: '180KB' },
]

/** 设备管理 */
export const devices = [
  { id: 'cam-01', name: '塔吊A区摄像头', type: '枪机', area: '塔吊A区', status: 'online', ip: '192.168.1.101' },
  { id: 'cam-02', name: '基坑B区摄像头', type: '球机', area: '基坑B区', status: 'online', ip: '192.168.1.102' },
  { id: 'cam-03', name: '材料堆场摄像头', type: '枪机', area: '材料堆场', status: 'online', ip: '192.168.1.103' },
  { id: 'cam-04', name: '脚手架C区摄像头', type: '球机', area: '脚手架C区', status: 'online', ip: '192.168.1.104' },
  { id: 'cam-08', name: '降水井摄像头', type: '枪机', area: '基坑', status: 'offline', ip: '192.168.1.108' },
]

/** 组织架构 */
export const orgTree = [
  {
    title: '滨江一期项目部',
    key: 'org-root',
    children: [
      {
        title: '安全管理部',
        key: 'org-safety',
        children: [
          { title: '张安全（安全员）', key: 'u-zhang', isLeaf: true },
          { title: '李安全（安全员）', key: 'u-li', isLeaf: true },
          { title: '王安全（安全员）', key: 'u-wang', isLeaf: true },
        ],
      },
      {
        title: '工程管理部',
        key: 'org-eng',
        children: [
          { title: '赵总监（总监）', key: 'u-zhao', isLeaf: true },
        ],
      },
      {
        title: '施工班组',
        key: 'org-team',
        children: [
          { title: '钢筋一班', key: 't1', isLeaf: true },
          { title: '木工二班', key: 't2', isLeaf: true },
          { title: '架子三班', key: 't3', isLeaf: true },
          { title: '水电四班', key: 't4', isLeaf: true },
          { title: '土建五班', key: 't5', isLeaf: true },
        ],
      },
    ],
  },
]
