import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { palettes, antTokens, chartTheme } from '../src/utils/designTokens.js'

function luminance(hex) {
  const rgb = hex.slice(1).match(/../g).map(v => parseInt(v, 16) / 255)
    .map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722
}
function contrast(a, b) {
  const x = luminance(a), y = luminance(b)
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
}

for (const mode of ['light', 'dark']) {
  test(`${mode}: core text, controls and status colors have readable contrast`, () => {
    const p = palettes[mode]
    for (const foreground of ['text-primary', 'text-secondary', 'text-muted', 'link', 'danger', 'warning', 'caution', 'success']) {
      for (const background of ['surface', 'surface-2', 'bg']) {
        assert.ok(contrast(p[foreground], p[background]) >= 4.5, `${foreground} on ${background}: ${contrast(p[foreground], p[background])}`)
      }
    }
    for (const action of ['primary', 'primary-strong']) assert.ok(contrast(p[action], p['on-primary']) >= 4.5)
    assert.ok(contrast(p.danger, p['on-danger']) >= 4.5)
    assert.ok(contrast(p['sider-text'], p['sider-bg']) >= 4.5)
    assert.ok(contrast(p.link, p['sider-active']) >= 4.5)
    assert.ok(contrast(p['hero-accent'], p['product-ink']) >= 4.5)
  })
  test(`${mode}: component, CSS and chart palettes agree; action is not danger`, () => {
    const p = palettes[mode], ant = antTokens(mode), chart = chartTheme(mode)
    assert.equal(ant.colorPrimary, p.primary)
    assert.equal(ant.colorError, p.danger)
    assert.notEqual(p.primary, p.danger)
    assert.equal(chart.primary, p.primary)
    assert.equal(chart.danger, p.danger)
    assert.equal(chart.tooltip.backgroundColor, p.surface)
    assert.equal(new Set(chart.colors).size, 5)
  })
}

test('both themes cover the same tokens; all are concrete CSS values', () => {
  assert.deepEqual(Object.keys(palettes.light).sort(), Object.keys(palettes.dark).sort())
  for (const p of Object.values(palettes)) for (const value of Object.values(p)) {
    assert.equal(typeof value, 'string')
    assert.ok(!value.includes('undefined'))
  }
})

test('global theme leaves semantic progress and disabled states to the component library', async () => {
  const css = await readFile(new URL('../src/styles/global.css', import.meta.url), 'utf8')
  assert.ok(!css.includes('.ant-progress-bg'))
  assert.ok(!css.includes('.ant-checkbox-indeterminate'))
  assert.ok(css.includes(':not(.ant-btn-dangerous):not(.ant-btn-background-ghost):not(:disabled)'))
})
