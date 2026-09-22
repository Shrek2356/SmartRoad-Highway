<template>
<div>
<WorkspaceBackup />
<a-alert type="info" show-icon message="此处备份仅包含业务数据库。迁移完整业务资料时还需复制图片、规范库与检测任务目录，详见交付说明。" style="margin-bottom:16px" />

        <a-space style="margin-bottom: 12px"><a-button type="primary" @click="userOpen = true">新增用户</a-button><a-button @click="backup">立即备份业务库</a-button></a-space>
        <a-table :columns="userColumns" :data-source="users" row-key="username" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'role'"><a-select :value="record.role" style="width: 150px" @change="(role) => changeRole(record, role)"><a-select-option value="admin">管理员</a-select-option><a-select-option value="safety_officer">道路值班员</a-select-option><a-select-option value="viewer">只读总监</a-select-option></a-select></template>
            <template v-if="column.key === 'action'"><a-button type="link" @click="resetPassword(record)">重置密码</a-button></template>
          </template>
        </a-table>
      
    <a-modal v-model:open="userOpen" title="新增平台用户" @ok="addUser"><a-form layout="vertical"><a-form-item label="用户名"><a-input v-model:value="newUser.username" /></a-form-item><a-form-item label="初始密码（至少6位）"><a-input-password v-model:value="newUser.password" /></a-form-item><a-form-item label="角色"><a-select v-model:value="newUser.role"><a-select-option value="safety_officer">道路值班员</a-select-option><a-select-option value="viewer">只读总监</a-select-option><a-select-option value="admin">管理员</a-select-option></a-select></a-form-item></a-form></a-modal>
</div>
</template>
<script setup>
import { h, onMounted, reactive, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { createBackup, createUser, fetchUsers, updateUserPassword, updateUserRole } from '@/api/agentCenter'
import WorkspaceBackup from './WorkspaceBackup.vue'
const users = ref([]), userOpen = ref(false), newUser = reactive({ username:'', password:'', role:'safety_officer' })
const userColumns = [{ title: '用户名', dataIndex: 'username' }, { title: '角色', key: 'role' }, { title: '操作', key: 'action' }]
async function loadUsers() { try { users.value = (await fetchUsers()).data } catch(e) { message.error(e.message || '用户列表读取失败') } }
async function addUser() { await createUser(newUser); message.success('用户已创建'); userOpen.value = false; Object.assign(newUser, { username: '', password: '', role: 'safety_officer' }); await loadUsers() }
async function changeRole(record, role) { await updateUserRole(record.username, role); message.success('角色已更新'); await loadUsers() }
function resetPassword(record) { let password = ''; Modal.confirm({ title: `重置 ${record.username} 的密码`, content: () => h('input', { class: 'ant-input', type: 'password', placeholder: '至少6位', onInput: (e) => { password = e.target.value } }), onOk: async () => { await updateUserPassword(record.username, password); message.success('密码已更新') } }) }
async function backup() { const res = await createBackup(); message.success(`备份完成：${res.data.backup}`) }
onMounted(loadUsers)
</script>
