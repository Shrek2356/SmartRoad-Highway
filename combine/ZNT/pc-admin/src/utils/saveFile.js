import { message } from 'ant-design-vue'
import { saveBlob, saveOutcome } from './fileTransfer'

export async function saveFile(blob, filename) {
  const result = await saveBlob(blob, filename)
  const notice = saveOutcome(result)
  message[notice.kind](notice.text)
  return result
}
