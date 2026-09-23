<template>
  <Teleport to="#view-tools">
    <div v-if="inspectionActive" class="view-glass" aria-label="画面放大查看区域" @pointerdown="startPan" @pointermove="movePan" @pointerup="endPan" @pointercancel="endPan" @lostpointercapture="endPan" />
    <section v-if="settingsOpen && !inspectionActive" class="reading-popover" role="dialog" aria-label="阅读显示设置">
      <button type="button" class="close-reading" aria-label="关闭阅读设置" @click="settingsOpen=false">×</button><ReadingSettings />
    </section>
    <div class="view-toolbar" role="toolbar" aria-label="阅读与画面放大">
      <template v-if="inspectionActive">
        <span class="view-instructions">滚轮缩放 · 拖动平移</span>
        <button type="button" aria-label="缩小画面" :disabled="view.scale<=1" @click="changeScale(view.scale/1.2)">−</button>
        <output aria-live="polite">{{ Math.round(view.scale*100) }}%</output>
        <button type="button" aria-label="放大画面" :disabled="view.scale>=4" @click="changeScale(view.scale*1.2)">＋</button>
        <button type="button" @click="resetView">退出查看 <kbd>Esc</kbd></button>
      </template>
      <template v-else>
        <button type="button" :aria-expanded="settingsOpen" @click="settingsOpen=!settingsOpen">字号 {{ fontPercent }}%</button>
        <button type="button" title="Ctrl＋滚轮也可直接放大" @click="openInspection">放大查看</button>
      </template>
    </div>
  </Teleport>
</template>
<script setup>
import { nextTick,onMounted,onBeforeUnmount,reactive,ref,watch } from 'vue'
import { useRoute } from 'vue-router'
import ReadingSettings from './ReadingSettings.vue'
import { fontPercent,inspectionActive,openInspection } from '@/utils/displayPreferences'
import { zoomAt,constrainView,wheelScale } from '@/utils/readingGeometry.js'
const route=useRoute(),settingsOpen=ref(false),view=reactive({scale:1,x:0,y:0})
let stage,drag=null,previousFocus=null
function paint(){if(stage)stage.style.transform=`translate(${view.x}px,${view.y}px) scale(${view.scale})`}
function changeScale(scale,point={x:innerWidth/2,y:innerHeight/2}){
  Object.assign(view,zoomAt(view,scale,point,innerWidth,innerHeight));paint()
}
function resetView(){inspectionActive.value=false;drag=null;Object.assign(view,{scale:1,x:0,y:0});paint()}
function wheel(event){
  if(!event.ctrlKey&&!inspectionActive.value)return
  event.preventDefault();event.stopImmediatePropagation()
  if(event.target.closest?.('.view-toolbar,.reading-popover'))return
  changeScale(wheelScale(view,event),{x:event.clientX,y:event.clientY})
  inspectionActive.value=true
}
function startPan(event){if(event.button!==0)return;event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:view.x,top:view.y}}
function movePan(event){if(!drag||drag.id!==event.pointerId)return;Object.assign(view,constrainView({scale:view.scale,x:drag.left+event.clientX-drag.x,y:drag.top+event.clientY-drag.y},innerWidth,innerHeight));paint()}
function endPan(){drag=null}
function keydown(event){
  if(event.key==='Escape'&&(inspectionActive.value||settingsOpen.value)){event.preventDefault();event.stopImmediatePropagation();settingsOpen.value=false;resetView();return}
  if(!event.ctrlKey||!['+','=','-','0'].includes(event.key))return
  event.preventDefault();event.stopImmediatePropagation()
  if(event.key==='0'){resetView();return}
  changeScale(view.scale*(event.key==='-'?1/1.2:1.2));inspectionActive.value=true
}
function resize(){Object.assign(view,constrainView(view,innerWidth,innerHeight));paint()}
watch(inspectionActive,async active=>{
  if(active){previousFocus=document.activeElement;settingsOpen.value=false}
  if(stage)stage.inert=active
  if(active){await nextTick();document.querySelector('.view-toolbar button:not(:disabled)')?.focus({preventScroll:true})}
  else{resetView();if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});previousFocus=null}
})
watch(()=>route.fullPath,()=>{settingsOpen.value=false;resetView()})
onMounted(()=>{stage=document.getElementById('view-stage');window.addEventListener('wheel',wheel,{capture:true,passive:false});window.addEventListener('keydown',keydown,true);window.addEventListener('resize',resize)})
onBeforeUnmount(()=>{resetView();window.removeEventListener('wheel',wheel,true);window.removeEventListener('keydown',keydown,true);window.removeEventListener('resize',resize)})
</script>
<style>
#view-window{position:fixed;inset:0;overflow:hidden;background:var(--bg)}
#view-stage{width:100%;height:100%;transform:translate(0,0) scale(1);transform-origin:0 0}
#view-tools{position:fixed;inset:0;z-index:10000;pointer-events:none}
.view-glass{position:absolute;inset:0;pointer-events:auto;cursor:grab;touch-action:none;user-select:none}.view-glass:active{cursor:grabbing}
.view-toolbar{position:absolute;right:18px;bottom:12px;display:flex;align-items:center;gap:8px;max-width:calc(100vw - 36px);padding:7px;background:var(--surface);color:var(--text-primary);border:1px solid var(--border-color);box-shadow:var(--shadow-float);border-radius:6px;pointer-events:auto;flex-wrap:wrap}
.view-toolbar button,.close-reading{font:inherit;font-size:14px;color:var(--text-primary);background:var(--surface-2);border:1px solid var(--border-color);border-radius:4px;padding:5px 10px;cursor:pointer;line-height:1.4}.view-toolbar button:hover{border-color:var(--primary)}.view-toolbar button:disabled{opacity:.4;cursor:default}.view-toolbar output{font:14px monospace;min-width:4ch;text-align:center}.view-toolbar kbd{font:11px monospace;color:var(--text-muted)}.view-instructions{font-size:12px;color:var(--text-secondary);padding:0 5px}.reading-popover{position:absolute;right:18px;bottom:82px;width:min(520px,calc(100vw - 36px));max-height:calc(100vh - 130px);overflow:auto;padding:28px 22px 16px;border:1px solid var(--border-color);border-radius:6px;background:var(--surface);box-shadow:var(--shadow-float);pointer-events:auto}.close-reading{position:absolute;right:8px;top:5px;padding:0 8px;font-size:20px}
@media(max-width:700px){.view-instructions{display:none}}
</style>
