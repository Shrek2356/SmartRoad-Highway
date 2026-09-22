import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { containRect } from '../src/utils/videoGeometry.js'

test('viewing historical imports cannot create live results or work orders', async () => {
  globalThis.localStorage = { getItem:()=>{throw new Error('archive must not read live storage')}, setItem:()=>{throw new Error('archive must not write live storage')} }
  const job = { source:'archive', status:'done', result:{ risks:[{verified:true}], input_image:'/old.png' } }
  for (const [file, method] of [['detectResults','syncDetectJobToResults'], ['detectWorkOrders','syncDetectJobToWorkOrders']]) {
    const source = (await readFile(new URL(`../src/utils/${file}.js`, import.meta.url),'utf8')).replace(/^import .*$/gm,'')
    const api = await import('data:text/javascript;base64,'+Buffer.from('const notifyModules=()=>{throw new Error("no live notifications")};\n'+source).toString('base64'))
    const result = api[method](job)
    if (file === 'detectResults') assert.equal(result,null)
    else assert.equal(result.created,0)
  }
})

test('automatic road report links follow the selected detection gateway', async () => {
  const stored = new Map()
  globalThis.localStorage = { getItem:k=>stored.get(k) ?? null }
  const endpointSource = (await readFile(new URL('../src/utils/endpoints.js', import.meta.url),'utf8'))
    .replace(/^import .*$/gm, '')
    .replaceAll('import.meta.env.VITE_API_BASE', 'undefined')
    .replaceAll('import.meta.env.VITE_DETECT_API', 'undefined')
  const endpointsUrl = 'data:text/javascript;base64,'+Buffer.from(endpointSource).toString('base64')
  const source = (await readFile(new URL('../src/api/detect.js', import.meta.url),'utf8')).replace(/^import .*$/gm, '')
  const fixture = { result:{ issue_report:'/api/detect/jobs/JOB-QA/media/issue_report.md',
    scene_annotation:'/api/detect/jobs/JOB-QA/media/scene_annotation.png',
    input_image:'/api/detect/jobs/JOB-QA/media/input.png' } }
  const api = await import('data:text/javascript;base64,'+Buffer.from(
    `import { getDetectApiBase, resolveDetectMediaUrl } from '${endpointsUrl}';\n`+
    `const axios={create:()=>({interceptors:{request:{use:()=>{}}},get:async()=>({data:${JSON.stringify(fixture)}})})};\n`+source
  ).toString('base64'))
  let job = await api.fetchDetectJob('JOB-QA')
  assert.equal(job.result.issue_report,'/detect-api/api/detect/jobs/JOB-QA/media/issue_report.md')
  assert.equal(job.result.scene_annotation,'/detect-api/api/detect/jobs/JOB-QA/media/scene_annotation.png')
  stored.set('znt_detect_api','http://127.0.0.1:8810')
  job = await api.fetchDetectJob('JOB-QA')
  assert.equal(job.result.issue_report,'http://127.0.0.1:8810/api/detect/jobs/JOB-QA/media/issue_report.md')
  assert.equal(job.result.scene_annotation,'http://127.0.0.1:8810/api/detect/jobs/JOB-QA/media/scene_annotation.png')
})

test('normal scene keeps green annotation without fabricating a risk or a binary mask', async () => {
  const stored=new Map()
  globalThis.localStorage={getItem:k=>stored.get(k)??null,setItem:(k,v)=>stored.set(k,v)}
  const source=(await readFile(new URL('../src/utils/detectResults.js',import.meta.url),'utf8')).replace(/^import .*$/gm,'')
  const api=await import('data:text/javascript;base64,'+Buffer.from('const notifyModules=()=>{};\n'+source).toString('base64'))
  const result=api.syncDetectJobToResults({job_id:'normal',status:'done',profile:'offline',result:{
    risks:[],assessment_quality:{result_status:'no_visible_anomaly'},scene_annotation:'/api/detect/jobs/normal/media/scene_annotation.png'}})
  assert.equal(result.expected,'未见可见异常')
  assert.equal(result.riskCount,0)
  assert.equal(result.autoConfirm,false)
  assert.equal(result.humanReview,false)
  assert.equal(result.images.mask,'')
  assert.match(result.cover,/scene_annotation.png$/)
})

test('portrait and landscape overlays stay on the contained image, not black bars', () => {
  assert.deepEqual(containRect(1000,600,1920,1080), { left:0, top:18.75, width:1000, height:562.5 })
  assert.deepEqual(containRect(1000,600,600,1200), { left:350, top:0, width:300, height:600 })
  assert.equal(containRect(0,600,1920,1080), null)
})

test('real login uses the entered account and password, not the role preset', async () => {
  const source = (await readFile(new URL('../src/api/auth.js', import.meta.url),'utf8'))
    .replace(/^import .*$/gm, '')
  const api = await import('data:text/javascript;base64,' + Buffer.from(
    'const USE_MOCK=false; const request={post:(url,data)=>({url,data})};\n'+source
  ).toString('base64'))
  assert.deepEqual(api.login({username:'new_manager',password:'custom-pass',role:'safety'}), {
    url:'/auth/login', data:{username:'new_manager',password:'custom-pass'},
  })
  assert.equal(api.login({username:'safety',password:'admin123',role:'safety'}).data.password, 'admin123')
})

test('road lab never enables construction showcase fixtures', async () => {
  const values = new Map()
  globalThis.localStorage = { getItem:k=>values.get(k) ?? null, setItem:(k,v)=>values.set(k,v) }
  globalThis.document = { documentElement:{ dataset:{} } }
  const source = (await readFile(new URL('../src/utils/preferences.js', import.meta.url),'utf8'))
    .replace("import { ref } from 'vue'", 'const ref = value => ({value})')
    .replace('import.meta.env.VITE_ENABLE_PRESENTATION_ASSETS', 'undefined')
  const prefs = await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))
  assert.equal(prefs.presentationEnabled(),false)
  prefs.setPresentationAssets(false)
  assert.equal(prefs.presentationEnabled(),false)
  assert.equal(values.get('znt_presentation_assets'),'false')
  prefs.setPresentationAssets(true)
  prefs.setWorkspaceStyle('showcase')
  assert.equal(document.documentElement.dataset.workspaceStyle,'showcase')
  assert.equal(prefs.presentationEnabled(),false)
})
