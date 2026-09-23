import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { routeNodes, landmarks, structures, devices, reports, normalSection } from '../../data/lexiDemo.js'

/** All geometry is local and procedural; no external map / tile / model requests. */
export function createHighwayScene(host, { onSelect, onLabels, onFailure, onReady }) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'low-power' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
  renderer.setClearColor('#07182f')
  host.appendChild(renderer.domElement)
  renderer.domElement.setAttribute('aria-label', '可旋转的乐西高速三维示意模型，左键拖动旋转，滚轮缩放，右键平移；点位也可由下方列表选择')
  const scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2('#07182f', 0.0016)
  const camera = new THREE.PerspectiveCamera(42, 1, 0.2, 1600)
  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.085
  controls.minDistance = 38
  controls.maxDistance = 540
  controls.maxPolarAngle = Math.PI * 0.48
  controls.autoRotateSpeed = 0.38
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
  const light = new THREE.DirectionalLight('#a3d6ff', 2.8)
  light.position.set(-70, 160, 90)
  scene.add(light, new THREE.HemisphereLight('#8cd9f5', '#08152e', 2.5))
  const road = new THREE.CatmullRomCurve3(routeNodes.map(p => new THREE.Vector3(...p)))
  const sampled = road.getPoints(260)
  const vUp = new THREE.Vector3(0, 1, 0)
  const markers = new Map(), selectable = []
  let activeId = '', layers = { devices: true, risks: true }, severity = 'all', dead = false
  let raf = 0, visible = true, lastTime = 0, pointerStart = null, contextLost = false
  function pointAt(t, offset = 0, lift = 0) {
    const p = road.getPointAt(t)
    const side = new THREE.Vector3().crossVectors(road.getTangentAt(t), vUp).normalize()
    return p.addScaledVector(side, offset).addScaledVector(vUp, lift)
  }
  function material(color, extra = {}) { return new THREE.MeshStandardMaterial({ color, roughness: 0.8, ...extra }) }
  function mesh(geometry, mat, position, parent = scene) {
    const object = new THREE.Mesh(geometry, mat)
    if (position) object.position.copy(position)
    parent.add(object)
    return object
  }
  function line(points, color, opacity = 1) {
    const object = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity }))
    scene.add(object)
    return object
  }
  function terrainHeight(x, z) {
    let distance = Infinity, nearest
    for (const p of sampled) {
      const d = (x-p.x)**2 + (z-p.z)**2
      if (d < distance) { distance = d; nearest = p }
    }
    const mountains = 12 + 16 * Math.sin(x * 0.027 + z * 0.012) ** 2 + 23 * Math.cos(x * 0.041 - z * 0.024) ** 2
    const blend = THREE.MathUtils.smoothstep(Math.sqrt(distance), 10, 47)
    return THREE.MathUtils.lerp(nearest.y - 4.4, mountains, blend) - 5
  }
  const terrain = new THREE.PlaneGeometry(350, 190, 90, 48)
  terrain.rotateX(-Math.PI / 2)
  const positions = terrain.attributes.position, colors = []
  for (let i = 0; i < positions.count; i++) {
    const h = terrainHeight(positions.getX(i), positions.getZ(i))
    positions.setY(i, h)
    const c = new THREE.Color('#0c2b42').lerp(new THREE.Color('#23516a'), THREE.MathUtils.clamp(h / 54, 0, 1))
    colors.push(c.r, c.g, c.b)
  }
  terrain.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
  terrain.computeVertexNormals()
  mesh(terrain, material('#ffffff', { vertexColors: true, flatShading: true }))
  mesh(terrain, new THREE.MeshBasicMaterial({ color: '#4b99ba', wireframe: true, transparent: true, opacity: 0.075 }))
  const grid = new THREE.GridHelper(460, 46, '#214968', '#123452')
  grid.position.y = -8
  scene.add(grid)
  const base = mesh(new THREE.BoxGeometry(350, 3, 190), material('#09213a'), new THREE.Vector3(0, -9, 0))
  scene.add(new THREE.BoxHelper(base, '#26506b'))
  // Road ribbon follows the same curve used for every device and report anchor.
  const vertices = [], indices = []
  for (let i = 0; i <= 400; i++) {
    for (const offset of [-4.3, 4.3]) vertices.push(...pointAt(i / 400, offset).toArray())
    if (i < 400) { const n = i * 2; indices.push(n, n+2, n+1, n+1, n+2, n+3) }
  }
  const ribbon = new THREE.BufferGeometry()
  ribbon.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
  ribbon.setIndex(indices); ribbon.computeVertexNormals()
  mesh(ribbon, material('#344a60', { side: THREE.DoubleSide }))
  for (const offset of [-4.1, 0, 4.1]) {
    line(Array.from({ length: 401 }, (_, i) => pointAt(i/400, offset, 0.13)), offset === 0 ? '#6fbbc8' : '#b3d9df', 0.88)
  }
  const laneDashes=[]
  for (let i = 0; i < 120; i++) for (const offset of [-2.1, 2.1]) {
    laneDashes.push(pointAt(i/120, offset, 0.16),pointAt((i+0.45)/120, offset, 0.16))
  }
  scene.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(laneDashes),new THREE.LineBasicMaterial({color:'#e3eff2',transparent:true,opacity:.75})))
  const bridge = structures.find(s => s.id === 'bridge')
  for (let t = bridge.start; t <= bridge.end; t += 0.022) {
    const p = pointAt(t)
    mesh(new THREE.BoxGeometry(2.5, p.y + 7, 7.5), material('#496b80'), new THREE.Vector3(p.x, (p.y-7)/2, p.z))
  }
  for (const offset of [-5, 5]) {
    line(Array.from({ length: 40 }, (_, i) => pointAt(bridge.start + (bridge.end-bridge.start)*i/39, offset, 1.2)), '#5ccef0')
  }
  const tunnel = structures.find(s => s.id === 'tunnel')
  const archVertices = [], archIndices = []
  for (let i = 0; i <= 40; i++) {
    const t = tunnel.start + (tunnel.end-tunnel.start)*i/40
    for (let j = 0; j <= 16; j++) {
      const a = j / 16 * Math.PI
      archVertices.push(...pointAt(t, Math.cos(a)*6.1, Math.sin(a)*6.1 + 0.1).toArray())
      if (i < 40 && j < 16) { const n = i*17+j; archIndices.push(n,n+1,n+17,n+1,n+18,n+17) }
    }
  }
  const arch = new THREE.BufferGeometry()
  arch.setAttribute('position', new THREE.Float32BufferAttribute(archVertices,3)); arch.setIndex(archIndices); arch.computeVertexNormals()
  mesh(arch, material('#39768b', { transparent: true, opacity: 0.48, side: THREE.DoubleSide }))
  for (const t of [tunnel.start, tunnel.end]) {
    line(Array.from({ length: 33 }, (_,i) => pointAt(t,Math.cos(i/32*Math.PI)*6.3,Math.sin(i/32*Math.PI)*6.3+0.3)), '#74d3ed')
  }
  // Visible condition geometry: inundation, scattered objects and roadside sign.
  const flood = mesh(new THREE.CircleGeometry(6, 32), material('#20b7df', { transparent: true, opacity: 0.75, metalness: 0.3 }), pointAt(0.50, 0, 0.22))
  flood.rotation.x = -Math.PI/2; flood.scale.set(1.9, 0.66, 1)
  for (const [t, scale, count] of [[0.735,1.4,5],[0.235,0.75,7]]) {
    for (let i = 0; i < count; i++) {
      const obj = mesh(new THREE.DodecahedronGeometry(scale*(0.65+i%3*0.15)), material(t>0.5?'#a5a8a0':'#c7ad80'), pointAt(t+(i-2)*0.002, -2.6+(i%3)*1.8, scale*0.48))
      obj.rotation.set(i*0.8,i*0.7,i*0.5)
    }
  }
  const sign = new THREE.Group(); sign.position.copy(pointAt(0.91, -7))
  sign.rotation.z = -0.2; scene.add(sign)
  mesh(new THREE.CylinderGeometry(.25,.25,7,8),material('#acc7d4'),new THREE.Vector3(0,3.5,0),sign)
  mesh(new THREE.BoxGeometry(6,3,.5),material('#168066'),new THREE.Vector3(0,7,0),sign)
  // Normal wet road is green and is never a risk marker.
  line(Array.from({ length: 32 }, (_,i) => pointAt(0.09+i/31*0.07,-4.8,.6)), '#52d7a2')
  function addMarker(item, kind) {
    const color = kind === 'risk' ? (item.severity === 'critical' ? '#ff6c75' : '#ffc66e') :
      ({ online:'#5bdbf2',offline:'#a6b0c0',maintenance:'#ffc66e' }[item.state])
    const anchor = pointAt(item.t, kind === 'device' ? 7.5 : -0.5, 0.5)
    const group = new THREE.Group(); group.position.copy(anchor); scene.add(group)
    const height = kind === 'risk' ? 15 : 9
    mesh(new THREE.CylinderGeometry(.18,.18,height,6),material(color),new THREE.Vector3(0,height/2,0),group)
    const cap = mesh(kind === 'risk' ? new THREE.OctahedronGeometry(2.5) : new THREE.BoxGeometry(2.7,2,2),material(color,{emissive:color,emissiveIntensity:.22}),new THREE.Vector3(0,height,0),group)
    cap.userData.id = item.id; selectable.push(cap)
    const ring = mesh(new THREE.RingGeometry(2.8,3.3,32),new THREE.MeshBasicMaterial({color,side:THREE.DoubleSide,transparent:true,opacity:.8}),new THREE.Vector3(0,.3,0),group)
    ring.rotation.x = -Math.PI/2
    markers.set(item.id, { group, cap, item, kind, anchor: anchor.clone().add(new THREE.Vector3(0,height+4,0)), ring })
  }
  devices.forEach(d=>addMarker(d,'device')); reports.forEach(r=>addMarker(r,'risk'))
  const textAnchors = landmarks.map(l=>({ id:l.name, text:l.name, type:'place', position:pointAt(l.t,20,2) }))
  textAnchors.push({id:'normal',text:normalSection.name,type:'normal',position:pointAt(normalSection.t,-9,1)})
  structures.forEach(s=>textAnchors.push({id:s.id,text:s.label,type:'structure',position:pointAt((s.start+s.end)/2,15,4)}))
  const raycaster = new THREE.Raycaster(), cursor = new THREE.Vector2()
  function down(event) { pointerStart = { x:event.clientX,y:event.clientY,button:event.button } }
  function up(event) {
    if (!pointerStart || pointerStart.button !== 0 || Math.hypot(event.clientX-pointerStart.x,event.clientY-pointerStart.y)>5) return
    const box = renderer.domElement.getBoundingClientRect()
    cursor.set((event.clientX-box.left)/box.width*2-1, -(event.clientY-box.top)/box.height*2+1)
    raycaster.setFromCamera(cursor,camera)
    const visibleObjects = selectable.filter(o=>o.parent.visible)
    const hit = raycaster.intersectObjects(visibleObjects,false)[0]
    if (hit) onSelect(hit.object.userData.id)
    pointerStart = null
  }
  renderer.domElement.addEventListener('pointerdown', down)
  renderer.domElement.addEventListener('pointerup', up)
  function project(position) {
    const p = position.clone().project(camera)
    return { x:(p.x+1)*host.clientWidth/2,y:(1-p.y)*host.clientHeight/2,visible:p.z>-1&&p.z<1&&Math.abs(p.x)<.98&&Math.abs(p.y)<.95 }
  }
  function renderLabels() {
    onLabels([
      ...textAnchors.map(a=>({ ...a,...project(a.position) })),
      ...Array.from(markers.values()).filter(m=>m.group.visible).map(m=>({id:m.item.id,text:m.item.short,type:m.kind,active:m.item.id===activeId,severity:m.item.severity,state:m.item.state,...project(m.anchor)})),
    ])
  }
  function frame(time) {
    raf = 0
    if (dead || contextLost || document.hidden || !visible) return
    raf = requestAnimationFrame(frame)
    if (time-lastTime < 32) return
    lastTime = time
    controls.update()
    renderer.render(scene,camera)
    renderLabels()
  }
  function resume() { if (!dead&&!contextLost&&!document.hidden&&visible&&!raf) raf=requestAnimationFrame(frame) }
  function resize() {
    const width=host.clientWidth,height=host.clientHeight
    if (!width||!height||dead) return
    camera.aspect=width/height;camera.updateProjectionMatrix();renderer.setSize(width,height);resume()
  }
  const observer = new ResizeObserver(resize); observer.observe(host)
  const intersection = new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;resume()});intersection.observe(host)
  document.addEventListener('visibilitychange',resume)
  function lost(event) { event.preventDefault();contextLost=true;cancelAnimationFrame(raf);raf=0;onFailure('三维渲染连接已中断，可重试；下方点位与报告仍可查看。') }
  renderer.domElement.addEventListener('webglcontextlost',lost)
  function setView(view='overview') {
    controls.target.set(0,8,0)
    if (view==='top') camera.position.set(0,330,0.1)
    else camera.position.set(78,210,280)
    controls.update();resume()
  }
  function rotate(direction) {
    const delta = camera.position.clone().sub(controls.target)
    delta.applyAxisAngle(vUp, direction*Math.PI/12);camera.position.copy(controls.target).add(delta);controls.update()
  }
  function zoom(factor) {
    const delta=camera.position.clone().sub(controls.target)
    delta.setLength(THREE.MathUtils.clamp(delta.length()*factor,controls.minDistance,controls.maxDistance))
    camera.position.copy(controls.target).add(delta);controls.update()
  }
  function update(options) {
    activeId=options.selectedId||'';layers=options.layers;severity=options.severity
    for (const m of markers.values()) {
      m.group.visible=m.kind==='device'?layers.devices:(layers.risks&&(severity==='all'||m.item.severity===severity))
      const active=m.item.id===activeId
      m.cap.scale.setScalar(active?1.5:1);m.ring.scale.setScalar(active?1.5:1)
    }
    controls.autoRotate=options.autoRotate&&!reduced.matches
  }
  function focus(id) {
    const marker=markers.get(id)
    if (!marker) return
    controls.target.copy(marker.group.position)
    camera.position.copy(marker.group.position).add(new THREE.Vector3(38,80,105));controls.update();resume()
  }
  function motionChanged() { if (reduced.matches) controls.autoRotate=false }
  reduced.addEventListener('change',motionChanged)
  function dispose() {
    if(dead)return
    dead=true;cancelAnimationFrame(raf);observer.disconnect();intersection.disconnect();controls.dispose()
    document.removeEventListener('visibilitychange',resume);reduced.removeEventListener('change',motionChanged)
    renderer.domElement.removeEventListener('pointerdown',down);renderer.domElement.removeEventListener('pointerup',up)
    renderer.domElement.removeEventListener('webglcontextlost',lost)
    const geometries=new Set(),materials=new Set()
    scene.traverse(object=>{if(object.geometry)geometries.add(object.geometry);if(object.material)(Array.isArray(object.material)?object.material:[object.material]).forEach(m=>materials.add(m))})
    geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()
  }
  setView();resize();onReady()
  return { update,focus,setView,rotate,zoom,dispose }
}
