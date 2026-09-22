<template>
  <div class="wo-card" :style="{ borderLeftColor: levelColor(order.level) }" @click="$emit('click', order)">
    <div class="row">
      <span class="level" :style="{ color: levelColor(order.level) }">{{ levelText(order.level) }}</span>
      <span class="status">{{ statusText(order.status) }}</span>
    </div>
    <div class="title">{{ order.title }}</div>
    <div class="meta">
      <span>{{ order.area }}</span>
      <span>{{ order.team || order.time }}</span>
    </div>
  </div>
</template>

<script setup>
import { levelColor, levelText, statusText } from '../utils/risk.js'

defineProps({
  order: { type: Object, required: true },
})
defineEmits(['click'])
</script>

<style scoped>
.wo-card {
  background: #fff;
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 10px;
  border-left: 4px solid #d9d9d9;
  cursor: pointer;
}
.row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}
.level { font-size: 12px; font-weight: 600; }
.status { font-size: 12px; color: #8c8c8c; }
.title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
.meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #8c8c8c;
}
</style>
