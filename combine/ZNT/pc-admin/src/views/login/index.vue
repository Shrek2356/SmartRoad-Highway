<template>
  <div class="login-page">
    <div class="ambient ambient-one"></div>
    <div class="ambient ambient-two"></div>

    <main class="login-shell">
      <section class="animation-side" aria-label="系统功能导览动画">
        <div class="system-kicker">
          <span class="pulse-dot"></span>
          ROAD SAFETY LAB
        </div>
        <div class="animation-copy">
          <h1>路安智巡 · 道路监测</h1>
          <p>从异常发现到整改复盘，以可追溯证据支持道路管理。</p>
        </div>

        <div class="animation-stage">
          <div class="animation-fallback">
            <div class="scan-ring scan-ring-one"></div>
            <div class="scan-ring scan-ring-two"></div>
            <div class="road-symbol" aria-label="道路监测">路</div>
            <span class="fallback-note">图像观察 · 风险复核 · 法规参考</span>
          </div>
          <div class="stage-grid"></div>
        </div>

        <div class="inspection-state">
          <div class="inspection-line">
            <span class="inspection-label">功能导览</span>
            <span class="inspection-name" :class="{ complete: inspectionComplete }">
              {{ inspectionComplete ? '导览已完成 · 实际服务状态请登录后查看' : activeModule.label }}
            </span>
            <span class="inspection-count">{{ activeIndex + 1 }}/{{ modules.length }}</span>
          </div>
          <div class="progress-track">
            <span
              :class="{ complete: inspectionComplete }"
              :style="{ width: `${inspectionComplete ? 100 : ((activeIndex + 1) / modules.length) * 100}%` }"
            ></span>
          </div>
        </div>

        <div class="module-groups">
          <div class="module-group detection-group">
            <div class="group-title">异常检测系统</div>
            <div class="module-list">
              <div
                v-for="(item, index) in modules.slice(0, 3)"
                :key="item.key"
                class="module-chip"
                :class="{
                  active: !inspectionComplete && activeIndex === index,
                  checked: inspectionComplete || activeIndex > index,
                }"
              >
                <span class="module-icon">{{ item.icon }}</span>
                <span>{{ item.short }}</span>
              </div>
            </div>
          </div>
          <div class="module-group agent-group">
            <div class="group-title">Agent管理系统</div>
            <div class="module-list">
              <div
                v-for="(item, index) in modules.slice(3)"
                :key="item.key"
                class="module-chip"
                :class="{
                  active: !inspectionComplete && activeIndex === index + 3,
                  checked: inspectionComplete || activeIndex > index + 3,
                }"
              >
                <span class="module-icon">{{ item.icon }}</span>
                <span>{{ item.short }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="login-panel">
        <div class="brand">
          <div class="brand-mascot" aria-hidden="true">路</div>
          <div>
            <div class="brand-eyebrow">SMARTROAD SAFETY LAB</div>
            <h2>道路风险智能检测软件</h2>
            <p class="team">道路检测 · 实验室小试</p>
          </div>
        </div>

        <div class="login-heading">
          <h3>欢迎登录</h3>
          <p>登录工作账号，进入智能安全管理平台</p>
        </div>

        <div class="endpoint-box">
          <button type="button" class="endpoint-toggle" @click="endpointOpen = !endpointOpen">
            <span>连接设置与排查</span>
            <span>{{ endpointOpen ? '收起' : '配置业务与检测接口' }} {{ endpointOpen ? '⌃' : '⌄' }}</span>
          </button>
          <div v-if="endpointOpen" class="endpoint-content">
            <label>
              <span>业务服务 API</span>
              <a-input v-model:value="endpointForm.businessApi" placeholder="例如：http://服务器:8800/api" />
            </label>
            <label>
              <span>检测服务 API</span>
              <a-input v-model:value="endpointForm.detectApi" placeholder="例如：http://服务器:8810" />
            </label>
            <div class="endpoint-actions">
              <a-button size="small" @click="resetEndpoints">恢复本机默认</a-button>
              <a-button size="small" :loading="testingEndpoints" @click="testEndpoints">测试连接</a-button>
              <a-button size="small" type="primary" @click="saveEndpoints">保存配置</a-button>
            </div>
            <div v-if="endpointStatus.text" class="endpoint-status" :class="endpointStatus.type">
              {{ endpointStatus.text }}
            </div>
            <p class="endpoint-help">配置保存在当前窗口。通常保持默认即可；连接失败时先测试并恢复默认，再检查后台。这里不是模型 API Key 输入框。</p>
          </div>
        </div>

        <a-form :model="form" layout="vertical" @finish="onSubmit">
          <a-form-item label="账号" name="username" :rules="[{ required: true, message: '请输入账号' }]">
            <a-input v-model:value="form.username" placeholder="工作账号，或选择下方示例账号" size="large" autocomplete="username" />
          </a-form-item>
          <a-form-item label="密码" name="password" :rules="[{ required: true, message: '请输入密码' }]">
            <a-input-password v-model:value="form.password" placeholder="默认：admin123" size="large" />
          </a-form-item>
          <a-form-item label="演示账号快速填入（真实权限由后台决定）">
            <a-radio-group v-model:value="form.role" @change="fillDemoAccount" button-style="solid" class="role-group">
              <a-radio-button value="admin">管理员</a-radio-button>
              <a-radio-button value="safety">道路值班员</a-radio-button>
              <a-radio-button value="director">只读观察员</a-radio-button>
            </a-radio-group>
          </a-form-item>
          <a-button type="primary" html-type="submit" block size="large" :loading="loading" class="login-button">
            {{ loading ? '正在进入系统…' : '进入系统' }}
          </a-button>
        </a-form>

        <div class="login-foot">
          <span>登录后可查看真实服务状态</span>
          <span>YOLO · Qwen · SAM3 · Agent</span>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { message } from 'ant-design-vue'
import axios from 'axios'
import {
  getEndpointSettings,
  joinEndpoint,
  normalizeBusinessApi,
  normalizeDetectApi,
  resetEndpointSettings,
  saveEndpointSettings,
} from '@/utils/endpoints'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const loading = ref(false)
const animationRef = ref(null)
const animationReady = ref(false)
const animationComplete = ref(false)
const animationStarted = ref(false)
const activeIndex = ref(0)
const inspectionComplete = ref(false)
const endpointOpen = ref(false)
const testingEndpoints = ref(false)
const endpointStatus = reactive({ type: '', text: '' })
const endpointForm = reactive(getEndpointSettings())
let inspectionTimer = null
const animationSources = {
  webm: '/media/login/' + 'jr-safety-system.webm',
  mp4: '/media/login/' + 'jr-safety-system.mp4',
}

const modules = [
  { key: 'realtime', label: '实时感知与调度模块介绍…', short: '实时感知', icon: '◉' },
  { key: 'discovery', label: '开放异常识别模块介绍…', short: '异常识别', icon: '◇' },
  { key: 'evidence', label: '正在检查风险定位与证据模块…', short: '证据核验', icon: '⌖' },
  { key: 'reason', label: '正在初始化风险推理Agent…', short: '风险推理', icon: '◆' },
  { key: 'response', label: '协同处置 Agent 介绍…', short: '协同处置', icon: '▣' },
  { key: 'learning', label: '复盘学习 Agent 介绍…', short: '复盘学习', icon: '↻' },
]
const activeModule = computed(() => modules[activeIndex.value])

function fillDemoAccount(e) {
  const role = e.target.value
  Object.assign(form, { username: { admin: 'admin', safety: 'safety', director: 'viewer' }[role], password: { admin: 'admin123', safety: 'safety123', director: 'viewer123' }[role] })
}

const form = reactive({
  username: 'admin',
  password: 'admin123',
  role: 'admin',
})

function stopInspectionTimer() {
  if (!inspectionTimer) return
  window.clearInterval(inspectionTimer)
  inspectionTimer = null
}

function startFallbackInspection(reset = false) {
  stopInspectionTimer()
  if (reset) {
    activeIndex.value = 0
    inspectionComplete.value = false
  }
  inspectionTimer = window.setInterval(() => {
    if (activeIndex.value < modules.length - 1) {
      activeIndex.value += 1
      return
    }
    inspectionComplete.value = true
    stopInspectionTimer()
  }, 900)
}

function completeInspection() {
  activeIndex.value = modules.length - 1
  inspectionComplete.value = true
  stopInspectionTimer()
}

function onAnimationReady() {
  animationReady.value = true
  if (animationComplete.value) {
    animationRef.value?.pause?.()
    return
  }
  if (!animationStarted.value) {
    animationStarted.value = true
    activeIndex.value = 0
    inspectionComplete.value = false
    stopInspectionTimer()
  }
  if (animationRef.value && animationRef.value.currentTime >= 5.5) {
    animationRef.value.currentTime = 0
  }
  animationRef.value?.play?.().catch(() => {
    animationReady.value = false
    animationStarted.value = false
    startFallbackInspection(true)
  })
}

function onAnimationError() {
  animationReady.value = false
  animationStarted.value = false
  startFallbackInspection(true)
}

function onAnimationTimeUpdate() {
  const video = animationRef.value
  if (!video || animationComplete.value) return

  const inspectionRatio = Math.min(1, Math.max(0, video.currentTime / 5.5))
  activeIndex.value = Math.min(
    modules.length - 1,
    Math.floor(inspectionRatio * modules.length),
  )
  if (video.currentTime < 5.45) return

  animationComplete.value = true
  video.pause()
  const holdAt = Math.min(5.5, Math.max(0, (video.duration || 5.5) - 0.05))
  if (Math.abs(video.currentTime - holdAt) > 0.001) video.currentTime = holdAt
  completeInspection()
}

async function onSubmit() {
  loading.value = true
  try {
    await userStore.login(form)
    message.success('登录成功')
    router.replace(route.query.redirect || '/dashboard')
  } finally {
    loading.value = false
  }
}

function applyEndpointValues(values) {
  endpointForm.businessApi = values.businessApi
  endpointForm.detectApi = values.detectApi
}

function saveEndpoints() {
  try {
  applyEndpointValues(saveEndpointSettings(endpointForm))
  endpointStatus.type = 'success'
  endpointStatus.text = '接口配置已保存，登录及后续请求将立即使用新地址。'
  } catch(e) { endpointStatus.type = 'error'; endpointStatus.text = e.message }
}

function resetEndpoints() {
  applyEndpointValues(resetEndpointSettings())
  endpointStatus.type = 'success'
  endpointStatus.text = '已恢复本机代理默认配置。'
}

async function testEndpoints() {
  testingEndpoints.value = true
  endpointStatus.text = ''
  const businessApi = normalizeBusinessApi(endpointForm.businessApi)
  const detectApi = normalizeDetectApi(endpointForm.detectApi)
  try {
    const [business, detect] = await Promise.allSettled([
      axios.get(joinEndpoint(businessApi, 'health'), { timeout: 6000 }),
      axios.get(joinEndpoint(detectApi, 'api/detect/health'), { timeout: 6000 }),
    ])
    const businessOk = business.status === 'fulfilled' && business.value.data?.ok === true && business.value.data?.service === 'znt-business-api'
    const detectOk = detect.status === 'fulfilled' && detect.value.data?.ok === true && detect.value.data?.service === 'site-OpenRisk-detect-bridge'
    endpointStatus.type = businessOk && detectOk ? 'success' : 'error'
    endpointStatus.text = `业务服务：${businessOk ? '已连接' : '连接失败'}；检测服务：${detectOk ? '已连接' : '连接失败'}`
  } finally {
    testingEndpoints.value = false
  }
}

onMounted(() => {
  // 视频不可用时，模块自检仍可独立完成，登录不会卡在加载状态。
  startFallbackInspection()
})

onBeforeUnmount(() => {
  stopInspectionTimer()
  animationRef.value?.pause?.()
})
</script>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  overflow: hidden;
  padding: 36px;
  color: #f7fbff;
  background:
    radial-gradient(circle at 14% 16%, rgba(21, 154, 194, 0.2), transparent 34%),
    radial-gradient(circle at 86% 84%, rgba(240, 149, 74, 0.15), transparent 32%),
    linear-gradient(145deg, #071522 0%, #0b2232 48%, #102a39 100%);
}
.login-page::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0.17;
  background-image:
    linear-gradient(rgba(126, 211, 238, 0.18) 1px, transparent 1px),
    linear-gradient(90deg, rgba(126, 211, 238, 0.18) 1px, transparent 1px);
  background-size: 42px 42px;
  mask-image: linear-gradient(to bottom, #000, transparent 84%);
}
.ambient { position: absolute; border-radius: 50%; filter: blur(2px); pointer-events: none; }
.ambient-one { width: 420px; height: 420px; left: -170px; top: -160px; border: 1px solid rgba(78, 200, 235, 0.24); }
.ambient-two { width: 560px; height: 560px; right: -230px; bottom: -300px; border: 1px solid rgba(245, 171, 86, 0.22); }
.login-shell {
  position: relative;
  z-index: 1;
  width: min(1320px, 100%);
  min-height: 750px;
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(400px, 0.72fr);
  overflow: hidden;
  border: 1px solid rgba(142, 213, 235, 0.18);
  border-radius: 28px;
  background: rgba(8, 26, 39, 0.76);
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.38);
  backdrop-filter: blur(22px);
}
.animation-side { position: relative; display: flex; flex-direction: column; padding: 48px 54px 40px; overflow: hidden; }
.animation-side::after {
  content: '';
  position: absolute;
  width: 340px;
  height: 340px;
  left: 50%;
  top: 225px;
  transform: translate(-50%, -50%);
  background: rgba(19, 154, 198, 0.15);
  filter: blur(70px);
  border-radius: 50%;
  pointer-events: none;
}
.system-kicker { display: flex; align-items: center; gap: 11px; color: var(--hero-accent); font-size: 14px; letter-spacing: 0.18em; font-weight: 700; }
.pulse-dot, .status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #4ed6a0; box-shadow: 0 0 12px #4ed6a0; }
.pulse-dot { animation: pulse 1.8s infinite; }
.animation-copy h1 { margin: 20px 0 12px; color: #fff; font-size: clamp(28px, 2.6vw, 38px); line-height: 1.18; }
.animation-copy p { margin: 0; color: #a9c1cc; font-size: 16px; }
.animation-stage { position: relative; z-index: 1; flex: 1; min-height: 355px; margin: 26px 0 16px; overflow: hidden; border: 1px solid rgba(122, 207, 234, 0.2); border-radius: 22px; background: linear-gradient(155deg, rgba(13, 52, 72, 0.55), rgba(8, 26, 39, 0.15)); }
.system-animation { position: absolute; z-index: 2; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.stage-grid { position: absolute; inset: 0; opacity: 0.35; background: linear-gradient(rgba(92, 203, 237, 0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(92, 203, 237, 0.08) 1px, transparent 1px); background-size: 28px 28px; }
.animation-fallback { position: absolute; z-index: 1; inset: 0; display: grid; place-items: center; }
.road-symbol { font-size:110px; color:#409eff; z-index:2; }
.fallback-mascot { position: relative; z-index: 2; width: min(42%, 210px); height: 78%; object-fit: contain; filter: drop-shadow(0 16px 25px rgba(0, 0, 0, 0.35)); animation: mascot-float 3.2s ease-in-out infinite; }
.scan-ring { position: absolute; width: 230px; height: 230px; border-radius: 50%; border: 1px solid rgba(83, 210, 241, 0.36); animation: scan 3s linear infinite; }
.scan-ring-two { width: 310px; height: 310px; animation-delay: -1.5s; }
.magnifier { position: absolute; z-index: 3; width: 72px; height: 72px; margin: 15px 0 0 126px; border: 5px solid #83ddf5; border-radius: 50%; box-shadow: inset 0 0 18px rgba(70, 211, 247, 0.25), 0 0 18px rgba(70, 211, 247, 0.25); animation: inspect 2.7s ease-in-out infinite; }
.magnifier::after { content: ''; position: absolute; width: 46px; height: 6px; right: -34px; bottom: -18px; transform: rotate(48deg); border-radius: 8px; background: #83ddf5; }
.fallback-note { position: absolute; left: 18px; bottom: 14px; color: #7396a8; font-size: 11px; }
.inspection-state { position: relative; z-index: 2; }
.inspection-line { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 14px; font-size: 15px; }
.inspection-label { color: var(--hero-accent); }
.inspection-name { color: #d8eaf0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inspection-name.complete { color: #64dda9; font-weight: 700; }
.inspection-count { color: #7192a2; font-variant-numeric: tabular-nums; }
.progress-track { height: 5px; margin-top: 11px; overflow: hidden; border-radius: 4px; background: rgba(132, 203, 225, 0.13); }
.progress-track span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #3cc8ec, #f3a257); transition: width 0.5s ease; }
.progress-track span.complete { background: linear-gradient(90deg, #34c990, #73e6b8); box-shadow: 0 0 12px rgba(78, 214, 160, 0.32); }
.module-groups { position: relative; z-index: 2; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 28px; }
.module-group { padding: 17px 18px 18px; border: 1px solid rgba(128, 203, 226, 0.16); border-radius: 17px; background: rgba(6, 25, 38, 0.52); }
.group-title { margin-bottom: 13px; color: #a6c2cd; font-size: 14px; font-weight: 700; letter-spacing: 0.08em; }
.module-list { display: flex; gap: 9px; }
.module-chip { flex: 1; min-width: 0; min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 7px; padding: 10px 8px; border-radius: 10px; color: #829eaa; font-size: 13px; font-weight: 600; white-space: nowrap; transition: 0.35s ease; }
.module-chip.active { color: #e9fbff; background: rgba(41, 179, 219, 0.2); box-shadow: inset 0 0 0 1px rgba(90, 211, 242, 0.25); }
.agent-group .module-chip.active { background: rgba(225, 135, 59, 0.19); box-shadow: inset 0 0 0 1px rgba(245, 172, 91, 0.28); }
.module-chip.checked { color: #79e7bb; background: rgba(48, 183, 135, 0.14); box-shadow: inset 0 0 0 1px rgba(92, 220, 170, 0.2); }
.module-icon { font-size: 16px; line-height: 1; }
.login-panel { display: flex; flex-direction: column; justify-content: center; padding: 50px 44px; color: var(--text-primary); background: var(--surface); }
.brand { display: flex; align-items: center; gap: 13px; }
.brand-mascot { width: 62px; height: 62px; display: grid; place-items: center; border-radius: 16px; background: var(--primary-soft); color: var(--primary); font-size: 32px; font-weight: 700; flex-shrink: 0; }
.brand-eyebrow { color: var(--text-muted); font-size: 9px; font-weight: 700; letter-spacing: 0.12em; }
.brand h2 { margin: 4px 0 0; color: var(--text-primary); font-size: 19px; line-height: 1.3; }
.team { margin: 3px 0 0; color: var(--link); font-size: 12px; font-weight: 600; }
.login-heading { margin: 42px 0 24px; }
.login-heading h3 { margin: 0; color: var(--text-primary); font-size: 26px; }
.login-heading p { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.endpoint-box { margin: -8px 0 18px; border: 1px solid var(--border-color); border-radius: 10px; background: var(--surface-2); }
.endpoint-toggle { width: 100%; display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 0; color: var(--text-secondary); background: transparent; font: inherit; font-size: 12px; cursor: pointer; }
.endpoint-toggle span:first-child { color: var(--link); font-weight: 700; }
.endpoint-content { display: grid; gap: 10px; padding: 0 12px 12px; border-top: 1px solid var(--border-color); }
.endpoint-content label { display: grid; gap: 4px; padding-top: 9px; color: var(--text-secondary); font-size: 11px; }
.endpoint-actions { display: flex; justify-content: flex-end; gap: 7px; }
.endpoint-status { padding: 7px 9px; border-radius: 6px; font-size: 11px; }
.endpoint-status.success { color:var(--success); background:color-mix(in srgb,var(--success) 10%,var(--surface)); }
.endpoint-status.error { color:var(--danger); background:color-mix(in srgb,var(--danger) 10%,var(--surface)); }
.endpoint-help { margin: 0; color: var(--text-muted); font-size: 10px; line-height: 1.5; }
.role-group { display: flex; width: 100%; }
.role-group :deep(.ant-radio-button-wrapper) { flex: 1; padding-inline: 8px; text-align: center; border-color: var(--border-color); color: var(--text-secondary); }
.login-button { height:46px; margin-top:8px; font-weight:650; box-shadow:0 8px 24px color-mix(in srgb,var(--primary) 18%,transparent); }
.login-foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 34px; padding-top: 18px; border-top: 1px solid var(--border-color); color: var(--text-muted); font-size: 10px; }
.login-foot span:first-child { display: flex; align-items: center; gap: 7px; }
.status-dot { width: 6px; height: 6px; box-shadow: none; }
@keyframes pulse { 50% { opacity: 0.42; transform: scale(0.78); } }
@keyframes mascot-float { 50% { transform: translateY(-7px); } }
@keyframes scan { from { transform: scale(0.72); opacity: 0.7; } to { transform: scale(1.15); opacity: 0; } }
@keyframes inspect { 0%, 100% { transform: translate(-35px, 18px) rotate(-8deg); } 50% { transform: translate(38px, -14px) rotate(8deg); } }
@media (max-width: 900px) {
  .login-page { padding: 18px; align-items: start; overflow: auto; }
  .login-shell { grid-template-columns: 1fr; min-height: auto; }
  .animation-side { min-height: 540px; padding: 32px; }
  .login-panel { padding: 38px 32px; }
}
@media (max-width: 1180px) and (min-width: 901px) {
  .login-page { padding: 22px; }
  .login-shell { min-height: 690px; grid-template-columns: minmax(0, 1.35fr) minmax(370px, 0.72fr); }
  .animation-side { padding: 36px 38px 32px; }
  .animation-stage { min-height: 300px; }
  .module-group { padding: 13px; }
  .group-title { font-size: 14px; }
  .module-chip { min-height: 44px; padding: 9px 6px; font-size: 13px; }
  .module-icon { font-size: 15px; }
}
@media (max-height: 820px) and (min-width: 901px) {
  .login-page { padding-block: 18px; overflow-y: auto; }
  .login-shell { min-height: 680px; }
  .animation-side { padding-block: 34px 28px; }
  .animation-copy h1 { margin-top: 14px; font-size: 34px; }
  .animation-stage { min-height: 285px; margin-block: 18px 12px; }
  .module-groups { margin-top: 18px; }
  .module-group { padding-block: 13px 14px; }
  .login-panel { padding-block: 36px; }
  .login-heading { margin-block: 28px 20px; }
}
@media (max-width: 540px) {
  .login-page { padding: 0; }
  .login-shell { border: 0; border-radius: 0; }
  .animation-side { min-height: 480px; padding: 26px 20px; }
  .module-groups { grid-template-columns: 1fr; }
  .animation-stage { min-height: 235px; }
  .login-panel { padding: 38px 24px; }
  .login-foot { flex-direction: column; }
}
@media (prefers-reduced-motion: reduce) {
  .pulse-dot, .fallback-mascot, .scan-ring, .magnifier { animation: none; }
  .progress-track span, .module-chip { transition: none; }
}
</style>
