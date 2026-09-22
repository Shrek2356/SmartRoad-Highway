/**
 * PC管理后台入口文件
 * 作用：挂载 Vue 应用，注册路由、状态管理、Ant Design Vue
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import router from './router'
import './styles/global.css'
import './styles/product.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(Antd)

app.mount('#app')
