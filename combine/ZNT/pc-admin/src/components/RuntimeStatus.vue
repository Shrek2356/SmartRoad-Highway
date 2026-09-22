<template>
  <div class="runtime-strip" aria-label="运行状态">
    <span class="runtime-title">服务连接</span>
    <a-badge :status="health.business == null ? 'default' : health.business ? 'success' : 'error'" :text="health.business == null ? '正在检查业务' : health.business ? '业务在线' : '业务未连接'" />
    <a-tooltip title="检测桥负责把任务交给模型；桥在线不等于模型已经加载。"><a-badge :status="!health.detect ? 'default' : health.detect.online ? 'success' : 'error'" :text="!health.detect ? '正在检查检测桥' : health.detect.online ? '检测桥在线' : '检测桥未连接'" /></a-tooltip>
    <router-link to="/task-center" class="queue-link">待处理 {{ health.detect?.inference_queue?.pending ?? '—' }}</router-link>
    <a-tooltip title="只影响案例和统计的展示，不代表当前检测模式。真实事件与展示素材分别标记。"><span class="source-indicator">{{ presentationAssets ? '含预置展示素材' : '已隐藏预置素材' }}</span></a-tooltip>
    <router-link class="diagnostics-link" to="/help-center?tab=diagnostics">{{ disconnected ? '连接异常 · 查看处理方法' : '连接诊断' }} <ArrowRightOutlined /></router-link>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { ArrowRightOutlined } from '@ant-design/icons-vue'
import { useServiceHealth } from '@/composables/useServiceHealth'
import { presentationAssets } from '@/utils/preferences'
const { health } = useServiceHealth()
const disconnected = computed(() => health.updatedAt && (!health.business || !health.detect?.online))
</script>
<style scoped>
.runtime-strip{display:flex;align-items:center;gap:20px;flex-wrap:wrap;padding:9px 24px;background:var(--surface);border-bottom:1px solid var(--border-color);color:var(--text-secondary);font-size:12px;min-height:40px}.runtime-title{color:var(--text-muted);font-size:11px;letter-spacing:.8px}.runtime-strip :deep(.ant-badge-status-text){font-size:12px;color:var(--text-secondary)}.queue-link{color:var(--text-secondary)}.source-indicator{border-left:1px solid var(--border-color);padding-left:20px;color:var(--text-muted);font-size:11px}.diagnostics-link{margin-left:auto;font-size:12px;font-weight:500}@media(max-width:1200px){.source-indicator{display:none}.runtime-strip{gap:16px}}
</style>
