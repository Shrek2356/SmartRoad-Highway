<template>
  <!--
    ⑥ 安全案例库与培训素材页
    业务：案例检索 → 海报/文档/脚本生成 → 历史归档可下载
  -->
  <div class="page-card">
    <div class="page-title">安全案例库与培训素材</div>

    <a-tabs v-model:activeKey="tab">
      <a-tab-pane key="cases" tab="案例检索">
        <a-form layout="inline" class="filter" :model="query">
          <a-form-item label="关键词">
            <a-input v-model:value="query.keyword" allow-clear placeholder="标题/标签" style="width: 180px" />
          </a-form-item>
          <a-form-item label="类型">
            <a-select v-model:value="query.type" allow-clear placeholder="全部" style="width: 140px">
              <a-select-option value="路面积水">路面积水</a-select-option>
              <a-select-option value="道路阻塞">道路阻塞</a-select-option>
              <a-select-option value="路面坑槽">路面坑槽</a-select-option>
              <a-select-option value="车辆或路侧疑似火情">车辆或路侧疑似火情</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item>
            <a-button type="primary" @click="loadCases">搜索</a-button>
          </a-form-item>
        </a-form>

        <a-row :gutter="[16, 16]">
          <a-col v-for="c in cases" :key="c.id" :span="12">
            <a-card hoverable>
              <template #title>
                <a-space>
                  <a-tag :color="levelColor(c.level)">{{ levelText(c.level) }}</a-tag>
                  {{ c.title }}
                </a-space>
              </template>
              <p>{{ c.summary }}</p>
              <div class="meta">
                <a-tag v-for="t in c.tags" :key="t">{{ t }}</a-tag>
                <span class="date">{{ c.date }}</span>
              </div>
              <a-space>
                <a-button type="link" style="padding-left: 0" @click="genFromCase(c, 'poster')">生成海报</a-button>
                <a-button type="link" @click="genFromCase(c, 'doc')">生成培训文档</a-button>
                <a-button type="link" @click="genFromCase(c, 'video')">生成脚本</a-button>
              </a-space>
            </a-card>
          </a-col>
        </a-row>
      </a-tab-pane>

      <a-tab-pane key="gen" tab="素材生成工具">
        <a-form :model="genForm" layout="vertical" style="max-width: 560px">
          <a-form-item label="基于案例" required>
            <a-select v-model:value="genForm.caseId" placeholder="选择案例">
              <a-select-option v-for="c in cases" :key="c.id" :value="c.id">{{ c.title }}</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="输出格式">
            <a-radio-group v-model:value="genForm.format">
              <a-radio-button value="poster">警示海报</a-radio-button>
              <a-radio-button value="doc">培训文档</a-radio-button>
              <a-radio-button value="video">短视频脚本</a-radio-button>
            </a-radio-group>
          </a-form-item>
          <a-form-item label="补充提示词（可选）">
            <a-textarea v-model:value="genForm.prompt" :rows="3" placeholder="例如：面向新工人班前教育，语气严肃" />
          </a-form-item>
          <a-button type="primary" :loading="genLoading" @click="onGenerate">提交生成任务</a-button>
        </a-form>

        <div v-if="lastResult" class="result-box">
          <div class="result-head">
            <div class="result-title">生成结果 · {{ lastResult.title }}</div>
            <a-space>
              <a-button size="small" type="primary" @click="downloadResult(lastResult)">下载</a-button>
              <a-button size="small" @click="tab = 'archive'">查看归档</a-button>
            </a-space>
          </div>

          <div v-if="lastResult.format === 'poster'" class="poster-wrap">
            <canvas ref="posterCanvas" width="720" height="960" class="poster-canvas" />
          </div>
          <pre v-else class="doc-preview">{{ lastResult.content }}</pre>
        </div>
      </a-tab-pane>

      <a-tab-pane key="archive" tab="历史素材归档">
        <a-table :columns="matCols" :data-source="materials" row-key="id" :pagination="{ pageSize: 8 }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'action'">
              <a-space>
                <a-button type="link" size="small" @click="previewMaterial(record)">查看</a-button>
                <a-button type="link" size="small" @click="downloadResult(record)">下载</a-button>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref, watch } from 'vue'
import { colorTheme } from '@/utils/theme'
import { message } from 'ant-design-vue'
import { fetchCases, fetchMaterials, generateMaterial } from '@/api/caseLibrary'
import { saveFile } from '@/utils/saveFile'

const tab = ref('cases')
const cases = ref([])
const materials = ref([])
const genLoading = ref(false)
const lastResult = ref(null)
const posterCanvas = ref(null)
const query = reactive({ keyword: '', type: undefined })
const genForm = reactive({ caseId: undefined, format: 'poster', prompt: '' })

const matCols = [
  { title: '素材名称', dataIndex: 'title', key: 'title' },
  { title: '类型', dataIndex: 'type', key: 'type', width: 90 },
  { title: '创建时间', dataIndex: 'createTime', key: 'createTime', width: 160 },
  { title: '大小', dataIndex: 'size', key: 'size', width: 100 },
  { title: '操作', key: 'action', width: 140 },
]

function levelColor(l) {
  return { red: 'red', orange: 'orange', yellow: 'gold' }[l]
}
function levelText(l) {
  return { red: '高危', orange: '中危', yellow: '低危' }[l]
}

async function loadCases() {
  const res = await fetchCases(query)
  cases.value = res.data
  if (!genForm.caseId && res.data[0]) genForm.caseId = res.data[0].id
}

async function loadMaterials() {
  const res = await fetchMaterials()
  materials.value = res.data
}

function genFromCase(c, format = 'poster') {
  genForm.caseId = c.id
  genForm.format = format
  tab.value = 'gen'
}

function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
  const chars = String(text || '').split('')
  let line = ''
  let yy = y
  for (let i = 0; i < chars.length; i++) {
    const test = line + chars[i]
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line, x, yy)
      line = chars[i]
      yy += lineHeight
    } else {
      line = test
    }
  }
  if (line) ctx.fillText(line, x, yy)
  return yy
}

function drawPoster(content) {
  const canvas = posterCanvas.value
  if (!canvas || !content) return
  const ctx = canvas.getContext('2d')
  const w = canvas.width
  const h = canvas.height

  // 背景
  const g = ctx.createLinearGradient(0, 0, 0, h)
  const ink = colorTheme.value === 'light'
  g.addColorStop(0, ink ? '#222222' : '#122c3a')
  g.addColorStop(0.45, ink ? '#444444' : '#1e4d58')
  g.addColorStop(1, ink ? '#666666' : '#087f78')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, w, h)

  // 白卡片
  ctx.fillStyle = 'rgba(255,255,255,0.95)'
  roundRect(ctx, 48, 120, w - 96, h - 240, 18)
  ctx.fill()

  ctx.fillStyle = '#fff'
  ctx.font = 'bold 42px Microsoft YaHei, sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText(content.headline || '道路风险提示', w / 2, 78)

  ctx.fillStyle = ink ? '#202020' : '#203544'
  ctx.font = 'bold 32px Microsoft YaHei, sans-serif'
  ctx.textAlign = 'left'
  let y = wrapText(ctx, content.title, 80, 190, w - 160, 42)

  ctx.fillStyle = '#595959'
  ctx.font = '22px Microsoft YaHei, sans-serif'
  y = wrapText(ctx, content.summary, 80, y + 36, w - 160, 34)

  y += 48
  ctx.fillStyle = ink ? '#333333' : '#08766f'
  ctx.font = 'bold 24px Microsoft YaHei, sans-serif'
  ctx.fillText('安全提示', 80, y)
  ctx.fillStyle = '#434343'
  ctx.font = '20px Microsoft YaHei, sans-serif'
  wrapText(ctx, content.tip, 80, y + 36, w - 160, 32)

  ctx.fillStyle = 'rgba(255,255,255,0.9)'
  ctx.font = '18px Microsoft YaHei, sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText(content.footer || '', w / 2, h - 48)
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function canvasBlob(canvas) {
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('海报图像导出失败'))))
}

function posterBlob(content) {
  const canvas = document.createElement('canvas')
  canvas.width = 720
  canvas.height = 960
  const prev = posterCanvas.value
  posterCanvas.value = canvas
  drawPoster(content)
  posterCanvas.value = prev
  if (prev && lastResult.value?.content) {
    nextTick(() => drawPoster(lastResult.value.content))
  }
  return canvasBlob(canvas)
}

async function downloadResult(item) {
  if (!item) return
  try {
  if (item.format === 'poster' && item.content) {
    if (lastResult.value?.id === item.id && posterCanvas.value) {
      await saveFile(await canvasBlob(posterCanvas.value), `${item.title}.png`)
    } else {
      await saveFile(await posterBlob(item.content), `${item.title}.png`)
    }
    return
  }
  if (!item.content) {
    message.info('该归档项为历史种子素材，无生成内容可下载')
    return
  }
  const text = typeof item.content === 'string' ? item.content : JSON.stringify(item.content, null, 2)
  const ext = item.format === 'doc' ? 'md' : 'txt'
  await saveFile(new Blob([text], { type: 'text/plain;charset=utf-8' }), `${item.title}.${ext}`)
  } catch (error) { message.error(error.message || '素材导出失败') }
}

async function previewMaterial(record) {
  lastResult.value = record
  tab.value = 'gen'
  if (record.format === 'poster') {
    await nextTick()
    drawPoster(record.content)
  }
}

async function onGenerate() {
  if (!genForm.caseId) {
    message.warning('请选择案例')
    return
  }
  genLoading.value = true
  try {
    const res = await generateMaterial({ ...genForm })
    if (!res.data?.material) {
      message.error(res.message || '生成失败')
      return
    }
    lastResult.value = res.data.material
    await loadMaterials()
    message.success(`${res.data.message}，任务号 ${res.data.taskId}`)
    await nextTick()
    if (lastResult.value.format === 'poster') {
      drawPoster(lastResult.value.content)
    }
  } catch (e) {
    message.error(e?.message || '生成失败')
  } finally {
    genLoading.value = false
  }
}

watch(colorTheme, async () => { await nextTick(); if (lastResult.value?.content) drawPoster(lastResult.value.content) })

onMounted(async () => {
  await loadCases()
  await loadMaterials()
})
</script>

<style scoped>
.filter { margin-bottom: 16px; }
.meta { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-bottom: 4px; }
.date { margin-left: auto; color: var(--text-secondary); font-size: 12px; }
.result-box {
  margin-top: 24px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 16px;
  background: var(--surface-2);
}
.result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.result-title { font-weight: 650; font-size: 15px; }
.poster-wrap { display: flex; justify-content: center; background: var(--surface); border-radius: 8px; padding: 12px; }
.poster-canvas {
  width: min(360px, 100%);
  height: auto;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}
.doc-preview {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  max-height: 480px;
  overflow: auto;
}
</style>
