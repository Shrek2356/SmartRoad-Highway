/**
 * 用户状态（登录态 / 角色 / 当前项目）
 */
import { defineStore } from 'pinia'
import { login as loginApi } from '@/api/auth'
import { switchProject as switchProjectApi } from '@/api/resource'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('znt_token') || '',
    user: JSON.parse(localStorage.getItem('znt_user') || 'null'),
    project: JSON.parse(localStorage.getItem('znt_project') || 'null'),
  }),
  getters: {
    isLogin: (s) => !!s.token,
    role: (s) => s.user?.role || '',
    displayName: (s) => s.user?.name || '未登录',
  },
  actions: {
    async login(form) {
      const res = await loginApi(form)
      this.token = res.data.token
      this.user = res.data.user
      localStorage.setItem('znt_token', this.token)
      localStorage.setItem('znt_user', JSON.stringify(this.user))
      return res.data
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('znt_token')
      localStorage.removeItem('znt_user')
    },
    async setProject(projectId) {
      const res = await switchProjectApi({ projectId })
      this.updateProjectMetadata(res.data)
    },
    updateProjectMetadata(project) {
      this.project = project
      localStorage.setItem('znt_project', JSON.stringify(this.project))
      return project
    },
  },
})
