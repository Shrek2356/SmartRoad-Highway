<template>
  <section class="service-diagnostics">
    <div class="diagnostics-heading">
      <div><h3>连接与运行诊断</h3><p>只检查服务状态，不加载模型，不启动检测。</p></div>
      <a-space wrap><a-button :loading="health.loading" @click="refresh">重新检查</a-button><a-button :disabled="!health.updatedAt" @click="download">导出诊断摘要</a-button></a-space>
    </div>
    <div class="diagnostics-grid">
      <article v-for="item in cards" :key="item.id" class="diagnostic-card">
        <div class="diagnostic-top"><h4>{{ item.title }}</h4><a-tag :color="colors[item.state]">{{ item.label }}</a-tag></div>
        <p>{{ item.description }}</p><p class="diagnostic-advice">{{ item.advice }}</p>
        <router-link v-if="canVisit(item.target, user.role)" :to="item.target">{{ item.id === 'cloud' ? '配置云端模式' : item.id === 'offline' ? '配置与启动模型' : '检查桌面与连接' }} <ArrowRightOutlined /></router-link>
        <span v-else class="access-note">需要管理员检查配置；可将诊断摘要发给管理员。</span>
      </article>
    </div>
    <div class="diagnostic-footer"><span>队列待处理 {{ health.detect?.inference_queue?.pending ?? '—' }} 项</span><span>{{ health.updatedAt ? `最近检查 ${new Date(health.updatedAt).toLocaleTimeString()}` : '等待检查' }} · 15 秒刷新</span></div>
    <a-alert type="info" show-icon message="导出内容仅含状态与排队数量，不包含 API Key、模型路径、图片或用户信息。" />
    <p v-if="nativeSupport" class="native-support"><a-button @click="openLogs">打开运行日志文件夹</a-button><span>进一步排查时可查看日志；分享前请确认没有密钥或现场敏感信息。</span></p>
  </section>
</template>
<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { message } from 'ant-design-vue'
import { ArrowRightOutlined } from '@ant-design/icons-vue'
import { useServiceHealth } from '@/composables/useServiceHealth'
import { healthCards, diagnosticSnapshot } from '@/utils/healthPresentation'
import { canVisit } from '@/utils/guidance'
import { useUserStore } from '@/stores/user'
import { saveFile } from '@/utils/saveFile'
const { health, refresh } = useServiceHealth(), user = useUserStore()
const nativeSupport = ref(false)
function detectNative() { nativeSupport.value = Boolean(window.pywebview?.api?.open_support_folder) }
onMounted(() => { detectNative(); window.addEventListener('pywebviewready', detectNative) })
onBeforeUnmount(() => window.removeEventListener('pywebviewready', detectNative))
async function openLogs() { try { await window.pywebview.api.open_support_folder('logs') } catch { message.error('未能打开日志目录，请到软件目录的 runtime/desktop/logs 查看。') } }
const cards = computed(() => healthCards(health))
const colors = { checking:'default', ready:'success', attention:'gold', error:'error' }
async function download() {
  try { await saveFile(new Blob([JSON.stringify(diagnosticSnapshot(health), null, 2)], { type:'application/json' }), 'SmartRoad-连接诊断.json') }
  catch (error) { message.error(error.message || '诊断导出失败') }
}
</script>
<style scoped>
.diagnostics-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:20px}.diagnostics-heading h3{margin:0 0 6px;font-size:20px}.diagnostics-heading p{margin:0;color:var(--text-secondary)}
.diagnostics-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.diagnostic-card{padding:24px;background:var(--surface);border:1px solid var(--border-color);border-radius:16px}.diagnostic-top{display:flex;align-items:center;justify-content:space-between;gap:8px}.diagnostic-top h4{font-size:16px;margin:0}.diagnostic-card p{color:var(--text-secondary);line-height:1.8;margin:14px 0}.diagnostic-advice{min-height:50px}.diagnostic-card a{font-weight:600}.access-note{font-size:12px;color:var(--text-muted)}.diagnostic-footer{display:flex;justify-content:space-between;gap:16px;color:var(--text-muted);font-size:12px;margin:18px 0}
@media(max-width:800px){.diagnostics-grid{grid-template-columns:1fr}.diagnostics-heading{align-items:flex-start;flex-direction:column}}
.native-support{display:flex;align-items:center;gap:12px;margin-top:20px}.native-support span{color:var(--text-muted);font-size:12px}
</style>
