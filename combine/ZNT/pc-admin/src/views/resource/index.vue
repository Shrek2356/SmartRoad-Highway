<template>
  <!--
    ⑦ 基础资源管理页
    业务：设备管理 / 组织架构 / 多项目切换
  -->
  <div class="page-card">
    <div class="page-title">基础资源管理</div>

    <a-tabs v-model:activeKey="tab">
      <a-tab-pane key="device" tab="设备管理">
        <a-space style="margin-bottom: 12px">
          <a-select v-model:value="deviceStatus" allow-clear placeholder="在线状态" style="width: 140px" @change="loadDevices">
            <a-select-option value="online">在线</a-select-option>
            <a-select-option value="offline">离线</a-select-option>
          </a-select>
          <a-input-search v-model:value="deviceKw" placeholder="设备名/区域" style="width: 220px" @search="loadDevices" />
        </a-space>
        <a-table :columns="deviceCols" :data-source="devices" row-key="id" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <a-badge :status="record.status === 'online' ? 'success' : 'default'" :text="record.status === 'online' ? '在线' : '离线'" />
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="org" tab="组织架构管理">
        <a-tree v-if="orgTree.length" :tree-data="orgTree" default-expand-all />
        <p class="tip">当前组织树由业务后台按平台角色返回，只读展示；用户与角色维护请到“Agent协同学习 → 用户与备份”。</p>
      </a-tab-pane>

      <a-tab-pane key="project" tab="多项目切换">
        <a-list :data-source="projects" item-layout="horizontal">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta :title="item.name" :description="item.address" />
              <template #actions>
                <a-button
                  type="link"
                  :disabled="currentId === item.id"
                  @click="onSwitch(item.id)"
                >
                  {{ currentId === item.id ? '当前项目' : '切换至此' }}
                </a-button>
              </template>
            </a-list-item>
          </template>
        </a-list>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouteTab } from '@/composables/useRouteTab'
import { message } from 'ant-design-vue'
import { fetchDevices, fetchOrgTree, fetchProjects } from '@/api/resource'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const tab = useRouteTab(['device','org','project'], 'device')
const devices = ref([])
const orgTree = ref([])
const projects = ref([])
const deviceStatus = ref(undefined)
const deviceKw = ref('')
const currentId = ref(userStore.project?.id || '')

const deviceCols = [
  { title: '设备ID', dataIndex: 'id', key: 'id', width: 120 },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '类型', dataIndex: 'type', key: 'type', width: 100 },
  { title: '区域', dataIndex: 'area', key: 'area', width: 140 },
  { title: 'IP', dataIndex: 'ip', key: 'ip', width: 140 },
  { title: '状态', key: 'status', width: 120 },
]

async function loadDevices() {
  const res = await fetchDevices({ status: deviceStatus.value, keyword: deviceKw.value })
  devices.value = res.data
}

async function onSwitch(id) {
  await userStore.setProject(id)
  currentId.value = id
  message.success('项目已切换')
}

onMounted(async () => {
  await loadDevices()
  const [o, p] = await Promise.all([fetchOrgTree(), fetchProjects()])
  orgTree.value = o.data
  projects.value = p.data
  currentId.value = userStore.project?.id || p.data[0]?.id
})
</script>

<style scoped>
.tip { color: var(--text-secondary); font-size: 12px; margin-top: 12px; }
</style>
