from __future__ import annotations


def build_json_repair_prompt(raw_output: str) -> str:
    """Ask the same local model to repair formatting without revising its verdict."""
    return f"""下面是一段模型刚刚生成的输出。它应该是一个 JSON 对象，但格式不合法。

请只做 JSON 格式修复：
1. 不得新增、删除或改写任何视觉事实、风险结论、置信度或字段语义；
2. 保留原有字段、数组元素和中文文本；
3. 仅修复引号、逗号、转义字符、代码围栏等语法问题，使其成为严格有效的 JSON 对象；
4. 只输出修复后的 JSON 对象，不要 Markdown、解释或额外文字。

待修复文本：
```text
{raw_output}
```
"""
