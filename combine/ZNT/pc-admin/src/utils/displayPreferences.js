import { ref } from 'vue'
import { normalizeFontPercent } from './readingGeometry.js'
const KEY='smartroad_font_percent'
function savedFont(){try{return localStorage.getItem(KEY)}catch{return 100}}
export const fontPercent=ref(normalizeFontPercent(savedFont()))
export const inspectionActive=ref(false)
export function setFontPercent(value){
  fontPercent.value=normalizeFontPercent(value)
  document.documentElement.style.setProperty('--ui-font-scale',String(fontPercent.value/100))
  document.documentElement.dataset.largeText=String(fontPercent.value>100)
  try{localStorage.setItem(KEY,String(fontPercent.value))}catch{/* Current session remains usable. */}
}
export function openInspection(){inspectionActive.value=true}
export function popupContainer(){return document.getElementById('view-popups') || document.body}
setFontPercent(fontPercent.value)
