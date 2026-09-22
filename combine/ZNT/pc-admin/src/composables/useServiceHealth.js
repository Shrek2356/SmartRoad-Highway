import { reactive, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'
import { getBusinessApiBase } from '@/utils/endpoints'
import { checkDetectHealth } from '@/api/detect'

// All visible status surfaces share one read-only request cycle. No model calls.
const state = reactive({ business:null, detect:null, loading:false, updatedAt:null })
let subscribers = 0, timer, inFlight
export function refreshServiceHealth() {
  if (inFlight) return inFlight
  clearTimeout(timer)
  state.loading = true
  inFlight = (async () => {
    const [b, d] = await Promise.allSettled([
      axios.get(`${getBusinessApiBase()}/health`, { timeout:5000 }), checkDetectHealth(),
    ])
    state.business = b.status === 'fulfilled' && b.value.data?.ok === true && b.value.data?.service === 'znt-business-api'
    state.detect = d.status === 'fulfilled' ? d.value : { online:false }
    state.updatedAt = new Date().toISOString()
  })().finally(() => {
    state.loading = false
    inFlight = null
    if (subscribers) timer = setTimeout(refreshServiceHealth, 15000)
  })
  return inFlight
}
export function useServiceHealth() {
  onMounted(() => { subscribers++; if (subscribers === 1) refreshServiceHealth() })
  onBeforeUnmount(() => { subscribers = Math.max(0, subscribers - 1); if (!subscribers) clearTimeout(timer) })
  return { health:state, refresh:refreshServiceHealth }
}
