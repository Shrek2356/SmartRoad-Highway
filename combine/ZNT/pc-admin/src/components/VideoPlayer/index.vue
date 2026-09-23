<template>
  <div class="video-player" ref="wrapRef">
    <img v-if="showExample && !imageError" class="example-image" :src="exampleImage" :alt="`${name} · 正常道路静态示例，非该点位实景`" @error="imageError=true" />
    <div v-if="showExample" class="example-caption"><strong>{{ name }}</strong><span>正常路况示例 · 非实时</span></div>
    <div v-if="showExample && !imageError" class="example-source">{{ exampleSource }}<br />静态参考图，不对应此摄像头实景或当前路况</div>
    <video v-show="hasStream && !error" ref="videoRef" class="video-el" muted autoplay controls
      @loadedmetadata="updateRect" @resize="updateRect" @error="hasStream && (error = '视频解码或连接失败，请检查预览地址与编码格式')" />
    <div v-if="(!hasStream && !showExample) || error || (showExample && imageError)" class="placeholder">
      <div class="cam-name">{{ name || '摄像头' }}</div>
      <div class="cam-hint">{{ imageError ? '示例图片加载失败，请刷新或检查本地资源' : error || (online === false ? '设备离线' : '暂无预览流 · 检测采集与窗口预览分别配置') }}</div>
    </div>
    <div v-if="!showExample && !error && (!hasStream || overlayRect)" class="overlay-viewport" :style="overlayStyle">
      <RiskMaskOverlay :masks="masks" />
    </div>
  </div>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import flvjs from 'flv.js'
import RiskMaskOverlay from '@/components/RiskMask/index.vue'
import { containRect } from '@/utils/videoGeometry'
const props = defineProps({
  streamUrl: { type:String, default:'' }, name:{ type:String, default:'' },
  online:{ type:Boolean, default:true }, masks:{ type:Array, default:() => [] },
  exampleImage:{type:String,default:''}, exampleSource:{type:String,default:''},
})
const videoRef = ref(null), wrapRef = ref(null), error = ref(''), overlayRect = ref(null)
let flvPlayer, observer
const hasStream = computed(() => Boolean(props.streamUrl))
const imageError=ref(false)
const showExample=computed(()=>!hasStream.value && Boolean(props.exampleImage))
const overlayStyle = computed(() => overlayRect.value
  ? Object.fromEntries(Object.entries(overlayRect.value).map(([k,v]) => [k, v + 'px']))
  : { inset:'0' })
function updateRect() {
  const v = videoRef.value, w = wrapRef.value
  overlayRect.value = v && w ? containRect(w.clientWidth,w.clientHeight,v.videoWidth,v.videoHeight) : null
}
function destroyPlayer() {
  if (flvPlayer) { flvPlayer.destroy(); flvPlayer = null }
  const v = videoRef.value
  if (v) { v.pause(); v.removeAttribute('src'); v.load() }
  overlayRect.value = null
}
function initPlayer() {
  destroyPlayer(); error.value = ''
  const url = props.streamUrl, v = videoRef.value
  if (!url || !v) return
  if (/^(rtsp:|[A-Za-z]:[\\/])/i.test(url)) {
    error.value = '采集地址不能直接预览，请在视频源设置中填写 HTTP 预览流'; return
  }
  if (/\.(mp4|webm|ogg|m3u8)(\?|$)/i.test(url) || /^(blob:|data:)/i.test(url)) {
    if (/\.m3u8(\?|$)/i.test(url) && !v.canPlayType('application/vnd.apple.mpegurl')) {
      error.value = '当前窗口不支持 HLS，请提供 FLV/MP4 预览地址'; return
    }
    v.src = url; v.play().catch(() => {}); return
  }
  if (!flvjs.isSupported()) { error.value = '当前窗口不支持 FLV，请提供 MP4/WebM 预览地址'; return }
  try {
    flvPlayer = flvjs.createPlayer({ type:'flv', url, isLive:true })
    flvPlayer.on(flvjs.Events.ERROR, () => { error.value = 'FLV 预览连接失败；请检查地址、编码和跨域配置' })
    flvPlayer.attachMediaElement(v); flvPlayer.load(); flvPlayer.play().catch(() => {})
  } catch(e) { error.value = e.message || '预览初始化失败' }
}
onMounted(() => { observer = new ResizeObserver(updateRect); observer.observe(wrapRef.value); initPlayer() })
watch(() => props.streamUrl, initPlayer)
watch(() => props.exampleImage,()=>{imageError.value=false})
onBeforeUnmount(() => { observer?.disconnect(); destroyPlayer() })
</script>
<style scoped>
.video-player { position:relative; width:100%; height:100%; min-height:140px; background:var(--media-bg); overflow:hidden; border-radius:6px; }
.example-image{display:block;width:100%;height:100%;object-fit:contain}.example-caption{position:absolute;top:0;left:0;right:0;padding:9px 12px;background:linear-gradient(#071c50ef,#071c5055);display:flex;gap:10px;align-items:center;justify-content:space-between;color:#e6f4ff;font-size:12px;pointer-events:none;z-index:1}.example-caption strong{font-weight:500}.example-caption span{font-size:10px;background:#154c48;color:#a5f4ca;padding:2px 6px;border:1px solid #408a78}.example-source{position:absolute;bottom:0;left:0;right:0;padding:8px 12px;background:#071c50d9;color:#d0e4ff;font-size:10px;line-height:1.5;pointer-events:none}
.video-el { display:block; width:100%; height:100%; object-fit:contain; }
.overlay-viewport { position:absolute; pointer-events:none; }
.placeholder { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:20px; background:var(--media-bg); color:#b8c6d2; }
.cam-name { font-size:14px; font-weight:600; margin-bottom:8px; color:#e2edf5; }
.cam-hint { font-size:12px; text-align:center; line-height:1.7; }
</style>
