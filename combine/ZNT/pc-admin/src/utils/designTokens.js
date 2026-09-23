/** Single palette for CSS, Ant Design and charts. Risk colors are not action colors. */
const shared = {
  'card-radius': '5px', 'product-ink': '#0a203c', 'media-bg': '#07182f',
  'hero-accent': '#88e0ca', 'hero-text': '#f1f8fb', 'hero-muted': '#b2c8d2',
}
export const palettes = {
  light: {
    ...shared,
    bg: '#f0f4f7', 'bg-2': '#e8eff3', surface: '#ffffff', 'surface-2': '#f6f9fb',
    'surface-muted': '#edf3f6', 'border-color': '#dbe5ec',
    'text-primary': '#203544', 'text-secondary': '#526978', 'text-muted': '#5b7082',
    primary: '#087f78', 'primary-strong': '#056b65', 'primary-soft': '#e4f4ef',
    'on-primary': '#ffffff', 'on-danger': '#ffffff', link: '#08766f', danger: '#c73749', warning: '#9a6100',
    caution: '#806400', success: '#187b5b', info: '#346fa7',
    'sider-bg': '#f9fbfc', 'sider-text': '#526978', 'sider-muted': '#5b7082',
    'sider-active': '#e0f1ed', 'sider-trigger': '#f9fbfc', 'sider-trigger-hover': '#edf3f6',
    'shadow-card': '0 2px 4px #183c5003, 0 8px 28px #183c5004',
    'shadow-float': '0 16px 48px #17344716',
    'chart-1': '#138a81', 'chart-2': '#557eaf', 'chart-3': '#a98040',
    'chart-4': '#866caf', 'chart-5': '#b46475',
  },
  dark: {
    ...shared,
    bg: '#071426', 'bg-2': '#0b1c33', surface: '#0e223d', 'surface-2': '#122b48',
    'surface-muted': '#193652', 'border-color': '#294862',
    'text-primary': '#e4effb', 'text-secondary': '#b4cce1', 'text-muted': '#99b5cd',
    primary: '#60d6f0', 'primary-strong': '#91e7fa', 'primary-soft': '#163c54',
    'on-primary': '#062437', 'on-danger': '#3f0f18', link: '#79dff5', danger: '#ff8994', warning: '#f5be7a',
    caution: '#e8cf76', success: '#70d6ad', info: '#85bcef',
    'sider-bg': '#091a30', 'sider-text': '#b4cce1', 'sider-muted': '#99b5cd',
    'sider-active': '#163c54', 'sider-trigger': '#091a30', 'sider-trigger-hover': '#122b48',
    'shadow-card': '0 2px 4px #00000008, 0 8px 28px #00000008',
    'shadow-float': '0 16px 48px #00000035',
    'chart-1': '#60d6f0', 'chart-2': '#85bcef', 'chart-3': '#d4b47b',
    'chart-4': '#bca2e6', 'chart-5': '#e69aae',
  },
}

export function paletteFor(mode) { return palettes[mode === 'dark' ? 'dark' : 'light'] }
export function antTokens(mode) {
  const p = paletteFor(mode)
  return {
    colorPrimary: p.primary, colorPrimaryHover: p['primary-strong'], colorPrimaryActive: p['primary-strong'],
    colorPrimaryBg: p['primary-soft'], colorPrimaryBgHover: p['primary-soft'], colorPrimaryText: p.link,
    colorLink: p.link, colorLinkHover: p['primary-strong'], colorLinkActive: p['primary-strong'],
    colorSuccess: p.success, colorWarning: p.warning, colorError: p.danger, colorInfo: p.info,
    colorBgBase: p.surface, colorBgContainer: p.surface, colorBgElevated: p.surface,
    colorBgLayout: p.bg, colorFillAlter: p['surface-2'], colorBorder: p['border-color'], colorBorderSecondary: p['border-color'],
    colorText: p['text-primary'], colorTextBase: p['text-primary'], colorTextSecondary: p['text-secondary'],
    colorTextTertiary: p['text-muted'], colorTextQuaternary: p['text-muted'],
    colorTextLightSolid: '#ffffff', colorBgSpotlight: '#0a203c', borderRadius: 4, borderRadiusLG: 5,
    fontFamily: '"Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
    fontSize: 14, controlHeight: 36, boxShadowSecondary: p['shadow-float'],
  }
}

export function chartTheme(mode) {
  const p = paletteFor(mode)
  return {
    text: p['text-secondary'], grid: p['border-color'], primary: p.primary,
    danger: p.danger, warning: p.warning, caution: p.caution,
    colors: [1, 2, 3, 4, 5].map(i => p[`chart-${i}`]),
    tooltip: { backgroundColor: p.surface, borderColor: p['border-color'], textStyle: { color: p['text-primary'], fontSize: 12 }, extraCssText: 'border-radius:10px;box-shadow:' + p['shadow-float'] },
  }
}
