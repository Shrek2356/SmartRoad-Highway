<template>
  <div class="page">
    <div class="card">
      <div class="label">隐患标题</div>
      <input v-model="form.title" class="input" placeholder="请输入隐患标题" />

      <div class="label">风险等级</div>
      <div class="levels">
        <div
          v-for="l in levels"
          :key="l.value"
          class="level-item"
          :class="{ active: form.level === l.value }"
          :style="form.level === l.value ? { borderColor: l.color, color: l.color } : {}"
          @click="form.level = l.value"
        >{{ l.label }}</div>
      </div>

      <div class="label">发生区域</div>
      <input v-model="form.area" class="input" placeholder="如：脚手架C区" />

      <div class="label">情况描述</div>
      <textarea v-model="form.desc" class="textarea" placeholder="请描述现场情况" />

      <div class="label">现场照片</div>
      <div class="photos">
        <div v-for="(p, i) in photos" :key="i" class="photo">已选图{{ i + 1 }}</div>
        <div class="photo add" @click="chooseImage">+</div>
      </div>

      <button type="button" class="primary" :disabled="loading" @click="onAiAssist">AI 辅助识别</button>
      <button type="button" class="warn" :disabled="loading" @click="onSubmit">提交上报</button>
      <div class="tip">AI 辅助识别调用检测桥；人工上报写入业务后台。</div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { detectImage, submitReport } from '../../api/index.js'

const levels = [
  { label: '高危', value: 'red', color: '#ff4d4f' },
  { label: '中危', value: 'orange', color: '#fa8c16' },
  { label: '低危', value: 'yellow', color: '#d4b106' },
]

const form = reactive({
  title: '',
  level: 'orange',
  area: '',
  desc: '',
})
const photos = ref([])
const loading = ref(false)

function chooseImage() {
  uni.chooseImage({
    count: 3,
    success: (res) => {
      const selected = (res.tempFiles || []).map((file, index) => ({
        file,
        url: res.tempFilePaths[index],
      }))
      photos.value = photos.value.concat(selected).slice(0, 3)
    },
  })
}

async function onAiAssist() {
  if (!photos.value.length) {
    uni.showToast({ title: '请先选择照片', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const job = await detectImage(photos.value[0].url)
    const risk = job.result?.risks?.[0]
    form.title = risk?.risk_name_zh || risk?.name || '现场异常待复核'
    form.level = risk?.risk_level === 'critical' ? 'red' : risk?.risk_level === 'major' ? 'orange' : 'yellow'
    form.desc = risk?.risk_description || risk?.description || form.desc
    uni.showToast({ title: 'AI识别完成', icon: 'success' })
  } catch (error) {
    uni.showToast({ title: error.message || 'AI识别失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function onSubmit() {
  if (!form.title || !form.area) {
    uni.showToast({ title: '请填写标题和区域', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const res = await submitReport({ ...form, images: photos.value })
    uni.showToast({ title: res.data.message, icon: 'success' })
    form.title = ''
    form.area = ''
    form.desc = ''
    photos.value = []
  } catch (error) {
    uni.showToast({ title: error.message || '上报失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.card {
  margin: 12px;
  background: #fff;
  border-radius: 12px;
  padding: 14px;
}
.label { font-size: 13px; color: #8c8c8c; margin: 8px 0 6px; }
.input, .textarea {
  background: #f5f5f5;
  border: 0;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  width: 100%;
  outline: none;
  font: inherit;
}
.textarea { min-height: 80px; resize: vertical; }
.levels { display: flex; gap: 8px; }
.level-item {
  flex: 1;
  text-align: center;
  padding: 8px 0;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
.photos { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.photo {
  width: 70px;
  height: 70px;
  background: #f0f5ff;
  color: #1677ff;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
}
.photo.add {
  font-size: 24px;
  background: #f5f5f5;
  color: #8c8c8c;
  cursor: pointer;
}
button {
  width: 100%;
  border: 0;
  border-radius: 8px;
  padding: 10px;
  cursor: pointer;
  font-size: 14px;
}
button:disabled { opacity: 0.6; cursor: not-allowed; }
button.primary { background: #1677ff; color: #fff; }
button.warn {
  margin-top: 10px;
  background: #ff4d4f;
  color: #fff;
}
.tip { margin-top: 10px; font-size: 11px; color: #bfbfbf; line-height: 1.5; }
</style>
