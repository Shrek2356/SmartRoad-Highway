<template>
  <div class="page-card system-page">
    <h2>系统设置</h2><p>集中管理桌面环境、展示方式、用户与备份。模型权重及云端连接在模型规则配置中维护。</p>
    <a-tabs v-model:activeKey="tab">
      <a-tab-pane key="workspace" tab="工作台与展示">
        <a-form layout="vertical" class="settings-form">
          <a-form-item label="界面风格"><a-radio-group :value="workspaceStyle" @change="e => setWorkspaceStyle(e.target.value)"><a-radio-button value="professional">专业工作台</a-radio-button><a-radio-button value="showcase">作品展示视图</a-radio-button></a-radio-group></a-form-item>
          <a-form-item label="预置展示素材"><a-switch :checked="presentationAssets" :disabled="!presentationAvailable" @change="toggleAssets" /> <span>{{ presentationAvailable ? '显示预编辑的八个案例、展示点位和成果图' : '当前构建已禁用预置素材，请联系部署者调整。' }}</span></a-form-item>
          <a-alert type="info" show-icon message="关闭只影响显示，不删除素材或历史检测。展示素材不写入真实事件数据库。切换后重新进入对应页面即可刷新。" />
        </a-form>
      </a-tab-pane>
      <a-tab-pane key="desktop" tab="桌面与连接">
        <a-alert :type="desktop ? 'success' : 'info'" show-icon :message="desktop ? '当前为独立桌面窗口；以下设置保存后在下次启动生效。' : '当前为浏览器入口。桌面环境设置需在 EXE 独立窗口内修改。'" />
        <a-form v-if="desktop" layout="vertical" class="settings-form">
          <a-form-item label="后台 Python（基础环境随包携带；真实检测选择完整环境）"><a-input v-model:value="settings.backend_python" /><a-button size="small" style="margin-top:8px" @click="pickPython">选择 python.exe</a-button></a-form-item>
          <a-form-item label="默认启动模式"><a-select v-model:value="settings.profile"><a-select-option value="demo">演示 · 不加载大模型</a-select-option><a-select-option value="offline">本地离线检测</a-select-option><a-select-option value="standard">云端检测</a-select-option></a-select></a-form-item>
          <a-row :gutter="16"><a-col :span="8" v-for="field in ports" :key="field.key"><a-form-item :label="field.label"><a-input-number v-model:value="settings[field.key]" :min="1024" :max="65535" style="width:100%" /></a-form-item></a-col></a-row>
          <a-button type="primary" :loading="saving" @click="saveDesktop">保存桌面配置</a-button><p v-if="saved">已保存。请关闭并重新打开桌面窗口；当前任务不会因保存被中断。</p>
          <p class="root-path">工作目录：{{ settings.app_root }}</p>
        </a-form>
        <a-divider />
        <a-form layout="vertical" class="settings-form"><a-alert type="info" show-icon message="通常无需修改。桌面默认通过同源网关连接；只有使用外部服务时才填写 HTTP(S) 地址。保存后请打开连接诊断验证。" /><a-form-item label="业务接口根地址（含 /api）"><a-input v-model:value="endpoints.businessApi" /></a-form-item><a-form-item label="检测桥根地址"><a-input v-model:value="endpoints.detectApi" /></a-form-item><a-space wrap><a-button @click="saveConnections">保存连接</a-button><a-button @click="resetConnections">恢复默认连接</a-button><router-link to="/model-config?tab=runtime">模型路径与启动 →</router-link><router-link to="/help-center?tab=diagnostics">验证连接 →</router-link></a-space></a-form>
      </a-tab-pane>
      <a-tab-pane key="users" tab="用户与工作空间备份"><SystemAdministration /></a-tab-pane>
      <a-tab-pane key="about" tab="关于与部署">
        <a-descriptions title="路安智巡 · SmartRoad-Inspection" bordered :column="1"><a-descriptions-item label="产品版本">1.4.3 · 道路检测与法规知识库</a-descriptions-item><a-descriptions-item label="软件结构">独立桌面窗口 → 同源网关 → 业务后台 / 检测桥 → 按需加载模型</a-descriptions-item><a-descriptions-item label="模型">Qwen 道路视觉核验、SAM3 定位与问题报告；道路初筛暂不启用，检测结果进入人工复核。</a-descriptions-item><a-descriptions-item label="首次部署">Windows 10/11 64位，WebView2；展示使用包内 Python，无需 Node。离线检测先打开“模型与规则 → 新设备部署”，按五步引导准备 GPU 环境和组件。</a-descriptions-item><a-descriptions-item label="使用边界">展示/试点版本。模型结论须经安全人员判断；本版本的软件链路回归不等同于新一轮模型准确率评测。</a-descriptions-item></a-descriptions>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>
<script setup>
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouteTab } from '@/composables/useRouteTab'
import { message } from 'ant-design-vue'
import SystemAdministration from '@/components/SystemAdministration.vue'
import { workspaceStyle, setWorkspaceStyle, presentationAssets, presentationAvailable, setPresentationAssets } from '@/utils/preferences'
import { getBusinessApiBase, getDetectApiBase, saveEndpointSettings, resetEndpointSettings } from '@/utils/endpoints'
import { refreshServiceHealth } from '@/composables/useServiceHealth'
const tab = useRouteTab(['workspace','desktop','users','about'], 'workspace')
const desktop = ref(false), saving = ref(false), saved = ref(false), settings = reactive({})
const endpoints = reactive({ businessApi:getBusinessApiBase(), detectApi:getDetectApiBase() })
const ports = [{ key:'frontend_port', label:'前端端口' }, { key:'business_port', label:'业务端口' }, { key:'bridge_port', label:'检测桥端口' }]
function toggleAssets(value) { setPresentationAssets(value); message.success('显示方式已保存，已有素材未删除') }
async function saveDesktop() {
  saving.value = true
  try { await window.pywebview.api.save_desktop_settings({ ...settings }); saved.value = true; message.success('配置已验证并保存，下次启动生效') }
  catch (e) { message.error(e.message || '配置保存失败') }
  finally { saving.value = false }
}
async function pickPython() { try { const path = await window.pywebview.api.choose_backend_python(); if (path) settings.backend_python = path } catch(e) { message.error(e.message) } }
function saveConnections() { try { Object.assign(endpoints, saveEndpointSettings({ ...endpoints })); refreshServiceHealth(); message.success('连接已保存，正在重新检查') } catch(e) { message.error(e.message) } }
function resetConnections() { Object.assign(endpoints, resetEndpointSettings()); refreshServiceHealth(); message.success('已恢复默认连接，正在重新检查') }
async function loadDesktop() {
  if (window.pywebview?.api?.get_desktop_settings) {
    desktop.value = true
    try { Object.assign(settings, await window.pywebview.api.get_desktop_settings()); saved.value = Boolean(settings.restart_required) } catch(e) { message.error(e.message) }
  }
}
onMounted(() => { loadDesktop(); window.addEventListener('pywebviewready',loadDesktop) })
onBeforeUnmount(() => window.removeEventListener('pywebviewready',loadDesktop))
</script>
<style scoped>
.settings-form { max-width:850px; margin-top:20px; } h2 { margin-top:0; color:var(--text-primary); } p,span { color:var(--text-secondary); } .root-path { margin-top:20px; overflow-wrap:anywhere; }
</style>
