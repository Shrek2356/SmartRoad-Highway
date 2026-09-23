import test from 'node:test'
import assert from 'node:assert/strict'
import { devices,reports,normalSection,corridor,demoSummary,selectReports,demoReportMarkdown } from '../src/data/lexiDemo.js'

test('road demo has valid device references, distinct IDs and finite scene anchors',()=>{
  const ids=[...devices,...reports].map(i=>i.id)
  assert.equal(new Set(ids).size,ids.length)
  for(const item of [...devices,...reports]){
    assert.ok(item.id.startsWith('DEMO-'))
    assert.ok(Number.isFinite(item.t)&&item.t>=0&&item.t<=1)
  }
  for(const report of reports)assert.ok(devices.some(d=>d.id===report.deviceId))
  assert.equal(corridor.mode,'demo')
})
test('risk filtering and totals never count wet normal road as an anomaly',()=>{
  assert.deepEqual(demoSummary(),{devices:8,online:6,critical:2,reports:4})
  assert.equal(selectReports('critical').length,2)
  assert.equal(selectReports('warning').length,2)
  assert.equal(selectReports('missing').length,0)
  assert.ok(!reports.some(r=>r.t===normalSection.t))
  assert.match(normalSection.description,/不计入异常/)
})
test('every exported report identifies fabricated data and has no invented evidence link',()=>{
  for(const r of reports){
    const text=demoReportMarkdown(r)
    assert.match(text,/虚构演示数据，不是实际检测结果/)
    assert.ok(text.includes(r.id)&&text.includes(r.chainage)&&text.includes(r.observation))
    assert.ok(text.includes(devices.find(d=>d.id===r.deviceId).name))
    assert.match(text,/无现场原图、掩码或模型推理记录/)
    assert.doesNotMatch(text,/!\[|\/api\/detect\/jobs|JOB-/)
  }
})
