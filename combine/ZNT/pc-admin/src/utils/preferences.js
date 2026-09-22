import { ref } from 'vue'
const assetsBundled = false
export const presentationAvailable = assetsBundled
export const workspaceStyle = ref(localStorage.getItem('znt_workspace_style') || 'professional')
export const presentationAssets = ref(assetsBundled && localStorage.getItem('znt_presentation_assets') !== 'false')
export const presentationEnabled = () => presentationAssets.value
export function setWorkspaceStyle(value) {
  workspaceStyle.value = value === 'showcase' ? 'showcase' : 'professional'
  localStorage.setItem('znt_workspace_style', workspaceStyle.value)
  document.documentElement.dataset.workspaceStyle = workspaceStyle.value
}
export function setPresentationAssets(value) {
  presentationAssets.value = assetsBundled && Boolean(value)
  localStorage.setItem('znt_presentation_assets', String(presentationAssets.value))
}
setWorkspaceStyle(workspaceStyle.value)
