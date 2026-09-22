<template>
  <a-card title="完整工作空间备份与恢复" class="workspace-backup">
    <p>包含业务账号与工单、规范库、检测任务原图/掩码/报告，以及用户阈值、通知对象和模型路径设置。</p>
    <a-alert type="info" show-icon message="关闭并重新打开桌面软件后执行；操作完成前不启动业务与检测服务。" description="不包含模型权重、云端密钥、程序代码、桌面 Python/端口、日志和浏览器登录状态。外部模型仍需在新设备配置；备份含现场资料与账号信息，请妥善保管。" />
    <a-alert v-if="!native" type="warning" show-icon style="margin-top:12px" message="请使用新版 EXE 独立窗口和本机管理员账号操作；浏览器仍可使用下方的业务数据库备份。" />
    <a-space wrap style="margin-top:16px">
      <a-button type="primary" :disabled="!native || !!state.pending" :loading="busy" @click="schedule('backup')">选择位置并安排备份</a-button>
      <a-button :disabled="!native || !!state.pending" :loading="busy" @click="schedule('restore')">选择备份并安排恢复</a-button>
      <a-button :disabled="!native" :loading="busy" @click="refresh">刷新维护状态</a-button>
    </a-space>
    <a-alert v-if="state.pending" type="warning" show-icon style="margin-top:16px" :message="`已安排${state.pending.action === 'backup' ? '备份' : '恢复'}，等待下次启动`">
      <template #description><p class="path">{{ state.pending.path }}</p><p>请等当前检测完成，再关闭并重新打开软件。不要同时运行其他平台副本。</p><a-button :disabled="busy" @click="cancel">取消本次安排</a-button></template>
    </a-alert>
    <a-alert v-if="state.last_result" :type="state.last_result.status === 'error' ? 'error' : 'success'" show-icon style="margin-top:16px" :message="resultTitle">
      <template #description><p>{{ state.last_result.message || `处理文件：${state.last_result.files || 0} 个` }}</p><p class="path">{{ state.last_result.path || state.last_result.recovery_backup }}</p><p v-if="state.last_result.status === 'restored'">恢复后请重新登录并检查模型路径。自动启动 Qwen、摄像头和未完成检测任务已暂停，需要手动确认后启动。</p><p>{{ state.last_result.completed_at }}</p></template>
    </a-alert>
  </a-card>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useUserStore } from '@/stores/user'
const user = useUserStore(), native = ref(false), busy = ref(false), state = ref({})
const resultTitle = computed(() => ({ error:'上次维护未完成', saved:'工作空间备份已完成', restored:'工作空间已恢复，原数据已保留' }[state.value.last_result?.status] || '维护结果'))
async function refresh() {
  native.value = Boolean(window.pywebview?.api?.workspace_status)
  if (!native.value) return
  try { state.value = await window.pywebview.api.workspace_status(user.token) }
  catch (error) { message.error(error.message || '无法读取维护状态') }
}
async function schedule(action) {
  busy.value = true
  try {
    const result = await window.pywebview.api.schedule_workspace(action, user.token)
    state.value = result
    if (!result.cancelled) message.info('已安排，请等当前任务完成后关闭并重新打开软件')
  } catch (error) { message.error(error.message || '无法安排维护') }
  finally { busy.value = false }
}
async function cancel() {
  busy.value = true
  try { state.value = await window.pywebview.api.cancel_workspace(user.token); message.info('已取消维护安排，现有数据未修改') }
  catch (error) { message.error(error.message || '取消失败') }
  finally { busy.value = false }
}
onMounted(() => { refresh(); window.addEventListener('pywebviewready', refresh) })
onBeforeUnmount(() => window.removeEventListener('pywebviewready', refresh))
</script>
<style scoped>
.workspace-backup{margin-bottom:24px}.path{overflow-wrap:anywhere}p{color:var(--text-secondary);line-height:1.8}
</style>
