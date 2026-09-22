/**
 * 角色权限工具
 * -------------------------------------------------------
 * 预留三种角色：admin(管理员) / safety(道路值班员) / director(只读观察员)
 * 【后续修改入口】对接真实权限体系时，改 checkPermission 与 ROLE_MENUS
 * -------------------------------------------------------
 */

/** 角色枚举 */
export const ROLES = {
  ADMIN: 'admin',
  SAFETY: 'safety',
  DIRECTOR: 'director',
}

/** 角色中文名 */
export const ROLE_LABELS = {
  admin: '管理员',
  safety: '道路值班员',
  director: '只读观察员',
}

/**
 * 各角色可访问的菜单 path 列表
 * 空数组表示全部可访问（管理员）
 */
export const ROLE_MENUS = {
  admin: [], // 全部
  safety: [
    '/help-center',
    '/task-center',
    '/dashboard',
    '/monitor',
    '/realtime-detect',
    '/workorder',
    '/agent-center',
    '/detection-results',
    '/case-library',
  ],
  director: [
    '/help-center',
    '/resource',
    '/task-center',
    '/dashboard',
    '/monitor',
    '/realtime-detect',
    '/workorder',
    '/analysis',
    '/detection-results',
    '/case-library',
  ],
}

/**
 * 检查当前角色是否有某路由权限
 * @param {string} role 角色
 * @param {string} path 路由 path
 * @returns {boolean}
 */
export function checkPermission(role, path) {
  if (!role) return false
  if (role === ROLES.ADMIN) return true
  const menus = ROLE_MENUS[role] || []
  // 精确匹配或前缀匹配（子路由）
  return menus.some((m) => path === m || path.startsWith(m + '/'))
}
