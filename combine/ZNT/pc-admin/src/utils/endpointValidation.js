export function validateEndpoint(value) {
  if (/^\/(?!\/)[A-Za-z0-9_./-]+$/.test(value) && !value.includes('..')) return value
  try {
    const url = new URL(value)
    if (!['http:','https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash || /\s|\\/.test(value)) throw new Error()
    return value
  } catch { throw new Error('请输入 HTTP(S) 服务地址或 / 开头的本机代理路径；不要填写磁盘路径、API Key、账号密码或查询参数。') }
}
