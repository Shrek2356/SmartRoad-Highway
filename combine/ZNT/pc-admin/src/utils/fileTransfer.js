export const MAX_EXPORT_BYTES = 64 * 1024 * 1024

export async function saveBlob(blob, filename, host = globalThis.window) {
  if (!blob || blob.size > MAX_EXPORT_BYTES) throw new Error('导出文件超过 64 MB，请缩小导出范围')
  if (host?.pywebview?.api) {
    if (!host.pywebview.api.save_export) throw new Error('桌面外壳版本较旧，请更新 EXE 后再导出')
    const bytes = new Uint8Array(await blob.arrayBuffer())
    const parts = []
    for (let i = 0; i < bytes.length; i += 32768) parts.push(String.fromCharCode(...bytes.subarray(i, i + 32768)))
    return host.pywebview.api.save_export(filename, btoa(parts.join('')))
  }
  const url = host.URL.createObjectURL(blob)
  const link = host.document.createElement('a')
  link.href = url; link.download = filename
  host.document.body.appendChild(link)
  try { link.click() } finally { link.remove(); host.setTimeout(() => host.URL.revokeObjectURL(url), 60000) }
  return { status: 'download_requested' }
}

export function saveOutcome(result) {
  if (result?.status === 'saved') return { kind: 'success', text: `文件已保存：${result.filename}` }
  if (result?.status === 'cancelled') return { kind: 'info', text: '已取消保存，未生成文件' }
  if (result?.status === 'download_requested') return { kind: 'info', text: '已发起下载，请在浏览器下载列表中确认' }
  throw new Error('未收到文件保存确认，请检查桌面连接后重试')
}
