<template>
  <a-layout class="basic-layout">
    <a class="skip-content" href="#main-content">跳转到页面内容</a>
    <!-- 侧边栏 -->
    <a-layout-sider v-model:collapsed="collapsed" collapsible :theme="colorTheme" width="224">
      <div class="logo">
        <SafetyCertificateOutlined class="brand-symbol" />
        <span v-if="!collapsed" class="logo-full">
          <span class="logo-title">路安智巡</span>
          <span class="logo-team">SMARTROAD-HIGHWAY</span>
        </span>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        :theme="colorTheme"
        mode="inline"
        @click="onMenuClick"
      >
        <a-menu-item-group v-for="group in menuGroups" :key="group.title" :title="collapsed ? '' : group.title">
          <a-menu-item v-for="item in group.items" :key="item.path">
            <component :is="iconMap[item.meta.icon]" />
            <span>{{ item.meta.title }}</span>
          </a-menu-item>
        </a-menu-item-group>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <!-- 顶栏 -->
      <a-layout-header class="header">
        <div class="header-left">
          <span class="project-label">当前项目</span>
          <a-select
            v-model:value="projectId"
            style="width: 218px"
            placeholder="切换项目"
            aria-label="切换当前项目"
            @change="onProjectChange"
          >
            <a-select-option v-for="p in projects" :key="p.id" :value="p.id">
              {{ p.name }}
            </a-select-option>
          </a-select>
        </div>
        <div class="header-right">
          <ProductGuide />
          <span class="industrial-label">HIGHWAY <i>/</i> 道路安全监测</span>
          <a-tooltip :title="colorTheme === 'dark' ? '切换明亮模式' : '切换暗色模式'">
            <a-button class="theme-toggle" shape="circle" :aria-label="colorTheme === 'dark' ? '切换明亮模式' : '切换暗色模式'" @click="toggleColorTheme">
              <BulbOutlined v-if="colorTheme === 'dark'" />
              <span v-else aria-hidden="true">☾</span>
            </a-button>
          </a-tooltip>
          <a-dropdown placement="bottomRight" :trigger="['click']"><a-button class="user-menu"><UserOutlined /><span class="username">{{ userStore.displayName }}</span><DownOutlined /></a-button><template #overlay><a-menu><a-menu-item disabled>{{ ROLE_LABELS[userStore.role] || userStore.role }}</a-menu-item><a-menu-item @click="router.push('/help-center')">使用与支持</a-menu-item><a-menu-item @click="setWorkspaceStyle(workspaceStyle === 'professional' ? 'showcase' : 'professional')">{{ workspaceStyle === 'professional' ? '切换为作品展示视图' : '切换为专业工作台' }}</a-menu-item><a-menu-divider /><a-menu-item @click="onLogout">退出登录（后台任务继续）</a-menu-item></a-menu></template></a-dropdown>
        </div>
      </a-layout-header>
      <RuntimeStatus />

      <!-- 内容区 -->
      <a-layout-content id="main-content" tabindex="-1" class="content">
        <div class="page-location"><span>工作空间</span><span>/</span><strong>{{ route.meta.title }}</strong><span v-if="route.path !== '/dashboard'" class="location-summary">{{ pageFor(route.path)?.description }}</span></div>
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup>
/**
 * 主布局：侧栏菜单 + 顶栏项目切换 + 内容区
 * 【后续修改入口】菜单来自路由 meta，新增页面只需加路由
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DashboardOutlined,
  VideoCameraOutlined,
  FileProtectOutlined,
  BarChartOutlined,
  ExperimentOutlined,
  BookOutlined,
  ClusterOutlined,
  SafetyCertificateOutlined,
  RadarChartOutlined,
  BulbOutlined,
  TeamOutlined,
  QuestionCircleOutlined, UserOutlined, DownOutlined,
} from '@ant-design/icons-vue'
import { getMenuRoutes } from '@/router'
import { useUserStore } from '@/stores/user'
import { ROLE_LABELS } from '@/utils/permission'
import { fetchProjects } from '@/api/resource'
import { message } from 'ant-design-vue'
import { colorTheme, toggleColorTheme } from '@/utils/theme'
import { startBusinessSocket, stopBusinessSocket } from '@/utils/businessSocket'
import RuntimeStatus from '@/components/RuntimeStatus.vue'
import { workspaceStyle, setWorkspaceStyle } from '@/utils/preferences'
import ProductGuide from '@/components/ProductGuide.vue'
import { pageFor } from '@/utils/guidance'

const iconMap = {
  DashboardOutlined,
  VideoCameraOutlined,
  FileProtectOutlined,
  BarChartOutlined,
  ExperimentOutlined,
  BookOutlined,
  ClusterOutlined,
  SafetyCertificateOutlined,
  RadarChartOutlined,
  TeamOutlined,
  QuestionCircleOutlined,
}

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const collapsed = ref(false)
const selectedKeys = ref([route.path.replace(/^\//, '')])
const projects = ref([])
const projectId = ref(userStore.project?.id || '')

const visibleMenus = computed(() => {
  const role = userStore.role
  return getMenuRoutes().filter((m) => {
    const roles = m.meta?.roles
    if (!roles?.length) return true
    return roles.includes(role)
  })
})
const menuGroups = computed(() => [
  ['巡检工作台', ['dashboard','monitor','realtime-detect','task-center']],
  ['结果与复核', ['detection-results','agent-center']],
  ['统计与复盘', ['analysis']],
  ['配置与资源', ['model-config','resource','system-settings']],
  ['使用指南', ['help-center']],
].map(([title, paths]) => ({ title, items:paths.map(path => visibleMenus.value.find(m => m.path === path)).filter(Boolean) })).filter(g => g.items.length))

watch(
  () => route.path,
  async (p) => {
    selectedKeys.value = [p.replace(/^\//, '')]
    await nextTick()
    document.getElementById('main-content')?.scrollTo({top:0,left:0,behavior:'instant'})
  }
)

function onMenuClick({ key }) {
  router.push('/' + key)
}

async function onProjectChange(id) {
  try { await userStore.setProject(id); message.success('已切换项目') }
  catch { projectId.value = userStore.project?.id || ''; message.error('项目切换失败，已保留原项目。请检查业务连接后重试。') }
}

function onLogout() {
  userStore.logout()
  router.push('/login')
}

onMounted(async () => {
  startBusinessSocket()
  try {
  const res = await fetchProjects()
  projects.value = res.data
  const savedProjectExists = res.data.some((item) => item.id === userStore.project?.id)
  if (!savedProjectExists && res.data[0]) {
    await userStore.setProject(res.data[0].id)
    projectId.value = res.data[0].id
  } else if (savedProjectExists) {
    userStore.updateProjectMetadata(res.data.find(item => item.id === userStore.project.id))
    projectId.value = userStore.project.id
  }
  } catch { message.warning('项目列表暂未加载，可从连接诊断检查业务后台。') }
})

onBeforeUnmount(stopBusinessSocket)
</script>

<style scoped>
.basic-layout { height:100vh; min-height:100vh; overflow:hidden; background:var(--bg); }
.basic-layout > :deep(.ant-layout) { height:100vh; min-width:0; overflow:hidden; background:transparent; display:flex; flex-direction:column; }
:deep(.ant-layout-sider) { height:100vh; position:sticky; top:0; overflow:hidden; background:var(--sider-bg); border-right:1px solid var(--border-color); }
:deep(.ant-layout-sider-children) { height:calc(100vh - 48px); overflow-x:hidden; overflow-y:auto; scrollbar-width:thin; }
:deep(.ant-menu) { background:transparent; border-inline-end:0!important; color:var(--sider-text); padding-inline:10px; }
:deep(.ant-menu-item) { height:40px; line-height:40px; margin:3px 0; width:100%; padding-left:14px!important; border-radius:8px; color:var(--sider-text); font-size:13px; }
:deep(.ant-menu-item .anticon) { font-size:17px; }
:deep(.ant-menu-item:hover) { background:var(--surface-muted)!important; color:var(--text-primary)!important; }
:deep(.ant-menu-item-selected), :deep(.ant-menu-item-selected:hover) { background:var(--sider-active)!important; color:var(--link)!important; font-weight:650; }
:deep(.ant-menu-item-selected)::before { content:''; position:absolute; left:0; top:13px; bottom:13px; width:3px; border-radius:3px; background:var(--primary); }
:deep(.ant-menu-item-group-title) { padding:17px 14px 6px; color:var(--sider-muted)!important; font-size:10px; letter-spacing:1.2px; }
:deep(.ant-menu-inline-collapsed .ant-menu-item) { padding-inline:18px!important; }
:deep(.ant-layout-sider-trigger) { background:var(--sider-trigger); color:var(--sider-text); border-top:1px solid var(--border-color); }
:deep(.ant-layout-sider-trigger:hover) { background:var(--sider-trigger-hover); }
.logo { display:flex; align-items:center; gap:12px; margin:26px 20px 20px; min-height:42px; color:var(--text-primary); }
.brand-symbol { display:grid; place-items:center; flex-shrink:0; width:38px; height:42px; border:1px solid color-mix(in srgb,var(--primary) 25%,var(--border-color)); border-radius:12px; color:var(--primary); font-size:25px; background:var(--primary-soft); }
.logo-full { display:flex; flex-direction:column; }
.logo-title { font-size:21px; letter-spacing:3px; font-weight:700; line-height:1.2; }
.logo-team { font-size:8px; letter-spacing:1.6px; color:var(--sider-muted); margin-top:7px; font-weight:600; }
.header { display:flex; align-items:center; justify-content:space-between; height:72px; line-height:normal; padding:0 28px; background:var(--surface); box-shadow:none; border-bottom:1px solid var(--border-color); flex-shrink:0; }
.header-left { display:flex; flex-direction:column; gap:5px; }
.project-label { font-size:10px; color:var(--text-muted); letter-spacing:1.2px; }
.header-left :deep(.ant-select-selector) { border:0!important; box-shadow:none!important; background:transparent!important; padding-left:0!important; font-weight:600; }
.header-right { display:flex; align-items:center; gap:14px; }
.theme-toggle { display:inline-flex; align-items:center; justify-content:center; background:var(--surface-2); border-color:var(--border-color); font-size:17px; }
.user-menu { border:0; background:transparent; font-size:12px; }
.username { color:var(--text-secondary); max-width:90px; overflow:hidden; text-overflow:ellipsis; display:inline-block; vertical-align:middle; }
.content { min-height:0; flex:1; overflow:auto; background:transparent; padding:20px 28px 32px; scrollbar-gutter:stable; }
.page-location { display:flex; align-items:center; gap:10px; font-size:11px; color:var(--text-muted); margin:0 0 18px; min-height:18px; }
.page-location strong { font-weight:600; color:var(--text-secondary); }
.location-summary { margin-left:auto; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:65%; font-size:11px; }
.skip-content { position:fixed; left:12px; top:-100px; background:var(--surface); color:var(--text-primary); padding:12px 20px; border:2px solid var(--primary); border-radius:8px; z-index:2000; }
.skip-content:focus { top:12px; }
@media(max-width:1360px) { .workspace-style-switch{display:none} .header-right{gap:9px} .header{padding:0 20px} .content{padding:18px 20px 28px} }
@media(max-width:1150px) { .username,.location-summary{display:none} }
@media(max-height:820px) {
  .logo { margin:18px 20px 10px; min-height:38px; }
  :deep(.ant-menu-item) { height:34px; line-height:34px; margin-block:1px; }
  :deep(.ant-menu-item-group-title) { padding-top:8px; padding-bottom:4px; line-height:14px; }
  :deep(.ant-menu-item-selected)::before { top:10px; bottom:10px; }
}
</style>
