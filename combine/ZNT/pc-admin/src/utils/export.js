/**
 * 导出工具
 * 作用：表格数据导出为 CSV（Mock 阶段本地导出，后续可改为后端导出）
 */
import dayjs from 'dayjs'
import { saveFile } from './saveFile'

/**
 * 将对象数组导出为 CSV 并触发下载
 * @param {Array<Object>} rows 数据行
 * @param {string} filename 文件名（不含扩展名）
 * @param {Array<{key:string,title:string}>} columns 列配置
 */
export async function exportCsv(rows, filename, columns) {
  if (!rows?.length) return

  const header = columns.map((c) => c.title).join(',')
  const body = rows
    .map((row) =>
      columns
        .map((c) => {
          const val = row[c.key] ?? ''
          // 处理逗号与换行，避免破坏 CSV
          const str = String(val).replace(/"/g, '""')
          return `"${str}"`
        })
        .join(',')
    )
    .join('\n')

  const bom = '\uFEFF' // Excel 兼容 UTF-8
  const blob = new Blob([bom + header + '\n' + body], {
    type: 'text/csv;charset=utf-8;',
  })
  return saveFile(blob, `${filename}_${dayjs().format('YYYYMMDD_HHmmss')}.csv`)
}
