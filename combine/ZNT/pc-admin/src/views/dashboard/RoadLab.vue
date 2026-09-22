<template>
  <main class="road-lab">
    <header><p class="eyebrow">SMARTROAD LAB · 实验室小试</p><h1>路安智巡</h1>
      <p>道路画面接入、风险分析与证据复核</p></header>
    <a-alert show-icon type="info" message="已开展 CRASAR 小样例诊断，尚未完成正式评测"
      description="已使用真实视觉模型与 SAM3 检查公开数据样例，仍存在漏检和定位不稳定。默认模拟档仅用于软件联调。" />
    <section class="actions"><a-button type="primary" size="large" @click="$router.push('/realtime-detect')">导入图像与检测</a-button>
      <a-button size="large" @click="$router.push('/monitor')">摄像头接入</a-button>
      <a-button size="large" @click="$router.push('/detection-results')">查看结果与报告</a-button></section>
    <section class="cards"><a-card title="一阶段 · 摄像头初筛"><p>保留视频帧和外部候选输入接口。</p><a-tag color="orange">道路专用初筛模型待接入</a-tag><p>当前按帧送入分析，不使用工地人员模型筛掉道路画面。</p></a-card>
      <a-card title="二阶段 · 服务器分析"><p>道路风险目录、视觉分析、区域定位、证据核验与结果归档。</p><p>本地或云端真实模型需配置后使用；默认采用明确标注的模拟联调档。</p></a-card>
      <a-card title="复核与迭代"><p>保留人工复核与结果记录，逐步积累误报、漏报和定位问题。</p><a-tag>普通微信测试待接入</a-tag><p>现阶段在软件内查看报告，不自动发送外部消息。</p></a-card></section>
    <a-card title="本阶段检查范围"><p>可见路面破损、散落异物、落石、积水和道路缺口。类别目录用于开发验证，不表示所有类别已经通过测试。</p>
      <p>CRASAR 灾后航拍画面与高速固定摄像头视角不同；后续分别记录验证结果。</p></a-card>
  </main>
</template>
<style scoped>
.road-lab{max-width:1200px;margin:auto}.eyebrow{letter-spacing:2px;color:#1677ff}h1{font-size:36px;margin:6px 0}header{padding:8px 0 24px}.actions{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-bottom:20px}.cards p{line-height:1.9}@media(max-width:900px){.cards{grid-template-columns:1fr}}
</style>
