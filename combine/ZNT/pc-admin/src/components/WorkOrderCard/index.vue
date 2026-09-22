<template>
  <!-- 工单卡片（列表/弹窗摘要复用） -->
  <div class="wo-card" :class="'level-' + order.level" @click="$emit('click', order)">
    <div class="wo-head">
      <a-tag :color="levelColor">{{ levelText }}</a-tag>
      <span class="wo-id">{{ order.id }}</span>
      <a-tag>{{ statusText }}</a-tag>
    </div>
    <div class="wo-title">{{ order.title }}</div>
    <div class="wo-meta">
      <span>{{ order.area }}</span>
      <span>{{ order.team }}</span>
      <span>{{ order.createTime }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  order: { type: Object, required: true },
})
defineEmits(['click'])

const levelMap = { red: '高危', orange: '中危', yellow: '低危' }
const colorMap = { red: 'red', orange: 'orange', yellow: 'gold' }
const statusMap = { pending: '待处理', processing: '处理中', done: '已完成' }

const levelText = computed(() => levelMap[props.order.level] || props.order.level)
const levelColor = computed(() => colorMap[props.order.level] || 'default')
const statusText = computed(() => statusMap[props.order.status] || props.order.status)
</script>

<style scoped>
.wo-card {
  background: var(--surface);
  border-radius: 8px;
  padding: 12px 14px;
  border-left: 4px solid var(--border-color);
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.wo-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.level-red { border-left-color: var(--danger); }
.level-orange { border-left-color: var(--warning); }
.level-yellow { border-left-color: var(--caution); }
.wo-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.wo-id {
  flex: 1;
  font-size: 12px;
  color: var(--text-secondary);
}
.wo-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.wo-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
