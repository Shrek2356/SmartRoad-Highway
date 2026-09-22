export function containRect(width, height, videoWidth, videoHeight) {
  if (![width,height,videoWidth,videoHeight].every(n => Number.isFinite(n) && n > 0)) return null
  const scale = Math.min(width / videoWidth, height / videoHeight)
  const w = Math.min(width, videoWidth * scale), h = Math.min(height, videoHeight * scale)
  return { left:(width-w)/2, top:(height-h)/2, width:w, height:h }
}
