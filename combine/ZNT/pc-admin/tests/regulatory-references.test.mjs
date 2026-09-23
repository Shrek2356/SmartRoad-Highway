import test from 'node:test'
import assert from 'node:assert/strict'
import { referenceGroups, referenceCount, emptyReferenceMessage, safeSourceUrl, scoreLabel } from '../src/utils/regulatoryReferences.js'

test('references remain associated with their own risk, and old collection dates never become search times', () => {
  const result = { risks: [
    { risk_id: 'water', name: '积水', knowledge_references: [{ section: '第三十条', retrieved_at: '2026-01-01' }] },
    { risk_id: 'debris', name: '异物', knowledge_references: [{ section: '第四十八条' }], knowledge_retrieval: { query: '异物', searched_at: '2026-09-22' } },
  ] }
  const before = JSON.stringify(result)
  const groups = referenceGroups(result)
  assert.equal(groups[0].references[0].section, '第三十条')
  assert.equal(groups[0].trace.searched_at, undefined)
  assert.equal(groups[0].trace.query, undefined)
  assert.equal(groups[1].references[0].section, '第四十八条')
  assert.equal(groups[1].trace.query, '异物')
  assert.equal(referenceCount(result), 2)
  assert.equal(JSON.stringify(result), before)
})

test('normal scenes, missing records, empty searches and unconfigured scopes are distinguished', () => {
  assert.match(emptyReferenceMessage({ assessment_quality: { result_status: 'no_visible_anomaly' } }), /未见可见异常/)
  assert.match(emptyReferenceMessage({}), /未保存规范检索记录/)
  assert.match(emptyReferenceMessage({}, { trace: { status: 'no_verified_match' } }), /已检索，未找到/)
  assert.match(emptyReferenceMessage({}, { trace: { status: 'not_configured' } }), /未执行规范检索/)
  assert.match(emptyReferenceMessage({ reference_record_status: 'invalid' }), /无法读取/)
  assert.equal(referenceCount({ risks: [{ knowledge_references: [null, 'wrong', []] }] }), 0)
})

test('source links reject executable and non-web URLs; missing scores are not zero or confidence', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,hi', 'file:///C:/secret', '//bad.example', 'https://user:password@bad.example', undefined]) assert.equal(safeSourceUrl(url), '')
  assert.equal(safeSourceUrl('https://www.beijing.gov.cn/law'), 'https://www.beijing.gov.cn/law')
  assert.equal(scoreLabel(0), '0.0000')
  assert.equal(scoreLabel(0.1275), '0.1275')
  for (const value of [undefined, null, '', NaN]) assert.equal(scoreLabel(value), '未记录')
})
