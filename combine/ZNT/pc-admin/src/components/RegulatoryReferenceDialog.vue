<template>
  <a-modal :open="open" title="图像检测 · 规范参考记录" :footer="null" width="1180px" @cancel="$emit('update:open', false)">
    <a-spin :spinning="loading">
      <a-alert v-if="error" type="warning" show-icon :message="error"><template #description><a-button @click="load">重新读取</a-button></template></a-alert>
      <div v-else-if="record?.result" class="reference-layout">
        <aside><a-tag v-if="record.source === 'archive'">历史档案 · {{ record.archive?.sample_id }}</a-tag><p class="job-id">{{ record.job_id }}</p><p>检测原图</p><a-image v-if="record.result.input_image" :src="record.result.input_image" :preview="{ getContainer: popupContainer }" alt="本次检测原图" /><p v-if="record.result.scene_annotation">场景标注</p><a-image v-if="record.result.scene_annotation" :src="record.result.scene_annotation" :preview="{ getContainer: popupContainer }" alt="本次检测场景标注" /><p>检测时间：{{ record.created_at || '未记录' }}</p><p>此处读取已保存的检测记录。</p></aside>
        <RegulatoryReferences :key="record.job_id" :result="record.result" />
      </div>
      <a-empty v-else-if="!loading" description="此任务暂无检测结果" />
    </a-spin>
  </a-modal>
</template>
<script setup>
import { ref, watch } from 'vue'
import { fetchDetectJob } from '@/api/detect'
import { popupContainer } from '@/utils/displayPreferences'
import RegulatoryReferences from './RegulatoryReferences.vue'
const props = defineProps({ open: Boolean, jobId: String, job: Object })
defineEmits(['update:open'])
const record = ref(null), loading = ref(false), error = ref('')
let generation = 0
async function load() {
  const request = ++generation
  record.value = null; error.value = ''; loading.value = false
  if (!props.open) return
  if (props.job) { record.value = props.job; return }
  if (!props.jobId) { error.value = '此展示案例未关联原始检测任务，无法提供实际检索记录。'; return }
  loading.value = true
  try { const job = await fetchDetectJob(props.jobId); if (request === generation) record.value = job }
  catch { if (request === generation) error.value = '无法读取此任务的规范记录，请检查检测服务连接或档案是否仍在。' }
  finally { if (request === generation) loading.value = false }
}
watch(() => [props.open, props.jobId, props.job], load)
</script>
<style scoped>
.reference-layout { display:grid; grid-template-columns:250px minmax(0,1fr); gap:24px; padding-top:12px; }
aside { color:var(--text-secondary); border-right:1px solid var(--border-color); padding-right:20px; line-height:1.7; }
.job-id { overflow-wrap:anywhere; font-size:13px; }
@media(max-width:850px) { .reference-layout { grid-template-columns:minmax(0,1fr); } aside { border-right:0; padding:0; } }
</style>
