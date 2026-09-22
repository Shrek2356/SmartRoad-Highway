<template>
  <div class="page">
    <div class="tabs">
      <div
        v-for="t in tabs"
        :key="t.value"
        class="tab"
        :class="{ active: status === t.value }"
        @click="switchTab(t.value)"
      >{{ t.label }}</div>
    </div>

    <div class="list">
      <div v-for="item in list" :key="item.id" class="card">
        <WorkOrderCard :order="item" />
        <div class="steps">
          <div
            v-for="(s, i) in item.steps"
            :key="s"
            class="step"
            :class="{ done: i <= item.currentStep }"
          >{{ i + 1 }}.{{ s }}</div>
        </div>
        <div class="btns" v-if="item.status !== 'done'">
          <button type="button" class="primary" @click="nextStep(item)">推进下一步</button>
          <button type="button" @click="takePhoto(item)">拍照复核</button>
        </div>
      </div>
      <div v-if="!list.length" class="empty">暂无工单</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import WorkOrderCard from '../../components/WorkOrderCard.vue'
import { advanceWorkOrder, fetchWorkOrders, uploadWorkOrderEvidence } from '../../api/index.js'

const tabs = [
  { label: '全部', value: '' },
  { label: '待处理', value: 'pending' },
  { label: '处理中', value: 'processing' },
  { label: '已完成', value: 'done' },
]
const status = ref('')
const list = ref([])

async function load() {
  const res = await fetchWorkOrders({ status: status.value || undefined })
  list.value = res.data
}

function switchTab(v) {
  status.value = v
  load()
}

async function nextStep(item) {
  try {
    const action = item.rawStatus === 'rectified' ? 'close' : 'next'
    await advanceWorkOrder({ id: item.id, action })
    await load()
    uni.showToast({ title: '已推进', icon: 'success' })
  } catch (error) {
    uni.showToast({ title: error.message || '推进失败', icon: 'none' })
  }
}

function takePhoto(item) {
  uni.chooseImage({
    count: 1,
    success: async (res) => {
      const file = res.tempFiles?.[0]
      const url = res.tempFilePaths?.[0]
      if (!file) return
      try {
        await uploadWorkOrderEvidence({ id: item.id, image: { file, url } })
        await load()
        uni.showToast({ title: '照片复核已提交', icon: 'success' })
      } catch (error) {
        uni.showToast({ title: error.message || '照片提交失败', icon: 'none' })
      }
    },
  })
}

onMounted(load)
</script>

<style scoped>
.tabs {
  display: flex;
  background: #fff;
  padding: 8px 4px;
}
.tab {
  flex: 1;
  text-align: center;
  font-size: 13px;
  color: #8c8c8c;
  padding: 8px 0;
  cursor: pointer;
}
.tab.active {
  color: #1677ff;
  font-weight: 600;
  border-bottom: 2px solid #1677ff;
}
.list { padding: 12px; }
.card {
  background: #fff;
  border-radius: 12px;
  padding: 4px 8px 10px;
  margin-bottom: 10px;
}
.steps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 4px 0 8px;
}
.step {
  font-size: 11px;
  color: #bfbfbf;
  background: #f5f5f5;
  padding: 4px 8px;
  border-radius: 4px;
}
.step.done { color: #1677ff; background: #e6f4ff; }
.btns { display: flex; gap: 8px; }
.btns button {
  flex: 1;
  border: 1px solid #d9d9d9;
  background: #fff;
  border-radius: 6px;
  padding: 8px;
  cursor: pointer;
  font-size: 12px;
}
.btns button.primary {
  background: #1677ff;
  color: #fff;
  border-color: #1677ff;
}
.empty { text-align: center; color: #8c8c8c; padding: 40px 0; }
</style>
