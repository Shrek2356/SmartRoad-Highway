// Scale authored pixel typography once, keeping widths and image coordinates intact.
// Ant Design's runtime typography is scaled separately through ConfigProvider.
export function scaleFontValue(prop,value) {
  if(!['font','font-size','line-height'].includes(prop)||value.includes('--ui-font-scale'))return value
  return value.replace(/(^|[\s,(/])([0-9]*\.?[0-9]+)px(?=$|[\s/),])/g,(_m,prefix,size)=>`${prefix}calc(${size}px * var(--ui-font-scale, 1))`)
}
export default function fontScale(){return {postcssPlugin:'smartroad-font-scale',Declaration(decl){
  const file=(decl.source?.input?.file||'').replaceAll('\\','/')
  if(!file.includes('/src/'))return
  decl.value=scaleFontValue(decl.prop,decl.value)
}}}
