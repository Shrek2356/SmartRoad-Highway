import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { installUni } from './uni'
import './styles.css'

installUni()
createApp(App).use(router).mount('#app')
