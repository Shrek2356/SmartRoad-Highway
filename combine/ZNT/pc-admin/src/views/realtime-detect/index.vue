<template>
  <!--
    实时检测页
    线下图片上传 / 摄像头截帧 → 检测桥接服务 → 各阶段协同展示 → 结果入库展示
    算法源码：detectmodel/Site_Safety_OpenRisk/
  -->
  <div class="page">
    <header class="head">
      <div class="head-text">
        <h1 class="page-title">实时检测</h1>
        <p class="desc">选择模式 → 上传图片 → 查看证据。真实风险按规则流转至结果与工单。</p>
      </div>
      <div class="head-actions">
        <a-tag :color="bridgeChecking ? 'processing' : bridgeOnline ? 'success' : 'error'">
          {{ bridgeChecking ? '正在连接检测服务' : bridgeOnline ? '检测服务已连接' : '检测服务离线' }}
        </a-tag>
        <a-button size="small" :loading="bridgeChecking" @click="refreshHealth">刷新连接</a-button>
        <a-button size="small" type="link" @click="codeOpen = true">算法源码</a-button>
      </div>
    </header>

    <section class="panel profile-panel">
      <div class="panel-title-row">
        <h2 class="panel-title">检测模式</h2>
        <span class="panel-sub">语义识别 · 空间定位 · 人工判断</span>
      </div>
      <div class="profile-group">
        <button
          v-for="item in modeOptions"
          :key="item.id"
          type="button"
          class="mode-card"
          :class="{ on: profile === item.id }"
          :aria-pressed="profile === item.id"
          :disabled="submitting"
          @click="profile = item.id"
        >
          <div class="mode-title">{{ item.label }}</div>
          <div class="mode-hint">{{ item.hint }}</div>
          <div class="mode-state" :class="modeReady(item.id) ? 'ok' : 'wait'">
            {{ modeReady(item.id) ? '可用' : '待配置' }}
          </div>
        </button>
      </div>
      <a-alert v-if="setupTip && profile !== 'demo'" class="mode-guidance" type="warning" show-icon :message="setupTip"><template #description><a-space wrap><router-link to="/help-center?tab=diagnostics">检查连接与处理方法 →</router-link><router-link v-if="user.role === 'admin'" to="/model-config?tab=runtime">前往配置模型 →</router-link></a-space></template></a-alert>
      <a-alert v-if="profile === 'demo'" class="mode-guidance" type="info" show-icon message="当前为演示模式：不会调用真实模型，也不能作为现场安全结论。" />

      <div v-if="profile === 'standard'" class="cloud-box">
        <div class="cloud-title">云端检测服务</div>
        <p class="cloud-desc">填写阿里云百炼 API Key 后即可使用云端 Qwen 视觉检测。</p>
        <div class="cloud-row">
          <a-input-password
            v-model:value="cloudKey"
            placeholder="DASHSCOPE_API_KEY"
            allow-clear
            class="cloud-input"
          />
          <a-button type="primary" :loading="savingKey" :disabled="!bridgeOnline" @click="saveCloudKey">
            保存并启用
          </a-button>
        </div>
        <p class="cloud-tip">
          {{
            bridgeOnline
              ? modeReady('standard')
                ? '云端已就绪，可直接开始检测。'
                : 'Key 保存后无需重启；若仍显示待配置，请点「刷新连接」。'
              : '请先启动检测桥接（8810），再保存 Key。'
          }}
        </p>
      </div>
    </section>

    <a-row :gutter="[12, 12]" class="main-workspace">
      <a-col :xs="24" :lg="10">
        <div class="panel left-panel">
          <a-tabs v-model:activeKey="tab" centered>
            <a-tab-pane key="upload" tab="线下图片上传">
              <a-upload-dragger
                :before-upload="onBeforeUpload"
                :show-upload-list="false"
                accept="image/jpeg,image/png,image/webp"
                class="upload-area"
              >
                <p class="ant-upload-drag-icon">📷</p>
                <p class="ant-upload-text">点击或拖拽图片到此处</p>
                <p class="ant-upload-hint">JPG / PNG / WebP，单张不超过 20 MB；也可选择下方示例</p>
              </a-upload-dragger>

              <div class="sample-block">
                <div class="sample-title">测试图片</div>
                <div class="sample-grid">
                  <div
                    v-for="ex in EXAMPLE_CASES"
                    :key="ex.id"
                    class="sample-card"
                    :class="{ active: selectedExampleId === ex.id }"
                    role="button"
                    tabindex="0"
                    :aria-label="`选择示例：${ex.title}`"
                    @keydown.enter="pickExample(ex)"
                    @keydown.space.prevent="pickExample(ex)"
                    @click="pickExample(ex)"
                  >
                    <img :src="ex.src" :alt="ex.title" />
                    <div class="sample-cap">
                      <div class="t">{{ ex.id }}. {{ ex.title }}</div>
                      <div class="r">{{ ex.risk }}</div>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="previewUrl" class="preview">
                <img :src="previewUrl" alt="待检测" />
              </div>
              <a-button
                type="primary"
                block
                class="detect-btn"
                :loading="submitting"
                :disabled="!pendingFile && !previewUrl"
                @click="startUploadDetect"
              >
                开始检测
              </a-button>
            </a-tab-pane>

            <a-tab-pane key="camera" tab="摄像头截帧">
              <div class="cam-box">
                <video ref="videoRef" class="cam-video" autoplay playsinline muted />
                <canvas ref="canvasRef" style="display: none" />
              </div>
              <div class="cam-actions">
                <a-button @click="startCamera" :disabled="camOn">打开摄像头</a-button>
                <a-button @click="stopCamera" :disabled="!camOn">关闭</a-button>
                <a-button type="primary" :loading="submitting" :disabled="!camOn" @click="captureAndDetect">
                  截帧并检测
                </a-button>
                <a-button :loading="submitting" :disabled="!camOn" @click="captureAndFullAudit">
                  立即全面检测
                </a-button>
              </div>
              <a-form layout="vertical" class="cam-form" size="small">
                <a-form-item label="设备编号">
                  <a-input v-model:value="deviceId" placeholder="CAM-WEB-01" />
                </a-form-item>
                <a-form-item label="RTSP / 流地址（预留）">
                  <a-input v-model:value="streamRef" placeholder="rtsp://..." />
                </a-form-item>
                <a-form-item label="大模型定时全面检测">
                  <a-select v-model:value="auditIntervalMinutes">
                    <a-select-option :value="30">每 30 分钟</a-select-option>
                    <a-select-option :value="120">每 2 小时</a-select-option>
                  </a-select>
                </a-form-item>
              </a-form>
              <p class="inline-tip">普通帧先经 YOLO 初筛；达到所选周期或点击“立即全面检测”时，绕过 YOLO 候选限制检查完整图像。</p>
            </a-tab-pane>
          </a-tabs>
        </div>
      </a-col>

      <a-col :xs="24" :lg="14">
        <div class="right-stack">
          <div class="panel recent-panel">
            <h2 class="panel-title">最近任务</h2>
            <div v-if="!recent.length" class="empty compact">还没有任务。先从左侧选择图片，或<router-link to="/detection-results">查看已有展示案例</router-link>。</div>
            <div v-else class="recent-list">
              <div
                v-for="item in recent"
                :key="item.job_id"
                class="recent-item"
                @click="loadJob(item.job_id)"
              >
                <div class="recent-main">
                  <div class="recent-id" :title="item.job_id">{{ shortJobId(item.job_id) }}</div>
                  <div class="recent-meta">
                    <span>{{ profileLabel(item.profile) }}</span>
                    <span>{{ sourceLabel(item.source) }}</span>
                    <span>{{ formatJobTime(item.created_at) }}</span>
                  </div>
                </div>
                <a-tag :color="statusColor(item.status)" class="recent-tag">{{ statusLabel(item.status) }}</a-tag>
              </div>
            </div>
          </div>

          <div class="panel">
            <h2 class="panel-title">各阶段协同进度</h2>
            <div v-if="!job" class="empty">上传图片或截帧后，将展示视觉模型 / 分割 / 核验 / 推理 / 处置协同过程</div>
            <div v-else class="stages">
              <div
                v-for="(s, i) in job.stages"
                :key="s.id"
                class="stage"
                :class="'s-' + s.status"
              >
                <div class="stage-no">{{ i + 1 }}</div>
                <div class="stage-body">
                  <div class="stage-name">
                    {{ s.name }}
                    <a-tag size="small">{{ s.agent }}</a-tag>
                  </div>
                  <div class="stage-msg">{{ s.message || statusLabel(s.status) }}</div>
                </div>
                <div class="stage-status">{{ statusLabel(s.status) }}</div>
              </div>
            </div>
            <div v-if="job" class="job-meta">
              <span class="job-meta-id" :title="job.job_id">{{ shortJobId(job.job_id) }}</span>
              <a-tag>{{ profileLabel(job.profile) }}</a-tag>
              <a-tag :color="statusColor(job.status)">{{ statusLabel(job.status) }}</a-tag>
              <span v-if="job.mock" class="job-meta-note">演示</span>
            </div>
            <a-alert v-if="job?.source === 'archive'" type="info" show-icon :message="`历史检测档案 · ${job.archive?.sample_id || ''}`" description="原图、掩码和报告来自此前检测，已归档留存；本次查看不重新检测，不生成现场告警或工单。" />
            <a-alert v-if="job?.source === 'learning_evaluation'" type="info" show-icon message="经验版本评测回放" description="此任务用于当前版与候选版对照；证据留存，不生成现场告警、工单或通知。" />
            <a-alert v-if="job?.error" type="error" :message="job.error" show-icon class="job-error" />
          </div>

          <div class="panel result-panel">
            <h2 class="panel-title">检测结果</h2>

            <template v-if="job?.result">
              <a-alert
                :type="job.result.risk_count || job.result.assessment_quality?.result_status === 'unable_to_assess' ? 'warning' : 'info'"
                show-icon
                :message="job.result.risk_count ? `保留 ${job.result.risk_count} 项观察，请核对证据与复核状态` : job.result.assessment_quality?.result_status === 'unable_to_assess' ? '画面不足以判断，请补充图像' : '未发现可见异常，不代表已确认安全'"
                :description="job.result.report_summary"
                class="result-alert"
              />
              <a-alert v-if="job.result.assessment_quality?.issues?.length" type="info" show-icon
                message="画面可判断范围" :description="job.result.assessment_quality.issues.join('；')" />
              <p v-if="job.result.issue_report"><a :href="job.result.issue_report" target="_blank" rel="noopener">查看自动问题报告与证据记录</a></p>
              <a-button class="reference-button" @click="referencesOpen = true">规范参考记录 · {{ referenceCount(job.result) }} 条关联引用</a-button>
              <a-button v-if="job.status === 'done' && job.profile !== 'demo' && job.source !== 'learning_evaluation' && !job.mock && ['admin','safety'].includes(user.role)" @click="correctionOpen = true">纠错与补标</a-button>
              <p v-if="job.result.case_memory">案例经验：{{ job.result.case_memory.version_id === 'none' ? '未启用经验版本' : job.result.case_memory.version_id }} · {{ ({ applied:'已辅助复查', no_match:'未检索到相关案例', disabled:'原始检测流程', unavailable:'经验已暂停', error:'参考失败，使用原始观察' })[job.result.case_memory.status] }}<br v-if="job.result.case_memory.detail" />{{ job.result.case_memory.detail || '' }}</p>
              <a-collapse v-if="job.result.case_memory?.references?.length"><a-collapse-panel key="case-memory" header="本次引用的人工案例"><p v-for="entry in job.result.case_memory.references" :key="entry.case_id">{{ entry.case_id }} · 文本相关性 {{ entry.score }}<br />{{ entry.reason }}</p></a-collapse-panel></a-collapse>
              <div v-if="job.result.screening" class="screening-summary">
                <a-tag :color="job.result.screening.triggered ? 'orange' : 'default'">
                  YOLO {{ job.result.screening.triggered ? '已触发' : '未触发' }}
                </a-tag>
                <a-tag>{{ ((job.result.screening.anomaly_score || 0) * 100).toFixed(0) }}%</a-tag>
                <a-tag :color="job.result.routed_to_vlm ? 'blue' : 'default'">
                  {{ job.result.routed_to_vlm ? '已送入VLM' : '实时门控跳过VLM' }}
                </a-tag>
                <span>{{ job.result.screening.reason }}</span>
              </div>
              <div v-else-if="job.result.full_audit" class="screening-summary">
                <a-tag color="purple">大模型全面检测</a-tag>
                <a-tag>{{ job.result.audit_mode === 'scheduled_full' ? '定时触发' : '人工/API触发' }}</a-tag>
                <span>已绕过 YOLO 候选提示，直接检查完整图像</span>
              </div>
              <div v-if="job.result.timings_ms" class="screening-summary timing-summary">
                <a-tag color="cyan">总耗时 {{ formatDuration(job.result.timings_ms.total) }}</a-tag>
                <a-tag>YOLO初筛 {{ formatDuration(job.result.timings_ms.screening) }}</a-tag>
                <a-tag v-if="job.result.timings_ms.vlm_sam_pipeline != null">
                  VLM+SAM流水线 {{ formatDuration(job.result.timings_ms.vlm_sam_pipeline) }}
                </a-tag>
                <a-tag v-if="job.result.timings_ms.agent_event != null">
                  Agent事件 {{ formatDuration(job.result.timings_ms.agent_event) }}
                </a-tag>
              </div>
              <a-row :gutter="12">
                <a-col :span="8">
                  <div class="img-label">输入图像</div>
                  <img class="result-img" :src="job.result.input_image" alt="input" />
                </a-col>
                <a-col :span="16">
                  <div class="img-label">场景与风险标注</div>
                  <DetectionLayers v-if="job.result.scene_layers?.length || job.result.risks?.some(r => r.mask)" :result="job.result" />
                  <div class="overlay-grid">
                    <img v-if="job.result.scene_annotation" class="result-img"
                      :src="job.result.scene_annotation" alt="道路及路牌场景标注"
                      @click="openPreview(job.result.scene_annotation)" />
                    <img
                      v-for="(u, i) in job.result.overlays"
                      :key="i"
                      class="result-img"
                      :src="u"
                      alt="overlay"
                      @click="openPreview(u)"
                    />
                    <img
                      v-if="job.result.screening_overlay"
                      class="result-img"
                      :src="job.result.screening_overlay"
                      alt="YOLO screening overlay"
                      @click="openPreview(job.result.screening_overlay)"
                    />
                    <div v-if="!job.result.overlays?.length && !job.result.screening_overlay && !job.result.scene_annotation" class="empty compact">暂无叠加图</div>
                  </div>
                </a-col>
              </a-row>

              <a-table
                class="risk-table"
                size="small"
                row-key="name"
                :pagination="false"
                :data-source="job.result.risks || []"
                :columns="riskColumns"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'confidence'">
                    {{ ((record.confidence || 0) * 100).toFixed(0) }}%
                  </template>
                  <template v-else-if="column.key === 'verified'">
                    <a-tag :color="record.verified ? 'success' : 'default'">
                      {{ record.verified ? '已确认' : '未确认' }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.key === 'manual_review'">
                    <a-tag :color="record.manual_review ? 'orange' : 'green'">
                      {{ record.manual_review ? '需复核' : '免复核' }}
                    </a-tag>
                  </template>
                </template>
              </a-table>
              <div v-for="risk in job.result.risks || []" :key="`${risk.risk_id}-refs`">
                <a-alert v-if="risk.evidence_state?.observation" type="info" show-icon class="rag-reference"
                  :message="`${risk.name} · ${roadEvidenceLabel(risk.evidence_state.localization)}`">
                  <template #description>
                    <p>{{ risk.description }}</p>
                    <p>道路影响：{{ risk.evidence_state.road_impact === 'supported' ? '自动证据支持，待业务复核' : '尚未确定' }}。模型分数不是准确率，定位预测不是真值。</p>
                    <div v-for="reason in risk.evidence_state.review_reasons || []" :key="reason">{{ reason }}</div>
                  </template>
                </a-alert>
              </div>
            </template>
            <div v-else class="empty">等待检测完成…</div>
          </div>
        </div>
      </a-col>
    </a-row>

    <RegulatoryReferenceDialog v-model:open="referencesOpen" :job="job" />
    <CorrectionDialog v-model:open="correctionOpen" :job-id="job?.job_id" />
    <a-modal v-model:open="codeOpen" title="算法源码与启动" :footer="null" width="680px">
      <p>目录：<code class="path">detectmodel/Site_Safety_OpenRisk/</code></p>
      <pre class="code">cd detectmodel/Site_Safety_OpenRisk
python detect_bridge.py --port 8810</pre>
    </a-modal>

    <a-modal v-model:open="previewOpen" :footer="null" width="860px" @cancel="closePreview">
      <img v-if="preview" :src="preview" style="width: 100%" alt="preview" />
    </a-modal>
  </div>
</template>

<script setup>
/**
 * 实时检测：优先调用 detect_bridge；离线则本地 Mock 演示全流程
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { normalizeDetectionProfile, detectionBlockReason } from '@/utils/detectionIntent'
import { message } from 'ant-design-vue'
import {
  advanceMockJob,
  checkDetectHealth,
  detectCameraFrame,
  detectFullAudit,
  fetchDetectJob,
  fetchRecentJobs,
  mockDetectPipeline,
  saveDetectCloudKey,
  uploadDetectImage,
} from '@/api/detect'
import { EXAMPLE_CASES } from '@/mock/examples'
import { syncDetectJobToWorkOrders } from '@/utils/detectWorkOrders'
import { syncDetectJobToResults } from '@/utils/detectResults'
import { referenceCount } from '@/utils/regulatoryReferences'
import RegulatoryReferenceDialog from '@/components/RegulatoryReferenceDialog.vue'
import CorrectionDialog from '@/components/CorrectionDialog.vue'
import DetectionLayers from '@/components/DetectionLayers.vue'
const correctionOpen = ref(false)

const route = useRoute()
const user = useUserStore()
watch(() => route.query.job, id => { if (id) loadJob(String(id)) })
const FALLBACK_PROFILES = [
  { id: 'standard', ready: false, missing: ['cloud_api'] },
  { id: 'offline', ready: false, missing: ['service_unavailable'] },
  { id: 'demo', ready: true, missing: [] },
]

const modeOptions = [
  { id: 'standard', label: '云端检测', hint: '云端视觉 API + 本地定位，需要网络与密钥' },
  { id: 'offline', label: '本地离线', hint: '本地部署，适合离线场景' },
  { id: 'demo', label: '演示模式', hint: '仅做前端 Mock 演示' },
]

const SETUP_HINTS = {
  cloud_api: '请在下方填写 DASHSCOPE_API_KEY 并保存',
  sam3_weights: '在模型配置中选择 SAM3 代码目录与权重',
  clip_weights: '选择 CLIP 权重，或按需求关闭该可选组件',
  yolo_weights: '在模型配置中选择 YOLO 权重',
  local_qwen_config: '请在「模型规则配置 - 模型部件与运行时」选择 Qwen 与 mmproj 路径',
}

const tab = ref('upload')
const bridgeOnline = ref(false)
const bridgeChecking = ref(true)
const profiles = ref([...FALLBACK_PROFILES])
const profile = ref(normalizeDetectionProfile(route.query.profile))
watch(() => route.query.profile, value => { if (value) profile.value = normalizeDetectionProfile(value) })
const submitting = ref(false)
const cloudKey = ref('')
const savingKey = ref(false)
const currentProfile = computed(() => profiles.value.find((p) => p.id === profile.value))

const setupTip = computed(() => {
  if (bridgeChecking.value) return '正在读取检测桥状态与模型运行配置…'
  if (!bridgeOnline.value) return '检测桥未连接。先恢复连接再提交真实检测；不会自动切换成演示模式。'
  const p = currentProfile.value
  if (p?.id === 'offline' && p.ready && p.runtime_ready === false) {
    return '模型文件已配置，但本地 Qwen 尚未在线；请在「模型部件与运行时」启动并等待连接成功。'
  }
  if (!p || p.ready || !p.missing?.length) return ''
  const steps = p.missing.map((k) => SETUP_HINTS[k] || k).filter(Boolean)
  return `待配置：${steps.join('；')}`
})

function modeReady(id) {
  if (id === 'demo') return true
  if (!bridgeOnline.value) return id === 'demo'
  const p = profiles.value.find((x) => x.id === id)
  if (id === 'offline' && p?.runtime_ready !== undefined) return !!p.runtime_ready
  return !!p?.ready
}

function profileLabel(id) {
  return {
    standard: '云端 Qwen API',
    offline: '本地离线',
    demo: '浏览器演示',
    weights: '本地离线',
    archive: '历史检测档案',
  }[id] || id || '未指定'
}

function shortJobId(id = '') {
  const text = String(id)
  if (text.length <= 22) return text
  return `${text.slice(0, 12)}…${text.slice(-6)}`
}

function formatJobTime(value = '') {
  if (!value) return '-'
  const m = String(value).match(/(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})/)
  if (m) return `${m[2]}-${m[3]} ${m[4]}:${m[5]}`
  return String(value).slice(0, 16)
}

function formatDuration(value) {
  const ms = Number(value)
  if (!Number.isFinite(ms)) return '-'
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms.toFixed(0)}ms`
}

function sourceLabel(source = '') {
  return { upload: '上传', camera: '摄像头', offline: '上传', archive: '历史导入' }[source] || source || '-'
}

const pendingFile = ref(null)
const previewUrl = ref('')
const selectedExampleId = ref(null)
const deviceId = ref('CAM-WEB-01')
const streamRef = ref('')
const auditIntervalMinutes = ref(30)
const job = ref(null)
const recent = ref([])
const codeOpen = ref(false)
const referencesOpen = ref(false)
const preview = ref('')
const previewOpen = ref(false)
const camOn = ref(false)
const videoRef = ref(null)
const canvasRef = ref(null)
let mediaStream = null
let pollTimer = null

const riskColumns = [
  { title: '风险', dataIndex: 'name', key: 'name' },
  { title: '等级', dataIndex: 'level_zh', key: 'level_zh', width: 100 },
  { title: '模型分数', key: 'confidence', width: 90 },
  { title: '确认', key: 'verified', width: 90 },
  { title: '复核', key: 'manual_review', width: 90 },
]

function roadEvidenceLabel(value) {
  return { not_attempted: '未尝试定位，观察已保留', missing: '定位失败，观察已保留', partial: '仅部分目标定位', predicted: '已生成定位预测，需核对' }[value] || '定位状态未知'
}

function statusColor(s) {
  return { done: 'success', running: 'processing', queued: 'orange', error: 'error' }[s] || 'default'
}
function statusLabel(s) {
  return {
    pending: '等待',
    running: '进行中',
    done: '完成',
    error: '失败',
    skipped: '跳过',
    queued: '排队',
  }[s] || s
}

async function refreshHealth() {
  bridgeChecking.value = true
  try {
    const h = await checkDetectHealth()
    bridgeOnline.value = !!h.online
    if (h.online && Array.isArray(h.profiles) && h.profiles.length) {
      profiles.value = h.profiles
    } else if (!h.online) {
      profiles.value = FALLBACK_PROFILES
    }
  } finally {
    bridgeChecking.value = false
  }
}

async function saveCloudKey() {
  const key = cloudKey.value.trim()
  if (key.length < 8) {
    message.warning('请填写有效的 API Key')
    return
  }
  if (!bridgeOnline.value) {
    message.warning('检测服务未连接，无法写入 Key')
    return
  }
  savingKey.value = true
  try {
    const data = await saveDetectCloudKey({ apiKey: key, persist: true })
    if (Array.isArray(data.profiles)) profiles.value = data.profiles
    bridgeOnline.value = true
    profile.value = 'standard'
    cloudKey.value = ''
    message.success(data.profiles?.find((p) => p.id === 'standard')?.ready ? '云端检测已启用' : 'Key 已保存，请检查权重配置')
    await refreshHealth()
  } catch (e) {
    message.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    savingKey.value = false
  }
}

function onBeforeUpload(file) {
  if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 20 * 1024 * 1024) {
    message.warning('请选择 JPG、PNG 或 WebP 图片，单张不超过 20 MB。'); return false
  }
  releasePreview()
  selectedExampleId.value = null
  pendingFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  return false
}

async function pickExample(ex) {
  try {
    const resp = await fetch(ex.src)
    if (!resp.ok || !resp.headers.get('content-type')?.startsWith('image/')) throw new Error('示例图片未找到')
    const blob = await resp.blob()
    const file = new File([blob], `example-case${ex.id}.png`, { type: blob.type || 'image/png' })
    releasePreview()
    selectedExampleId.value = ex.id
    pendingFile.value = file
    previewUrl.value = ex.src
    message.success(`已选择：${ex.title}`)
  } catch {
    message.error('加载测试图失败')
  }
}

async function startUploadDetect() {
  if (!pendingFile.value && !previewUrl.value) {
    message.warning('请先选择图片')
    return
  }
  submitting.value = true
  try {
    await refreshHealth()
    if (detectionBlockReason(profile.value, { online:bridgeOnline.value, profiles:profiles.value })) {
      message.warning(setupTip.value || '当前检测模式尚未配置完整')
      return
    }
    if (bridgeOnline.value && pendingFile.value && profile.value !== 'demo') {
      const res = await uploadDetectImage(pendingFile.value, { profile: profile.value })
      await loadJob(res.job_id)
      message.success('已提交')
    } else {
      const res = await mockDetectPipeline({
        source: 'upload',
        fileName: pendingFile.value?.name,
        exampleId: selectedExampleId.value,
        previewUrl: previewUrl.value,
      })
      job.value = { ...res.data, profile: 'demo' }
      startMockPoll()
      message.info('已按你选择的演示模式运行，不会调用真实模型')
    }
    recent.value = await fetchRecentJobs()
  } catch (e) {
    message.error(e?.response?.data?.detail || e?.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

async function startCamera() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
    if (videoRef.value) {
      videoRef.value.srcObject = mediaStream
    }
    camOn.value = true
  } catch {
    message.error('无法打开摄像头，请检查浏览器权限')
  }
}

function stopCamera() {
  mediaStream?.getTracks()?.forEach((t) => t.stop())
  mediaStream = null
  camOn.value = false
  if (videoRef.value) videoRef.value.srcObject = null
}

function captureCameraFrame() {
  if (!videoRef.value || !canvasRef.value) return
  const video = videoRef.value
  const canvas = canvasRef.value
  canvas.width = video.videoWidth || 640
  canvas.height = video.videoHeight || 480
  const ctx = canvas.getContext('2d')
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  const dataUrl = canvas.toDataURL('image/jpeg', 0.92)
  releasePreview()
  previewUrl.value = dataUrl
  return dataUrl
}

async function captureAndDetect() {
  const dataUrl = captureCameraFrame()
  if (!dataUrl) return

  submitting.value = true
  try {
    await refreshHealth()
    if (profile.value !== 'demo' && !modeReady(profile.value)) {
      message.warning(setupTip.value || '当前检测模式尚未配置完整')
      return
    }
    if (bridgeOnline.value) {
      const res = await detectCameraFrame({
        imageBase64: dataUrl,
        deviceId: deviceId.value,
        streamRef: streamRef.value,
        profile: profile.value,
        auditIntervalMinutes: auditIntervalMinutes.value,
      })
      await loadJob(res.job_id)
      message.success('已提交')
    } else {
      const res = await mockDetectPipeline({ source: 'camera' })
      job.value = { ...res.data, profile: 'demo' }
      startMockPoll()
      message.info('检测服务离线，已启用本地演示流程')
    }
    recent.value = await fetchRecentJobs()
  } catch (e) {
    message.error(e?.response?.data?.detail || e?.message || '截帧检测失败')
  } finally {
    submitting.value = false
  }
}

async function captureAndFullAudit() {
  const dataUrl = captureCameraFrame()
  if (!dataUrl) return
  submitting.value = true
  try {
    await refreshHealth()
    if (profile.value !== 'demo' && !modeReady(profile.value)) {
      message.warning(setupTip.value || '当前检测模式尚未配置完整')
      return
    }
    if (bridgeOnline.value) {
      const res = await detectFullAudit({
        imageBase64: dataUrl,
        deviceId: deviceId.value,
        streamRef: streamRef.value,
        profile: profile.value,
        auditIntervalMinutes: auditIntervalMinutes.value,
      })
      await loadJob(res.job_id)
      message.success('已提交完整图像检测')
    } else {
      const res = await mockDetectPipeline({ source: 'camera' })
      job.value = { ...res.data, profile: 'demo' }
      startMockPoll()
      message.info('检测服务离线，已启用本地演示流程')
    }
    recent.value = await fetchRecentJobs()
  } catch (e) {
    message.error(e?.response?.data?.detail || e?.message || '全面检测提交失败')
  } finally {
    submitting.value = false
  }
}

function ingestWorkOrders(currentJob) {
  if (currentJob?.source === 'archive') return
  if (!currentJob || currentJob.status !== 'done') return
  syncDetectJobToResults(currentJob)
  if (currentJob._ordersSynced) return
  const { created } = syncDetectJobToWorkOrders(currentJob)
  currentJob._ordersSynced = true
  if (created > 0) {
    message.success(`已同步结果汇总，并生成 ${created} 条待处置工单`)
  }
}

let pollGeneration = 0
async function loadJob(jobId) {
  stopPoll()
  if (String(jobId).startsWith('MOCK')) return
  const generation = pollGeneration
  let failures = 0
  async function poll() {
    try {
      const data = await fetchDetectJob(jobId)
      if (generation !== pollGeneration) return
      failures = 0
      job.value = data
      if (data.status === 'done') ingestWorkOrders(data)
      if (['done', 'error', 'cancelled'].includes(data.status)) return
    } catch (error) {
      if (generation !== pollGeneration) return
      failures++
      if (failures === 1) message.warning('任务连接暂时中断，正在自动重连；任务仍在后台执行')
      if (error.response?.status === 404) { message.error('任务不存在或已按保留策略清理'); return }
    }
    if (generation === pollGeneration) pollTimer = setTimeout(poll, Math.min(15000, 1000 * 2 ** Math.min(failures, 4)))
  }
  await poll()
}

function startMockPoll() {
  stopPoll()
  pollTimer = setInterval(() => {
    if (!job.value) {
      stopPoll()
      return
    }
    if (job.value.status === 'done') {
      ingestWorkOrders(job.value)
      stopPoll()
      return
    }
    job.value = advanceMockJob(job.value)
    if (job.value.status === 'done') ingestWorkOrders(job.value)
  }, 450)
}

function stopPoll() {
  pollGeneration++
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function openPreview(url) {
  preview.value = url
  previewOpen.value = true
}
function closePreview() {
  previewOpen.value = false
  preview.value = ''
}

onMounted(async () => {
  await refreshHealth()
  recent.value = await fetchRecentJobs()
  if (route.query.job) await loadJob(String(route.query.job))
})

function releasePreview() { if (previewUrl.value.startsWith('blob:')) URL.revokeObjectURL(previewUrl.value) }
onBeforeUnmount(() => {
  stopPoll()
  stopCamera()
  releasePreview()
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 8px;
  background: transparent;
}
.page :deep(.ant-upload-drag) {
  text-align: center;
}
.page :deep(.ant-upload-drag:hover) {
  border-color: var(--primary);
  background: var(--surface-2);
}
.page :deep(.ant-upload-drag:focus-within) {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-soft);
}
.page :deep(.ant-upload-text),
.page :deep(.ant-upload-hint) {
  text-align: center;
}
.page :deep(.ant-upload-text) {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.page :deep(.ant-upload-hint) {
  font-size: 12px;
  color: var(--text-secondary);
}

.head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 14px 16px;
}
.head-text {
  text-align: left;
  flex: 1;
  min-width: 0;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.25;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}
.desc {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.45;
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 12px 14px;
}
.panel-title-row {
  display: flex;
  align-items: baseline;
  justify-content: flex-start;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.panel-title {
  margin: 0 0 10px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  text-align: center;
  line-height: 1.3;
}
.panel-title-row .panel-title {
  margin: 0;
  font-size: 18px;
  text-align: left;
}
.panel-sub {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.profile-panel .panel-title-row {
  margin-bottom: 12px;
}
.profile-group {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  width: 100%;
}
.mode-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: 12px 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  background: var(--surface-muted);
  min-height: 92px;
  text-align: center;
  transition: border-color 0.15s, background 0.15s;
}
.mode-card.on {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 12%, var(--surface));
}
.mode-card:active {
  transform: translateY(1px);
}
.mode-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
}
.mode-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}
.mode-state {
  margin-top: 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
}
.mode-state.ok { color: var(--success); }
.mode-state.wait { color: var(--warning); }
.profile-miss {
  margin: 10px 0 0;
  color: var(--warning);
  font-size: 12px;
  line-height: 1.5;
  text-align: center;
}

.cloud-box {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px dashed var(--primary);
  border-radius: 8px;
  background: color-mix(in srgb, var(--warning) 8%, var(--surface));
  text-align: center;
}
.cloud-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}
.cloud-desc {
  margin: 4px 0 10px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.45;
}
.cloud-row {
  display: flex;
  gap: 8px;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
}
.cloud-input {
  max-width: 420px;
  flex: 1;
  min-width: 220px;
}
.cloud-tip {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.main-workspace {
  align-items: flex-start;
}
.left-panel :deep(.ant-tabs-nav) {
  margin-bottom: 10px;
}
.right-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.recent-panel {
  margin-top: 0;
}
.detect-btn {
  margin-top: 10px;
}
.preview {
  margin-top: 10px;
  border-radius: 8px;
  overflow: hidden;
  background: var(--media-bg);
  max-height: 180px;
}
.preview img {
  width: 100%;
  max-height: 180px;
  object-fit: contain;
  display: block;
}
.sample-block { margin-top: 12px; }
.sample-title {
  font-size: 13px;
  font-weight: 650;
  margin-bottom: 8px;
  color: var(--text-primary);
  text-align: center;
}
.sample-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  max-height: 220px;
  overflow: auto;
}
.sample-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--surface-muted);
}
.sample-card:hover,
.sample-card.active {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(242, 106, 87, 0.18);
}
.sample-card img {
  width: 100%;
  height: 64px;
  object-fit: cover;
  display: block;
  background: var(--media-bg);
}
.sample-cap {
  padding: 5px 6px;
  text-align: center;
}
.sample-cap .t {
  font-size: 11px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--text-primary);
}
.sample-cap .r {
  font-size: 10px;
  color: var(--text-secondary);
  margin-top: 2px;
}
.cam-box {
  background: var(--media-bg);
  border-radius: 8px;
  overflow: hidden;
  min-height: 180px;
}
.cam-video {
  width: 100%;
  max-height: 220px;
  background: #000;
  display: block;
}
.cam-actions {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}
.cam-form {
  margin-top: 10px;
  max-width: 420px;
  margin-left: auto;
  margin-right: auto;
}
.inline-tip {
  margin: 0;
  font-size: 11px;
  color: var(--text-secondary);
  text-align: center;
  line-height: 1.4;
}
.stages {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.stage {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--surface-muted);
  border-left: 3px solid var(--border-color);
}
.stage.s-running { border-left-color: var(--primary); background: color-mix(in srgb, var(--primary) 12%, var(--surface)); }
.stage.s-done { border-left-color: var(--success); background: color-mix(in srgb, var(--success) 12%, var(--surface)); }
.stage.s-error { border-left-color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, var(--surface)); }
.stage-no {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--link);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.stage-body { flex: 1; min-width: 0; }
.stage-name {
  font-weight: 600;
  font-size: 13px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.stage-msg {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}
.stage-status {
  font-size: 12px;
  color: var(--text-secondary);
  flex-shrink: 0;
}
.job-meta {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}
.job-meta-id {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.job-meta-note { color: var(--text-secondary); }
.job-error { margin-top: 10px; }
.empty {
  color: var(--text-secondary);
  font-size: 13px;
  padding: 16px 8px;
  text-align: center;
  line-height: 1.5;
}
.empty.compact {
  padding: 10px 0;
  font-size: 12px;
}
.img-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
  text-align: center;
}
.result-alert { margin-bottom: 10px; }
.screening-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0 0 10px;
  color: var(--text-secondary);
  font-size: 12px;
}
.risk-table { margin-top: 10px; }
.result-img {
  width: 100%;
  border-radius: 8px;
  background: var(--media-bg);
  max-height: 160px;
  object-fit: cover;
  cursor: zoom-in;
}
.overlay-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.recent-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow: auto;
}
.recent-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--surface-muted);
  cursor: pointer;
}
.recent-item:hover {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--warning) 10%, var(--surface));
}
.recent-main {
  min-width: 0;
  flex: 1;
  text-align: left;
}
.recent-id {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-meta {
  margin-top: 2px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.4;
}
.recent-tag {
  flex-shrink: 0;
  margin: 0 !important;
}
.path {
  display: block;
  background: var(--surface-muted);
  padding: 8px 10px;
  border-radius: 6px;
  color: var(--link);
  word-break: break-all;
}
.code {
  background: var(--media-bg);
  color: #fff5ef;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.55;
  overflow: auto;
}
@media (max-width: 900px) {
  .profile-group { grid-template-columns: 1fr; }
  .head {
    flex-direction: column;
    align-items: stretch;
  }
  .head-actions {
    justify-content: center;
  }
}
.mode-guidance{margin-top:16px}.profile-group button:disabled{cursor:wait;opacity:.7}.sample-card{border-radius:12px}.sample-card:focus-visible{outline:2px solid var(--primary);outline-offset:3px}
.page { gap:16px; }
.head { padding:22px 24px; }
.panel { padding:20px; }
.panel-title { text-align:left; font-size:15px; }
.mode-card { align-items:flex-start; text-align:left; padding:18px 20px; border-radius:12px; }
.mode-card.on { background:var(--primary-soft); box-shadow:inset 0 0 0 1px var(--primary); }
.mode-card:hover:not(:disabled) { border-color:var(--primary); }
.mode-title { font-size:16px; }
</style>
