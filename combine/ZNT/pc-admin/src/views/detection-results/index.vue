<template>
  <!--
    检测结果汇总（展示向）
    - 合并现场样例 + 实时检测结果（数据互通，侧栏导航）
  -->
  <div class="result-page">
    <div class="hero">
      <div class="hero-text">
        <h1>检测结果汇总</h1>
        <p>
          现场样例与实时检测结论、标注图一览。点击顶部数字可筛选；<br />
          需要了解判定依据时可打开「结果由来」。
        </p>
        <a-space class="hero-actions">
          <a-button size="large" @click="originOpen = true">结果由来</a-button>
          <a-button size="large" @click="codeOpen = true">对接检测源码</a-button>
        </a-space>
      </div>
      <div class="hero-stats" v-if="summary.total">
        <div
          v-for="s in statCards"
          :key="s.key"
          class="stat"
          :class="{ active: filter === s.filter }"
          @click="onStatClick(s.filter)"
        >
          <div class="num">{{ s.value }}</div>
          <div class="lab">{{ s.label }}</div>
          <div class="hint">点击筛选</div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">
        <div class="panel-title" style="margin: 0">
          检测结果
          <span v-if="summary.liveCount" class="live-tip">含 {{ summary.liveCount }} 条实时检测</span>
          <span v-if="summary.presentationCount" class="presentation-tip">保留 {{ summary.presentationCount }} 张展示案例</span>
        </div>
        <a-radio-group v-model:value="filter" button-style="solid" size="middle">
          <a-radio-button value="all">全部 {{ summary.total || 0 }}</a-radio-button>
          <a-radio-button value="real">真实 {{ realCount }}</a-radio-button>
          <a-radio-button value="presentation">展示 {{ presentationCount }}</a-radio-button>
          <a-radio-button value="live">实时 {{ liveCount }}</a-radio-button>
          <a-radio-button value="confirmed">已确认 {{ confirmedCount }}</a-radio-button>
          <a-radio-button value="review">真实待复核 {{ reviewCount }}</a-radio-button>
          <a-radio-button value="high">高置信 {{ highCount }}</a-radio-button>
        </a-radio-group>
      </div>

      <a-row :gutter="[20, 20]">
        <a-col v-for="c in filteredCases" :key="c.id" :xs="24" :md="12" :xl="8">
          <div class="case-card" :id="'case-' + c.id" :class="{ live: c.live, presentation: c.presentationAsset }">
            <div class="cover" @click="preview(c.cover || c.images?.overlay || c.images?.original)">
              <img :src="c.cover || c.images?.original" :alt="c.expected" />
              <div class="cover-tags">
                <a-tag v-if="c.sourceType === 'demo-run'" color="orange">演示运行</a-tag>
                <a-tag v-else-if="c.sourceType === 'pending-sync'" color="blue">真实·待同步</a-tag>
                <a-tag v-else-if="c.live">实时</a-tag>
                <a-tag v-else-if="c.presentationAsset" color="cyan">预设展示</a-tag>
                <a-tag v-else color="green">真实记录</a-tag>
                <a-tag>{{ statusText(c.status) }}</a-tag>
                <a-tag>{{ (c.confidence * 100).toFixed(0) }}%</a-tag>
              </div>
            </div>
            <div class="body">
              <div class="title">{{ displayId(c) }} {{ c.expected }}</div>
              <div class="result">{{ c.result }}</div>
              <p class="analysis">{{ c.analysis }}</p>
              <div class="suggest">建议：{{ c.suggestion }}</div>
              <div class="actions">
                <a-button type="link" @click="preview(c.images?.overlay || c.cover)">查看标注图</a-button>
                <a-button
                  v-if="c.images?.original"
                  type="link"
                  @click="preview(c.images.original)"
                >查看原图</a-button>
              </div>
            </div>
          </div>
        </a-col>
      </a-row>

      <a-empty v-if="!filteredCases.length" description="当前筛选下暂无结果" />
      <p class="conclusion">{{ summary.conclusion }}</p>
    </div>

    <a-modal v-model:open="originOpen" title="结果由来" width="720px" :footer="null">
      <p class="origin-summary">{{ origin.summary }}</p>
      <div class="flow">
        <div v-for="(step, i) in origin.flow || []" :key="i" class="flow-step">
          <span class="no">{{ i + 1 }}</span>
          <span>{{ step }}</span>
          <span v-if="i < origin.flow.length - 1" class="arrow">→</span>
        </div>
      </div>
      <a-alert type="info" show-icon message="主界面只展示检测结论与标注图；算法与模型细节请在源码目录查阅。" />
    </a-modal>

    <a-modal v-model:open="codeOpen" title="对接异常检测源码" width="720px" :footer="null">
      <p>原始检测代码位置（仓库内相对路径）：</p>
      <div class="path-box">
        <code>{{ origin.codePath }}</code>
        <a-button size="small" type="link" @click="copyPath">复制路径</a-button>
      </div>
      <p>{{ origin.codeHint }}</p>
      <div class="sub-label">快速验证</div>
      <pre class="code-block">{{ (origin.quickStart || []).join('\n') }}</pre>
      <p class="tip">实时检测完成后会自动同步到本页清单，可通过左侧菜单切换各模块。</p>
    </a-modal>

    <a-modal v-model:open="previewOpen" :footer="null" width="960px" centered destroy-on-close>
      <img v-if="previewUrl" :src="previewUrl" style="width: 100%" alt="预览" />
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { fetchDetectionResults } from '@/api/detectionResults'
import { subscribeModules } from '@/utils/moduleBus'

const route = useRoute()
const router = useRouter()

const summary = ref({})
const cases = ref([])
const origin = ref({})
const filter = ref('all')
const originOpen = ref(false)
const codeOpen = ref(false)
const previewOpen = ref(false)
const previewUrl = ref('')

const confirmedCount = computed(() => cases.value.filter((c) => c.autoConfirm).length)
const reviewCount = computed(() => cases.value.filter((c) => !c.presentationAsset && c.humanReview).length)
const highCount = computed(() => cases.value.filter((c) => c.confidence >= 0.9 && !c.humanReview).length)
const liveCount = computed(() => cases.value.filter((c) => c.live && !c.presentationAsset).length)
const realCount = computed(() => cases.value.filter((c) => !c.presentationAsset).length)
const presentationCount = computed(() => cases.value.filter((c) => c.presentationAsset).length)

const statCards = computed(() => [
  { key: 'total', label: '结果总数', value: summary.value.total, filter: 'all' },
  { key: 'real', label: '真实记录', value: realCount.value, filter: 'real' },
  { key: 'presentation', label: '预设案例', value: presentationCount.value, filter: 'presentation' },
  { key: 'review', label: '真实待复核', value: summary.value.humanReview || 0, filter: 'review' },
])

const filteredCases = computed(() => {
  if (filter.value === 'live') return cases.value.filter((c) => c.live && !c.presentationAsset)
  if (filter.value === 'real') return cases.value.filter((c) => !c.presentationAsset)
  if (filter.value === 'presentation') return cases.value.filter((c) => c.presentationAsset)
  if (filter.value === 'confirmed') return cases.value.filter((c) => c.autoConfirm)
  if (filter.value === 'review') return cases.value.filter((c) => !c.presentationAsset && c.humanReview)
  if (filter.value === 'high') return cases.value.filter((c) => c.confidence >= 0.9 && !c.humanReview)
  return cases.value
})

function displayId(c) {
  if (c.sourceType === 'demo-run') return '演示运行 ·'
  if (c.sourceType === 'pending-sync') return '真实待同步 ·'
  if (c.live) return '实时 ·'
  if (c.presentationAsset) return `示例 ${c.exampleId} ·`
  if (c.sourceType === 'persisted') return '真实 ·'
  return `${c.id}.`
}
function statusText(s) {
  return { confirmed: '已确认', partial: '部分确认', review: '待复核' }[s] || s
}
function preview(url) {
  if (!url) return
  previewUrl.value = url
  previewOpen.value = true
}
function onStatClick(f) {
  filter.value = f
  router.replace({ query: { ...route.query, filter: f } })
}
function copyPath() {
  const text = origin.value.codePath || ''
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(() => message.success('路径已复制'))
  } else {
    message.info(text)
  }
}

async function loadData() {
  const res = await fetchDetectionResults({
    job: route.query.job,
    case: route.query.case,
  })
  summary.value = res.data.summary
  cases.value = res.data.cases
  origin.value = res.data.origin
}

watch(
  () => route.query.filter,
  (v) => {
    if (v && ['all', 'real', 'presentation', 'live', 'confirmed', 'review', 'high'].includes(String(v))) {
      filter.value = String(v)
    }
  },
  { immediate: true }
)

watch(
  () => [route.query.case, route.query.job],
  async () => {
    await loadData()
    if (route.query.case) {
      filter.value = 'all'
      await scrollToCase(route.query.case)
    } else if (route.query.job) {
      filter.value = 'live'
      const hit = cases.value.find((c) => c.detectJobId === route.query.job)
      if (hit) await scrollToCase(hit.id)
    }
  }
)

onMounted(async () => {
  await loadData()
  if (route.query.filter) filter.value = String(route.query.filter)
  if (route.query.case) {
    filter.value = 'all'
    await scrollToCase(route.query.case)
  } else if (route.query.job) {
    filter.value = 'live'
    const hit = cases.value.find((c) => c.detectJobId === route.query.job)
    if (hit) await scrollToCase(hit.id)
  }
})

const unsub = subscribeModules(async (detail) => {
  if (detail?.type === 'detect-results' || detail?.type === 'workorders') {
    await loadData()
  }
})
onBeforeUnmount(() => unsub())

async function scrollToCase(caseId) {
  if (!caseId) return
  await new Promise((r) => setTimeout(r, 80))
  const match = cases.value.find((item) => String(item.id) === String(caseId)
    || String(item.exampleId) === String(caseId))
  const el = document.getElementById('case-' + (match?.id || caseId))
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('pulse')
    setTimeout(() => el.classList.remove('pulse'), 1600)
  }
}
</script>

<style scoped>
.result-page { display: flex; flex-direction: column; gap: 14px; }
.hero {
  display: flex;
  gap: 28px;
  justify-content: space-between;
  align-items: stretch;
  padding: 28px 30px;
  border-radius: 12px;
  color: var(--text-primary);
  background: var(--surface);
  border: 1px solid var(--border-color);
  min-height: 200px;
}
.hero-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 0;
}
.hero h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
}
.hero p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 15px;
  max-width: 640px;
  line-height: 1.75;
  flex: 1;
}
.hero-actions { margin-top: auto; }
.hero-stats {
  display: grid;
  grid-template-columns: repeat(2, 118px);
  gap: 12px;
  align-content: center;
  flex-shrink: 0;
}
.stat {
  background: var(--surface-muted);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 10px 12px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  min-height: 78px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.stat:hover, .stat.active {
  background: var(--surface-2);
  border-color: var(--primary);
}
.stat .num { font-size: 28px; font-weight: 600; line-height: 1.1; color: var(--text-primary); font-variant-numeric:tabular-nums; }
.stat .lab { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }
.stat .hint { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

.panel {
  background: var(--surface);
  border-radius: 12px;
  padding: 22px 24px;
  border: 1px solid var(--border-color);
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  gap: 12px;
  flex-wrap: wrap;
}
.panel-title { font-size: 18px; font-weight: 650; }
.live-tip {
  margin-left: 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}
.presentation-tip {
  margin-left: 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
}

.case-card {
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.case-card.live { border-color: var(--border-color); }
.case-card.presentation { border-style: dashed; }
.case-card.pulse {
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.18);
  transition: box-shadow 0.3s;
}
.cover { position: relative; height: 220px; background: #1f1f1f; cursor: zoom-in; }
.cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cover-tags { position: absolute; left: 10px; top: 10px; display: flex; gap: 6px; flex-wrap: wrap; }
.body { padding: 16px 18px 12px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
.title { font-weight: 650; font-size: 16px; color: var(--text-primary); line-height: 1.4; }
.result { color: var(--text-primary); font-size: 14px; line-height: 1.5; }
.analysis { margin: 0; font-size: 13px; color: var(--text-secondary); line-height: 1.65; }
.suggest {
  font-size: 13px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px 14px;
  color: var(--text-secondary);
  background: var(--surface-muted);
  line-height: 1.55;
}
.actions { margin-top: auto; padding-top: 4px; }

.conclusion {
  margin: 20px 0 0;
  padding: 16px 18px;
  background: var(--surface-muted);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  color: var(--text-secondary);
  line-height: 1.7;
  font-size: 14px;
}
.origin-summary { line-height: 1.8; color: var(--text-primary); font-size: 14px; }
.flow { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 18px 0; }
.flow-step {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--surface-muted); border: 1px solid var(--border-color); border-radius: 8px; padding: 8px 12px; font-size: 14px;
  color: var(--text-secondary);
}
.flow-step .no {
  width: 22px; height: 22px; border-radius: 50%; background: var(--text-secondary); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-size: 12px;
}
.flow-step .arrow { color: #bfbfbf; }
.sub-label { font-size: 13px; color: var(--text-secondary); font-weight: 650; margin: 14px 0 8px; }
.code-block {
  background: #1f1f1f; color: #f5f5f5; padding: 14px 16px; border-radius: 8px;
  font-size: 13px; line-height: 1.65; overflow: auto;
}
.path-box {
  display: flex; align-items: center; gap: 8px;
  background: var(--surface-muted); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px;
}
.path-box code { flex: 1; color: var(--text-primary); font-size: 13px; word-break: break-all; }
.tip { font-size: 13px; color: var(--text-secondary); margin-top: 12px; }

@media (max-width: 900px) {
  .hero { flex-direction: column; min-height: 0; }
  .hero-stats { grid-template-columns: repeat(2, 1fr); width: 100%; }
}
</style>
