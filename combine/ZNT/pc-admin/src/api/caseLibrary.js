/**
 * 安全案例库与培训素材接口
 * 生成结果写入本地归档，可下载海报 / 培训文档
 */
import { USE_MOCK, mockDelay } from '@/utils/request'
import request from '@/utils/request'
import { caseList, trainingMaterials } from '@/mock'

const ARCHIVE_KEY = 'znt_training_materials'

function loadArchive() {
  try {
    const raw = localStorage.getItem(ARCHIVE_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

function saveArchive(list) {
  localStorage.setItem(ARCHIVE_KEY, JSON.stringify(list))
}

function nowText() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/**
 * 案例检索
 */
export function fetchCases(params = {}) {
  if (USE_MOCK) {
    let list = [...caseList]
    if (params.keyword) {
      const kw = params.keyword
      list = list.filter(
        (c) => c.title.includes(kw) || c.summary.includes(kw) || c.tags.some((t) => t.includes(kw))
      )
    }
    if (params.type) list = list.filter((c) => c.type === params.type)
    if (params.level) list = list.filter((c) => c.level === params.level)
    return mockDelay(list)
  }
  return request.get('/case/list', { params })
}

/**
 * 获取历史培训素材（种子 + 本地生成归档）
 */
export function fetchMaterials() {
  if (USE_MOCK) {
    const generated = loadArchive()
    return mockDelay([...generated, ...trainingMaterials])
  }
  return request.get('/case/materials')
}

function buildPosterContent(c, prompt = '') {
  return {
    headline: '道路风险提示',
    title: c.title,
    summary: c.summary,
    tags: c.tags || [],
    level: c.level,
    tip: prompt || '请严格遵守现场安全规定，落实防护措施。',
    footer: '道路检测 · 实验室小试 · 安全案例库',
  }
}

function buildDocContent(c, prompt = '') {
  return [
    `# 培训文档：${c.title}`,
    '',
    `案例类型：${c.type}`,
    `风险等级：${c.level}`,
    `日期：${c.date}`,
    '',
    '## 一、案例概述',
    c.summary,
    '',
    '## 二、培训要点',
    '1. 识别风险场景与高发环节',
    '2. 明确责任人与班前交底要求',
    '3. 对照防护措施逐项检查',
    '4. 发生异常立即停工并上报',
    '',
    '## 三、现场要求',
    ...(c.tags || []).map((t, i) => `${i + 1}. 重点关注：${t}`),
    '',
    '## 四、补充说明',
    prompt || '请结合本路段风险与处置案例组织值班人员学习。',
    '',
    '—— 道路风险智能检测软件自动生成',
  ].join('\n')
}

function buildVideoScript(c, prompt = '') {
  return [
    `【短视频脚本】${c.title}`,
    `开场（3s）：警示画面 + 标题字幕`,
    `冲突（8s）：${c.summary}`,
    `讲解（12s）：对照 ${ (c.tags || []).join('、') || '安全规范' } 说明正确做法`,
    `收尾（5s）：口号「道路检测 · 实验室小试」`,
    `补充提示：${prompt || '语气严肃，面向一线工人'}`,
  ].join('\n')
}

/**
 * 素材生成：返回可下载内容，并写入归档
 * @param {{ caseId: string, format: 'video'|'poster'|'doc', prompt?: string }} data
 */
export function generateMaterial(data) {
  if (USE_MOCK) {
    const c = caseList.find((x) => x.id === data.caseId)
    if (!c) {
      return Promise.resolve({ code: 1, message: '案例不存在', data: null })
    }
    const taskId = 'gen-' + Date.now()
    const stamp = nowText()
    let item
    if (data.format === 'poster') {
      const content = buildPosterContent(c, data.prompt)
      item = {
        id: taskId,
        title: `警示海报 · ${c.title}`,
        type: '海报',
        format: 'poster',
        createTime: stamp,
        size: '约 180KB',
        caseId: c.id,
        content,
        status: 'done',
      }
    } else if (data.format === 'doc') {
      const text = buildDocContent(c, data.prompt)
      item = {
        id: taskId,
        title: `培训文档 · ${c.title}`,
        type: '文档',
        format: 'doc',
        createTime: stamp,
        size: `${Math.max(1, Math.round(text.length / 1024))}KB`,
        caseId: c.id,
        content: text,
        status: 'done',
      }
    } else {
      const text = buildVideoScript(c, data.prompt)
      item = {
        id: taskId,
        title: `短视频脚本 · ${c.title}`,
        type: '脚本',
        format: 'video',
        createTime: stamp,
        size: `${Math.max(1, Math.round(text.length / 1024))}KB`,
        caseId: c.id,
        content: text,
        status: 'done',
      }
    }
    const archive = loadArchive()
    archive.unshift(item)
    saveArchive(archive.slice(0, 50))
    return mockDelay({
      success: true,
      taskId,
      status: 'done',
      message: '素材已生成',
      material: item,
    })
  }
  return request.post('/case/generate', data)
}

export function getMaterialById(id) {
  return loadArchive().find((m) => m.id === id) || null
}
