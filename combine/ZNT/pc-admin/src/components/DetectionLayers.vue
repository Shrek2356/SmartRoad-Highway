<template>
  <section class="detection-layers">
    <div class="layer-tools">
      <label>显示 <select v-model="mode"><option value="both">框与掩码</option><option value="box">仅框</option><option value="mask">仅掩码</option></select></label>
      <label>掩码透明度 <input v-model.number="opacity" type="range" min="0" max="80" step="5" /> {{ opacity }}%</label>
    </div>
    <canvas ref="canvas" aria-label="道路与异常区域分层标注" />
    <div class="layer-tools"><label v-for="(layer,i) in layers" :key="layer.id"><input :checked="!hidden[i]" type="checkbox" @change="hidden[i] = !$event.target.checked" /> {{ layer.name }}</label></div>
    <p v-if="error" role="status">{{ error }}</p>
    <small>绿色：未见可见异常的路面；蓝色：场景对象；黄／红色：异常候选／已确认异常。没有掩码的风险仍保留在下方结果中。</small>
  </section>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
const props = defineProps({ result: { type: Object, required: true } })
const canvas=ref(null), mode=ref('both'), opacity=ref(25), hidden=ref({}), error=ref('')
const layers=computed(() => [
  ...(props.result.scene_layers || []).map((s,i) => ({id:`scene-${i}`,name:({road:'路面',traffic_sign:'路牌',guardrail:'护栏'})[s.concept] || s.concept,defaultHidden:s.concept==='guardrail',mask:s.mask,color:s.color==='green'?[28,175,83]:[44,127,208],boxes:s.boxes})),
  ...(props.result.risks || []).filter(r=>r.mask).map((r,i)=>({id:`risk-${i}`,name:r.name,mask:r.mask,color:r.verified?[235,65,55]:[245,180,35]}))
])
let generation=0
const cache=new Map()
function load(url) {
  if (!cache.has(url)) cache.set(url,new Promise((resolve,reject)=>{const img=new Image();img.crossOrigin='anonymous';img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('图层读取失败'));img.src=url}))
  return cache.get(url)
}
async function render() {
  const token=++generation
  if (!canvas.value || !props.result.input_image) return
  error.value=''
  try {
    const base=await load(props.result.input_image)
    const selected=layers.value.filter((_,i)=>!hidden.value[i])
    const loaded=await Promise.allSettled(selected.map(l=>load(l.mask)))
    if(token!==generation || !canvas.value) return
    const c=canvas.value;c.width=base.naturalWidth;c.height=base.naturalHeight
    const ctx=c.getContext('2d');ctx.drawImage(base,0,0)
    const outlines=[]
    loaded.forEach((entry,i)=>{
      if(entry.status!=='fulfilled'){error.value='部分掩码读取失败，未显示的图层不代表没有异常。';return}
      const l=selected[i], m=entry.value
      if(m.naturalWidth!==c.width || m.naturalHeight!==c.height){error.value='部分掩码尺寸与原图不一致，已跳过。';return}
      const off=document.createElement('canvas');off.width=c.width;off.height=c.height
      const oc=off.getContext('2d');oc.drawImage(m,0,0)
      const pixels=oc.getImageData(0,0,c.width,c.height)
      let x1=c.width,y1=c.height,x2=-1,y2=-1
      for(let p=0;p<pixels.data.length;p+=4){
        const on=pixels.data[p]>127 && pixels.data[p+3]>0
        if(on){const n=p/4,x=n%c.width,y=Math.floor(n/c.width);x1=Math.min(x1,x);y1=Math.min(y1,y);x2=Math.max(x2,x);y2=Math.max(y2,y)}
        pixels.data[p]=l.color[0];pixels.data[p+1]=l.color[1];pixels.data[p+2]=l.color[2];pixels.data[p+3]=on?Math.round(opacity.value*2.55):0
      }
      if(mode.value!=='box'){oc.putImageData(pixels,0,0);ctx.drawImage(off,0,0)}
      if(x2>=0)outlines.push({ ...l, boxes:l.boxes?.length?l.boxes:[[x1,y1,x2+1,y2+1]] })
    })
    if(mode.value!=='mask')for(const l of outlines){ctx.strokeStyle=`rgb(${l.color.join(',')})`;ctx.lineWidth=Math.max(2,c.width/500);ctx.font=`${Math.max(16,c.width/65)}px sans-serif`;for(const [x1,y1,x2,y2] of l.boxes){ctx.strokeRect(x1,y1,x2-x1,y2-y1);const y=Math.max(20,y1);ctx.fillStyle='#101c30';ctx.fillRect(x1,y-20,ctx.measureText(l.name).width+8,24);ctx.fillStyle='#fff';ctx.fillText(l.name,x1+4,y)}}
  }catch{if(token===generation)error.value='原图或掩码无法读取，请检查检测档案。'}
}
watch(()=>props.result,()=>{hidden.value=Object.fromEntries(layers.value.map((l,i)=>[i,!!l.defaultHidden]));cache.clear()}, {flush:'sync',immediate:true})
watch([canvas,()=>props.result,mode,opacity,hidden],render,{deep:true,flush:'post'})
</script>
<style scoped>
.detection-layers{width:100%;min-width:0}.detection-layers canvas{display:block;width:100%;height:auto}.layer-tools{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:8px 0}.layer-tools label{display:flex;align-items:center;gap:6px}.layer-tools select{color:var(--text-primary);background:var(--surface);padding:5px}.detection-layers small{color:var(--text-secondary)}
</style>
