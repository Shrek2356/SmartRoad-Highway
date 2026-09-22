import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequestGate } from '../src/utils/requestGate.js'
import { saveBlob, saveOutcome } from '../src/utils/fileTransfer.js'

test('native exports preserve bytes and distinguish saved, cancelled and failed', async () => {
  let received
  const host = {pywebview:{api:{save_export:async(name,body)=>{ received = Buffer.from(body,'base64').toString(); return {status:'saved',filename:name} }}}}
  const result = await saveBlob(new Blob(['中文报告']), '报告.md', host)
  assert.equal(received, '中文报告')
  assert.equal(saveOutcome(result).kind,'success')
  host.pywebview.api.save_export = async()=>({status:'cancelled'})
  assert.equal(saveOutcome(await saveBlob(new Blob(['text']),'报告.md',host)).kind,'info')
  host.pywebview.api.save_export = async()=>{throw new Error('disk full')}
  await assert.rejects(saveBlob(new Blob(['text']),'报告.md',host),/disk full/)
  assert.throws(()=>saveOutcome({}),/未收到/)
  await assert.rejects(saveBlob(new Blob(['text']),'报告.md',{pywebview:{api:{}}}),/更新 EXE/)
})

test('browser export only reports requested and cleans up after the click', async () => {
  const events = []
  const host = {URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>events.push('revoked')},
    document:{body:{appendChild:()=>events.push('attached')},createElement:()=>({click:()=>events.push('clicked'),remove:()=>events.push('removed')})},
    setTimeout:fn=>{events.push('scheduled');fn()}}
  const result = await saveBlob(new Blob(['csv']),'test.csv',host)
  assert.equal(result.status,'download_requested')
  assert.equal(saveOutcome(result).kind,'info')
  assert.deepEqual(events,['attached','clicked','removed','scheduled','revoked'])
})

test('actual analysis loader ignores old project responses and responses after unmount', async () => {
  const source = await readFile(new URL('../src/views/analysis/index.vue',import.meta.url),'utf8')
  const code = source.slice(source.indexOf('async function loadData()'), source.indexOf('async function onExport()'))
  const ref = value=>({value}), pending=[]
  let project='A', renders=0
  const requests=createRequestGate(), state={loading:ref(false),loadError:ref(''),analysisPresentation:ref(false),sourceNote:ref(''),analysisEmpty:ref(false),rangeMeta:ref({}),trendRef:ref({}),heatRef:ref({}),teamRef:ref({}),colorTheme:ref('dark')}
  const dependencies={...state,requests,charts:[],lastData:null,fetchAnalysisData:()=>new Promise(resolve=>pending.push(resolve)),queryParams:()=>({projectId:project}),nextTick:async()=>{},chartTheme:()=>({}),echarts:{init:node=>{assert.ok(node);renders++;return {setOption(){},dispose(){}}}}}
  const load=new Function(...Object.keys(dependencies),code+';return loadData;')(...Object.values(dependencies))
  const data = p=>({data:{trend:{dates:['day'],red:[1],orange:[0],yellow:[0]},areaHeat:[],teamViolation:[],range:{start:p,end:p,days:1}}})
  const a=load();project='B';const b=load()
  pending[1](data('B'));await b;pending[0](data('A'));await a
  assert.equal(state.rangeMeta.value.start,'B');assert.equal(renders,3)
  const c=load();requests.dispose();state.trendRef.value=null;pending[2](data('C'));await c
  assert.equal(renders,3)
  assert.doesNotMatch(source.slice(source.indexOf('watch(colorTheme'),source.indexOf('watch(() => userStore')),/loadData/)
})

test('threshold save failure restores the persisted value and does not claim success', async () => {
  const source=await readFile(new URL('../src/views/model-config/index.vue',import.meta.url),'utf8')
  assert.match(source, /@afterChange=/)
  assert.doesNotMatch(source, /@change="\(v\) => onThreshold/)
  const code=source.slice(source.indexOf('async function onThreshold('),source.indexOf('async function loadKnowledge('))
  const row={key:'risk',value:.8}, thresholds={value:[row]}, savedThresholds=new Map([['risk',.6]]), thresholdSaving={value:{}}
  let successes=0,errors=0
  const save = new Function('thresholds','savedThresholds','thresholdSaving','updateThreshold','message',code+';return onThreshold;')(
    thresholds,savedThresholds,thresholdSaving,async()=>{throw new Error('offline')},{success:()=>successes++,error:()=>errors++})
  await save('risk',.8)
  assert.equal(row.value,.6);assert.equal(successes,0);assert.equal(errors,1);assert.equal(thresholdSaving.value.risk,false)
})

test('project metadata update returns the project, not an out-of-scope response', async () => {
  const source=await readFile(new URL('../src/stores/user.js',import.meta.url),'utf8')
  assert.match(source,/updateProjectMetadata\(project\)[\s\S]*?return project/)
})
