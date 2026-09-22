<template>
  <div class="phone">
    <header class="top">
      <div>
        <div class="brand">路安智巡道路监测</div>
        <div class="title">道路值班工作台</div>
      </div>
      <button type="button" class="settings-button" title="连接设置" @click="openSettings">⚙</button>
    </header>

    <main class="body">
      <router-view />
    </main>

    <nav v-if="showTab" class="tabs">
      <router-link
        v-for="item in tabs"
        :key="item.path"
        :to="item.path"
        class="tab"
        :class="{ on: route.path === item.path }"
      >
        {{ item.label }}
      </router-link>
    </nav>

    <div v-if="settingsVisible" class="settings-mask" @click.self="settingsVisible = false">
      <section class="settings-panel">
        <div class="settings-head">
          <strong>移动端连接设置</strong>
          <button type="button" class="close-button" @click="settingsVisible = false">×</button>
        </div>
        <label>
          <span>业务后台地址</span>
          <input v-model.trim="settings.businessApi" placeholder="http://127.0.0.1:8800" />
        </label>
        <label>
          <span>检测桥地址</span>
          <input v-model.trim="settings.detectApi" placeholder="http://127.0.0.1:8810" />
        </label>
        <div class="settings-row">
          <label>
            <span>登录账号</span>
            <input v-model.trim="settings.username" autocomplete="username" />
          </label>
          <label>
            <span>登录密码</span>
            <input v-model="settings.password" type="password" autocomplete="current-password" />
          </label>
        </div>
        <label>
          <span>AI 检测模式</span>
          <select v-model="settings.profile">
            <option v-for="option in profileOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
        <p class="settings-tip">配置只保存在本机浏览器；保存后会重新连接业务后台。</p>
        <div class="settings-actions">
          <button type="button" class="reset-button" @click="resetSettings">恢复演示默认</button>
          <button type="button" class="save-button" @click="saveSettings">保存并重连</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  DETECT_PROFILE_OPTIONS,
  getRuntimeConfig,
  resetRuntimeConfig,
  saveRuntimeConfig,
} from '../api/index.js'

const route = useRoute()
const showTab = computed(() => !!route.meta.tab)
const settingsVisible = ref(false)
const settings = reactive(getRuntimeConfig())
const profileOptions = DETECT_PROFILE_OPTIONS

const tabs = [
  { path: '/', label: '首页' },
  { path: '/workorder', label: '工单' },
  { path: '/case', label: '案例' },
  { path: '/report', label: '上报' },
]

function openSettings() {
  Object.assign(settings, getRuntimeConfig())
  settingsVisible.value = true
}

function stripRuntimeQuery() {
  const url = new URL(window.location.href)
  ;['api', 'detect', 'username', 'user', 'password', 'profile'].forEach((key) => {
    url.searchParams.delete(key)
  })
  window.history.replaceState({}, '', url.toString())
}

function saveSettings() {
  try {
    saveRuntimeConfig(settings)
    stripRuntimeQuery()
    uni.showToast({ title: '配置已保存，正在重连', icon: 'success' })
    setTimeout(() => window.location.reload(), 350)
  } catch (error) {
    uni.showToast({ title: error.message || '配置保存失败', icon: 'none' })
  }
}

function resetSettings() {
  Object.assign(settings, resetRuntimeConfig())
  stripRuntimeQuery()
  uni.showToast({ title: '已恢复演示默认配置', icon: 'success' })
}
</script>

<style scoped>
.phone {
  width: min(390px, 100vw);
  min-height: 100vh;
  max-height: 100vh;
  background: #f5f6f8;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(11, 31, 58, 0.18);
}
.top {
  background: #0b1f3a;
  color: #fff;
  padding: 14px 16px 12px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.brand {
  font-size: 12px;
  opacity: 0.85;
}
.title {
  font-size: 18px;
  font-weight: 700;
  margin-top: 4px;
}
.settings-button,
.close-button {
  border: 0;
  color: #fff;
  background: transparent;
  cursor: pointer;
}
.settings-button {
  width: 36px;
  height: 36px;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 50%;
  font-size: 18px;
}
.body {
  flex: 1;
  overflow: auto;
  padding-bottom: 56px;
}
.tabs {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  background: #fff;
  border-top: 1px solid #eee;
  padding: 10px 0;
  text-align: center;
  font-size: 12px;
}
.tab {
  color: #8c8c8c;
  text-decoration: none;
}
.tab.on {
  color: #1677ff;
  font-weight: 700;
}
.settings-mask {
  position: absolute;
  inset: 0;
  z-index: 200;
  background: rgba(5, 18, 36, 0.62);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.settings-panel {
  width: 100%;
  max-height: calc(100vh - 32px);
  overflow: auto;
  border-radius: 14px;
  padding: 16px;
  background: #fff;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.2);
}
.settings-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 16px;
}
.close-button {
  color: #8c8c8c;
  font-size: 24px;
  line-height: 1;
}
.settings-panel label {
  display: block;
  margin-top: 10px;
}
.settings-panel label span {
  display: block;
  margin-bottom: 5px;
  color: #595959;
  font-size: 12px;
}
.settings-panel input,
.settings-panel select {
  width: 100%;
  min-width: 0;
  border: 1px solid #d9d9d9;
  border-radius: 7px;
  background: #fff;
  padding: 9px 10px;
  color: #262626;
  font: inherit;
  font-size: 13px;
  outline: none;
}
.settings-panel input:focus,
.settings-panel select:focus {
  border-color: #1677ff;
}
.settings-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.settings-tip {
  margin: 12px 0;
  color: #8c8c8c;
  font-size: 11px;
  line-height: 1.5;
}
.settings-actions {
  display: flex;
  gap: 8px;
}
.settings-actions button {
  flex: 1;
  border: 0;
  border-radius: 8px;
  padding: 10px 8px;
  cursor: pointer;
  font-size: 13px;
}
.reset-button {
  background: #f0f2f5;
  color: #595959;
}
.save-button {
  background: #1677ff;
  color: #fff;
}
</style>
