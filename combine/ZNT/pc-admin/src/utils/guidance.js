// Shared by navigation, search and contextual help. Keep destinations in-app;
// visiting an entry must never start inference or alter a user's configuration.
export const HELP_PAGES = [
  { path:'/dashboard', title:'公路空间总览', group:'工作台', description:'旋转三维道路模型，查看演示设备与路况报告。', keywords:'首页 驾驶舱 三维 3D 乐西 地图 设备 报告 数据',
    steps:['拖动旋转、滚轮缩放，或使用俯视和全线斜视按钮。','点击设备或路况点位，在右侧查看详情；可按等级筛选或开关图层。','导出演示报告；使用“新建真实检测”进入实际图像分析。'], result:'乐西高速空间示意、虚构设备台账与演示路况报告。', caution:'模型、桩号和点位均为演示构造，不是测绘成果或现场事件，不进入真实档案与统计。', next:'/realtime-detect' },
  { path:'/monitor', title:'视频监控', group:'工作台', description:'查看摄像头画面，管理实时初筛与定期全图巡检。', keywords:'摄像头 YOLO RTSP 视频 监测',
    steps:['在基础资源管理中登记设备及流地址。','选择摄像头；预览地址与检测用 RTSP 地址可以不同。','启用实时监测，并按需要配置 30 分钟或 2 小时的全面检测。'], result:'监测任务和送往视觉模型的候选帧。', caution:'窗口不能直接播放 RTSP。预览需 MP4/WebM 或受支持的 FLV 地址；检测服务可单独读取 RTSP。', next:'/task-center' },
  { path:'/realtime-detect', title:'图片与截帧检测', group:'工作台', description:'从一张图片开始，获取风险说明、位置和处理建议。', keywords:'上传 图片 异常 Qwen 云端 API 检测',
    steps:['选择演示、本地或云端模式；先确认模式的就绪状态。','上传 JPG/PNG，或选择包内案例图片。','提交后查看阶段进度，完成后检查证据与不确定项。'], result:'风险描述、模型判断及可用的框/掩码；需要时进入人工复核。', caution:'演示模式不运行真实模型。定位失败不代表没有风险；没有发现风险也不构成安全保证。', next:'/detection-results' },
  { path:'/task-center', title:'检测任务中心', group:'工作台', description:'追踪排队、处理和完成状态，找回历史结果。', keywords:'队列 历史 慢 重试 取消 进度',
    steps:['按状态筛选，查看任务创建时间和处理耗时。','点击“过程与结果”查看完整检测记录。','取消尚未开始的任务；失败时排除原因后重新检测。'], result:'可追踪的任务记录与失败原因。', caution:'离开页面不会停止后台任务；关闭整个桌面窗口会停止由它启动的服务。', next:'/detection-results' },
  { path:'/detection-results', title:'检测结果与证据', group:'风险闭环', roles:['admin','director','safety'], description:'把风险、原图、定位和报告放在一起核对。', keywords:'掩码 框 报告 案例 结果',
    steps:['筛选实时、已确认或待复核结果。','打开案例，核对原图、风险说明和证据。','将疑问交由安全人员判断，并跟进对应工单。'], result:'可展示、可解释的案例与风险结论。', caution:'待复核表示证据不足或存在疑问，不表示已经确认违规。', next:'/workorder' },
  { path:'/workorder', title:'风险工单处置', group:'风险闭环', description:'把发现的问题落实到负责人和整改记录。', keywords:'整改 派单 负责人 待办 闭环',
    steps:['优先筛选高危和待处理工单。','在详情中分配责任人，填写处置与整改信息。','补充证据后提交或确认完成，留下可追溯记录。'], result:'从发现到处理、完成的工单链路。', caution:'演示工单与真实事件需区分；自动建议不能替代现场决策。', next:'/agent-center' },
  { path:'/agent-center', title:'Agent 协同学习', group:'风险闭环', roles:['admin','safety'], description:'让人员参与复核、处置与规则改进。', keywords:'人工 复核 学习 反证 通知 交底',
    steps:['在人工复核中对照模型判断、支持证据与反证。','记录确认或排除依据，不要只依据置信度。','查看复盘建议；管理员审核后才应用规则变化。'], result:'人工裁决、通知与经批准的改进建议。', caution:'复盘不是自动训练大模型；规则改变需批准，不能把建议当成已生效。', next:'/analysis' },
  { path:'/analysis', title:'智能复盘分析', group:'知识与分析', roles:['admin','director'], description:'按时间和项目观察风险变化与整改成效。', keywords:'趋势 分析 汇报 导出 复盘',
    steps:['选择时间范围、项目等条件并查询。','区分真实统计与有标记的展示数据。','导出报告，将重复问题带回规则与人员培训。'], result:'风险趋势、整改统计和可导出报告。', caution:'空数据不等于没有隐患；请核对时间范围与数据源。', next:'/case-library' },
  { path:'/case-library', title:'安全案例库', group:'知识与分析', description:'检索已有案例，整理培训与交底素材。', keywords:'培训 素材 生成 归档 案例',
    steps:['按类型或关键词检索案例。','查看案例内容，按需使用素材生成工具。','到历史归档查看已有材料，区分生成素材与实拍证据。'], result:'用于培训、展示和复盘的案例材料。', caution:'生成素材不应作为真实事故证据；素材来源与授权需保留。', next:'/help-center' },
  { path:'/model-config', title:'模型与规则', group:'系统配置', roles:['admin'], description:'接入本地模型或云端服务，导入规范并管理检测规则。', keywords:'Qwen SAM3 CLIP YOLO 权重 阈值 RAG 规范 知识库 模型',
    steps:['新设备先打开“新设备部署”，按目标模式准备环境和组件，再在运行时页选择路径。','校验并保存；启动本地 Qwen，等待连接成功。SAM3/YOLO/CLIP 按任务加载。','在知识库导入规范，再用检索测试确认条款可查。'], result:'持久化模型配置、可检索规范和可管理的规则。', caution:'开关已启用不等于模型已加载；扫描 PDF 需要先 OCR，导入文件不等于重新训练模型。', next:'/realtime-detect' },
  { path:'/resource', title:'项目与设备', group:'系统配置', roles:['admin','director'], description:'维护摄像头、组织和项目，让检测对上真实场景。', keywords:'设备 地址 项目 处置单位 组织 资源',
    steps:['新增或核对项目基本信息。','登记设备，区分预览流与检测流地址。','维护组织与负责人，再检查监控和工单是否对应。'], result:'项目、设备、组织与后续任务的关联。', caution:'设备已登记不等于视频已连通；需到视频监控验证。', next:'/monitor' },
  { path:'/system-settings', title:'系统设置', group:'系统配置', roles:['admin'], description:'管理桌面环境、连接、视觉偏好、账号与业务备份。', keywords:'Python 端口 启动 主题 明暗 备份 用户 桌面 字号 字体 放大 缩放',
    steps:['在工作台与展示中调整字号，立即生效并自动保存；右下角也有字号快捷入口。','点击“放大查看”后滚轮缩放、拖动平移，按 Esc 恢复操作；也可按 Ctrl＋滚轮直接放大。','在桌面与连接中修改环境；用户与业务备份中管理账号和工作空间备份。'], result:'可持久保存的环境与个性化设置。', caution:'桌面启动配置需重启才生效；业务库备份不是整个系统的完整备份。', next:'/help-center' },
  { path:'/help-center', title:'使用与支持', group:'帮助', description:'找到每个功能的操作方法，排查连接并继续下一步。', keywords:'帮助 引导 开始 故障 排错 部署',
    steps:['选择一个使用目标，按步骤进入对应功能。','从功能索引查看输入、操作与输出。','遇到异常时展开常见问题，或查看连接诊断。'], result:'可执行的操作路径，而不是只有术语说明。', caution:'入门清单是个人操作记录，不是模型或服务验收。', next:'/dashboard' },
]

export const QUICK_ACTIONS = [
  { id:'deployment', title:'新设备模型部署', description:'选模式、准备环境、取得组件、配置路径与图片验收', target:'/model-config?tab=deployment', keywords:'新电脑 迁移 部署 下载 安装 模型 Python CUDA' },
  { id:'examples', title:'查看八个展示案例', description:'已有报告与掩码，无需重新推理', target:'/detection-results', keywords:'示例 展示 演示' },
  { id:'detect', title:'开始图片检测', description:'选择模式、图片，再提交任务', target:'/realtime-detect', keywords:'上传 风险' },
  { id:'models', title:'配置本地模型', description:'直接进入模型部件与运行时', target:'/model-config?tab=runtime', keywords:'qwen sam3 clip yolo 路径 权重 本地' },
  { id:'cloud', title:'连接云端视觉模型', description:'明确选择云端模式后填写 API Key', target:'/realtime-detect?profile=standard', keywords:'api key 云端 联网' },
  { id:'knowledge', title:'导入行业规范', description:'导入文档并测试条款检索', target:'/model-config?tab=kb', keywords:'rag pdf word 规范 知识库' },
  { id:'devices', title:'管理摄像头设备', description:'登记设备和流地址', target:'/resource?tab=device', keywords:'监控 rtsp 摄像头' },
  { id:'review', title:'处理人工复核', description:'核对支持证据与不确定项', target:'/agent-center?tab=review', keywords:'审核 待复核' },
  { id:'connection', title:'排查服务连接', description:'查看状态、原因与恢复入口', target:'/help-center?tab=diagnostics', keywords:'离线 检测桥 断开 连接 启动 失败' },
  { id:'desktop', title:'配置桌面环境', description:'Python、端口及默认启动方式', target:'/system-settings?tab=desktop', keywords:'环境 exe python 重启' },
  { id:'backup', title:'用户与业务备份', description:'管理权限和业务库备份', target:'/system-settings?tab=users', keywords:'账号 用户 备份 导出' },
]

export function pageFor(path = '') { return HELP_PAGES.find(p => p.path === String(path).split('?')[0]) }
export function canVisit(target, role) {
  const page = pageFor(target)
  return !!role && !!page && (!page.roles || page.roles.includes(role))
}
export function searchFunctions(query, role) {
  const terms = String(query || '').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  const entries = [...QUICK_ACTIONS, ...HELP_PAGES.map(p => ({ id:p.path, title:p.title, description:p.description, target:p.path, keywords:p.keywords }))]
  return entries.filter(item => canVisit(item.target, role) && terms.every(term => `${item.title} ${item.description} ${item.keywords}`.toLocaleLowerCase().includes(term)))
}

export const FAQS = [
  { title:'检测桥未连接，是否要重新安装模型？', body:'不一定。检测桥负责把界面请求交给模型。先打开连接诊断并刷新；桌面窗口通常会启动它。如果刚改过 Python 或端口，关闭并重新打开窗口。仍失败时检查后台依赖与地址。不要通过重复启动 Qwen 来修复检测桥。', target:'/help-center?tab=diagnostics', action:'查看连接诊断' },
  { title:'模型已激活，为什么没有立刻占用显存？', body:'SAM3、YOLO 和可选 CLIP 按任务加载，开关表示允许使用，不是已完成加载。Qwen 是独立推理服务，需要等待测试连接成功。配置检查通过也不代表实际推理已经验收。', target:'/model-config?tab=runtime', action:'查看模型状态' },
  { title:'检测很慢，可以切走页面吗？', body:'可以，任务在后台执行。到任务中心查看真实阶段与处理耗时；排队中的任务可取消，正在推理的任务不提供强制取消。关闭整个桌面窗口可能中止它所启动的后台任务。', target:'/task-center', action:'打开任务中心' },
  { title:'有风险说明但没有掩码，算检测失败吗？', body:'语义判断与空间定位是不同步骤。模型可能发现风险，但无法明确定位积水、遮挡后的道路边界等目标。请保留判断和疑问，由安全人员核对原图，不能把“无掩码”当作“无风险”。', target:'/detection-results', action:'查看风险与证据' },
  { title:'规范文件导入了，为什么检索不到？', body:'先确认导入结果与解析内容。扫描版 PDF 或纯图片文档需要先 OCR；换成含可复制文字的 PDF、DOCX 或文本再导入。随后使用条款检索测试。导入规范更新的是知识库，不是模型权重。', target:'/model-config?tab=kb', action:'测试知识库检索' },
  { title:'为什么看到预先编辑的案例和数据？', body:'道路版不启用历史展示素材，界面会标记其来源。“展示视图”控制外观；“预置展示素材”控制数据展示，两者互不等同。关闭素材显示不会删除文件或真实历史任务。', target:'/system-settings?tab=workspace', action:'设置展示方式' },
  { title:'换电脑要带哪些内容？', body:'先完整复制交付文件夹，不要只拿走 EXE。新版桌面在系统设置提供工作空间备份与恢复，迁移业务库、规范、任务图片/报告和用户配置；关闭并重开后执行。权重、云端密钥、桌面 Python 与端口不迁移，需在新设备配置。旧的单独业务备份仍只含数据库。', target:'/system-settings?tab=users', action:'备份与迁移' },
  { title:'摄像头有地址，为什么预览是黑屏？', body:'地址可能属于检测输入而非窗口可播放的格式。RTSP 需要另外提供可播放的预览流；同时检查设备在线状态、网络、地址权限和服务是否在工作。不要用示例视频判断真实设备已连接。', target:'/monitor', action:'检查摄像头' },
]

export const JOURNEYS = [
  { id:'showcase', title:'先看作品', tag:'无需模型', description:'从实际道路检测任务理解风险识别与处置流程。', steps:[{title:'查看任务与证据',target:'/detection-results'},{title:'了解人工判断与工单',target:'/workorder'},{title:'查看功能全景与使用边界',target:'/help-center?tab=library'}] },
  { id:'local', title:'接入真实检测', tag:'管理员配置', description:'配置环境和模型后，再用图片验证完整链路。', steps:[{title:'按新设备向导准备模型',target:'/model-config?tab=deployment'},{title:'配置后台环境',target:'/system-settings?tab=desktop'},{title:'选择权重并启动 Qwen',target:'/model-config?tab=runtime'},{title:'提交图片验证',target:'/realtime-detect'},{title:'核对报告与证据',target:'/detection-results'}] },
  { id:'daily', title:'开始日常巡检', tag:'人员参与闭环', description:'从监测到复核，把风险落实为可追踪的工作。', steps:[{title:'查看现场画面',target:'/monitor'},{title:'追踪检测任务',target:'/task-center'},{title:'处理风险工单',target:'/workorder'},{title:'整理案例用于培训',target:'/case-library'}] },
]
