export function healthCards(health) {
  const checking = health.updatedAt == null
  const d = health.detect || {}
  const offline = d.profiles?.find(p => p.id === 'offline')
  const cloud = d.profiles?.find(p => p.id === 'standard')
  return [
    { id:'business', title:'业务后台', state:checking ? 'checking' : health.business ? 'ready' : 'error', label:checking ? '待检查' : health.business ? '已连接' : '未连接', description:'账号、项目、工单与复盘数据的服务。', advice:'未连接时，确认桌面后台已启动，并核对业务接口地址。', target:'/system-settings?tab=desktop' },
    { id:'bridge', title:'检测桥', state:checking ? 'checking' : d.online ? 'ready' : 'error', label:checking ? '待检查' : d.online ? '已连接' : '未连接', description:'负责提交检测任务、传递模型输出和返回证据。', advice:'先恢复检测桥连接，再配置模型；它不是 Qwen 模型本身。', target:'/system-settings?tab=desktop' },
    { id:'offline', title:'本地视觉模型', state:!d.online ? 'checking' : offline?.runtime_ready ? 'ready' : 'attention', label:!d.online ? '暂无法检查' : offline?.runtime_ready ? '配置与服务就绪' : offline?.ready ? '配置齐备 · 服务待就绪' : '待配置', description:'Qwen 进行语义判断与报告；SAM3 等按任务加载。', advice:'选择模型路径并校验，启动 Qwen 后等待连接成功。就绪不等于已通过图片实测。', target:'/model-config?tab=runtime' },
    { id:'cloud', title:'云端视觉模型', state:!d.online ? 'checking' : cloud?.ready ? 'ready' : 'attention', label:!d.online ? '暂无法检查' : cloud?.ready ? '配置检查通过' : '未配置 / 可选', description:'使用云端视觉 API；本地离线模式不需要这项。', advice:'需要云端检测时配置 API Key 和本地定位组件。配置检查不保证远端额度或网络可用。', target:'/realtime-detect?profile=standard' },
  ]
}

export function diagnosticSnapshot(health) {
  // Deliberate allowlist: no credentials, full health payload, local paths,
  // endpoint URLs, prompts, screenshots or user identities in the export.
  return { product:'SmartRoad-Inspection', reportVersion:1, checkedAt:health.updatedAt,
    services:healthCards(health).map(({ id, state, label }) => ({ id, state, label })),
    pendingTasks:health.detect?.inference_queue?.pending ?? null,
    note:'只读连接检查；不代表模型准确率或实际推理验收。',
  }
}
