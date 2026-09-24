<template>
  <a-modal :open="open" title="检测纠错 · 原图与人工标注" width="1180px" :confirm-loading="saving" :ok-button-props="{ disabled: !context || !!error }" ok-text="提交待审核案例" @ok="submit" @cancel="$emit('update:open', false)">
    <a-spin :spinning="loading">
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <div v-if="context" class="correction-grid">
        <section>
          <p>{{ jobId }} · 原始结果保留，纠正作为独立记录追加</p>
          <div class="annotation-image">
            <img :src="imageUrl" alt="待纠错的检测原图" draggable="false" @load="imageReady = true" @error="error = '原图加载失败，无法提交可复核标注'" />
            <svg v-if="imageReady" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="目标范围标注区" @pointerdown="begin" @pointermove="move" @pointerup="finish" @pointercancel="cancelDraw">
              <rect v-for="(label, i) in labels.filter(l => l.bbox)" :key="i" :x="label.bbox[0]" :y="label.bbox[1]" :width="label.bbox[2]-label.bbox[0]" :height="label.bbox[3]-label.bbox[1]" class="saved-box" />
              <rect v-if="box" :x="box[0]" :y="box[1]" :width="box[2]-box[0]" :height="box[3]-box[1]" class="draft-box" />
            </svg>
          </div>
          <p>在图中按住拖动画框，再添加判断。框是目标范围，不是像素级掩码。正常画面无需框。</p>
          <a-collapse><a-collapse-panel key="original" header="查看原始模型结论"><p>{{ context.result?.report_summary || '原记录无文字摘要' }}</p><a-tag v-for="risk in context.result?.risks || []" :key="risk.risk_id">{{ risk.name || risk.risk_id }} · {{ risk.verified ? '模型保留' : '待复核' }}</a-tag></a-collapse-panel></a-collapse>
        </section>
        <a-form layout="vertical">
          <a-form-item label="本次纠正类型"><a-select v-model:value="kind" :options="correctionKinds" /></a-form-item>
          <template v-if="kind !== 'normal'">
            <a-form-item label="目标类别"><a-select v-model:value="riskId" show-search option-filter-prop="label" :options="riskOptions" /></a-form-item>
            <a-row v-if="riskId === '__new'" :gutter="8"><a-col :span="12"><a-form-item label="新类别编号"><a-input v-model:value="newId" placeholder="open_英文名称" /></a-form-item></a-col><a-col :span="12"><a-form-item label="新类别名称"><a-input v-model:value="newName" placeholder="可见异常名称" /></a-form-item></a-col></a-row>
            <a-space wrap><a-radio-group v-model:value="present" @change="box = null"><a-radio :value="true">实际存在</a-radio><a-radio :value="false">实际不存在</a-radio></a-radio-group><a-button @click="addLabel">添加此项判断</a-button><a-button v-if="box" type="link" @click="box = null">清除待添加框</a-button></a-space>
            <ul class="labels"><li v-for="(label, i) in labels" :key="i">{{ label.name }} · {{ label.present ? '存在' : '不存在' }} · {{ label.bbox ? '有范围框' : '无范围框' }} <a-button size="small" type="link" danger @click="labels.splice(i, 1)">移除</a-button></li></ul>
          </template>
          <a-form-item label="可见证据 / 排除依据 / 新类别定义"><a-textarea v-model:value="reason" :rows="3" :maxlength="2000" placeholder="例如：路面只有雨后反光，标线仍连续清楚，没有积聚水体或漫流边界。请根据当前图填写。" /></a-form-item>
          <a-form-item label="来源分组"><a-input v-model:value="group" :maxlength="160" /><small>同一视频、相邻帧或同一采集批次填相同分组，禁止跨数据用途。</small></a-form-item>
          <a-form-item label="数据用途"><a-select v-model:value="partition" :options="partitions" /></a-form-item>
          <a-checkbox v-model:checked="complete">已复查整张图，以上列出了全部可见异常</a-checkbox>
          <p v-if="kind === 'novel_class'">新类别按候选保留；审核通过后可作案例参考，不会自动修改正式风险目录。</p>
        </a-form>
      </div>
    </a-spin>
  </a-modal>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { correctionContext, submitCorrection, learningError } from '@/api/continuousLearning'
import { resolveBusinessMediaUrl } from '@/utils/endpoints'
import { normalizedPoint, normalizedBox, correctionKinds, partitions } from '@/utils/correctionGeometry'
const props = defineProps({ open: Boolean, jobId: String })
const emit = defineEmits(['update:open', 'submitted'])
const context = ref(null), loading = ref(false), saving = ref(false), error = ref(''), imageReady = ref(false)
const kind = ref('false_positive'), partition = ref('train'), riskId = ref(''), newId = ref('open_'), newName = ref('')
const present = ref(false), labels = ref([]), reason = ref(''), group = ref(''), complete = ref(false), box = ref(null)
const imageUrl = computed(() => resolveBusinessMediaUrl(context.value?.image_url || ''))
const riskOptions = computed(() => [...(context.value?.catalog || []).map(r => ({ value: r.risk_id, label: r.name_zh })), { value: '__new', label: '新增目录外类别…' }])
let generation = 0, start = null
watch(() => [props.open, props.jobId], async () => {
  const ticket = ++generation
  context.value = null; error.value = ''; loading.value = false; imageReady.value = false; start = null
  if (!props.open || !props.jobId) return
  labels.value = []; box.value = null; reason.value = ''; complete.value = false; kind.value = 'false_positive'; partition.value = 'train'; present.value = false
  loading.value = true
  try { const res = await correctionContext(props.jobId); if (ticket === generation) { context.value = res.data; group.value = res.data.group_key; riskId.value = res.data.catalog[0]?.risk_id || '' } }
  catch (err) { if (ticket === generation) error.value = learningError(err) }
  finally { if (ticket === generation) loading.value = false }
})
watch(kind, value => { box.value = null; if (value === 'normal') labels.value = []; if (value === 'novel_class') riskId.value = '__new'; present.value = !['false_positive', 'normal'].includes(value) })
function begin(event) { if (!present.value || kind.value === 'normal' || event.button !== 0) return; start = normalizedPoint(event, event.currentTarget.getBoundingClientRect()); box.value = null; event.currentTarget.setPointerCapture(event.pointerId) }
function move(event) { if (start) box.value = normalizedBox(start, normalizedPoint(event, event.currentTarget.getBoundingClientRect())) }
function finish(event) { move(event); start = null }
function cancelDraw() { start = null; box.value = null }
function addLabel() {
  const id = riskId.value === '__new' ? newId.value.trim() : riskId.value
  const name = riskId.value === '__new' ? newName.value.trim() : riskOptions.value.find(r => r.value === id)?.label
  if (!id || !name || (riskId.value === '__new' && !/^open_[a-z0-9_]{2,60}$/.test(id))) { message.warning('请填写有效的类别和名称'); return }
  if (labels.value.some(l => l.risk_id === id)) { message.warning('该类别已添加，请移除旧判断后重新标注'); return }
  labels.value.push({ risk_id: id, name, present: present.value, bbox: present.value ? box.value : null }); box.value = null
}
async function submit() {
  if (saving.value || !context.value || !imageReady.value) return
  if (box.value) { message.warning('画框后请先点击“添加此项判断”'); return }
  saving.value = true
  try { await submitCorrection({ job_id: props.jobId, kind: kind.value, partition: partition.value, labels: labels.value, reason: reason.value, group_key: group.value, complete: complete.value }); message.success('已保存原图与纠正，等待审核'); emit('submitted'); emit('update:open', false) }
  catch (err) { message.error(learningError(err)) }
  finally { saving.value = false }
}
</script>
<style scoped>
.correction-grid { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(320px,1fr); gap:24px; padding-top:12px; }
.annotation-image { position:relative; line-height:0; }
.annotation-image img { display:block; width:100%; user-select:none; }
.annotation-image svg { position:absolute; inset:0; width:100%; height:100%; touch-action:none; cursor:crosshair; }
.saved-box, .draft-box { fill:transparent; stroke:var(--text-primary); stroke-width:.003; vector-effect:non-scaling-stroke; }
.saved-box { stroke:#e8ae49; stroke-width:2px; } .draft-box { stroke-width:2px; stroke-dasharray:5 3; }
.labels { padding-left:20px; } p, small { color:var(--text-secondary); line-height:1.65; }
@media(max-width:850px) { .correction-grid { grid-template-columns:minmax(0,1fr); } }
</style>
