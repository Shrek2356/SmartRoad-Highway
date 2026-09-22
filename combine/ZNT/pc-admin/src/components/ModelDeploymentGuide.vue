<template>
  <section class="deployment-guide">
    <header class="guide-heading">
      <div><span class="eyebrow">NEW DEVICE / 模型部署</span><h2>从打开软件，到完成第一次真实检测。</h2><p>先选目标，再补齐所需组件。检查、安装、启动与推理验收是不同步骤。</p></div>
      <a-button :loading="loading" @click="loadGuide">刷新部署清单</a-button>
    </header>
    <a-alert v-if="loadError" type="error" show-icon :message="loadError" description="请确认检测桥在线且包含 requirements 目录。离线文字说明位于 requirements/DEPLOYMENT_GUIDE.md。" />
    <div class="mode-grid">
      <button v-for="item in DEPLOYMENT_MODES" :key="item.id" :class="{ selected: mode === item.id }" :aria-pressed="mode === item.id" @click="mode = item.id">
        <strong>{{ item.title }}</strong><span>{{ item.description }}</span>
      </button>
    </div>
    <p class="muted">这里选择的是部署检查目标，不会修改检测模式、启动模型或调用云端 API。</p>
    <template v-if="mode === 'demo'">
      <a-alert type="success" show-icon message="演示不需要安装大模型环境" description="完整解压后打开 EXE。软件使用随包 Python 和已构建前端；不要为了展示重新安装 Node 或 CUDA。Windows 10/11 x64 需 WebView2。" />
      <a-space wrap class="guide-actions"><router-link to="/realtime-detect"><a-button type="primary">上传图像进行演示联调</a-button></router-link><a v-if="safeSource(links.webview2)" :href="safeSource(links.webview2)" target="_blank" rel="noopener noreferrer">WebView2 官方说明</a></a-space>
    </template>
    <template v-else>
      <a-steps :current="step" size="small" class="guide-steps" @change="value => step = value" :items="steps" />
      <article class="step-panel" v-if="step === 0">
        <h3>01 · 为真实检测准备独立环境</h3>
        <p>新建环境建议 Python 3.12 x64。当前官方 SAM3 要求 3.12+；旧的 3.10 是历史适配环境，不能直接当成新机安装方案。</p>
        <p>{{ mode === 'offline' ? '本地 8B 检测建议 32 GB 内存、16 GB 以上 NVIDIA 显存；12 GB 仅属于需实测的尝试条件。' : '云端只替代视觉大模型，本机仍需能运行 SAM3 的 NVIDIA GPU 和 CUDA PyTorch。' }} 多模型同时运行可能显存不足，检查通过不保证速度或并发能力。</p>
        <a-space wrap><a v-if="safeSource(links.python)" :href="safeSource(links.python)" target="_blank" rel="noopener noreferrer">下载 Python（官方）</a><a v-if="safeSource(links.pytorch)" :href="safeSource(links.pytorch)" target="_blank" rel="noopener noreferrer">选择 PyTorch / CUDA（官方）</a></a-space>
        <ol><li>已有兼容环境可直接使用；没有时，安装 Python 3.12 后在 PowerShell 创建独立环境。</li><li>先为该环境安装相互匹配的 CUDA PyTorch 与 torchvision，不对随包 Demo Python 安装 GPU 依赖。</li><li>安装平台完整依赖；SAM3 代码取得后还需单独安装（下一步）。</li></ol>
        <template v-if="guide.app_root"><label>创建环境（已有环境跳过）</label><pre>{{ commands.create }}</pre><label>安装平台依赖（先完成 CUDA PyTorch 安装）</label><pre>{{ commands.dependencies }}</pre></template>
        <p class="muted">以上命令需自行执行，本页不会自动安装。PyTorch 网站命令中的 pip 应替换成目标环境的 python.exe -m pip。</p>
      </article>
      <article class="step-panel" v-else-if="step === 1">
        <h3>02 · 取得模型与配套组件</h3><p>建议放在下列包内目录。道路初筛模型暂缓训练和接入；当前无需旧领域检测权重。</p>
        <div class="model-grid"><section v-for="item in items" :key="item.key" class="model-item">
          <div class="model-heading"><strong>{{ item.label }}</strong><a-tag :color="item.required ? 'blue' : 'default'">{{ item.required ? '此模式必需' : '可选 · 默认关闭' }}</a-tag></div>
          <code>{{ item.relative_path }}</code><p>{{ item.note }}</p>
          <a-tag v-if="item.check" :color="item.check.exists ? 'green' : item.required ? 'orange' : 'default'">{{ item.check.exists ? '文件/目录存在 · 尚非推理验收' : '尚未找到' }}</a-tag>
          <a v-if="safeSource(item.download_url)" :href="safeSource(item.download_url)" target="_blank" rel="noopener noreferrer">打开组件来源 ↗</a><span v-else class="muted">项目下载地址待补充；可直接选择已有文件。</span>
        </section></div>
        <template v-if="guide.app_root"><p>取得 SAM3 代码后，使用与检测桥一致的 Python 安装。源码在其他位置时替换末尾目录：</p><pre>{{ commands.sam3 }}</pre></template>
        <a-alert type="info" show-icon message="文件存在 ≠ 配对正确 ≠ 已经可以推理" description="Qwen 的 GGUF 与 mmproj 必须配套；llama.cpp 解压后保留发行包 DLL；SAM3 保留所需代码与 sam3.pt，不自动替换新版权重。" />
      </article>
      <article class="step-panel" v-else-if="step === 2">
        <h3>03 · 让软件使用正确的 Python 和模型</h3>
        <ol><li>到“系统设置 → 桌面与连接”选择刚准备好的 python.exe，保存并关闭、重开软件。</li><li>到“模型部件与运行时”自动查找包内组件，找不到的使用“浏览…”手动选择。</li><li>选择 Qwen 推理引擎 llama-server.exe，无需修改系统 PATH。云端模式不要求本地 Qwen。</li><li>校验并保存，再“更新初始化配置”；之后不需要每次登录重新填写。</li></ol>
        <a-space wrap><router-link to="/system-settings?tab=desktop"><a-button>选择检测 Python</a-button></router-link><router-link to="/model-config?tab=runtime"><a-button type="primary">选择模型与组件路径</a-button></router-link></a-space>
        <p class="muted">包内模型路径会按相对位置保存；外部模型仍需随设备重新配置。自动查找不扫描整块磁盘，也不会自动下载模型。</p>
      </article>
      <article class="step-panel" v-else-if="step === 3">
        <h3>04 · 检查环境，然后手动启动服务</h3>
        <p>点击下方“检查当前模式环境”。结果显示实际运行检测桥的 Python；若与保存设置不同，先重启，避免向错误环境安装依赖。</p>
        <p v-if="mode === 'offline'">检查缺项修复后，在模型运行时页激活所需组件，点击“启动 Qwen”，等待“测试连接”成功。SAM3 与可选 CLIP 在任务到来时加载，不需要单独启动服务。</p>
        <p v-else>在实时检测选择云端模式，填写兼容的多模态 API 地址、模型名和密钥并测试连接。环境检查不会验证密钥权限，也不会消费云端调用额度。</p>
        <a-space wrap><router-link to="/model-config?tab=runtime"><a-button>打开模型激活与服务</a-button></router-link><router-link v-if="mode === 'cloud'" to="/realtime-detect?profile=standard"><a-button type="primary">填写并测试云端 API</a-button></router-link></a-space>
      </article>
      <article class="step-panel" v-else>
        <h3>05 · 用真实图片验收，不用预置案例代替</h3>
        <ol><li>在实时检测明确选择{{ mode === 'offline' ? '本地离线' : '云端' }}，提交一张新图片，确认产生新的任务记录。</li><li>核对风险描述、证据、疑问说明及可用的框/掩码。无掩码不等于没有发现风险。</li><li>抽取道路样本进行真实回归，记录模型、环境和结果；不把已有展示报告当作新设备推理结果。</li><li>需要实时视频时，先评估抽帧周期、重复事件合并和延迟；道路专用初筛后续单独接入。</li></ol>
        <router-link :to="mode === 'offline' ? '/realtime-detect?profile=offline' : '/realtime-detect?profile=standard'"><a-button type="primary">提交第一张真实检测图片</a-button></router-link>
      </article>
      <a-space class="guide-actions"><a-button :disabled="step === 0" @click="step--">上一步</a-button><a-button :disabled="step === 4" @click="step++">下一步</a-button></a-space>
    </template>
    <section class="check-panel">
      <div class="guide-heading"><div><h3>当前设备检查</h3><p>只检查已保存的配置。无需打开终端；耗时较长时最多等待 90 秒。</p></div><a-button type="primary" :loading="checking" :disabled="loading || !guide.manifest" @click="runCheck">检查当前模式环境</a-button></div>
      <a-alert :type="summary.type" show-icon :message="summary.title" :description="summary.detail" />
      <template v-if="report?.system"><dl><dt>实际检测 Python</dt><dd>{{ report.system.python_executable }}</dd><dt>桌面选定 Python</dt><dd>{{ report.system.desktop_python || '未设置' }}</dd><dt>显卡</dt><dd>{{ report.system.gpu?.devices?.map(d => `${d.name} / ${(d.vram_mb / 1024).toFixed(1)} GB`).join('；') || '未检测到 NVIDIA GPU（Demo 不要求）' }}</dd><dt>检查时间</dt><dd>{{ report.generated_at }}</dd></dl></template>
      <ul v-if="report?.issues?.length" class="issue-list"><li v-for="(issue,index) in report.issues" :key="index"><a-tag :color="issue.level === 'error' ? 'red' : 'orange'">{{ issue.level === 'error' ? '需处理' : '提醒' }}</a-tag>{{ issue.message }}</li></ul>
      <a-collapse v-if="Object.keys(report?.system?.dependencies?.failures || {}).length" ghost><a-collapse-panel key="imports" header="展开依赖导入错误（供部署人员排查）"><p v-for="(detail,name) in report.system.dependencies.failures" :key="name" class="muted">{{ name }}：{{ detail }}</p></a-collapse-panel></a-collapse>
      <p v-if="report" class="muted">报告只对应上面的模式和检查时间；修改路径、环境或开关后请重新检查。云端连接和实际推理需单独验收。</p>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { fetchDeploymentGuide, checkDeploymentEnvironment } from '@/api/detect'
import { DEPLOYMENT_MODES, modelItems, safeSource, reportSummary, installCommands } from '@/utils/deploymentGuide'
const mode = ref('demo'), step = ref(0), loading = ref(false), checking = ref(false)
const guide = ref({}), report = ref(null), loadError = ref('')
let revision = 0, disposed = false
const steps = ['准备环境', '取得组件', '配置路径', '检查与启动', '图片验收'].map(title => ({title}))
const links = computed(() => guide.value.manifest?.links || {})
const items = computed(() => modelItems(guide.value.manifest, mode.value, report.value?.models))
const summary = computed(() => reportSummary(report.value))
const commands = computed(() => installCommands(guide.value.app_root, guide.value.python_executable))
watch(mode, () => { revision++; report.value = null; step.value = 0 })
async function loadGuide() {
  loading.value = true; loadError.value = ''; report.value = null; revision++
  try { const result = await fetchDeploymentGuide(); if (!disposed) guide.value = result }
  catch (error) { if (!disposed) loadError.value = error?.response?.data?.detail || '部署清单未加载，请检查检测桥连接后重试。' }
  finally { if (!disposed) loading.value = false }
}
async function runCheck() {
  if (checking.value) return
  const ticket = ++revision, selectedMode = mode.value
  checking.value = true; report.value = null
  try { const result = await checkDeploymentEnvironment(selectedMode); if (!disposed && ticket === revision) report.value = result }
  catch (error) { if (!disposed && ticket === revision) report.value = {error: error?.response?.data?.detail || '环境检查未完成，请确认检测桥连接后重试。'} }
  finally { if (!disposed) checking.value = false }
}
onMounted(loadGuide)
onBeforeUnmount(() => { disposed = true; revision++ })
</script>

<style scoped>
.deployment-guide{max-width:1400px}.guide-heading{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:18px}.guide-heading h2{font-size:24px;margin:9px 0}.guide-heading p,.step-panel p,.step-panel li{line-height:1.9;color:var(--text-secondary)}.eyebrow{font-size:11px;letter-spacing:1.5px;color:var(--primary)}.mode-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.mode-grid button{padding:22px;text-align:left;background:var(--surface);color:var(--text-primary);border:1px solid var(--border-color);border-radius:14px;cursor:pointer}.mode-grid button.selected{border-color:var(--primary);box-shadow:inset 0 0 0 1px var(--primary);background:var(--surface-muted)}.mode-grid strong{display:block;font-size:17px;margin-bottom:10px}.mode-grid span{font-size:13px;line-height:1.9;color:var(--text-secondary)}.muted{color:var(--text-secondary);font-size:12px;line-height:1.9}.guide-steps{margin:28px 0}.step-panel,.check-panel{padding:24px;border:1px solid var(--border-color);border-radius:14px;background:var(--surface)}.step-panel h3,.check-panel h3{font-size:19px;color:var(--text-primary)}.guide-actions{margin:18px 0}.model-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-bottom:20px}.model-item{padding:18px;border:1px solid var(--border-color);border-radius:12px;background:var(--surface-muted)}.model-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}.model-item p{font-size:13px}.model-item code{display:block;font-size:12px;overflow-wrap:anywhere;margin-top:14px}.model-item a{display:inline-block;font-size:13px;margin-top:10px}.step-panel pre{padding:16px;background:var(--surface-muted);border-radius:10px;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--text-primary);font-size:12px}.check-panel{margin-top:24px}dl{display:grid;grid-template-columns:135px 1fr;gap:10px;font-size:13px;margin:20px 0}dt{color:var(--text-secondary)}dd{margin:0;overflow-wrap:anywhere}.issue-list{list-style:none;padding:0}.issue-list li{padding:12px 0;border-bottom:1px solid var(--border-color);line-height:1.9;overflow-wrap:anywhere}
@media(max-width:850px){.mode-grid,.model-grid{grid-template-columns:1fr}.guide-heading{align-items:flex-start;flex-direction:column}.step-panel,.check-panel{padding:18px}dl{grid-template-columns:1fr}}
</style>
