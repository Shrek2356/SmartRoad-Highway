<template>
  <!-- Components and custom surfaces share one semantic palette. -->
  <a-config-provider :theme="activeTheme" :locale="zhCN" :get-popup-container="popupContainer">
    <router-view />
    <VisualAccessibility />
  </a-config-provider>
</template>

<script setup>
/**
 * 根组件
 * 仅作为路由容器，业务页面见 views/ 目录
 * 主题色与 styles/global.css 中的 CSS 变量保持一致
 */
import { computed } from 'vue'
import { theme as antTheme } from 'ant-design-vue'
import { colorTheme } from '@/utils/theme'
import { antTokens, paletteFor } from '@/utils/designTokens'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import VisualAccessibility from '@/components/VisualAccessibility.vue'
import { fontPercent,popupContainer } from '@/utils/displayPreferences'

const activeTheme = computed(() => ({
  algorithm: colorTheme.value === 'dark' ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
  token: { ...antTokens(colorTheme.value), fontSize:Math.round(14*fontPercent.value/100),controlHeight:Math.max(36,Math.round(30*fontPercent.value/100)) },
  components: {
    Slider: { colorPrimaryBorder: paletteFor(colorTheme.value).primary, colorPrimaryBorderHover: paletteFor(colorTheme.value)['primary-strong'] },
    Tooltip: { colorBgDefault: colorTheme.value === 'light' ? '#242424' : '#122c3a', colorTextLightSolid: colorTheme.value === 'light' ? '#fafafa' : '#f1f8fb' },
  },
}))
</script>
