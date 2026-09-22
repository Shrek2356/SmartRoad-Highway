<template>
  <div class="guide-tools">
    <a-tooltip title="搜索功能、操作与帮助（Ctrl + K）"><a-button class="function-search" @click="openSearch"><SearchOutlined /><span>搜索功能</span><kbd>Ctrl K</kbd></a-button></a-tooltip>
    <a-button class="page-help-button" @click="helpOpen = true"><QuestionCircleOutlined />本页指南</a-button>
  </div>

  <a-modal v-model:open="searchOpen" title="你想做什么？" :footer="null" :width="660" :after-close="resetSearch" @after-open-change="focusSearch">
    <a-input ref="searchInput" v-model:value="query" size="large" allow-clear placeholder="搜索功能，例如：导入规范、模型、检测桥…" aria-label="搜索功能" @press-enter="goFirst"><template #prefix><SearchOutlined /></template></a-input>
    <p class="search-caption">仅显示当前账号可访问的入口 · Enter 打开首项 · Esc 关闭</p>
    <div class="search-results">
      <button v-for="item in results" :key="item.id" class="search-result" @click="navigate(item.target)"><span><strong>{{ item.title }}</strong><small>{{ item.description }}</small></span><ArrowRightOutlined /></button>
      <a-empty v-if="!results.length" description="没有找到匹配项；试试“模型”“规范”或“任务”。"><a-button @click="navigate('/help-center')">浏览全部帮助</a-button></a-empty>
    </div>
  </a-modal>

  <a-drawer v-model:open="helpOpen" title="本页操作指南" :width="440">
    <div v-if="page" class="context-guide">
      <span class="eyebrow">{{ page.group }} / {{ page.title }}</span><h2>{{ page.description }}</h2>
      <h3>怎么使用</h3><ol class="guide-steps"><li v-for="(step, index) in page.steps" :key="step"><span>{{ String(index + 1).padStart(2,'0') }}</span><p>{{ step }}</p></li></ol>
      <h3>完成后会得到什么</h3><p>{{ page.result }}</p>
      <a-alert type="info" show-icon :message="page.caution" />
      <a-button v-if="canVisit(page.next, user.role)" type="primary" block class="guide-next" @click="navigate(page.next)">下一步：{{ pageFor(page.next)?.title }} <ArrowRightOutlined /></a-button>
    </div>
    <div class="help-bottom"><a-button block @click="navigate('/help-center?tab=diagnostics')">遇到连接问题？查看诊断</a-button><a-button block @click="navigate('/help-center')">打开完整使用指南</a-button><a-button type="link" block @click="helpOpen = false; welcomeOpen = true">重新打开欢迎引导</a-button></div>
  </a-drawer>

  <a-modal v-model:open="welcomeOpen" :footer="null" :width="800" :mask-closable="false" @cancel="dismissWelcome">
    <div class="welcome-guide">
      <div class="welcome-top"><span class="welcome-mark"><SafetyCertificateOutlined /></span><span class="eyebrow">SMARTROAD LAB / 快速开始</span></div>
      <h1>让每一次发现，<br/>都有下一步。</h1><p class="welcome-intro">从查看作品到现场巡检，为你准备了清晰的操作路径。<br/>你可以随时从右上角“本页指南”回来。</p>
      <div class="welcome-options"><button v-for="journey in journeys" :key="journey.id" @click="startJourney(journey.id)"><span>{{ journey.tag }}</span><strong>{{ journey.title }}</strong><p>{{ journey.description }}</p><ArrowRightOutlined /></button></div>
      <div class="welcome-bottom"><span><CheckCircleOutlined /> 不会自动开启模型或改变配置</span><a-button @click="dismissWelcome">暂时跳过，直接进入</a-button></div>
    </div>
  </a-modal>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SearchOutlined, QuestionCircleOutlined, ArrowRightOutlined, SafetyCertificateOutlined, CheckCircleOutlined } from '@ant-design/icons-vue'
import { useUserStore } from '@/stores/user'
import { searchFunctions, pageFor, canVisit, JOURNEYS } from '@/utils/guidance'
const user = useUserStore(), route = useRoute(), router = useRouter()
const searchOpen = ref(false), helpOpen = ref(false), welcomeOpen = ref(false), query = ref(''), searchInput = ref()
const page = computed(() => pageFor(route.path))
const results = computed(() => searchFunctions(query.value, user.role).slice(0,14))
const journeys = computed(() => JOURNEYS.filter(j => j.steps.every(s => canVisit(s.target, user.role))))
const welcomeKey = () => `smartroad_welcome_v1_${user.user?.id || user.user?.username || user.role}`
function dismissWelcome() { welcomeOpen.value = false; try { localStorage.setItem(welcomeKey(), 'seen') } catch { /* A blocked storage area must not block entry. */ } }
function navigate(target) { searchOpen.value = false; helpOpen.value = false; router.push(target) }
function startJourney(id) { dismissWelcome(); navigate(`/help-center?journey=${id}`) }
function openSearch() { searchOpen.value = true; focusSearch(true) }
function focusSearch(open) { if (open) nextTick(() => searchInput.value?.focus()) }
function resetSearch() { query.value = '' }
function goFirst() { if (results.value[0]) navigate(results.value[0].target) }
function shortcut(e) { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if (!welcomeOpen.value) openSearch() } }
onMounted(() => { document.addEventListener('keydown', shortcut); try { welcomeOpen.value = localStorage.getItem(welcomeKey()) !== 'seen' } catch { welcomeOpen.value = false } })
onBeforeUnmount(() => document.removeEventListener('keydown', shortcut))
</script>
<style scoped>
.guide-tools{display:flex;gap:10px;align-items:center}.function-search{display:flex;align-items:center;gap:9px;color:var(--text-secondary);background:var(--surface-2);border-color:var(--border-color)}kbd{font:10px 'Segoe UI',sans-serif;border:1px solid var(--border-color);border-radius:4px;padding:1px 4px;color:var(--text-muted)}.search-caption{color:var(--text-muted);font-size:12px;margin:14px 0}.search-results{max-height:480px;overflow-y:auto}.search-result{display:flex;align-items:center;justify-content:space-between;width:100%;gap:16px;text-align:left;background:none;border:0;border-radius:10px;padding:15px 12px;color:var(--text-primary);cursor:pointer}.search-result:hover,.search-result:focus-visible{background:var(--surface-muted)}.search-result strong{display:block;font-size:14px}.search-result small{display:block;color:var(--text-secondary);margin-top:5px;line-height:1.6}.eyebrow{font-size:11px;letter-spacing:1.3px;color:var(--text-secondary);font-weight:600}.context-guide h2{font-size:23px;line-height:1.55;margin:16px 0 28px}.context-guide h3{font-size:13px;font-weight:700;margin-top:28px}.context-guide p{color:var(--text-secondary);line-height:1.85}.guide-steps{padding:0;list-style:none}.guide-steps li{display:flex;gap:14px;align-items:flex-start}.guide-steps li>span{font-size:12px;color:var(--primary);font-weight:700;line-height:28px}.guide-steps p{margin:0 0 18px}.guide-next{margin-top:24px}.help-bottom{border-top:1px solid var(--border-color);margin-top:28px;padding-top:24px;display:grid;gap:12px}.welcome-guide{padding:16px 10px 8px}.welcome-top{display:flex;align-items:center;gap:12px}.welcome-mark{width:40px;height:40px;border-radius:13px;background:var(--product-ink);color:var(--hero-accent);display:grid;place-items:center;font-size:23px}.welcome-guide h1{font-size:36px;line-height:1.35;letter-spacing:-1px;margin:28px 0 14px;color:var(--text-primary)}.welcome-intro{font-size:14px;color:var(--text-secondary);line-height:1.9}.welcome-options{display:flex;gap:12px;margin:24px 0}.welcome-options button{flex:1;min-width:0;text-align:left;padding:22px 18px;background:var(--surface-2);border:1px solid var(--border-color);border-radius:14px;color:var(--text-primary);cursor:pointer;transition:border-color .15s,transform .15s}.welcome-options button:hover{border-color:var(--primary);transform:translateY(-2px)}.welcome-options button>span:first-child{font-size:11px;color:var(--primary)}.welcome-options strong{display:block;font-size:18px;margin-top:10px}.welcome-options p{font-size:12px;color:var(--text-secondary);line-height:1.8;min-height:43px}.welcome-bottom{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;color:var(--text-muted)}
@media(max-width:1200px){.function-search kbd,.page-help-button .anticon{display:none}}@media(max-width:640px){.welcome-options{flex-direction:column}.welcome-guide h1{font-size:28px}.welcome-bottom{align-items:flex-start;flex-direction:column}}
</style>
