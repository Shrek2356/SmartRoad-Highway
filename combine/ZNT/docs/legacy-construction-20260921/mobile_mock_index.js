/**
 * 移动端 Mock 数据
 * 【后续对接】api/ 目录改为真实请求后可删除本文件
 */

/** 首页待办提醒 */
export const homeReminders = [
  { id: 'WO-20260726001', title: '脚手架C区未戴安全帽', level: 'red', time: '14:32', status: 'pending' },
  { id: 'WO-20260726002', title: '塔吊A区吊物下方站人', level: 'red', time: '14:28', status: 'processing' },
  { id: 'WO-20260726003', title: '基坑B区临边防护缺失', level: 'orange', time: '14:15', status: 'pending' },
]

/** 弹窗告警 */
export const latestAlarm = {
  id: 'a1',
  level: 'red',
  title: '未戴安全帽',
  area: '脚手架C区',
  camera: 'CAM-04',
  time: '2026-07-26 14:32:10',
  snapTip: '抓拍图占位（对接后显示真实图片）',
  regulation: '《建筑施工安全检查标准》JGJ59-2011：进入施工现场必须正确佩戴安全帽。',
}

/** 工单列表 */
export const workOrders = [
  {
    id: 'WO-20260726001',
    title: '脚手架C区未戴安全帽',
    level: 'red',
    status: 'pending',
    area: '脚手架C区',
    team: '架子三班',
    deadline: '16:30',
    steps: ['接单', '现场整改', '拍照复核', '关闭工单'],
    currentStep: 0,
  },
  {
    id: 'WO-20260726002',
    title: '塔吊A区吊物下方站人',
    level: 'red',
    status: 'processing',
    area: '塔吊A区',
    team: '土建五班',
    deadline: '15:30',
    steps: ['接单', '现场整改', '拍照复核', '关闭工单'],
    currentStep: 1,
  },
  {
    id: 'WO-20260725008',
    title: '材料堆场侵占消防通道',
    level: 'yellow',
    status: 'done',
    area: '材料堆场',
    team: '水电四班',
    deadline: '已完成',
    steps: ['接单', '现场整改', '拍照复核', '关闭工单'],
    currentStep: 3,
  },
]

/** 案例 */
export const cases = [
  { id: 'case-001', title: '未戴安全帽典型案例', type: '未戴安全帽', level: 'red', summary: '工人未佩戴安全帽攀爬脚手架坠落受伤。' },
  { id: 'case-002', title: '吊装下方站人险情', type: '吊装违规', level: 'red', summary: '塔吊吊运时下方穿行，险些砸伤。' },
  { id: 'case-003', title: '临边防护缺失整改', type: '临边防护', level: 'orange', summary: '基坑临边栏杆缺失，整改后恢复封闭。' },
]
