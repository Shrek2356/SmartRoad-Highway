<template>
  <section ref="shell" class="scene-shell" :class="{ expanded }" :role="expanded ? 'dialog' : 'region'" :aria-modal="expanded || undefined" aria-label="三维道路概况">
    <header class="scene-header">
      <div><span class="section-index">01 /</span><strong>公路空间总览</strong><span class="scene-mode">{{ ready ? '3D' : '2D' }} 示意模型</span></div>
      <button class="tool-button" :aria-pressed="expanded" @click="expanded = !expanded">{{ expanded ? '退出大图' : '展开大图' }} <span aria-hidden="true">⛶</span></button>
    </header>
    <div class="scene-stage">
      <div ref="host" class="webgl-host" :class="{ hidden: error }" />
      <div v-if="error" class="fallback-map">
        <svg viewBox="0 0 350 190" role="img" aria-label="三维不可用时的二维道路示意">
          <defs><pattern id="road-grid" width="12" height="12" patternUnits="userSpaceOnUse"><path d="M12 0H0V12" fill="none" :stroke="colorTheme === 'light' ? '#cccccc' : '#214263'" stroke-width=".3" /></pattern></defs>
          <rect width="350" height="190" fill="url(#road-grid)" />
          <polyline :points="fallbackRoad" fill="none" :stroke="colorTheme === 'light' ? '#555555' : '#243f5c'" stroke-width="9" />
          <polyline :points="fallbackRoad" fill="none" :stroke="colorTheme === 'light' ? '#eeeeee' : '#6fd6ed'" stroke-width=".8" stroke-dasharray="3 2" />
          <g v-for="p in fallbackPoints" :key="p.id"><circle :cx="p.x" :cy="p.y" r="3" :fill="p.kind === 'risk' ? '#ff868c' : colorTheme === 'light' ? '#333333' : '#6fd6ed'"/><text :x="p.x" :y="p.y - 6" :fill="colorTheme === 'light' ? '#202020' : '#deefff'" font-size="4" text-anchor="middle">{{ p.short }}</text></g>
        </svg>
        <div class="fallback-notice"><p>{{ error }}</p><button class="tool-button" @click="initialize">重试三维</button></div>
      </div>
      <div v-else-if="!ready" class="scene-loading">正在构建山区道路模型…</div>
      <div v-if="ready && !error" class="scene-labels">
        <template v-for="label in labels.filter(l => l.visible)" :key="label.id">
          <button v-if="['risk','device'].includes(label.type)" class="map-marker" :class="[label.type, label.severity, label.state, { active: label.active }]"
            :style="{ left: label.x+'px', top: label.y+'px' }" :aria-label="markerTitle(label.id)" :aria-pressed="label.active" @click="emitSelection(label.id)">
            <span>{{ label.type === 'risk' ? '!' : '◉' }}</span><b>{{ label.type === 'risk' ? '事件 ' : '' }}{{ label.text }}</b>
          </button>
          <span v-else class="map-label" :class="label.type" :style="{ left: label.x+'px', top: label.y+'px' }">{{ label.text }}</span>
        </template>
      </div>
      <div class="scene-caption"><span class="caption-kicker">LEXI EXPRESSWAY</span><strong>乐西高速 · 山区桥隧走廊</strong><small>马边 → 雷波 → 美姑 → 昭觉</small></div>
      <div class="scene-tools" aria-label="模型视角控制">
        <button :disabled="!ready" class="tool-button" @click="setView('overview')">全线斜视</button>
        <button :disabled="!ready" class="tool-button" @click="setView('top')">俯视</button>
        <button :disabled="!ready" class="tool-button" aria-label="向左旋转视角" @click="engine?.rotate(-1)">↶</button>
        <button :disabled="!ready" class="tool-button" aria-label="向右旋转视角" @click="engine?.rotate(1)">↷</button>
        <button :disabled="!ready" class="tool-button" aria-label="放大模型" @click="engine?.zoom(.8)">＋</button>
        <button :disabled="!ready" class="tool-button" aria-label="缩小模型" @click="engine?.zoom(1.25)">−</button>
        <button :disabled="!ready || reducedMotion" class="tool-button" :aria-pressed="autoRotate" @click="autoRotate = !autoRotate">{{ autoRotate ? '暂停环绕' : '自动环绕' }}</button>
      </div>
      <div class="scene-compass" aria-hidden="true"><span>3D</span><div>↗</div><small>空间示意</small></div>
      <div v-if="expanded && selectedItem" class="expanded-selection"><small>当前点位 · 演示</small><strong>{{ selectedItem.title || selectedItem.name }}</strong><span>{{ selectedItem.chainage }} · 示意桩号</span><button class="tool-button" @click="expanded=false">返回工作台查看详情 →</button></div>
      <div class="scene-bottom"><span><i class="legend-dot cyan"></i>设备 <i class="legend-dot red"></i>严重 <i class="legend-dot amber"></i>关注 <i class="legend-dot green"></i>正常路段</span><span>拖动旋转 · 滚轮缩放 · 右键平移</span></div>
    </div>
    <footer class="scene-footer"><span>示意地形 / 示意桩号 / 演示点位</span><span>无现场数据接入</span></footer>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { devices, reports, routeNodes } from '../../data/lexiDemo.js'
import { colorTheme } from '../../utils/theme'
const props = defineProps({ selectedId: String, layers: Object, severity: String })
const emit = defineEmits(['select'])
const host=ref(null),shell=ref(null),labels=ref([]),ready=ref(false),error=ref(''),expanded=ref(false),autoRotate=ref(false),reducedMotion=ref(false)
let engine=null,disposed=false,generation=0,motionQuery=null
const items=[...devices,...reports]
const selectedItem=computed(()=>items.find(i=>i.id===props.selectedId))
const fallbackRoad=routeNodes.map(([x,,z])=>`${x+175},${z*1.7+90}`).join(' ')
const fallbackPoints=computed(()=>items.filter(p=>p.severity ? props.layers.risks&&(props.severity==='all'||p.severity===props.severity) : props.layers.devices).map(p=>{
  const i=p.t*(routeNodes.length-1),a=routeNodes[Math.floor(i)],b=routeNodes[Math.min(Math.ceil(i),routeNodes.length-1)],f=i%1
  return {...p,kind:p.severity?'risk':'device',x:175+a[0]*(1-f)+b[0]*f,y:90+(a[2]*(1-f)+b[2]*f)*1.7}
}))
function markerTitle(id){const item=items.find(i=>i.id===id);return `${item?.title||item?.name}（演示）`}
function update(){engine?.update({selectedId:props.selectedId,layers:props.layers,severity:props.severity,autoRotate:autoRotate.value})}
function setView(view){autoRotate.value=false;engine?.setView(view)}
function focus(id){autoRotate.value=false;engine?.focus(id)}
defineExpose({focus})
function fail(text){error.value=text;ready.value=false;labels.value=[]}
async function initialize(){
  const current=++generation
  engine?.dispose();engine=null;ready.value=false;error.value='';labels.value=[]
  try{
    const {createHighwayScene}=await import('./scene.js')
    if(disposed||current!==generation)return
    engine=createHighwayScene(host.value,{theme:colorTheme.value,onSelect:id=>emitSelection(id),onLabels:value=>{labels.value=value},onReady:()=>{ready.value=true},onFailure:fail})
    update()
  }catch{if(!disposed&&current===generation)fail('当前环境无法启用三维，已显示二维示意。设备和报告仍可通过下方列表查看。')}
}
// Keep selection in the parent so canvas, accessible lists and report details stay consistent.
function emitSelection(id){ emit('select', id) }
watch(()=>[props.selectedId,props.layers.devices,props.layers.risks,props.severity,autoRotate.value],update)
watch(colorTheme,mode=>engine?.setTheme(mode))
watch(expanded,async()=>{await nextTick();shell.value?.querySelector('.scene-header button')?.focus()})
function keydown(event){
  if(event.key==='Escape')expanded.value=false
  if(!expanded.value||event.key!=='Tab')return
  const buttons=[...shell.value.querySelectorAll('button:not(:disabled)')].filter(b=>b.getClientRects().length)
  const first=buttons[0],last=buttons.at(-1)
  if(event.shiftKey&&(document.activeElement===first||!shell.value.contains(document.activeElement))){event.preventDefault();last?.focus()}
  else if(!event.shiftKey&&(document.activeElement===last||!shell.value.contains(document.activeElement))){event.preventDefault();first?.focus()}
}
function motionChange(){reducedMotion.value=motionQuery.matches;if(reducedMotion.value)autoRotate.value=false}
onMounted(()=>{motionQuery=matchMedia('(prefers-reduced-motion: reduce)');motionChange();motionQuery.addEventListener('change',motionChange);document.addEventListener('keydown',keydown);initialize()})
onBeforeUnmount(()=>{disposed=true;generation++;engine?.dispose();document.removeEventListener('keydown',keydown);motionQuery?.removeEventListener('change',motionChange)})
</script>

<style scoped>
.expanded-selection{position:absolute;right:22px;bottom:60px;display:grid;gap:7px;padding:13px;background:#113b80ec;border:1px solid #426880;max-width:230px;border-radius:4px;color:#dcecf8}.expanded-selection small{font-size:9px;color:#94b6cc}.expanded-selection strong{font-size:12px;font-weight:500}.expanded-selection>span{font-size:10px;color:#b3cfe0}.expanded-selection button{margin-top:3px}@media(max-width:650px){.expanded-selection{bottom:123px;right:14px;max-width:185px}}
.scene-shell{border:1px solid var(--border-color);background:#0a2a65;min-width:0;overflow:hidden;display:flex;flex-direction:column;border-radius:5px}.scene-shell.expanded{position:fixed;inset:18px;z-index:1100;box-shadow:0 0 0 24px #020913df}.scene-header{height:49px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid #254560;color:#dfedfc;background:#123a7b}.scene-header>div{display:flex;align-items:center;gap:12px}.section-index{font:11px monospace;color:#56cde4}.scene-header strong{font-size:14px;font-weight:600;letter-spacing:1px}.scene-mode{font-size:10px;color:#99bad2;border:1px solid #35566f;padding:1px 6px}.scene-stage{position:relative;flex:1;min-height:490px;isolation:isolate}.expanded .scene-stage{min-height:0}.webgl-host,.fallback-map{position:absolute;inset:0}.webgl-host :deep(canvas){display:block;width:100%;height:100%;touch-action:none}.webgl-host.hidden{visibility:hidden}.scene-caption{position:absolute;top:24px;left:24px;display:grid;gap:4px;pointer-events:none;color:#d5e8f8}.caption-kicker{font:9px monospace;letter-spacing:2px;color:#79a4c2}.scene-caption strong{font-size:16px;font-weight:500;letter-spacing:1px}.scene-caption small{font-size:10px;color:#96b8cc}.scene-tools{position:absolute;left:18px;bottom:46px;display:flex;gap:5px;flex-wrap:wrap;max-width:calc(100% - 36px)}.tool-button{border:1px solid #385b77;background:#16488cea;color:#c7dfef;font:inherit;font-size:11px;line-height:1.4;border-radius:3px;padding:6px 9px;cursor:pointer}.tool-button:hover,.tool-button[aria-pressed=true]{background:#13405a;color:#8ae7ff;border-color:#55c9e7}.tool-button:disabled{opacity:.4;cursor:not-allowed}.scene-bottom{position:absolute;bottom:14px;left:20px;right:20px;display:flex;justify-content:space-between;gap:8px;font-size:10px;color:#a8c2d6;pointer-events:none}.legend-dot{display:inline-block;width:5px;height:5px;margin:0 4px 2px 12px;border-radius:50%}.legend-dot:first-child{margin-left:0}.cyan{background:#64daf2}.red{background:#ff7985}.amber{background:#ffc776}.green{background:#64d8ab}.scene-footer{padding:8px 18px;border-top:1px solid #254560;color:#9ab5cd;display:flex;justify-content:space-between;font-size:10px;background:#113572}.scene-compass{position:absolute;right:22px;top:25px;text-align:center;color:#77a6c4;pointer-events:none}.scene-compass span{font:11px monospace;letter-spacing:2px}.scene-compass div{font-size:30px;line-height:1.2}.scene-compass small{font-size:9px}.scene-labels{position:absolute;inset:0;pointer-events:none;overflow:hidden}.map-marker{position:absolute;transform:translate(-50%,-100%);pointer-events:auto;color:#90e5f3;background:#144987e8;border:1px solid #47aec5;display:flex;align-items:center;gap:5px;line-height:1;padding:5px 7px;font-size:10px;cursor:pointer;border-radius:3px;white-space:nowrap}.map-marker span{font-weight:800}.map-marker b{font-size:9px;font-weight:500;letter-spacing:.5px}.map-marker.risk{color:#ffd193;border-color:#bd9053;background:#352a21eb}.map-marker.critical{color:#ffb6bb;border-color:#ec7c87;background:#422b3ceb}.map-marker.offline{color:#bac5d1;border-color:#748495}.map-marker.maintenance{color:#ffcc88;border-color:#ba955a}.map-marker:hover,.map-marker.active{z-index:2;outline:1px solid currentColor;outline-offset:3px}.map-label{position:absolute;transform:translate(-50%,-50%);white-space:nowrap;color:#b4d0e1;font-size:11px;letter-spacing:2px;text-shadow:0 1px 4px #000}.map-label.structure{font-size:9px;color:#a1bfd3;letter-spacing:0}.map-label.normal{font-size:9px;color:#7de9b6;letter-spacing:0;background:#092e30bd;padding:3px 6px;border-left:2px solid #50c79c}.scene-loading{position:absolute;inset:0;display:grid;place-items:center;color:#b6dcec}.fallback-map svg{width:100%;height:100%}.fallback-notice{position:absolute;left:24px;right:24px;bottom:92px;background:#103c80ed;padding:12px;border:1px solid #4d667f;color:#c6daec;font-size:12px}.fallback-notice p{margin:0 0 8px}@media(max-width:1280px){.scene-bottom{flex-direction:column}.scene-tools{bottom:63px}.scene-stage{min-height:500px}}@media(max-width:700px){.scene-stage{min-height:430px}.scene-caption{left:16px}.scene-caption strong{font-size:13px}.scene-compass{display:none}.scene-shell.expanded{inset:6px}.scene-mode{display:none}.scene-header{padding:0 12px}.scene-tools{gap:4px}.tool-button{padding:6px}.map-label.structure{display:none}}
</style>
