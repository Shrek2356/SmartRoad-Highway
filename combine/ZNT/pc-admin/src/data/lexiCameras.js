import { devices } from './lexiDemo.js'

// Fixed image-to-device bindings, separate from real configured stream sources.
const examples = {
  'DEMO-CAM-01': { file:'normal-day.jpg', sample:'N02', source:'UA-DETRAC 城市道路 · 白天正常车流' },
  'DEMO-CAM-02': { file:'normal-corridor.jpg', sample:'N04', source:'UA-DETRAC 城市道路 · 正常通行' },
  'DEMO-CAM-03': { file:'normal-wet-highway.png', sample:'S10', source:'合成高速道路 · 湿润路面正常示例' },
  'DEMO-CAM-04': { file:'normal-wet.jpg', sample:'N03', source:'UA-DETRAC 城市道路 · 湿路正常车流' },
  'DEMO-CAM-05': { file:'normal-night.jpg', sample:'N01', source:'UA-DETRAC 城市道路 · 夜间正常车流' },
}
export const demoCameras = devices.filter(d=>Object.hasOwn(examples,d.id)).map(d=>({
  ...d, source:'demo', online:false, streamUrl:'', masks:[],
  exampleImage:`/media/road-monitor/${examples[d.id].file}`,
  exampleSource:examples[d.id].source, sample:examples[d.id].sample,
}))
export function cameraMonitorLocation(id) {
  if(!demoCameras.some(c=>c.id===id))return null
  return {path:'/monitor',query:{source:'demo',cameraId:id,layout:'1'}}
}
export const demoDeviceTree = [{title:'乐西高速 · 静态演示摄像头',key:'DEMO-LEXI-CAMERAS',children:
  demoCameras.map(c=>({title:c.name,key:c.id,isLeaf:true,presentationAsset:true}))}]
