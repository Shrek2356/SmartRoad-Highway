import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { modelItems, safeSource, reportSummary, installCommands, psQuote } from '../src/utils/deploymentGuide.js'

const manifest = {models:{qwen:{required_for:['offline']},sam3:{required_for:['offline','cloud']},clip_checkpoint_path:{required_for:[]}}}
test('deployment modes require only their own components', () => {
  assert.deepEqual(modelItems(manifest,'demo'), [])
  assert.deepEqual(modelItems(manifest,'cloud').map(x=>x.key), ['sam3','clip_checkpoint_path'])
  assert.equal(modelItems(manifest,'offline').length, 3)
  assert.equal(modelItems(manifest,'cloud').at(-1).required, false)
})
test('empty project download is not an invented or dangerous URL', () => {
  for(const value of ['',null,'javascript:alert(1)','file:///C:/private','https://user:secret@host']) assert.equal(safeSource(value), '')
  assert.equal(safeSource('https://github.com/project/releases'), 'https://github.com/project/releases')
})
test('environment success does not claim inference passed', () => {
  assert.match(reportSummary(null).title,/尚未/)
  assert.match(reportSummary({ready:true}).title,/仍需真实图片验收/)
  assert.equal(reportSummary({error:'missing python'}).type,'error')
  assert.equal(reportSummary({ready:false}).type,'warning')
})
test('installation commands are quoted and never target portable Demo Python', () => {
  const commands = installCommands("D:/新设备 with 'quotes'", 'D:/新设备/python-runtime/python.exe')
  assert.ok(commands.dependencies.includes('/env/Scripts/python.exe'))
  assert.ok(!commands.dependencies.includes('python-runtime'))
  assert.ok(commands.create.includes("''quotes''"))
  assert.equal(psQuote("a'b"), "'a''b'")
  assert.match(installCommands('D:/SiteSafe','D:/custom/python.exe').dependencies,/custom/)
})
test('mode changes invalidate reports and page entry does not trigger checks', async () => {
  const source = await readFile(new URL('../src/components/ModelDeploymentGuide.vue',import.meta.url),'utf8')
  assert.ok(source.includes('onMounted(loadGuide)'))
  assert.ok(source.includes('watch(mode, () => { revision++; report.value = null;'))
  assert.ok(source.includes('ticket === revision'))
  assert.ok(!source.includes('onMounted(runCheck)'))
  assert.ok(!source.includes('startQwenService'))
})
