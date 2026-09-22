<template>
  <div class="page">
    <div class="card" v-if="alarm.id">
      <div class="title" :style="{ color: levelColor(alarm.level) }">
        {{ levelText(alarm.level) }} · {{ alarm.title }}
      </div>
      <div class="line">区域：{{ alarm.area }}</div>
      <div class="line">设备：{{ alarm.camera }}</div>
      <div class="line">时间：{{ alarm.time }}</div>
      <div class="snap">{{ alarm.snapTip }}</div>
      <div class="reg">{{ alarm.regulation }}</div>
      <button type="button" class="primary" @click="onHandle('accept')">接单处置</button>
      <button type="button" class="ghost" @click="onHandle('ignore')">误报忽略</button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchLatestAlarm, handleAlarm } from '../../api/index.js'
import { levelColor, levelText } from '../../utils/risk.js'

const alarm = ref({})

async function onHandle(action) {
  try {
    await handleAlarm({ alarmId: alarm.value.id, action })
    uni.showToast({ title: '已提交', icon: 'success' })
  } catch (error) {
    uni.showToast({ title: error.message || '提交失败', icon: 'none' })
  }
}

onMounted(async () => {
  const res = await fetchLatestAlarm()
  alarm.value = res.data
})
</script>

<style scoped>
.card {
  margin: 12px;
  background: #fff;
  border-radius: 12px;
  padding: 14px;
}
.title { font-size: 17px; font-weight: 700; margin-bottom: 10px; }
.line { font-size: 14px; margin-bottom: 6px; color: #595959; }
.snap {
  height: 120px;
  margin: 10px 0;
  background: #0a1628;
  color: #8cbfef;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  text-align: center;
  padding: 0 10px;
}
.reg { font-size: 12px; color: #8c8c8c; margin-bottom: 12px; line-height: 1.5; }
button {
  width: 100%;
  border: 0;
  border-radius: 8px;
  padding: 10px;
  cursor: pointer;
  font-size: 14px;
}
button.primary { background: #1677ff; color: #fff; }
button.ghost {
  margin-top: 8px;
  background: #fff;
  color: #595959;
  border: 1px solid #d9d9d9;
}
</style>
