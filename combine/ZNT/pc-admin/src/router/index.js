/**
 * 路由配置
 * -------------------------------------------------------
 * 预留角色权限：meta.roles 为空表示所有登录用户可访问
 * 【后续修改入口】新增页面时在此注册路由，并在 layouts 菜单同步
 * -------------------------------------------------------
 */
import { createRouter, createWebHistory } from 'vue-router'
import { checkPermission } from '@/utils/permission'
import { useUserStore } from '@/stores/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/BasicLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'help-center', name: 'HelpCenter', component: () => import('@/views/help-center/index.vue'),
        meta: { title: '使用与支持', icon: 'QuestionCircleOutlined', roles: [] },
      },
      {
        path: 'task-center', name: 'TaskCenter', component: () => import('@/views/task-center/index.vue'),
        meta: { title: '检测任务中心', icon: 'RadarChartOutlined', roles: [] },
      },
      {
        path: 'system-settings', name: 'SystemSettings', component: () => import('@/views/system-settings/index.vue'),
        meta: { title: '系统设置', icon: 'ClusterOutlined', roles: ['admin'] },
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/RoadLab.vue'),
        meta: { title: '首页工作台', icon: 'DashboardOutlined', roles: [] },
      },
      {
        path: 'monitor',
        name: 'Monitor',
        component: () => import('@/views/monitor/index.vue'),
        meta: { title: '实时视频监控', icon: 'VideoCameraOutlined', roles: [] },
      },
      {
        path: 'realtime-detect',
        name: 'RealtimeDetect',
        component: () => import('@/views/realtime-detect/index.vue'),
        meta: {
          title: '实时检测',
          icon: 'RadarChartOutlined',
          roles: [],
        },
      },
      {
        path: 'workorder',
        name: 'WorkOrder',
        component: () => import('@/views/workorder/index.vue'),
        meta: { title: '风险工单处置', icon: 'FileProtectOutlined', roles: [] },
      },
      {
        path: 'agent-center',
        name: 'AgentCenter',
        component: () => import('@/views/agent-center/index.vue'),
        meta: { title: 'Agent协同学习', icon: 'TeamOutlined', roles: ['admin', 'safety'] },
      },
      {
        path: 'analysis',
        name: 'Analysis',
        component: () => import('@/views/analysis/index.vue'),
        meta: {
          title: '智能复盘分析',
          icon: 'BarChartOutlined',
          roles: ['admin', 'director'],
        },
      },
      {
        path: 'detection-results',
        name: 'DetectionResults',
        component: () => import('@/views/detection-results/index.vue'),
        meta: {
          title: '检测结果汇总',
          icon: 'SafetyCertificateOutlined',
          roles: ['admin', 'director', 'safety'],
        },
      },
      {
        path: 'model-config',
        name: 'ModelConfig',
        component: () => import('@/views/model-config/index.vue'),
        meta: {
          title: '模型规则配置',
          icon: 'ExperimentOutlined',
          roles: ['admin'],
        },
      },
      {
        path: 'case-library',
        name: 'CaseLibrary',
        component: () => import('@/views/case-library/index.vue'),
        meta: { title: '安全案例库', icon: 'BookOutlined', roles: [] },
      },
      {
        path: 'resource',
        name: 'Resource',
        component: () => import('@/views/resource/index.vue'),
        meta: {
          title: '基础资源管理',
          icon: 'ClusterOutlined',
          roles: ['admin', 'director'],
        },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/** 全局守卫：登录校验 + 角色权限 */
router.beforeEach((to, _from, next) => {
  document.title = `${to.meta.title || '道路安全'} · 路安智巡 SmartRoad-Inspection`

  if (to.meta.public) {
    next()
    return
  }

  const userStore = useUserStore()
  if (!userStore.isLogin) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  // 路由 meta.roles 优先；同时兼容 permission 工具
  const roles = to.meta.roles
  if (roles?.length && !roles.includes(userStore.role)) {
    next('/dashboard')
    return
  }
  if (!checkPermission(userStore.role, '/' + (to.path.split('/')[1] || ''))) {
    next('/dashboard')
    return
  }
  next()
})

export default router

/** 供菜单渲染使用的路由列表 */
export function getMenuRoutes() {
  const layout = routes.find((r) => r.path === '/')
  return layout?.children || []
}
