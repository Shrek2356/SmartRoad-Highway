<template>
  <!--
    ⑤ 模型规则配置页
    业务：阈值 / 知识库 / 推送规则 / 训练进度
    阈值保存到业务后端配置，并由检测流水线在新任务中读取。
  -->
  <div class="page-card">
    <div class="page-title">模型规则配置</div>

    <a-tabs v-model:activeKey="tab">
      <a-tab-pane key="deployment" tab="新设备部署"><ModelDeploymentGuide /></a-tab-pane>
      <!-- 检测阈值 -->
      <a-tab-pane key="threshold" tab="检测阈值配置">
        <a-table :columns="thCols" :data-source="thresholds" row-key="key" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'value'">
              <div class="threshold-control">
              <a-slider
                v-model:value="record.value"
                :min="0.5"
                :max="0.99"
                :step="0.01"
                style="flex: 1; min-width: 100px"
                :disabled="thresholdSaving[record.key]"
                @afterChange="(v) => onThreshold(record.key, v)"
              />
              <span>{{ record.value }}</span>
              </div>
            </template>
            <template v-else-if="column.key === 'source'">
              <a-tag :color="record.approved ? 'green' : 'blue'">
                {{ record.source === 'manual_override' ? '人工配置覆盖' : record.approved ? '复盘批准覆盖' : '风险算子默认' }}
              </a-tag>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- 安全知识库 -->
      <a-tab-pane key="kb" tab="安全知识库管理">
        <a-alert type="info" show-icon style="margin-bottom: 14px" message="导入 md、txt、pdf 或 docx 行业规范，系统会自动解析、按条款切块并建立本地检索索引。" />
        <a-space wrap style="margin-bottom: 14px">
          <a-upload :show-upload-list="false" :before-upload="beforeKnowledgeUpload" accept=".md,.txt,.pdf,.docx">
            <a-button type="primary" :loading="knowledgeLoading">导入规范文件</a-button>
          </a-upload>
          <a-input-search
            v-model:value="knowledgeQuery"
            placeholder="输入问题验证规范检索，如：道路损毁后由谁设置警示并修复"
            style="width: 420px"
            enter-button="检索验证"
            @search="searchKnowledge"
          />
          <a-tag color="blue">{{ knowledgeSummary.file_count || 0 }} 个文件</a-tag>
          <a-tag color="cyan">{{ knowledgeSummary.chunk_count || 0 }} 个条款块</a-tag>
        </a-space>
        <a-table :columns="kbCols" :data-source="knowledge" row-key="source_file" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'action'">
              <a-popconfirm title="确认删除该规范文件及其索引？" @confirm="delKb(record)">
                <a-button type="link" danger>删除</a-button>
              </a-popconfirm>
            </template>
          </template>
        </a-table>
        <a-list v-if="knowledgeHits.length" bordered class="knowledge-hits" :data-source="knowledgeHits">
          <template #header><strong>检索结果</strong></template>
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta :title="`${item.source_file} · ${item.section}`" :description="item.text" />
              <div><p>{{ item.version || '版本未登记' }} · {{ item.provenance_status === 'verified_checksum' ? '来源校验通过' : '来源待核验' }}</p><p>{{ item.applicability }}</p><a v-if="item.source_url?.startsWith('https://')" :href="item.source_url" target="_blank" rel="noopener noreferrer">查看官方原文</a><a-tag>文本相关度 {{ item.score }}</a-tag></div>
            </a-list-item>
          </template>
        </a-list>
      </a-tab-pane>

      <!-- 告警推送 -->
      <a-tab-pane key="push" tab="告警推送规则">
        <a-table :columns="pushCols" :data-source="pushRules" row-key="id" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'level'">
              <a-tag :color="levelColor(record.level)">{{ levelText(record.level) }}</a-tag>
            </template>
            <template v-else-if="column.key === 'channels'">
              <a-tag v-for="c in record.channels" :key="c">{{ c }}</a-tag>
            </template>
            <template v-else-if="column.key === 'action'">
              <a-button type="link" @click="editPush(record)">编辑</a-button>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="runtime" tab="模型部件与运行时">
        <a-alert
          type="info"
          show-icon
          style="margin-bottom: 16px"
          message="路径由检测桥后端校验，保存后仅影响新任务；浏览器不会也不能直接读取任意本机绝对路径。"
        />
        <a-spin :spinning="runtimeLoading">
          <a-form layout="vertical" class="runtime-form">
            <a-card size="small" class="service-card" title="模型组件激活控制台">
              <div class="component-grid">
                <div v-for="component in modelComponents" :key="component.key" class="component-item">
                  <div>
                    <strong>{{ component.name }}</strong>
                    <p>{{ component.description }}</p>
                  </div>
                  <div class="component-actions">
                    <a-tag :color="componentStatus(component).color">
                      {{ componentStatus(component).text }}
                    </a-tag>
                    <a-switch
                      v-model:checked="runtimeForm[component.key]"
                      :checked-children="'已激活'"
                      :un-checked-children="'未激活'"
                      @change="() => activateComponent(component)"
                    />
                  </div>
                </div>
              </div>
              <p class="tip">道路初筛模型暂未启用。SAM3、CLIP 采用任务级懒加载；激活不会立即占用显存，下一个检测任务才加载。Qwen 需在下方单独启动推理服务。</p>
            </a-card>
            <a-card size="small" class="service-card" title="本地 Qwen 推理服务">
              <a-space wrap>
                <a-badge
                  :status="qwenStatus.reachable ? 'success' : qwenStatus.running ? 'processing' : 'default'"
                  :text="qwenStatus.detail || '状态未知'"
                />
                <a-tag v-if="qwenStatus.pid">PID {{ qwenStatus.pid }}</a-tag>
                <a-button @click="refreshQwenStatus">测试连接</a-button>
                <a-button type="primary" :disabled="qwenStatus.running || qwenStatus.reachable" @click="startQwen">
                  启动 Qwen
                </a-button>
                <a-button danger :disabled="!qwenStatus.managed" @click="stopQwen">停止 Qwen</a-button>
              </a-space>
              <div class="autostart-row">
                <a-switch v-model:checked="runtimeForm.qwen_autostart" @change="() => activateComponent({ key: 'qwen_autostart', name: 'Qwen随平台启动' })" />
                <span>随平台自动启动 Qwen（双击 start-platform 后由检测桥启动，无需进入前端再点击）</span>
              </div>
              <p class="tip">只停止由本平台启动的进程；模型加载期间接口可能暂时显示不可访问。</p>
            </a-card>
            <a-row :gutter="16">
              <a-col v-for="field in runtimeFields" :key="field.key" :xs="24" :xl="12">
                <a-form-item :label="field.label">
                  <a-input-group compact class="path-input">
                    <a-input v-model:value="runtimeForm[field.key]" :placeholder="field.placeholder">
                    <template #suffix>
                      <a-tag :color="runtimeValidation[field.key]?.ok ? 'green' : 'red'">
                        {{ runtimeValidation[field.key]?.ok ? '可用' : '未找到' }}
                      </a-tag>
                    </template>
                    </a-input>
                    <a-button v-if="field.browsable !== false" @click="browseRuntimePath(field)">浏览…</a-button>
                  </a-input-group>
                </a-form-item>
              </a-col>
            </a-row>
            <a-space>
              <a-button @click="loadRuntime">刷新</a-button>
              <a-button @click="autoDiscoverRuntime">自动查找模型部件</a-button>
              <a-button type="primary" @click="saveRuntime">校验并保存</a-button>
              <a-popconfirm
                title="将当前路径和组件开关保存为新的初始化配置？"
                ok-text="更新"
                cancel-text="取消"
                @confirm="updateInitialRuntime"
              >
                <a-button>更新初始化配置</a-button>
              </a-popconfirm>
              <a-popconfirm
                title="使用初始化配置覆盖当前编辑内容？"
                ok-text="恢复"
                cancel-text="取消"
                @confirm="restoreInitialRuntime"
              >
                <a-button>恢复初始化配置</a-button>
              </a-popconfirm>
            </a-space>
            <p class="tip">
              配置持久保存在后端，不会因退出或重新登录丢失。初始化配置用于首次运行、换机调整或一键恢复。
            </p>
          </a-form>
        </a-spin>
      </a-tab-pane>

      <!-- 训练进度 -->
      <a-tab-pane key="train" tab="模型训练进度">
        <a-card>
          <h3>{{ train.modelName }}</h3>
          <p>状态：{{ train.status === 'training' ? '训练中' : train.status }} · Epoch {{ train.epoch }} · ETA {{ train.eta }}</p>
          <a-progress :percent="train.progress" :status="train.status === 'training' ? 'active' : 'normal'" />
          <a-alert
            type="info"
            show-icon
            message="当前没有平台内训练任务；这不是模型未接入"
            description="本版本采用本地Qwen开放识别、RiskSpec编译和SAM3零样本定位。YOLO训练在独立训练工程完成，平台负责加载权重、评测和在线配置。"
            style="margin: 16px 0"
          />
          <a-descriptions title="当前模型迭代方式" bordered :column="2" size="small">
            <a-descriptions-item label="YOLO26">独立训练工程更新权重</a-descriptions-item>
            <a-descriptions-item label="Qwen3-VL">提示词、结构化输出与模型替换</a-descriptions-item>
            <a-descriptions-item label="SAM3">零样本提示与空间核验规则</a-descriptions-item>
            <a-descriptions-item label="CLIP">可选语义一致性模块</a-descriptions-item>
            <a-descriptions-item label="复盘学习Agent">阈值、规则、案例和知识库更新</a-descriptions-item>
            <a-descriptions-item label="完整回归">八张示例 + 58张异常 + 40张控制候选</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-tab-pane>
    </a-tabs>
    <a-modal v-model:open="pushEditorOpen" title="编辑告警推送规则" @ok="savePushRule">
      <a-form layout="vertical">
        <a-form-item label="风险等级"><a-input :value="levelText(pushEditor.level)" disabled /></a-form-item>
        <a-form-item label="推送对象">
          <a-select v-model:value="pushEditor.channels" mode="tags" placeholder="输入对象后回车，如 道路值班员">
            <a-select-option value="道路值班员">道路值班员</a-select-option>
            <a-select-option value="项目经理">项目经理</a-select-option>
            <a-select-option value="公司安全部">公司安全部</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import ModelDeploymentGuide from '@/components/ModelDeploymentGuide.vue'
import { useRouteTab } from '@/composables/useRouteTab'
import { message } from 'ant-design-vue'
import { fetchModelConfig, updatePushRule, updateThreshold } from '@/api/modelConfig'
import {
  discoverRuntimeSettings,
  deleteKnowledgeDocument,
  fetchKnowledgeBase,
  fetchRuntimeSettings,
  fetchQwenServiceStatus,
  pickRuntimePath,
  resetRuntimeSettingsToInitial,
  saveRuntimeSettings,
  saveInitialRuntimeSettings,
  searchKnowledgeBase,
  startQwenService,
  stopQwenService,
  uploadKnowledgeDocument,
} from '@/api/detect'

const tab = useRouteTab(['deployment','threshold','kb','push','runtime','train'], 'deployment')
const thresholds = ref([])
const knowledge = ref([])
const knowledgeSummary = ref({})
const knowledgeLoading = ref(false)
const knowledgeQuery = ref('')
const knowledgeHits = ref([])
const pushRules = ref([])
const pushEditorOpen = ref(false)
const pushEditor = ref({ id: '', level: '', channels: [] })
const train = ref({})
const runtimeLoading = ref(false)
const runtimeForm = ref({ qwen_enabled: true, yolo_enabled: false, sam3_enabled: true, clip_enabled: false })
const runtimeValidation = ref({})
const initialRuntime = ref({})
const qwenStatus = ref({ running: false, reachable: false, managed: false, detail: '状态未知' })
const runtimeFields = [
  { key: 'llama_server_path', label: 'Qwen 推理引擎 llama-server.exe', placeholder: '可执行文件路径；留空时从 PATH 查找' },
  { key: 'qwen_model_path', label: '本地 Qwen GGUF', placeholder: 'Qwen3-VL 模型文件路径' },
  { key: 'qwen_mmproj_path', label: 'Qwen 视觉投影 mmproj', placeholder: 'mmproj GGUF 文件路径' },
  { key: 'qwen_base_url', label: '本地 Qwen 推理地址', placeholder: 'http://127.0.0.1:8080/v1/chat/completions', browsable: false },
  { key: 'sam3_repo_path', label: 'SAM3 代码目录', placeholder: 'sam3-main 目录' },
  { key: 'sam3_checkpoint_path', label: 'SAM3 权重', placeholder: 'sam3.pt 文件路径' },
  { key: 'clip_checkpoint_path', label: 'CLIP 权重', placeholder: 'ViT-L-14.pt 文件路径' },
]
const modelComponents = [
  { key: 'qwen_enabled', validation: 'qwen_runtime', name: 'Qwen3-VL', description: '异常语义识别与结构化 RiskSpec' },
  { key: 'sam3_enabled', validation: 'sam3_runtime', name: 'SAM3', description: '风险实体定位、边界框与像素掩码' },
  { key: 'clip_enabled', validation: 'clip_runtime', name: 'CLIP', description: '可选语义一致性辅助，当前设备建议关闭' },
]

const thCols = [
  { title: '检测项', dataIndex: 'label', key: 'label' },
  { title: '阈值', key: 'value', width: 260 },
  { title: '配置来源', key: 'source', width: 150 },
  { title: '说明', dataIndex: 'desc', key: 'desc' },
]
const kbCols = [
  { title: '规范文件', dataIndex: 'source_file', key: 'source_file' },
  { title: '版本', dataIndex: 'version', key: 'version' },
  { title: '来源校验', dataIndex: 'provenance_status', key: 'provenance_status' },
  { title: '条款块数', dataIndex: 'chunk_count', key: 'chunk_count', width: 120 },
  { title: '文件大小(B)', dataIndex: 'size_bytes', key: 'size_bytes', width: 140 },
  { title: '操作', key: 'action', width: 100 },
]
const pushCols = [
  { title: '风险等级', key: 'level', width: 120 },
  { title: '推送通道', key: 'channels' },
  { title: '延迟(分钟)', dataIndex: 'delayMin', key: 'delayMin', width: 120 },
  { title: '操作', key: 'action', width: 100 },
]

function levelColor(l) {
  return { critical: 'red', major: 'orange', general: 'gold', red: 'red', orange: 'orange', yellow: 'gold' }[l]
}
function levelText(l) {
  return { critical: '高危', major: '中危', general: '一般', red: '高危', orange: '中危', yellow: '低危' }[l] || l
}

function componentStatus(component) {
  if (!runtimeForm.value[component.key]) return { color: 'default', text: '已停用' }
  if (!component.validation) return { color: 'success', text: '已开启' }
  const validation = runtimeValidation.value[component.validation]
  if (!validation) return { color: 'processing', text: '待校验' }
  if (!validation.ok) return { color: 'error', text: '配置不完整' }
  if (component.key === 'qwen_enabled' && qwenStatus.value.reachable) {
    return { color: 'success', text: '运行中' }
  }
  if (component.key === 'qwen_enabled') return { color: 'blue', text: '已激活·待启动' }
  return { color: 'success', text: '已激活·按需加载' }
}

async function activateComponent(component) {
  try {
    if (component.key === 'qwen_enabled' && !runtimeForm.value.qwen_enabled && qwenStatus.value.managed) {
      qwenStatus.value = await stopQwenService()
    }
    const res = await saveRuntimeSettings(runtimeForm.value)
    runtimeForm.value = { ...res.settings }
    initialRuntime.value = { ...(res.initial_settings || {}) }
    runtimeValidation.value = res.validation || {}
    const status = componentStatus(component)
    if (component.validation && runtimeForm.value[component.key] && !runtimeValidation.value[component.validation]?.ok) {
      message.warning(`${component.name} 已选择，但模型路径尚未配置完整`)
    } else {
      message.success(`${component.name} ${status.text}`)
    }
  } catch (error) {
    runtimeForm.value[component.key] = !runtimeForm.value[component.key]
    message.error(error?.response?.data?.detail || `${component.name} 状态更新失败`)
  }
}

const thresholdSaving = ref({})
const savedThresholds = new Map()
async function onThreshold(key, value) {
  if (thresholdSaving.value[key]) return
  thresholdSaving.value[key] = true
  const row = thresholds.value.find(item => item.key === key)
  try {
    const response = await updateThreshold({ key, value })
    const accepted = response.data.value ?? value
    savedThresholds.set(key, accepted)
    if (row) Object.assign(row, { value: accepted, approved: true, source: 'manual_override' })
    message.success('阈值已保存，将用于新检测任务')
  } catch (error) {
    if (row) row.value = savedThresholds.get(key) ?? row.value
    message.error(error?.response?.data?.detail || '保存失败，已恢复上次保存的阈值')
  } finally { thresholdSaving.value[key] = false }
}

async function loadKnowledge() {
  try {
    const res = await fetchKnowledgeBase()
    knowledgeSummary.value = res
    knowledge.value = res.documents || []
  } catch {
    knowledge.value = []
  }
}

async function beforeKnowledgeUpload(file) {
  knowledgeLoading.value = true
  try {
    const res = await uploadKnowledgeDocument(file)
    message.success(`${res.filename} 已导入，生成 ${res.document_chunk_count ?? res.chunk_count} 个条款块`)
    await loadKnowledge()
  } catch (error) {
    message.error(error?.response?.data?.detail || '规范导入失败')
  } finally {
    knowledgeLoading.value = false
  }
  return false
}

async function delKb(record) {
  try {
    await deleteKnowledgeDocument(record.source_file)
    message.success('规范文件及其索引已删除')
    await loadKnowledge()
  } catch (error) {
    message.error(error?.response?.data?.detail || '删除失败')
  }
}

async function searchKnowledge() {
  if (!knowledgeQuery.value.trim()) return
  try {
    const res = await searchKnowledgeBase(knowledgeQuery.value)
    knowledgeHits.value = res.hits || []
    if (!knowledgeHits.value.length) message.warning('未检索到相关条款，请检查文档解析结果或换一个问题')
  } catch (error) {
    message.error(error?.response?.data?.detail || '知识库检索失败')
  }
}

function editPush(record) {
  pushEditor.value = { ...record, channels: [...(record.channels || [])] }
  pushEditorOpen.value = true
}

async function savePushRule() {
  await updatePushRule(pushEditor.value)
  const index = pushRules.value.findIndex((item) => item.id === pushEditor.value.id)
  if (index >= 0) pushRules.value[index] = { ...pushEditor.value }
  pushEditorOpen.value = false
  message.success('推送规则已持久保存')
}

async function load() {
  const res = await fetchModelConfig()
  thresholds.value = res.data.thresholds.map((t) => ({ ...t }))
  for (const item of thresholds.value) savedThresholds.set(item.key, item.value)
  pushRules.value = res.data.pushRules
  train.value = res.data.trainProgress
}

async function loadRuntime() {
  runtimeLoading.value = true
  try {
    const res = await fetchRuntimeSettings()
    runtimeForm.value = { ...res.settings }
    runtimeValidation.value = res.validation || {}
  } catch {
    message.warning('检测桥未启动，模型路径设置暂不可用；业务数据仍可查看')
  } finally {
    runtimeLoading.value = false
  }
}

async function autoDiscoverRuntime() {
  runtimeLoading.value = true
  try {
    const res = await discoverRuntimeSettings(runtimeForm.value)
    runtimeForm.value = { ...res.settings }
    runtimeValidation.value = res.validation || {}
    message.success('已完成后端路径发现，请确认后保存')
  } catch {
    message.error('自动查找失败，请确认检测桥已启动')
  } finally {
    runtimeLoading.value = false
  }
}

async function saveRuntime() {
  runtimeLoading.value = true
  try {
    const res = await saveRuntimeSettings(runtimeForm.value)
    runtimeForm.value = { ...res.settings }
    runtimeValidation.value = res.validation || {}
    const missing = Object.entries(runtimeValidation.value)
      .filter(([key, value]) => !key.endsWith('_runtime') && !value.ok)
      .map(([key]) => runtimeFields.find((item) => item.key === key)?.label || key)
    if (missing.length) message.warning(`设置已保存，但这些部件未通过校验：${missing.join('、')}`)
    else message.success('模型部件路径与运行时开关已保存')
  } catch {
    message.error('保存失败，请确认检测桥已启动')
  } finally {
    runtimeLoading.value = false
  }
}

async function updateInitialRuntime() {
  runtimeLoading.value = true
  try {
    const saved = await saveRuntimeSettings(runtimeForm.value)
    runtimeForm.value = { ...saved.settings }
    runtimeValidation.value = saved.validation || {}
    const res = await saveInitialRuntimeSettings(runtimeForm.value)
    initialRuntime.value = { ...res.initial_settings }
    message.success('当前配置已保存，并更新为新的初始化配置')
  } catch (error) {
    message.error(error?.response?.data?.detail || '初始化配置更新失败')
  } finally {
    runtimeLoading.value = false
  }
}

async function restoreInitialRuntime() {
  runtimeLoading.value = true
  try {
    const res = await resetRuntimeSettingsToInitial()
    runtimeForm.value = { ...res.settings }
    runtimeValidation.value = res.validation || {}
    message.success('已恢复初始化配置')
  } catch (error) {
    message.error(error?.response?.data?.detail || '恢复初始化配置失败')
  } finally {
    runtimeLoading.value = false
  }
}

async function browseRuntimePath(field) {
  message.info('已请求本机文件选择窗口，请在桌面窗口中选择模型部件')
  try {
    const res = await pickRuntimePath(field.key, runtimeForm.value[field.key] || '')
    if (res.selected) runtimeForm.value[field.key] = res.path
  } catch {
    message.error('无法打开本地路径选择器，请确认检测桥运行在本机桌面环境')
  }
}

async function refreshQwenStatus(showMessage = true) {
  try {
    qwenStatus.value = await fetchQwenServiceStatus()
    if (showMessage) message.success(qwenStatus.value.detail || '连接测试完成')
  } catch {
    qwenStatus.value = { running: false, reachable: false, managed: false, detail: '检测桥未连接' }
    if (showMessage) message.error('检测桥未启动，无法检查 Qwen')
  }
}

async function startQwen() {
  runtimeLoading.value = true
  try {
    if (!runtimeForm.value.qwen_enabled) {
      runtimeForm.value.qwen_enabled = true
    }
    await saveRuntimeSettings(runtimeForm.value)
    qwenStatus.value = await startQwenService()
    message.success('Qwen 启动命令已提交，首次加载模型需要等待')
  } catch (error) {
    message.error(error?.response?.data?.detail || 'Qwen 启动失败')
  } finally {
    runtimeLoading.value = false
  }
}

async function stopQwen() {
  runtimeLoading.value = true
  try {
    qwenStatus.value = await stopQwenService()
    message.success(qwenStatus.value.detail || 'Qwen 已停止')
  } catch {
    message.error('停止失败；平台不会终止非本平台启动的进程')
  } finally {
    runtimeLoading.value = false
  }
}

onMounted(() => {
  load()
  loadKnowledge()
  loadRuntime()
  refreshQwenStatus(false)
})
</script>

<style scoped>
.threshold-control { display:flex; align-items:center; gap:16px; min-width:180px; }
.threshold-control > span { min-width:32px; font-variant-numeric:tabular-nums; }
.tip { color: var(--text-secondary); font-size: 12px; margin-top: 12px; }
.runtime-form { max-width: 1320px; }
.switch-tip { margin-left: 12px; color: var(--text-secondary); }
.service-card { margin-bottom: 18px; }
.path-input { display: flex; }
.path-input :deep(.ant-input-affix-wrapper) { flex: 1; width: auto; }
.component-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.component-item { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 14px 16px; border: 1px solid var(--border-color); border-radius: 8px; background: var(--surface-muted); }
.component-item p { margin: 5px 0 0; color: var(--text-secondary); font-size: 12px; }
.component-actions { display: flex; align-items: center; gap: 10px; flex: none; }
.autostart-row { display: flex; align-items: center; gap: 10px; margin-top: 14px; color: var(--text-secondary); }
.knowledge-hits { margin-top: 16px; }
@media (max-width: 800px) {
  .component-grid { grid-template-columns: 1fr; }
  .component-item { align-items: flex-start; }
}
</style>
