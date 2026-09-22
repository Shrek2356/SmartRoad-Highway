import { ref } from 'vue'
import { paletteFor } from './designTokens'

const STORAGE_KEY = 'znt_color_theme'
const saved = localStorage.getItem(STORAGE_KEY)
export const colorTheme = ref(saved === 'dark' ? 'dark' : 'light')

function applyTheme(value) {
  for (const [key, color] of Object.entries(paletteFor(value))) {
    document.documentElement.style.setProperty(`--${key}`, color)
  }
  document.documentElement.dataset.theme = value
  document.documentElement.style.colorScheme = value
}

export function setColorTheme(value) {
  colorTheme.value = value === 'dark' ? 'dark' : 'light'
  localStorage.setItem(STORAGE_KEY, colorTheme.value)
  applyTheme(colorTheme.value)
}

export function toggleColorTheme() {
  setColorTheme(colorTheme.value === 'dark' ? 'light' : 'dark')
}

applyTheme(colorTheme.value)
