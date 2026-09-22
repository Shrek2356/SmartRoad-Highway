/**
 * 风险掩码坐标渲染工具
 * -------------------------------------------------------
 * 作用：将 AI 返回的 bbox/mask 转为可叠加在视频上的样式
 * 【对接说明】视觉模型坐标体系变化时，只需改 toPercentMask
 * -------------------------------------------------------
 */

/** 风险等级对应描边/填充色 */
export const RISK_COLORS = {
  red: { border: '#ff4d4f', bg: 'rgba(255, 77, 79, 0.28)', label: '高危' },
  orange: { border: '#fa8c16', bg: 'rgba(250, 140, 22, 0.28)', label: '中危' },
  yellow: { border: '#fadb14', bg: 'rgba(250, 219, 20, 0.28)', label: '低危' },
}

/**
 * 将掩码转为 CSS 定位样式（父容器需 position:relative）
 * @param {{ x:number, y:number, w:number, h:number }} mask 百分比坐标
 * @param {'red'|'orange'|'yellow'} level
 * @returns {object} style 对象
 */
export function maskToStyle(mask, level = 'yellow') {
  const color = RISK_COLORS[level] || RISK_COLORS.yellow
  return {
    position: 'absolute',
    left: `${mask.x}%`,
    top: `${mask.y}%`,
    width: `${mask.w}%`,
    height: `${mask.h}%`,
    border: `2px solid ${color.border}`,
    background: color.bg,
    boxSizing: 'border-box',
    pointerEvents: 'none',
  }
}

/**
 * 像素坐标 → 百分比坐标
 * @param {{x,y,w,h}} bbox 像素
 * @param {{width:number,height:number}} videoSize 视频实际尺寸
 */
export function toPercentMask(bbox, videoSize) {
  if (!videoSize?.width || !videoSize?.height) return bbox
  return {
    x: (bbox.x / videoSize.width) * 100,
    y: (bbox.y / videoSize.height) * 100,
    w: (bbox.w / videoSize.width) * 100,
    h: (bbox.h / videoSize.height) * 100,
  }
}
