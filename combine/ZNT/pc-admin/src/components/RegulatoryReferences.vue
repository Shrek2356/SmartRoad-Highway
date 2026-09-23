<template>
  <section class="reference-panel" aria-label="规范参考记录">
    <div class="reference-heading">
      <div><h3>规范参考记录 <span>RAG</span></h3><p>{{ groups.length }} 项观察 · {{ count }} 条关联引用</p></div>
      <a v-if="result.regulatory_references" :href="result.regulatory_references" target="_blank" rel="noopener noreferrer">查看原始记录 JSON ↗</a>
    </div>
    <p class="reference-note">以下是这次检测保存的规范摘录，用于核对处置建议。引用条款不证明图像异常成立，适用条件需人工核查。</p>
    <a-alert v-if="result.reference_record_status === 'invalid'" type="warning" show-icon message="规范记录文件无法读取，下方仅展示任务摘要中已有的引用。" />
    <a-tabs v-if="groups.length" v-model:active-key="activeId" class="risk-tabs">
      <a-tab-pane v-for="group in groups" :key="group.id" :tab="`${group.name}（${group.references.length}）`">
        <p v-if="group.description" class="observation"><strong>图像观察：</strong>{{ group.description }}</p>
        <div class="retrieval-summary">
          <span>{{ methodLabel(group) }}</span>
          <span>检索时间：{{ group.trace.status === 'not_configured' ? '未执行检索' : group.trace.searched_at || '历史记录未保存' }}</span>
        </div>
        <p class="query"><strong>检索词：</strong>{{ group.trace.status === 'not_configured' ? '未执行检索' : group.trace.query || '历史记录未保存，不作补推' }}</p>
        <details v-if="group.trace.allowed_sections?.length" class="trace-details">
          <summary>查看本次检索范围与参数</summary>
          <p>最多返回 {{ group.trace.top_k }} 条；最低相关度 {{ group.trace.min_score }}；{{ group.trace.verified_only ? '仅使用来源校验通过的材料' : '来源过滤未启用' }}。</p>
          <ul><li v-for="scope in group.trace.allowed_sections" :key="`${scope.source_file}-${scope.section}`">{{ scope.source_file }} · {{ scope.section }}</li></ul>
        </details>
        <a-empty v-if="!group.references.length" :description="emptyReferenceMessage(result, group)" />
        <article v-for="(ref, index) in group.references" :key="`${ref.chunk_id}-${index}`" class="reference-card">
          <div class="clause-heading"><h4>{{ ref.title || ref.source_file || '未记录名称' }} · {{ ref.section || '未记录条款' }}</h4><a-tag>{{ ref.provenance_status === 'verified_checksum' ? '检索时摘录校验通过' : '来源校验未确认' }}</a-tag></div>
          <p class="reference-version">{{ ref.version || '版本未记录' }}<span v-if="ref.issuer"> · {{ ref.issuer }}</span></p>
          <div class="clause-text">{{ ref.text || '未保存条款原文' }}</div>
          <div class="applicability"><strong>适用条件</strong><p>{{ ref.applicability || '未记录，需人工核查' }}</p></div>
          <div class="reference-footer"><a v-if="safeSourceUrl(ref.source_url)" :href="safeSourceUrl(ref.source_url)" target="_blank" rel="noopener noreferrer">查看来源网页 ↗</a><span v-else>未保存可访问的来源链接</span><span>文本相关度 {{ scoreLabel(ref.score) }}（不是检测置信度）</span></div>
          <details class="trace-details"><summary>来源与留痕</summary>
            <dl><dt>引用编号</dt><dd>{{ ref.regulation_id || '未记录' }}</dd><dt>摘录块</dt><dd>{{ ref.chunk_id || '未记录' }}</dd><dt>来源文件</dt><dd>{{ ref.source_file || '未记录' }}</dd><dt>资料采集时间</dt><dd>{{ ref.retrieved_at || '未记录' }}（不是本次检测检索时间）</dd><dt>摘录 SHA-256</dt><dd>{{ ref.sha256 || '未记录' }}</dd></dl>
            <p>{{ ref.scope }}</p><p>{{ ref.usage || '处置参考，不构成违法认定。' }}</p>
          </details>
        </article>
      </a-tab-pane>
    </a-tabs>
    <a-empty v-else :description="emptyReferenceMessage(result)" />
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { referenceGroups, referenceCount, emptyReferenceMessage, safeSourceUrl, scoreLabel } from '@/utils/regulatoryReferences'
const props = defineProps({ result: { type: Object, default: () => ({}) } })
const groups = computed(() => referenceGroups(props.result))
const count = computed(() => referenceCount(props.result))
const activeId = ref('')
watch(groups, value => { if (!value.some(group => group.id === activeId.value)) activeId.value = value[0]?.id || '' }, { immediate: true })
function methodLabel(group) {
  if (group.trace.status === 'not_configured') return '未配置条款检索范围'
  const method = group.trace.method || group.references[0]?.retrieval_method
  return method === 'curated_risk_scope_then_tfidf' ? '按风险限定条款范围 · TF-IDF 文本检索' : '检索方式未记录'
}
</script>

<style scoped>
.reference-panel { color:var(--text-primary); min-width:0; }
.reference-heading,.clause-heading,.reference-footer,.retrieval-summary { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }
h3 { font-size:20px; margin:0 0 6px; } h3 span { font-size:13px; font-weight:400; color:var(--text-secondary); margin-left:8px; }
h4 { font-size:17px; margin:0; } p { margin:8px 0; line-height:1.7; }
.reference-heading p,.reference-note,.reference-version,.retrieval-summary,.trace-details,.reference-footer { color:var(--text-secondary); }
.reference-note { font-size:14px; padding:12px 14px; background:var(--surface-muted); border-left:3px solid var(--border-color); }
.observation,.query { overflow-wrap:anywhere; }
.reference-card { border:1px solid var(--border-color); background:var(--surface); border-radius:8px; padding:18px; margin-top:16px; }
.clause-text { white-space:pre-wrap; line-height:1.9; margin:16px 0; padding:16px; background:var(--surface-muted); border-radius:4px; overflow-wrap:anywhere; }
.applicability { border-left:3px solid var(--border-color); padding:2px 14px; margin:14px 0; }
.reference-footer { font-size:14px; margin:16px 0 0; }
.trace-details { margin-top:14px; font-size:14px; overflow-wrap:anywhere; } summary { cursor:pointer; padding:5px 0; }
dl { display:grid; grid-template-columns:110px minmax(0,1fr); gap:10px; } dd { margin:0; } dt { color:var(--text-primary); }
@media(max-width:600px) { .reference-card { padding:12px; } dl { display:block; } dd { margin-bottom:10px; } }
</style>
