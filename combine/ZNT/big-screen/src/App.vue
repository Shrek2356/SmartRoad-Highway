<template>
  <!--
    道路监控可视化大屏（极简大字）
    模块：高危滚动 / 今日指标 / 违规案例循环 / 处置单位排名
  -->
  <div class="screen" ref="screenRef">
    <dv-border-box-11 title="路安智巡 · 道路监测大屏" :title-width="520" class="border">
      <div class="screen-inner">
        <button v-if="loadError" class="connection-error" type="button" @click="load">
          业务数据连接失败：{{ loadError }}（点击重试）
        </button>
        <!-- 顶部：高危告警滚动 -->
        <header class="alert-bar">
          <span class="alert-label">高危告警</span>
          <dv-scroll-board :config="scrollConfig" class="scroll-board" />
        </header>

        <main class="main">
          <!-- 左侧大字指标 -->
          <section class="stats">
            <div class="stat-block">
              <div class="stat-num danger">{{ stats.hazardTotal }}</div>
              <div class="stat-label">今日隐患总数</div>
            </div>
            <div class="stat-block">
              <div class="stat-num success">{{ stats.fixedRate }}<small>%</small></div>
              <div class="stat-label">整改完成率</div>
            </div>
            <div class="stat-row">
              <div class="mini">
                <div class="mini-num">{{ stats.highRisk }}</div>
                <div class="mini-label">高危待处</div>
              </div>
              <div class="mini">
                <div class="mini-num">{{ stats.pending }}</div>
                <div class="mini-label">待整改工单</div>
              </div>
            </div>
            <dv-decoration-5 style="width: 100%; height: 40px; margin-top: 12px" />
          </section>

          <!-- 中间：违规案例循环 -->
          <section class="cases">
            <div class="section-title">违规案例循环播报</div>
            <transition name="fade" mode="out-in">
              <div :key="currentCase.id" class="case-card" :class="'lv-' + currentCase.level">
                <div class="case-level">{{ levelText(currentCase.level) }}</div>
                <div class="case-title">{{ currentCase.title }}</div>
                <div class="case-meta">{{ currentCase.area }} · {{ currentCase.time }}</div>
                <div class="case-visual">
                  <img v-if="currentCase.image" :src="currentCase.image" alt="AI 检测抓拍证据" />
                  <span v-else>暂无抓拍证据</span>
                </div>
              </div>
            </transition>
          </section>

          <!-- 右侧：处置单位排名 + 图表 -->
          <section class="rank">
            <div class="section-title">处置单位响应排名</div>
            <div ref="rankChartRef" class="rank-chart" />
            <div class="rank-list">
              <div v-for="(t, i) in teamRank" :key="t.name" class="rank-item">
                <span class="no" :class="'n' + (i + 1)">{{ i + 1 }}</span>
                <span class="name">{{ t.name }}</span>
                <span class="rate">{{ t.rate }}%</span>
              </div>
            </div>
          </section>
        </main>

        <footer class="footer">
          <dv-decoration-10 style="width: 100%; height: 5px" />
          <div class="footer-text">数据每 30 秒自动刷新 · 业务后台实时汇总 · {{ now }}</div>
        </footer>
      </div>
    </dv-border-box-11>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { fetchScreenData } from '@/api/screen'

const stats = ref({ hazardTotal: 0, fixedRate: 0, highRisk: 0, pending: 0 })
const alerts = ref([])
const cases = ref([])
const teamRank = ref([])
const caseIndex = ref(0)
const now = ref(dayjs().format('YYYY-MM-DD HH:mm:ss'))
const loadError = ref('')
const rankChartRef = ref(null)
let chart = null
let caseTimer = null
let clockTimer = null
let refreshTimer = null

const currentCase = computed(() => cases.value[caseIndex.value] || { id: '-', title: '-', area: '-', time: '-', level: 'yellow' })

const scrollConfig = computed(() => ({
  header: ['告警内容'],
  data: alerts.value.map((a) => [`<span style="color:${a.level === 'red' ? '#ff4d4f' : a.level === 'orange' ? '#fa8c16' : '#fadb14'}">${a.text}</span>`]),
  rowNum: 1,
  headerBGC: 'transparent',
  oddRowBGC: 'transparent',
  evenRowBGC: 'transparent',
  align: ['left'],
  waitTime: 3000,
}))

function levelText(l) {
  return { red: '高危告警', orange: '中危告警', yellow: '低危提示' }[l] || l
}

function renderRankChart() {
  if (!rankChartRef.value) return
  chart?.dispose()
  chart = echarts.init(rankChartRef.value)
  chart.setOption({
    grid: { left: 70, right: 20, top: 20, bottom: 20 },
    xAxis: { type: 'value', max: 100, axisLabel: { color: '#8cbfef' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } } },
    yAxis: {
      type: 'category',
      data: [...teamRank.value].reverse().map((t) => t.name),
      axisLabel: { color: '#e6f4ff' },
    },
    series: [{
      type: 'bar',
      data: [...teamRank.value].reverse().map((t) => t.rate),
      barWidth: 14,
      itemStyle: {
        borderRadius: [0, 6, 6, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#1677ff' },
          { offset: 1, color: '#36cfc9' },
        ]),
      },
      label: { show: true, position: 'right', color: '#fff', formatter: '{c}%' },
    }],
  })
}

async function load() {
  try {
    const res = await fetchScreenData()
    stats.value = res.data.stats
    alerts.value = res.data.alerts
    cases.value = res.data.cases
    teamRank.value = res.data.teamRank
    loadError.value = ''
    await nextTick()
    renderRankChart()
  } catch (error) {
    loadError.value = error?.response?.data?.detail || error?.message || '未知错误'
  }
}

onMounted(async () => {
  await load()
  caseTimer = setInterval(() => {
    if (!cases.value.length) return
    caseIndex.value = (caseIndex.value + 1) % cases.value.length
  }, 4000)
  clockTimer = setInterval(() => {
    now.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
  }, 1000)
  refreshTimer = setInterval(load, 30000)
  window.addEventListener('resize', () => chart?.resize())
})

onBeforeUnmount(() => {
  clearInterval(caseTimer)
  clearInterval(clockTimer)
  clearInterval(refreshTimer)
  chart?.dispose()
})
</script>

<style scoped>
.screen {
  width: 100vw;
  height: 100vh;
  padding: 12px;
  background:
    radial-gradient(ellipse at 50% 0%, rgba(22, 119, 255, 0.2), transparent 55%),
    #020b1a;
}
.border { width: 100%; height: 100%; }
.screen-inner {
  height: 100%;
  padding: 70px 36px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.connection-error {
  flex: none;
  padding: 10px 14px;
  color: #ffd8d8;
  background: rgba(255, 77, 79, 0.18);
  border: 1px solid rgba(255, 77, 79, 0.55);
  border-radius: 6px;
  cursor: pointer;
}
.alert-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  height: 56px;
  background: rgba(255, 77, 79, 0.12);
  border: 1px solid rgba(255, 77, 79, 0.35);
  border-radius: 6px;
  padding: 0 16px;
}
.alert-label {
  flex-shrink: 0;
  font-size: 22px;
  font-weight: 700;
  color: #ff4d4f;
  letter-spacing: 2px;
}
.scroll-board { flex: 1; height: 48px; }
.main {
  flex: 1;
  display: grid;
  grid-template-columns: 1.1fr 1.4fr 1.1fr;
  gap: 20px;
  min-height: 0;
}
.section-title {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 16px;
  letter-spacing: 2px;
}
.stats {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 20px;
  padding: 12px;
}
.stat-block { text-align: center; }
.stat-num {
  font-size: 96px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: 2px;
}
.stat-num small { font-size: 40px; }
.stat-num.danger { color: #ff4d4f; text-shadow: 0 0 24px rgba(255, 77, 79, 0.45); }
.stat-num.success { color: #36cfc9; text-shadow: 0 0 24px rgba(54, 207, 201, 0.45); }
.stat-label { margin-top: 8px; font-size: 24px; color: #8cbfef; }
.stat-row { display: flex; gap: 16px; }
.mini {
  flex: 1;
  text-align: center;
  padding: 16px;
  background: rgba(22, 119, 255, 0.12);
  border: 1px solid rgba(22, 119, 255, 0.3);
  border-radius: 8px;
}
.mini-num { font-size: 48px; font-weight: 700; color: #69b1ff; }
.mini-label { font-size: 16px; color: #8cbfef; }
.cases {
  padding: 12px;
  display: flex;
  flex-direction: column;
}
.case-card {
  flex: 1;
  border-radius: 12px;
  padding: 28px;
  border: 2px solid rgba(255, 255, 255, 0.15);
  display: flex;
  flex-direction: column;
  background: rgba(0, 0, 0, 0.25);
}
.case-card.lv-red { border-color: rgba(255, 77, 79, 0.7); }
.case-card.lv-orange { border-color: rgba(250, 140, 22, 0.7); }
.case-card.lv-yellow { border-color: rgba(250, 219, 20, 0.5); }
.case-level { font-size: 20px; color: #ff7875; margin-bottom: 8px; }
.case-title { font-size: 48px; font-weight: 800; letter-spacing: 2px; }
.case-meta { margin-top: 12px; font-size: 22px; color: #8cbfef; }
.case-visual {
  margin-top: auto;
  height: 220px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(22,119,255,0.05) 3px, rgba(22,119,255,0.05) 6px),
    linear-gradient(180deg, #0d2137, #132f4c);
  color: #69b1ff;
  font-size: 18px;
  overflow: hidden;
}
.case-visual img { width: 100%; height: 100%; object-fit: contain; }
.rank { padding: 12px; display: flex; flex-direction: column; min-height: 0; }
.rank-chart { height: 220px; }
.rank-list { margin-top: 8px; overflow: auto; }
.rank-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 20px;
}
.no {
  width: 28px; height: 28px; border-radius: 50%;
  background: #1677ff; color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700;
}
.no.n1 { background: #ff4d4f; }
.no.n2 { background: #fa8c16; }
.no.n3 { background: #d4b106; }
.name { flex: 1; }
.rate { color: #36cfc9; font-weight: 700; font-size: 24px; }
.footer { text-align: center; }
.footer-text { margin-top: 8px; font-size: 14px; color: #595959; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.45s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
