/** Road clients use mobile/api, which submits evidence to the detection bridge. */
const unavailable = () => Promise.resolve({ code: -1, message: '请通过道路检测任务接口提交图片，当前无独立AI服务' })
export const visionDetectFromImage = unavailable
export const reasonAnalyze = unavailable
export const actionCreateOrder = unavailable
