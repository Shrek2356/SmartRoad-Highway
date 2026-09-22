import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// Deep links and in-page tabs use one source of truth, including Back/Forward.
export function useRouteTab(allowed, fallback) {
  const route = useRoute(), router = useRouter()
  return computed({
    get: () => allowed.includes(route.query.tab) ? route.query.tab : fallback,
    set: value => {
      if (allowed.includes(value)) router.replace({ query:{ ...route.query, tab:value } })
    },
  })
}
