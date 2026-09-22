<template>
  <!--
    道路监控点位图
    -------------------------------------------------------
    当前：静态 CAD 底图占位 + 百分比点位
    【地图对接预留】高德 / 百度 API
    - 将 useMapProvider 改为 'amap' 或 'baidu'
    - 填写下方 API Key
    - 实现 initRealMap() 即可切换
  -->
  <div class="site-map" ref="mapRef">
    <!-- 静态 CAD 底图占位 -->
    <div v-if="provider === 'static'" class="cad-bg">
      <svg class="cad-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
        <!-- 道路点位示意 -->
        <rect x="5" y="5" width="90" height="90" fill="none" stroke="var(--text-muted)" stroke-width="0.4" />
        <rect x="10" y="15" width="30" height="25" fill="var(--surface-muted)" stroke="var(--border-color)" stroke-width="0.3" />
        <text x="15" y="28" font-size="3" fill="var(--text-secondary)">主体结构</text>
        <rect x="50" y="20" width="35" height="30" fill="var(--primary-soft)" stroke="var(--primary)" stroke-width="0.3" />
        <text x="58" y="35" font-size="3" fill="var(--link)">材料区</text>
        <rect x="20" y="55" width="40" height="28" fill="var(--surface-muted)" stroke="var(--text-muted)" stroke-width="0.3" />
        <text x="30" y="70" font-size="3" fill="var(--text-secondary)">基坑区</text>
        <line x1="5" y1="50" x2="95" y2="50" stroke="var(--border-color)" stroke-width="0.2" stroke-dasharray="1,1" />
        <line x1="50" y1="5" x2="50" y2="95" stroke="var(--border-color)" stroke-width="0.2" stroke-dasharray="1,1" />
      </svg>
      <!-- 风险点位 -->
      <div
        v-for="p in points"
        :key="p.id"
        class="point"
        role="button"
        tabindex="0"
        :aria-label="`${p.name}，隐患${p.riskCount}件，查看监控`"
        @keydown.enter="$emit('point-click', p)"
        @keydown.space.prevent="$emit('point-click', p)"
        :class="'risk-' + p.riskLevel"
        :style="{ left: p.x + '%', top: p.y + '%' }"
        @click="$emit('point-click', p)"
      >
        <a-tooltip :title="`${p.name} · 隐患${p.riskCount}件`">
          <span class="dot" />
        </a-tooltip>
        <span class="point-name">{{ p.name }}</span>
      </div>
    </div>

    <!-- 高德地图容器预留 -->
    <div v-else-if="provider === 'amap'" id="amap-container" class="real-map" />
    <!-- 百度地图容器预留 -->
    <div v-else-if="provider === 'baidu'" id="baidu-container" class="real-map" />
  </div>
</template>

<script setup>
/**
 * 地图能力切换说明（后续对接）：
 * 1. provider 改为 'amap' 或 'baidu'
 * 2. 在 index.html 引入对应地图 JS SDK
 * 3. 在 onMounted 中调用 initAmap / initBaidu
 */
import { onMounted, ref } from 'vue'

defineProps({
  points: { type: Array, default: () => [] },
  /** static | amap | baidu */
  provider: { type: String, default: 'static' },
})
defineEmits(['point-click'])

const mapRef = ref(null)

/** 【对接位】高德 Key */
const AMAP_KEY = 'YOUR_AMAP_KEY'
/** 【对接位】百度 Key */
const BAIDU_KEY = 'YOUR_BAIDU_KEY'

function initAmap() {
  // 示例：new AMap.Map('amap-container', { zoom: 16, center: [120.2, 30.2] })
  console.info('[SiteMap] 高德地图预留，请配置 AMAP_KEY=', AMAP_KEY)
}

function initBaidu() {
  // 示例：new BMap.Map('baidu-container')
  console.info('[SiteMap] 百度地图预留，请配置 BAIDU_KEY=', BAIDU_KEY)
}

onMounted(() => {
  // provider 非 static 时在此初始化真实地图
})

defineExpose({ initAmap, initBaidu })
</script>

<style scoped>
.site-map {
  width: 100%;
  height: 100%;
  min-height: 320px;
  position: relative;
  background: var(--surface-muted);
  border-radius: 8px;
  overflow: hidden;
}
.cad-bg {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 320px;
}
.cad-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.point {
  position: absolute;
  transform: translate(-50%, -50%);
  cursor: pointer;
  z-index: 2;
  text-align: center;
}
.dot {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--surface);
  background: currentColor;
  box-shadow: 0 0 0 2px currentColor, 0 0 0 6px color-mix(in srgb,currentColor 12%,transparent);

}
.risk-red { color: var(--danger); }
.risk-orange { color: var(--warning); }
.risk-yellow { color: var(--caution); }
.risk-green { color: var(--success); }
.point-name {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  white-space: nowrap;
  background: color-mix(in srgb, var(--surface) 88%, transparent);
  color: var(--text-primary);
  padding: 0 4px;
  border-radius: 2px;
}
.real-map {
  width: 100%;
  height: 100%;
  min-height: 320px;
}
@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.25); opacity: 0.75; }
}
</style>
