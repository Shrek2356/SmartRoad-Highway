<template>
  <div class="page">
    <div class="search-bar">
      <input
        v-model="keyword"
        class="input"
        placeholder="搜索案例标题/摘要"
        @keyup.enter="load"
      />
      <div class="search-btn" @click="load">搜索</div>
    </div>

    <div class="list">
      <div v-for="c in list" :key="c.id" class="card">
        <div class="title">
          <span :style="{ color: levelColor(c.level) }">[{{ levelText(c.level) }}]</span>
          {{ c.title }}
        </div>
        <div class="type">类型：{{ c.type }}</div>
        <div class="summary">{{ c.summary }}</div>
      </div>
      <div v-if="!list.length" class="empty">未找到相关案例</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchCases } from '../../api/index.js'
import { levelColor, levelText } from '../../utils/risk.js'

const keyword = ref('')
const list = ref([])

async function load() {
  const res = await fetchCases({ keyword: keyword.value })
  list.value = res.data
}

onMounted(load)
</script>

<style scoped>
.search-bar {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  background: #fff;
}
.input {
  flex: 1;
  background: #f5f5f5;
  border: 0;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  outline: none;
}
.search-btn {
  background: #1677ff;
  color: #fff;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
.list { padding: 12px; }
.card {
  background: #fff;
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 10px;
}
.title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
.type { font-size: 12px; color: #8c8c8c; margin-bottom: 4px; }
.summary { font-size: 13px; color: #595959; line-height: 1.5; }
.empty { text-align: center; color: #8c8c8c; padding: 40px 0; }
</style>
