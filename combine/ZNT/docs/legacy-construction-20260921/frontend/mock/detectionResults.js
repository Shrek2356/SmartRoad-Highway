/**
 * 检测结果汇总 Mock（面向前端展示，弱化算法细节）
 * 素材来自 Outcomes/代表性结果图 与 public/outcomes
 * 原始检测代码：detectmodel/Site_Safety_OpenRisk/
 */

/** 结果由来（点击弹窗展示，不在主界面堆砌） */
export const resultOrigin = {
  title: '检测结果如何得出？',
  summary:
    '系统对现场图片先发现疑似隐患，再通过实体定位与空间关系核验后确认。只有证据足够时才自动确认；证据不足则转人工复核，避免误报。管理报告只整理整改建议，不改写检测结论。',
  flow: [
    '现场图像输入',
    '发现疑似隐患',
    '定位风险区域并生成标注图',
    '证据核验（通过→自动确认 / 不足→人工复核）',
    '生成处置建议与管理摘要',
  ],
  codePath: 'detectmodel/Site_Safety_OpenRisk/',
  codeHint: '对接真实检测时，优先阅读该目录 README，并用 run_mock_demo.py / serve_demo.py 验证全链路。',
  quickStart: [
    'cd detectmodel/Site_Safety_OpenRisk',
    'pip install -r requirements.txt',
    'python run_mock_demo.py',
    'python serve_demo.py',
  ],
}

export const detectionSummary = {
  total: 8,
  autoConfirmed: 6,
  humanReview: 4,
  highConfidenceNoReview: 4,
  conclusion:
    '八张关键现场样例均已保留：7张形成异常报告，7张生成有效风险标注，第8张验证了人员倒地等开放风险发现能力。',
}

/**
 * 样例结果（展示向）
 * cover: 成果叠加图（优先用于轮播/卡片）
 */
export const detectionCases = [
  {
    id: 1,
    expected: '高处作业未佩戴安全带',
    result: '临边防护缺失（安全带状态需复核）',
    confidence: 0.6,
    autoConfirm: true,
    humanReview: true,
    status: 'partial',
    analysis: '工人在楼板边缘作业，视野内未见防护栏杆。存在坠落风险，安全带是否佩戴受遮挡无法确认。',
    suggestion: '暂停临边作业，补设防护并核查安全带挂设。',
    cover: '/outcomes/case1_overlay.png',
    images: {
      original: '/results/case1_original.jpg',
      overlay: '/outcomes/case1_overlay.png',
      mask: '/results/case1_mask.jpg',
    },
  },
  {
    id: 2,
    expected: '吊装作业下方有人',
    result: '人员位于悬吊物下方',
    confidence: 0.98,
    autoConfirm: true,
    humanReview: false,
    status: 'confirmed',
    analysis: '大型构件悬吊，下方有人员处于投影危险区，证据完整，已自动确认。',
    suggestion: '立即停止吊装，疏散人员并设置硬质警戒区。',
    cover: '/outcomes/case2_overlay.png',
    images: {
      original: '/results/case2_original.jpg',
      overlay: '/outcomes/case2_overlay.png',
      mask: '/results/case2_mask.jpg',
    },
  },
  {
    id: 3,
    expected: '临边洞口未防护',
    result: '临边防护缺失',
    confidence: 0.6,
    autoConfirm: true,
    humanReview: true,
    status: 'confirmed',
    analysis: '作业人员位于洞口/临边，未见护栏或盖板，已确认防护缺失，建议现场复核覆盖范围。',
    suggestion: '立即设置隔离与硬质防护，排查同层同类洞口。',
    cover: '/outcomes/case3_overlay.png',
    images: {
      original: '/results/case3_original.jpg',
      overlay: '/outcomes/case3_overlay.png',
      mask: '/results/case3_mask.jpg',
    },
  },
  {
    id: 4,
    expected: '电气线路裸露、违规用电',
    result: '地面电缆敷设混乱且浸水',
    confidence: 0.95,
    autoConfirm: true,
    humanReview: false,
    status: 'confirmed',
    analysis: '积水地面散落电缆，未见架空或穿管保护，触电风险明确。',
    suggestion: '先断电，再完成绝缘检查与架空/穿管整改。',
    cover: '/outcomes/case4_overlay.png',
    images: {
      original: '/results/case4_original.jpg',
      overlay: '/outcomes/case4_overlay.png',
      mask: '/results/case4_mask.jpg',
    },
  },
  {
    id: 5,
    expected: '材料堆放、通道堵塞',
    result: '疑似通道被材料侵占（待复核）',
    confidence: 0.45,
    autoConfirm: false,
    humanReview: true,
    status: 'review',
    analysis: '画面显示材料侵占通行空间，但通道属性证据不足，系统未自动确认。',
    suggestion: '现场确认是否为规定通道，并测量剩余有效宽度。',
    cover: '/outcomes/case5_overlay.png',
    images: {
      original: '/results/case5_original.jpg',
      overlay: '/outcomes/case5_overlay.png',
      mask: '/results/case5_mask.jpg',
    },
  },
  {
    id: 6,
    expected: '脚手架安全隐患',
    result: '疑似脚手板/防护不规范（待复核）',
    confidence: 0.35,
    autoConfirm: false,
    humanReview: true,
    status: 'review',
    analysis: '发现候选隐患，但关键结构未稳定定位，未生成有效叠加标注，转人工复核。',
    suggestion: '核查脚手板满铺、搭接绑扎及外侧栏杆连续性。',
    cover: '/results/case6_original.jpg',
    images: {
      original: '/results/case6_original.jpg',
      overlay: '',
      mask: '',
    },
  },
  {
    id: 7,
    expected: '未佩戴安全帽',
    result: '施工人员未佩戴安全帽',
    confidence: 0.98,
    autoConfirm: true,
    humanReview: false,
    status: 'confirmed',
    analysis: '目标人员头部清晰可见且未戴安全帽，周围人员有佩戴对比，已确认。',
    suggestion: '立即督促佩戴安全帽，复核通过后再复工。',
    cover: '/outcomes/case7_overlay.png',
    images: {
      original: '/results/case7_original.jpg',
      overlay: '/outcomes/case7_overlay.png',
      mask: '/results/case7_mask.jpg',
    },
  },
  {
    id: 8,
    expected: '工人独自昏倒',
    result: '人员异常倒地',
    confidence: 0.95,
    autoConfirm: true,
    humanReview: false,
    status: 'confirmed',
    analysis: 'YOLO未触发已训练类别，但开放风险识别发现人员异常倒地，SAM3完成倒地人员区域定位。',
    suggestion: '立即派员确认意识与呼吸状态，启动现场急救并保持救援通道畅通。',
    cover: '/outcomes/case8_overlay.png',
    images: {
      original: '/examples/case8.png',
      overlay: '/outcomes/case8_overlay.png',
      mask: '/outcomes/case8_overlay.png',
    },
  },
]
