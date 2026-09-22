<template>
  <div class="page">
    <div class="hero">
      <div class="hello">您好，道路值班员</div>
      <div class="sub">今日待办 {{ reminders.length }} 件 · 业务后台实时数据</div>
    </div>

    <div class="card">
      <div class="section-title">工单提醒</div>
      <WorkOrderCard
        v-for="item in reminders"
        :key="item.id"
        :order="item"
        @click="goWorkOrder"
      />
      <div v-if="!reminders.length" class="empty">暂无待办</div>
    </div>

    <div class="card actions">
      <div class="action" @click="showAlarm = true">查看最新告警</div>
      <div class="action ghost" @click="goReport">人工上报隐患</div>
    </div>

    <div v-if="showAlarm" class="mask" @click="showAlarm = false">
      <div class="dialog" @click.stop>
        <div class="dialog-title" :style="{ color: levelColor(alarm.level) }">
          {{ levelText(alarm.level) }}告警
        </div>
        <div class="dialog-body">
          <div class="line"><span class="label">类型</span>{{ alarm.title }}</div>
          <div class="line"><span class="label">区域</span>{{ alarm.area }}</div>
          <div class="line"><span class="label">摄像头</span>{{ alarm.camera }}</div>
          <div class="line"><span class="label">时间</span>{{ alarm.time }}</div>
          <div class="snap">{{ alarm.snapTip }}</div>
          <div class="reg">{{ alarm.regulation }}</div>
        </div>
        <div class="dialog-actions">
          <button type="button" @click="onHandle('accept')">接单处置</button>
          <button type="button" class="ghost" @click="onHandle('escalate')">升级上报</button>
          <button type="button" class="ghost" @click="onHandle('ignore')">误报忽略</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import WorkOrderCard from '../../components/WorkOrderCard.vue'
import { fetchHomeReminders, fetchLatestAlarm, handleAlarm } from '../../api/index.js'
import { levelColor, levelText } from '../../utils/risk.js'

const reminders = ref([])
const alarm = ref({})
const showAlarm = ref(false)

function goWorkOrder() {
  uni.switchTab({ url: '/pages/workorder/index' })
}
function goReport() {
  uni.switchTab({ url: '/pages/report/index' })
}

async function onHandle(action) {
  try {
    await handleAlarm({ alarmId: alarm.value.id, action })
    uni.showToast({ title: '操作成功', icon: 'success' })
    showAlarm.value = false
    if (action === 'accept') goWorkOrder()
  } catch (error) {
    uni.showToast({ title: error.message || '操作失败', icon: 'none' })
  }
}

onMounted(async () => {
  try {
    const [r, a] = await Promise.all([fetchHomeReminders(), fetchLatestAlarm()])
    reminders.value = r.data
    alarm.value = a.data
    if (a.data?.level === 'red') {
      setTimeout(() => { showAlarm.value = true }, 600)
    }
  } catch (error) {
    uni.showToast({ title: error.message || '后台连接失败，请打开右上角设置', icon: 'none' })
  }
})
</script>

<style scoped>
.hero {
  background: linear-gradient(135deg, #0b1f3a, #1677ff);
  color: #fff;
  padding: 24px 16px 28px;
}
.hello { font-size: 20px; font-weight: 700; }
.sub { margin-top: 6px; opacity: 0.85; font-size: 13px; }
.card {
  background: #fff;
  border-radius: 12px;
  padding: 12px;
  margin: 12px;
}
.section-title { font-size: 15px; font-weight: 600; margin-bottom: 10px; }
.empty { text-align: center; color: #8c8c8c; padding: 20px 0; }
.actions { display: flex; flex-direction: column; gap: 10px; }
.action {
  background: #1677ff;
  color: #fff;
  text-align: center;
  padding: 12px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}
.action.ghost {
  background: #fff;
  color: #1677ff;
  border: 1px solid #1677ff;
}
.mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 99;
}
.dialog {
  width: 86%;
  max-width: 340px;
  background: #fff;
  border-radius: 12px;
  padding: 16px;
}
.dialog-title { font-size: 18px; font-weight: 700; margin-bottom: 10px; }
.line { font-size: 14px; margin-bottom: 6px; }
.label { color: #8c8c8c; margin-right: 8px; }
.snap {
  margin: 8px 0;
  height: 100px;
  background: #0a1628;
  color: #8cbfef;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  padding: 0 10px;
  text-align: center;
}
.reg { font-size: 12px; color: #595959; line-height: 1.5; }
.dialog-actions {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.dialog-actions button {
  flex: 1;
  border: 0;
  border-radius: 6px;
  padding: 8px 6px;
  background: #1677ff;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
}
.dialog-actions button.ghost {
  background: #fff;
  color: #1677ff;
  border: 1px solid #1677ff;
}
</style>
