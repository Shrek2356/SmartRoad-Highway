<template>
  <div class="help-center">
    <header class="support-hero"><div><span class="eyebrow">FIELD GUIDE / 使用与支持</span><h1>从这里，找到下一步。</h1><p>功能说明、操作路径与连接排查，都放在你用得上的地方。</p></div><div class="support-emblem" aria-hidden="true"><SafetyCertificateOutlined /><span>看见风险 · 连接行动</span></div></header>
    <a-tabs v-model:activeKey="tab" class="support-tabs">
      <a-tab-pane key="start" tab="快速开始">
        <a-alert v-if="journey.id === 'showcase' && !presentationAssets" type="info" show-icon :message="presentationAvailable ? '当前窗口已隐藏预置展示素材。想看完整八个案例，请先启用显示；不会写入真实业务事件。' : '本部署已在构建时禁用预置展示素材，无法从窗口中启用。请联系部署者使用展示构建。'" style="margin-bottom:18px"><template #action><a-button v-if="presentationAvailable" size="small" @click="setPresentationAssets(true)">启用预置案例显示</a-button></template></a-alert>
        <div class="journey-choices"><button v-for="j in journeys" :key="j.id" :class="{selected:journey.id===j.id}" :aria-pressed="journey.id===j.id" @click="choose(j.id)"><span>{{ j.tag }}</span><strong>{{ j.title }}</strong><p>{{ j.description }}</p><ArrowRightOutlined /></button></div>
        <section class="journey-panel">
          <div class="section-heading"><div><h2>{{ journey.title }} · 操作清单</h2><p>你可以随时离开，再从这里继续。勾选仅表示你已完成操作，不代表服务验收。</p></div><span class="completion-count">{{ completedCount }} / {{ journey.steps.length }}</span></div>
          <ol class="journey-steps"><li v-for="(step,index) in journey.steps" :key="step.target"><span class="step-index">{{ String(index+1).padStart(2,'0') }}</span><div class="step-info"><strong>{{ step.title }}</strong><small>{{ pageFor(step.target)?.result }}</small></div><a-checkbox :checked="isChecked(index)" @change="e=>check(index,e.target.checked)">已操作</a-checkbox><router-link :to="step.target">前往 <ArrowRightOutlined /></router-link></li></ol>
        </section>
        <div class="support-footnote"><InfoCircleOutlined /> 不知道从哪开始？先查看展示案例，不需要下载或启动大模型。</div>
      </a-tab-pane>
      <a-tab-pane key="library" tab="功能全景">
        <a-input v-model:value="search" size="large" allow-clear placeholder="搜索模块、工具或操作，如：SAM3、复核、备份" class="help-search"><template #prefix><SearchOutlined /></template></a-input>
        <div class="help-library"><article v-for="item in pages" :key="item.path"><span class="eyebrow">{{ item.group }}</span><h2>{{ item.title }}</h2><p>{{ item.description }}</p><ol><li v-for="s in item.steps" :key="s">{{ s }}</li></ol><div class="library-result"><strong>输出</strong> {{ item.result }}</div><p class="library-caution"><InfoCircleOutlined /> {{ item.caution }}</p><router-link :to="item.path">打开{{ item.title }} <ArrowRightOutlined /></router-link></article></div><a-empty v-if="!pages.length" description="没有匹配功能，换个关键词试试。" />
      </a-tab-pane>
      <a-tab-pane key="diagnostics" tab="连接诊断"><ServiceDiagnostics /></a-tab-pane>
      <a-tab-pane key="faq" tab="常见问题">
        <div class="faq-heading"><h2>遇到问题，不必从头重来。</h2><p>先确认具体环节，再恢复连接或调整配置。</p></div>
        <a-collapse accordion ghost class="faq-list"><a-collapse-panel v-for="item in FAQS" :key="item.title" :header="item.title"><p>{{ item.body }}</p><router-link v-if="canVisit(item.target,user.role)" :to="item.target">{{ item.action }} <ArrowRightOutlined /></router-link><span v-else class="support-footnote">这项配置需要管理员操作，可以向管理员提供上述说明。</span></a-collapse-panel></a-collapse>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>
<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SafetyCertificateOutlined, SearchOutlined, ArrowRightOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import { HELP_PAGES, FAQS, JOURNEYS, canVisit, pageFor } from '@/utils/guidance'
import { useRouteTab } from '@/composables/useRouteTab'
import { useUserStore } from '@/stores/user'
import ServiceDiagnostics from '@/components/ServiceDiagnostics.vue'
import { presentationAssets, presentationAvailable, setPresentationAssets } from '@/utils/preferences'
const user=useUserStore(), route=useRoute(), router=useRouter(), search=ref('')
const tab=useRouteTab(['start','library','diagnostics','faq'],'start')
const journeys=computed(()=>JOURNEYS.filter(j=>j.steps.every(s=>canVisit(s.target,user.role))))
const journey=computed(()=>journeys.value.find(j=>j.id===route.query.journey)||journeys.value[0]||JOURNEYS[2])
const pages=computed(()=>HELP_PAGES.filter(p=>p.path!=='/help-center'&&canVisit(p.path,user.role)&&`${p.title} ${p.keywords} ${p.description}`.toLowerCase().includes(search.value.trim().toLowerCase())))
const progressKey=`smartroad_guide_v1_${user.user?.id||user.user?.username||user.role}`
function readProgress(){try{const value=JSON.parse(localStorage.getItem(progressKey)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{}}catch{return {}}}
const progress=ref(readProgress())
const key=index=>`${journey.value.id}:${index}`
const isChecked=index=>progress.value[key(index)]===true
const completedCount=computed(()=>journey.value.steps.filter((_,index)=>isChecked(index)).length)
function check(index,value){progress.value={...progress.value,[key(index)]:value};try{localStorage.setItem(progressKey,JSON.stringify(progress.value))}catch{/* Progress remains usable for this session. */}}
function choose(id){router.replace({query:{...route.query,journey:id}})}
</script>
<style scoped>
.help-center{max-width:1440px;margin:0 auto;padding-bottom:28px}.support-hero{position:relative;overflow:hidden;padding:36px 40px;background:var(--product-ink);color:#edf3f3;border-radius:20px;display:flex;justify-content:space-between;gap:24px}.support-hero:after{content:'';position:absolute;width:340px;height:340px;border:1px solid #ffffff12;border-radius:50%;right:-70px;top:-180px;box-shadow:0 0 0 40px #ffffff05,0 0 0 80px #ffffff03;pointer-events:none}.eyebrow{font-size:11px;letter-spacing:1.6px;color:var(--text-muted);font-weight:600}.support-hero .eyebrow{color:#b4c7c9}.support-hero h1{font-size:34px;letter-spacing:-.6px;margin:18px 0 12px;color:#fff}.support-hero p{color:#bdcdd0;margin:0;font-size:14px;line-height:1.8}.support-emblem{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;min-width:180px;color:var(--hero-accent);font-size:60px}.support-emblem>span:last-child{font-size:11px;letter-spacing:3px}.support-tabs{margin-top:20px}.journey-choices{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:8px 0 24px}.journey-choices button{position:relative;padding:24px;text-align:left;border:1px solid var(--border-color);background:var(--surface);border-radius:16px;color:var(--text-primary);cursor:pointer}.journey-choices button.selected{border-color:var(--primary);box-shadow:inset 0 0 0 1px var(--primary)}.journey-choices button>span:first-child{font-size:11px;color:var(--primary)}.journey-choices strong{display:block;font-size:21px;margin:10px 0}.journey-choices p{color:var(--text-secondary);font-size:13px;line-height:1.75;margin-bottom:0}.journey-choices button>.anticon:last-child{position:absolute;right:24px;top:24px;color:var(--text-muted)}.journey-panel{background:var(--surface);padding:28px 32px;border:1px solid var(--border-color);border-radius:16px}.section-heading{display:flex;justify-content:space-between;gap:18px;align-items:center}.section-heading h2,.faq-heading h2{font-size:21px;margin:0 0 8px}.section-heading p,.faq-heading p{font-size:13px;color:var(--text-secondary);line-height:1.75}.completion-count{font-size:26px;white-space:nowrap;color:var(--primary);font-variant-numeric:tabular-nums}.journey-steps{padding:0;margin:18px 0 0;list-style:none}.journey-steps li{display:flex;align-items:center;gap:24px;padding:22px 0;border-top:1px solid var(--border-color)}.step-index{font-size:13px;font-weight:700;color:var(--text-muted)}.step-info{flex:1}.step-info strong{display:block;font-size:15px}.step-info small{display:block;margin-top:7px;color:var(--text-secondary);line-height:1.6}.journey-steps a{white-space:nowrap;font-weight:600}.support-footnote{display:block;color:var(--text-secondary);font-size:12px;margin-top:20px;line-height:1.9}.help-search{max-width:640px;margin:6px 0 24px}.help-library{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.help-library article{background:var(--surface);border:1px solid var(--border-color);border-radius:16px;padding:28px;display:flex;flex-direction:column;align-items:flex-start}.help-library h2{font-size:22px;margin:12px 0}.help-library p,.help-library li{color:var(--text-secondary);font-size:13px;line-height:1.9}.help-library ol{padding-left:20px}.library-result{font-size:13px;line-height:1.9;background:var(--surface-2);padding:14px;border-radius:10px;width:100%}.library-result strong{margin-right:8px;color:var(--primary)}.library-caution{font-size:12px!important}.help-library a{margin-top:auto;font-weight:600}.faq-heading{margin:18px 0 28px}.faq-list{max-width:1000px}.faq-list :deep(.ant-collapse-item){border:1px solid var(--border-color);border-radius:12px!important;background:var(--surface);margin-bottom:12px}.faq-list p{line-height:2;color:var(--text-secondary)}
@media(max-width:1000px){.journey-choices{grid-template-columns:1fr}.help-library{grid-template-columns:1fr}.support-emblem{display:none}.journey-steps li{gap:12px;flex-wrap:wrap}.support-hero{padding:28px}.journey-panel{padding:24px}}
</style>
