<template>
  <section class="reading-settings" aria-label="字体与画面设置">
    <div class="reading-heading"><strong>字体大小</strong><output aria-live="polite">{{ fontPercent }}%</output></div>
    <label class="size-slider">调整字体大小（100%–200%）
      <input type="range" min="100" max="200" step="5" :value="fontPercent" aria-label="字体大小" @input="setFontPercent($event.target.value)" />
    </label>
    <div class="font-presets"><button v-for="option in presets" :key="option.value" type="button" :aria-pressed="fontPercent===option.value" @click="setFontPercent(option.value)">{{ option.label }} {{ option.value }}%</button></div>
    <p class="reading-sample">路面巡检 · 查看设备状态与风险报告</p>
    <p>立即生效并自动保存。文字增大后可换行；图像、视频和检测数据不变。</p>
    <div class="reading-heading"><strong>画面放大</strong><button type="button" @click="openInspection">打开查看模式</button></div>
    <p>Ctrl＋滚轮直接放大；查看模式下滚轮缩放、拖动平移，布局保持原样。按 Esc 或“退出查看”恢复页面操作。</p>
  </section>
</template>
<script setup>
import { fontPercent,setFontPercent,openInspection } from '@/utils/displayPreferences'
const presets=[{label:'标准',value:100},{label:'大',value:125},{label:'特大',value:150},{label:'最大',value:200}]
</script>
<style scoped>
.reading-settings{color:var(--text-primary);max-width:850px}.reading-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:12px 0}.reading-heading strong{font-size:16px}.reading-heading output{font:16px monospace;color:var(--text-primary)}.size-slider{display:grid;gap:12px;font-size:13px}.size-slider input{width:100%;height:28px;accent-color:var(--primary)}.font-presets{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.reading-settings button{font:inherit;font-size:13px;border:1px solid var(--border-color);color:var(--text-primary);background:var(--surface);border-radius:4px;padding:6px 10px;cursor:pointer}.reading-settings button[aria-pressed=true]{color:var(--on-primary);background:var(--primary);border-color:var(--primary)}.reading-sample{padding:16px;border:1px solid var(--border-color);background:var(--surface-2);font-size:16px;color:var(--text-primary)}.reading-settings p:not(.reading-sample){font-size:12px;color:var(--text-secondary);line-height:1.8}
</style>
