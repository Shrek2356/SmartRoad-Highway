<template>
  <div class="learning-center">
    <a-alert type="info" show-icon message="先纠正并审核，再积累案例，最后回放验证" description="当前升级使用人工案例辅助大模型复查。不会自动训练模型或用模型判断充当标签；正式风险目录保持人工管理。" />
    <div class="learning-stats">
      <div><small>待审核案例</small><strong>{{ data.cases.filter(c => c.status === 'pending').length }}</strong></div>
      <div><small>已审核经验 / 训练</small><strong>{{ approved('train') }}</strong></div>
      <div><small>已审核验证 / 测试</small><strong>{{ approved('validation') + approved('holdout') }}</strong></div>
      <div><small>当前经验版本</small><strong class="version-name">{{ data.active.version_id === 'none' ? '原始检测流程' : data.active.version_id }}</strong></div>
    </div>
    <a-space wrap class="toolbar">
      <a-button :loading="loading" @click="load">刷新记录</a-button>
      <a-button v-if="canReview" @click="loadAudits">抽查未报告异常的图像</a-button>
      <a-button v-if="isAdmin" :disabled="!approved('train') || busy" @click="build">生成候选经验版本</a-button>
      <a-popconfirm v-if="isAdmin && data.active.version_id !== 'none'" title="停用当前经验版本，恢复原始检测流程？" @confirm="rollback"><a-button danger>回退原始流程</a-button></a-popconfirm>
    </a-space>
    <a-alert v-if="error" :message="error" type="error" show-icon />
    <a-tabs>
      <a-tab-pane key="cases" tab="纠错与样本审核">
        <p>在检测结果的“纠错与补标”中提交案例。重新标注同一图时，先撤回旧案例，再审核新案例。</p>
        <a-table :data-source="data.cases" :columns="caseColumns" row-key="case_id" :scroll="{ x: 900 }" :pagination="{ pageSize: 8 }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'image'"><img class="thumb" :src="media(record.image_url)" alt="纠错案例原图" /></template>
            <template v-else-if="column.key === 'kind'">{{ kindName(record.kind) }}<small class="block">{{ record.case_id }}</small></template>
            <template v-else-if="column.key === 'purpose'">{{ partitionName(record.partition) }}<small class="block">{{ record.group_key }}</small></template>
            <template v-else-if="column.key === 'status'"><a-tag :color="record.status === 'pending' ? 'orange' : undefined">{{ statusName(record.status) }}</a-tag></template>
            <template v-else-if="column.key === 'action'"><a-button @click="reviewTarget = record; reviewNote = ''; reviewOpen = true">{{ canReview ? '查看与审核' : '查看记录' }}</a-button></template>
          </template>
        </a-table>
        <a-space v-if="canReview" wrap><span>导出已审核原图与标注：</span><a-button v-for="p in partitions" :key="p.value" :disabled="!approved(p.value)" @click="exportPartition(p.value)">{{ p.label }} ZIP</a-button></a-space>
      </a-tab-pane>
      <a-tab-pane key="versions" tab="候选版本与真实回放">
        <a-alert type="warning" show-icon message="回放会调用真实模型；每张图分别运行当前版本与候选版本" description="回放结果与现场告警隔离。启用至少需4张整图复核图、2个独立分组、正常与所涉风险正例及范围框，且出现改善、未发现逐图退步。小样本通过不代表全场景有效。" />
        <a-form v-if="isAdmin" layout="vertical" class="replay-form">
          <a-form-item label="候选经验版本"><a-select v-model:value="selectedVersion" placeholder="先生成候选版本" :options="data.versions.filter(v => v.version_id !== data.active.version_id).map(v => ({ value:v.version_id, label:`${v.version_id} · ${v.case_count} 个案例` }))" /></a-form-item>
          <a-form-item label="评测数据"><a-select v-model:value="evaluationPartition" :options="partitions.filter(p => p.value !== 'train')" /></a-form-item>
          <a-form-item label="真实检测档位"><a-select v-model:value="profile" :options="[{value:'standard',label:'标准 · 云端视觉 + 本地SAM3'},{value:'offline',label:'离线 · 本地Qwen + SAM3'}]" /></a-form-item>
          <a-button type="primary" :disabled="!selectedVersion || running || busy" @click="replay">开始配对回放</a-button>
        </a-form>
        <p v-if="evaluationPartition === 'holdout'">保留测试集建议冻结后限次使用；反复用它选版本后，不能再称为独立盲测。</p>
        <a-empty v-if="!data.runs.length" description="尚无真实回放记录；当前没有经过验证的精度提升结论" />
        <a-card v-for="run in data.runs" :key="run.run_id" :title="run.run_id" class="run-card">
          <a-space wrap><a-tag>{{ statusName(run.status) }}</a-tag><span>{{ run.progress }}</span><a-tag v-if="run.gate">{{ run.gate.passed ? '小试门槛通过' : '暂不可启用' }}</a-tag></a-space>
          <p>{{ run.baseline === 'none' ? '原始流程' : run.baseline }} → {{ run.candidate }} · {{ partitionName(run.partition) }} · {{ run.profile }}</p>
          <a-alert v-if="run.error" type="error" :message="run.error" />
          <a-alert v-if="run.gate?.reasons?.length" type="warning" :message="run.gate.reasons.join('；')" />
          <a-table v-if="run.results.length" :data-source="run.results" :columns="resultColumns" row-key="case_id" size="small" :pagination="false" :scroll="{ x:750 }">
            <template #bodyCell="{ column, record }">
              <template v-if="['fp','fn','candidate_misses'].includes(column.key)">{{ record.baseline[column.key].length }} → {{ record.candidate[column.key].length }}</template>
              <template v-if="column.key === 'box'">{{ boxText(record) }}</template>
              <template v-if="column.key === 'evidence'"><a-space direction="vertical"><router-link :to="{path:'/realtime-detect',query:{job:record.baseline.job_id}}">当前版图像与报告</router-link><router-link :to="{path:'/realtime-detect',query:{job:record.candidate.job_id}}">候选版图像与报告</router-link></a-space></template>
            </template>
          </a-table>
          <a-space wrap class="toolbar"><a-button @click="downloadRun(run)">下载对照报告</a-button><a-button v-if="isAdmin && ['queued','running'].includes(run.status)" @click="cancel(run)">停止后续回放</a-button><a-popconfirm v-if="isAdmin && run.gate?.passed && run.candidate !== data.active.version_id" title="启用该经验版本？系统将再次检查数据和配置是否变化。" @confirm="activate(run)"><a-button type="primary">启用经验版本</a-button></a-popconfirm></a-space>
        </a-card>
      </a-tab-pane>
    </a-tabs>
    <a-modal v-model:open="reviewOpen" title="人工案例审核" width="1040px" :footer="null">
      <div v-if="reviewTarget" class="review-grid">
        <div><div class="review-image"><img :src="media(reviewTarget.image_url)" alt="审核案例原图" /><svg viewBox="0 0 1 1" preserveAspectRatio="none"><rect v-for="(l,i) in reviewTarget.labels.filter(l => l.bbox)" :key="i" :x="l.bbox[0]" :y="l.bbox[1]" :width="l.bbox[2]-l.bbox[0]" :height="l.bbox[3]-l.bbox[1]" /></svg></div><a-button type="link" @click="router.push({path:'/realtime-detect',query:{job:reviewTarget.job_id}})">查看原始检测过程与掩码</a-button></div>
        <div><a-tag>{{ kindName(reviewTarget.kind) }}</a-tag><a-tag>{{ statusName(reviewTarget.status) }}</a-tag><p>{{ reviewTarget.reason }}</p><p v-for="l in reviewTarget.labels" :key="l.risk_id">{{ l.name }}（{{ l.risk_id }}）· {{ l.present ? '实际存在' : '实际不存在' }} · {{ l.bbox ? '已标范围' : '未标范围' }}</p><p>{{ reviewTarget.complete ? '整图复核' : '仅部分目标复核' }} · {{ partitionName(reviewTarget.partition) }}</p><p>来源：{{ reviewTarget.group_key }}<br />提交人：{{ reviewTarget.submitted_by }}</p><p v-for="(r,i) in reviewTarget.reviews" :key="i">{{ r.time }} · {{ r.reviewer }} · {{ statusName(r.decision) }}：{{ r.note }}</p>
          <template v-if="canReview"><a-textarea v-model:value="reviewNote" :rows="3" placeholder="填写本次审核依据；核对原图与人工判断后提交" /><a-space wrap class="toolbar"><a-button v-if="reviewTarget.status !== 'approved'" type="primary" :loading="busy" @click="review('approved')">审核通过</a-button><a-button :loading="busy" @click="review('rejected')">驳回</a-button><a-button v-if="reviewTarget.status === 'approved'" danger :loading="busy" @click="review('withdrawn')">撤回此案例</a-button></a-space></template>
        </div>
      </div>
    </a-modal>
    <a-modal v-model:open="auditOpen" title="未报告异常的图像 · 随机抽查" :footer="null" width="720px"><p>从已完成的真实任务中抽取最多10张尚无纠错记录的图像；需要人工确认是否确实正常。</p><a-list :data-source="audits"><template #renderItem="{ item }"><a-list-item><span>{{ item.job_id }}</span><a-button @click="correctionJob = item.job_id; correctionOpen = true">查看原图并补标</a-button></a-list-item></template></a-list></a-modal>
    <CorrectionDialog v-model:open="correctionOpen" :job-id="correctionJob" @submitted="load" />
  </div>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { message } from 'ant-design-vue'
import * as api from '@/api/continuousLearning'
import { correctionKinds, partitions } from '@/utils/correctionGeometry'
import { resolveBusinessMediaUrl as media } from '@/utils/endpoints'
import { saveFile } from '@/utils/saveFile'
import CorrectionDialog from './CorrectionDialog.vue'
const router = useRouter(), user = useUserStore()
const isAdmin = computed(() => user.role === 'admin'), canReview = computed(() => ['admin','safety'].includes(user.role))
const data = ref({ cases:[], versions:[], runs:[], active:{ version_id:'none' } }), loading = ref(false), busy = ref(false), error = ref('')
const selectedVersion = ref(), evaluationPartition = ref('validation'), profile = ref('standard')
const reviewOpen = ref(false), reviewTarget = ref(null), reviewNote = ref(''), auditOpen = ref(false), audits = ref([]), correctionOpen = ref(false), correctionJob = ref('')
const running = computed(() => data.value.runs.some(r => ['queued','running'].includes(r.status)))
const approved = p => data.value.cases.filter(c => c.status === 'approved' && c.partition === p).length
const kindName = k => correctionKinds.find(x => x.value === k)?.label || k
const partitionName = k => partitions.find(x => x.value === k)?.label || k
const statusName = k => ({ pending:'待审核', approved:'已审核', rejected:'已驳回', withdrawn:'已撤回', queued:'排队', running:'回放中', done:'已完成', error:'失败', cancelled:'已取消', interrupted:'已中断' }[k] || k)
const caseColumns = [{title:'原图',key:'image',width:105},{title:'纠错类型',key:'kind'},{title:'人工依据',dataIndex:'reason'},{title:'用途与分组',key:'purpose'},{title:'状态',key:'status',width:100},{title:'操作',key:'action',width:135}]
const resultColumns = [{title:'案例',dataIndex:'case_id'},{title:'误报类别 当前→候选',key:'fp'},{title:'漏报类别 当前→候选',key:'fn'},{title:'观察阶段漏项',key:'candidate_misses'},{title:'范围框IoU 当前→候选',key:'box'},{title:'回放证据',key:'evidence'}]
const boxText = r => Object.keys(r.baseline.box_iou).map(k => `${k}: ${r.baseline.box_iou[k].toFixed(2)} → ${(r.candidate.box_iou[k] || 0).toFixed(2)}`).join('；') || '未标注'
async function load() { if (loading.value) return; loading.value = true; try { data.value = (await api.learningOverview()).data; error.value = '' } catch(e) { error.value = api.learningError(e) } finally { loading.value = false } }
async function action(fn, text) { if (busy.value) return; busy.value = true; try { await fn(); message.success(text); await load() } catch(e) { message.error(api.learningError(e)) } finally { busy.value = false } }
async function build() { await action(async () => { const r = await api.buildMemory(); selectedVersion.value = r.data.version_id }, '候选版本已生成，尚未启用') }
async function replay() { await action(() => api.startReplay({ version_id:selectedVersion.value, partition:evaluationPartition.value, profile:profile.value }), '已提交真实模型回放') }
async function activate(run) { await action(() => api.activateMemory(run.run_id), '经验版本已启用') }
async function rollback() { await action(() => api.rollbackMemory(), '已恢复原始检测流程') }
async function cancel(run) { await action(() => api.cancelReplay(run.run_id), '已请求停止后续回放') }
async function review(decision) { if (!reviewNote.value.trim()) { message.warning('请填写审核依据'); return }; await action(async () => { await api.reviewCase(reviewTarget.value.case_id, { decision, note:reviewNote.value }); reviewOpen.value = false }, '审核记录已保存') }
async function loadAudits() { await action(async () => { audits.value = (await api.auditSamples()).data; auditOpen.value = true }, '已抽取待复查任务') }
async function exportPartition(partition) { await action(async () => { const r = await api.exportCases(partition); await saveFile(r.data, `道路人工案例_${partition}.zip`) }, '数据包已生成') }
async function downloadRun(run) {
  const text = [`# 道路案例经验版本配对回放报告`, ``, `回放编号：${run.run_id}`, `状态：${statusName(run.status)}`, `档位：${run.profile}`, `数据用途：${partitionName(run.partition)}`, `当前版本：${run.baseline}`, `候选版本：${run.candidate}`, `运行配置指纹：${run.fingerprint}`, ``, `门槛：${run.gate ? run.gate.passed ? '通过' : '未通过' : '尚无有效结论'}`, ...(run.gate?.reasons || []), run.error || '', '', '每个案例保存当前与候选版本的实际检测任务编号；范围框IoU不等于像素掩码质量。小样本结果不代表全场景精度。', '', '```json', JSON.stringify(run.results, null, 2), '```'].join('\n')
  try { await saveFile(new Blob([text],{type:'text/markdown;charset=utf-8'}), `${run.run_id}_对照报告.md`) } catch(e) { message.error(api.learningError(e)) }
}
let timer
onMounted(() => { load(); timer = setInterval(() => { if (running.value) load() }, 5000) })
onBeforeUnmount(() => clearInterval(timer))
</script>
<style scoped>
.learning-stats { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:18px 0; }
.learning-stats>div { padding:18px; border:1px solid var(--border-color); background:var(--bg-card); }
.learning-stats strong { display:block; font-size:28px; margin-top:10px; }.learning-stats .version-name { font-size:16px; overflow-wrap:anywhere; }
.toolbar { margin:16px 0; } .block { display:block; overflow-wrap:anywhere; }.thumb { width:84px; height:54px; object-fit:contain; }
p,small { color:var(--text-secondary); line-height:1.7; }.replay-form { display:grid; grid-template-columns:2fr 1fr 1.5fr auto; gap:12px; align-items:end; margin:20px 0; }.replay-form .ant-btn { margin-bottom:24px; }
.run-card { margin-top:16px; }.review-grid { display:grid; grid-template-columns:1.2fr 1fr; gap:20px; }.review-image { position:relative; line-height:0; }.review-image img { width:100%; }.review-image svg { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }.review-image rect { fill:transparent; stroke:#e8ae49; stroke-width:2px; vector-effect:non-scaling-stroke; }
@media(max-width:900px) { .learning-stats { grid-template-columns:repeat(2,minmax(0,1fr)); }.replay-form,.review-grid { grid-template-columns:minmax(0,1fr); } }
</style>
