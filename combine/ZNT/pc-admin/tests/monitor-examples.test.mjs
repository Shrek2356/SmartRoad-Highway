import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { demoCameras,cameraMonitorLocation,demoDeviceTree } from '../src/data/lexiCameras.js'
import { visibleCameras } from '../src/utils/monitorSelection.js'

test('only camera IDs navigate to matching monitor pictures; sensors do not',()=>{
  assert.equal(demoCameras.length,5)
  for(const c of demoCameras){
    const target=cameraMonitorLocation(c.id)
    assert.equal(target.path,'/monitor');assert.equal(target.query.cameraId,c.id)
    assert.equal(target.query.source,'demo');assert.equal(target.query.layout,'1')
    assert.equal(c.streamUrl,'');assert.equal(c.online,false);assert.deepEqual(c.masks,[])
    assert.equal(demoDeviceTree[0].children.find(n=>n.key===c.id).title,c.name)
  }
  for(const id of ['DEMO-RAD-01','DEMO-WX-01','DEMO-SIGN-01','unknown','CAM-REAL-01'])assert.equal(cameraMonitorLocation(id),null)
})
test('each fixed camera binding points to the original verified local image bytes',async()=>{
  const root=new URL('../public/media/road-monitor/',import.meta.url)
  const provenance=JSON.parse(await readFile(new URL('provenance.json',root),'utf8'))
  for(const c of demoCameras){
    const file=c.exampleImage.split('/').at(-1),record=provenance.find(p=>p.file===file)
    assert.ok(record);assert.equal(c.sample,record.sample)
    const bytes=await readFile(new URL(file,root))
    assert.equal(createHash('sha256').update(bytes).digest('hex'),record.sha256)
    assert.ok(bytes.length>1000)
  }
  assert.equal(new Set(demoCameras.map(c=>c.exampleImage)).size,5)
})
test('fifth camera remains selected in single and four-window layouts without duplicates',()=>{
  const id=demoCameras[4].id
  assert.equal(visibleCameras(demoCameras,id,[],1)[0].id,id)
  const grid=visibleCameras(demoCameras,id,[id,demoCameras[0].id],4)
  assert.equal(grid[0].id,id);assert.equal(new Set(grid.map(c=>c.id)).size,4)
})
test('empty or missing real cameras never become demo cameras',()=>{
  assert.deepEqual(visibleCameras([],'DEMO-CAM-01',[],4),[null,null,null,null])
  const real={id:'real-1',streamUrl:'https://example.test/live.flv'}
  assert.deepEqual(visibleCameras([real],'DEMO-CAM-01',['missing'],1),[real])
  assert.equal(visibleCameras([real],'real-1',[],9).filter(Boolean).length,1)
})
