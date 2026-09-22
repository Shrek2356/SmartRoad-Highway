/**
 * ============================================================
 * AI 模型对接预留模块（核心对接入口）
 * ============================================================
 *
 * 本目录封装三类能力，对应三个智能体/模型：
 *
 * 1. 视觉大模型（Vision Model）      → vision.js
 * 2. 推理智能体（Reasoning Agent）    → reason.js
 * 3. 处置智能体（Action Agent）        → action.js
 *
 * 【实时检测整链路】推荐走桥接服务，而不是单独调上述占位：
 *   - 后端：detectmodel/Site_Safety_OpenRisk/detect_bridge.py
 *   - 前端：src/api/detect.js + views/realtime-detect
 *   - 启动：仓库根目录「启动检测服务.bat」
 *
 * 桥接会串起：接收图像 → 视觉初检 → SAM3 掩码 → 证据门控 →
 * 二次核验 → 风险推理 → 处置建议，并把各阶段状态回传前端。
 * ============================================================
 */
export * from './vision'
export * from './reason'
export * from './action'
export * from './maskRender'
