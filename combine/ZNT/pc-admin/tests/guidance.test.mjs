import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { HELP_PAGES, QUICK_ACTIONS, JOURNEYS, FAQS, pageFor, canVisit, searchFunctions } from '../src/utils/guidance.js'
import { checkPermission } from '../src/utils/permission.js'
import { diagnosticSnapshot, healthCards } from '../src/utils/healthPresentation.js'
import { detectionBlockReason, normalizeDetectionProfile } from '../src/utils/detectionIntent.js'
import { validateEndpoint } from '../src/utils/endpointValidation.js'

test('every operational route has contextual guidance and a registered next step', async()=>{
  const routes = await readFile(new URL('../src/router/index.js',import.meta.url),'utf8')
  const registered = [...routes.matchAll(/path:\s*'([a-z][a-z-]*)'/g)].map(m=>'/'+m[1])
  assert.deepEqual(HELP_PAGES.map(p=>p.path).sort(),registered.sort())
  for(const page of HELP_PAGES){ assert.ok(page.steps.length>=3); assert.ok(page.result); assert.ok(page.caution); assert.ok(pageFor(page.next)) }
})
test('help, role menus and actionable destinations agree',()=>{
  for(const role of ['admin','safety','director']) for(const page of HELP_PAGES) assert.equal(canVisit(page.path,role),checkPermission(role,page.path),`${role}: ${page.path}`)
  for(const target of [...QUICK_ACTIONS.map(a=>a.target),...FAQS.map(a=>a.target),...JOURNEYS.flatMap(j=>j.steps.map(s=>s.target))]) assert.ok(pageFor(target),target)
  assert.equal(canVisit('/model-config?tab=runtime','safety'),false)
  assert.equal(canVisit('/help-center',''),false)
})
test('search supports operational keywords, trims whitespace and filters restricted settings',()=>{
  assert.ok(searchFunctions('  QWEN  ','admin').some(x=>x.target==='/model-config?tab=runtime'))
  assert.ok(searchFunctions('规范','admin').some(x=>x.target==='/model-config?tab=kb'))
  assert.ok(searchFunctions('检测桥','safety').some(x=>x.target==='/help-center?tab=diagnostics'))
  assert.ok(searchFunctions('','director').every(x=>!x.target.startsWith('/model-config')))
  assert.equal(searchFunctions('不存在的模块abcxyz','admin').length,0)
})
test('diagnostics distinguish unknown, configured and runtime-ready, without claiming inference success',()=>{
  assert.ok(healthCards({}).every(x=>x.state==='checking'))
  const configured={updatedAt:'2026-09-07',business:true,detect:{online:true,profiles:[{id:'offline',ready:true,runtime_ready:false}]}}
  assert.equal(healthCards(configured).find(x=>x.id==='offline').state,'attention')
  configured.detect.profiles[0].runtime_ready=true
  assert.equal(healthCards(configured).find(x=>x.id==='offline').label,'配置与服务就绪')
})
test('exported support snapshot never copies secrets, paths, images or identities',()=>{
  const snapshot=JSON.stringify(diagnosticSnapshot({updatedAt:'now',business:true,user:'private-name',detect:{online:true,key:'secret-123',config:{model:'E:\\private'},image:'private-image',inference_queue:{pending:2}}}))
  for(const secret of ['private-name','secret-123','E:', 'private-image']) assert.equal(snapshot.includes(secret),false)
  assert.equal(JSON.parse(snapshot).pendingTasks,2)
})
test('real detection cannot silently degrade to demo when service disconnects',()=>{
  for(const profile of ['offline','standard']){const health={online:false,profiles:[]};assert.ok(detectionBlockReason(profile,health));assert.equal(normalizeDetectionProfile(profile),profile)}
  assert.equal(detectionBlockReason('demo',{online:false}),'')
  assert.equal(detectionBlockReason('offline',{online:true,profiles:[{id:'offline',ready:true,runtime_ready:true}]}),'')
  assert.ok(detectionBlockReason('offline',{online:true,profiles:[{id:'offline',ready:true,runtime_ready:false}]}))
  assert.equal(normalizeDetectionProfile('malicious'),'offline')
})
test('connection configuration accepts service URLs, not weights or credentials',()=>{
  for(const valid of ['/detect-api','/business-api/api','http://127.0.0.1:8810','https://example.com/api']) assert.equal(validateEndpoint(valid),valid)
  for(const invalid of ['E:\\model','javascript:alert(1)','file:///C:/config','//external/api','http://user:pass@localhost','https://example.com?key=secret','https://example.com/#secret','/../private','localhost:8810']) assert.throws(()=>validateEndpoint(invalid))
})
test('mode refresh no longer changes the selected intent and deep-linked jobs load on mount', async()=>{
  const source=await readFile(new URL('../src/views/realtime-detect/index.vue',import.meta.url),'utf8')
  const refresh=source.split('async function refreshHealth()')[1].split('async function saveCloudKey()')[0]
  assert.equal(/profile\.value\s*=/.test(refresh),false)
  assert.ok(source.includes('if (route.query.job) await loadJob(String(route.query.job))'))
})
