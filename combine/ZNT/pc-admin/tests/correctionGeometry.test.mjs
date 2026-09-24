import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizedPoint, normalizedBox } from '../src/utils/correctionGeometry.js'

test('annotation coordinates are independent of image size and reverse drag direction', () => {
  assert.deepEqual(normalizedPoint({clientX:300,clientY:200},{left:100,top:100,width:400,height:200}), [.5,.5])
  assert.deepEqual(normalizedPoint({clientX:900,clientY:20},{left:100,top:100,width:400,height:200}), [1,0])
  assert.deepEqual(normalizedBox([.8,.7],[.2,.1]), [.2,.1,.8,.7])
})
test('clicks or unloaded images cannot create a valid box', () => {
  assert.equal(normalizedPoint({clientX:2,clientY:2},{left:0,top:0,width:0,height:0}),null)
  assert.equal(normalizedBox([.1,.1],[.1001,.9]),null)
  assert.equal(normalizedBox(null,[1,1]),null)
})
