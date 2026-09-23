import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeFontPercent,zoomAt,constrainView,wheelScale } from '../src/utils/readingGeometry.js'
import { scaleFontValue } from '../scripts/fontScale.js'

test('invalid saved font sizes recover to readable defaults with a 200 percent upper bound',()=>{
  for(const value of [null,undefined,'garbage',-50,0,99])assert.equal(normalizeFontPercent(value),100)
  assert.equal(normalizeFontPercent('125'),125)
  assert.equal(normalizeFontPercent(999),200)
})
test('inspection zoom keeps the content under the pointer stationary',()=>{
  const original={scale:1,x:0,y:0},point={x:400,y:240}
  const enlarged=zoomAt(original,2,point,1200,800)
  assert.deepEqual(enlarged,{scale:2,x:-400,y:-240})
  assert.equal((point.x-enlarged.x)/enlarged.scale,400)
  assert.equal((point.y-enlarged.y)/enlarged.scale,240)
  assert.deepEqual(zoomAt(enlarged,1,point,1200,800),original)
})
test('dragging and extreme zoom cannot lose the page outside the viewport',()=>{
  assert.deepEqual(constrainView({scale:2,x:-99999,y:99999},1200,800),{scale:2,x:-1200,y:0})
  assert.deepEqual(constrainView({scale:1,x:-50,y:-50},1200,800),{scale:1,x:0,y:0})
  assert.equal(zoomAt({scale:1,x:0,y:0},99,{x:0,y:0},1200,800).scale,4)
})
test('mouse and trackpad wheel units agree; wheel direction is conventional',()=>{
  const view={scale:2,x:0,y:0}
  assert.equal(wheelScale(view,{deltaY:1,deltaMode:1}),wheelScale(view,{deltaY:16,deltaMode:0}))
  assert.ok(wheelScale(view,{deltaY:-80,deltaMode:0})>2)
  assert.ok(wheelScale(view,{deltaY:80,deltaMode:0})<2)
})
test('font scaling handles shorthand and clamp while leaving geometry and colors unchanged',()=>{
  for(const prop of ['width','height','border','transform'])assert.equal(scaleFontValue(prop,'12px'), '12px')
  assert.equal(scaleFontValue('font','12px/18px sans-serif'),'calc(12px * var(--ui-font-scale, 1))/calc(18px * var(--ui-font-scale, 1)) sans-serif')
  const value=scaleFontValue('font-size','clamp(12px,2vw,24px)')
  assert.ok(value.includes('calc(12px'))
  assert.ok(value.includes('calc(24px'))
  assert.equal(scaleFontValue('font-size',value),value)
})
