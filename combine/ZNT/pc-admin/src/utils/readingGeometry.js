export function normalizeFontPercent(value) {
  const n=Number(value)
  return Number.isFinite(n) && n>=100 ? Math.min(200,Math.round(n/5)*5) : 100
}
export function constrainView(view,width,height) {
  const scale=Math.max(1,Math.min(4,Number(view.scale)||1))
  return {scale,x:Math.max(width*(1-scale),Math.min(0,Number(view.x)||0)),y:Math.max(height*(1-scale),Math.min(0,Number(view.y)||0))}
}
export function zoomAt(view,nextScale,point,width,height) {
  const scale=Math.max(1,Math.min(4,nextScale)),ratio=scale/view.scale
  return constrainView({scale,x:point.x-(point.x-view.x)*ratio,y:point.y-(point.y-view.y)*ratio},width,height)
}
export function wheelScale(view,event) {
  const pixels=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?400:1)
  return view.scale*Math.exp(-Math.max(-180,Math.min(180,pixels))*.002)
}
