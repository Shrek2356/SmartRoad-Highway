<template>
  <!--
    风险掩码叠加层：红/橙/黄三级标注
    坐标为父容器百分比，配合 VideoPlayer 使用
  -->
  <div class="mask-layer">
    <div
      v-for="(m, idx) in masks"
      :key="idx"
      class="mask-box"
      :style="maskToStyle(m, m.level)"
    >
      <span class="mask-label" :style="{ background: RISK_COLORS[m.level]?.border }">
        {{ m.label || RISK_COLORS[m.level]?.label }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { maskToStyle, RISK_COLORS } from '@/ai/maskRender'

defineProps({
  masks: { type: Array, default: () => [] },
})
</script>

<style scoped>
.mask-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;
}
.mask-label {
  position: absolute;
  top: -20px;
  left: 0;
  padding: 1px 6px;
  font-size: 11px;
  /* Labels sit on fixed red/orange/yellow image annotations, not theme surfaces. */
  color: #102431;
  font-weight: 650;
  white-space: nowrap;
  border-radius: 2px;
}
</style>
