// Road laboratory empty states. Only real backend records populate operational statistics.
export const currentProject = { id:'road-lab', name:'路安智巡道路实验室', address:'未配置道路位置' }
export const projectList = [currentProject]
export const dashboardMetrics = []
export const sitePoints = []
export const highRiskVideos = []
export const riskTrendHours = { hours:[], values:[] }
export const hazardTypes = []
export const teamRank = []
export const topHazards = []
export const dashboardByProject = {}
export const deviceTree = []
export const cameraList = []
export const realtimeAlarms = []
export const workOrders = []
export const analysisTrend = { dates:[], red:[], orange:[], yellow:[] }
export const areaHeat = []
export const teamViolation = []
export const modelConfig = { thresholds:[], knowledgeBase:[], pushRules:[], trainProgress:{ modelName:'道路模型外部训练流程', progress:0, epoch:'未启动', status:'not_started', eta:'未提供' } }
export const caseList = []
export const trainingMaterials = []
export const devices = []
export const orgTree = []
export function getDashboardByProject() { return { shortName:currentProject.name, address:currentProject.address, metrics:dashboardMetrics, sitePoints, highRiskVideos, riskTrendHours, hazardTypes, teamRank, topHazards } }
