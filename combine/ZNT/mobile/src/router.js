import { createRouter, createWebHashHistory } from 'vue-router'
import Home from '../pages/index/index.vue'
import Alarm from '../pages/alarm/index.vue'
import WorkOrder from '../pages/workorder/index.vue'
import CasePage from '../pages/case/index.vue'
import Report from '../pages/report/index.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: Home, meta: { title: '首页', tab: true } },
    { path: '/workorder', name: 'workorder', component: WorkOrder, meta: { title: '工单', tab: true } },
    { path: '/case', name: 'case', component: CasePage, meta: { title: '案例', tab: true } },
    { path: '/report', name: 'report', component: Report, meta: { title: '上报', tab: true } },
    { path: '/alarm', name: 'alarm', component: Alarm, meta: { title: '告警处置' } },
  ],
})

export default router
