/**
 * 道路监控可视化大屏入口
 * 技术栈：Vue3 + DataV + ECharts
 */
import { createApp } from 'vue'
import DataVVue3 from '@kjgl77/datav-vue3'
import App from './App.vue'
import './styles/screen.css'

const app = createApp(App)
app.use(DataVVue3)
app.mount('#app')
