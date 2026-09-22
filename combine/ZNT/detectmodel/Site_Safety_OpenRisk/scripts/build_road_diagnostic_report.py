"""Render the retained CRASAR diagnostic evidence; does not rerun inference."""
import argparse
import html
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    root = args.workspace
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "fixed_v2/summary.json").read_text(encoding="utf-8"))
    observations = {
        "S01": "提出积水候选，但未获得有效分割实体；淹水范围未定位，待人工复核。",
        "S02": "提出积水候选，但掩码仅覆盖小片区域，缺少道路主体定位，空间关系核验失败。",
        "S03": "将障碍解释为散落异物；仅定位道路主体，异常物体定位失败。类别口径需要对齐。",
        "S04": "官方目标为颗粒物覆盖；系统提出积水候选后仍不能区分泥浆与水，未确认风险。",
        "S05": "未输出候选。原标注为无法判断，画面有大面积黑色无数据区域；不能据此认定安全或正确阴性。",
        "S06": "未输出候选，漏掉道路状况异常目标。前两轮输出也不稳定，需要补充道路破损识别能力。",
        "S07": "提出可疑异物候选，异常掩码大范围覆盖草地和路侧，定位明显不合理。Road Line仅为道路几何标注，不能据此计算误报率。",
    }
    rows = []
    cards = []
    for source, item in zip(manifest["items"], summary["items"]):
        sid = source["sample_id"]
        assert sid == item["sample_id"]
        risks = item["visual"]["final_risks"]
        state = "待人工复核" if risks else "未输出候选"
        rows.append(f"| {sid} | {source['label']} | {state} | {item['seconds']:.2f} | {observations[sid]} |")
        panels = [(f"inputs/{sid}.png", "模型输入原图"), (f"references/{sid}.png", "参考标注，仅用于人工核对")]
        panels += [(p.relative_to(root).as_posix(), "最终模型定位叠加图") for p in sorted((root / "fixed_v2" / sid).glob("overlay_*.png"))]
        figures = "".join(f'<figure><img src="{html.escape(path)}"><figcaption>{html.escape(label)}</figcaption></figure>' for path, label in panels)
        cards.append(f'<article><h2>{sid} · {html.escape(source["label"])} · {state}</h2><p>{observations[sid]}</p><div class="images">{figures}</div><a href="fixed_v2/{sid}/final_report.json">原始结构化报告</a></article>')
    report = """# CRASAR道路样例检测诊断报告

日期：2026-09-13。对象：路安智巡路面风险智能检测软件，实验室小试版。

## 结论

系统已完成真实模型样例联调，但仍需修改检测能力。最终7张样例全部完成软件流程，其中5张保留待复核候选，2张未输出候选，自动确认风险为0。这是流程完成情况，不是检测准确率。发现积水与障碍定位不稳、道路破损漏检、覆盖物类别混淆等问题，暂不能作为全自动路况判定系统。

## 数据与证据边界

从本机 E:\\数据集\\CRASAR-U-DROIDs 的道路损伤标注 road_damage_assessment 中选择7个裁剪样例，涉及淹水、阻塞、颗粒物覆盖、道路状况异常、无法判断与道路几何参考。数据来源可参见[CRASAR道路损伤任务仓库](https://github.com/CRASAR/CRASAR-U-DROIDs-RDA)。灾后航拍数据与高速固定摄像头存在明显视角和场景差异，不能直接证明实时高速检测效果。

选择在模型运行前确定，使用原始GeoTIFF窗口读取，不修改数据源。模型只收到裁剪图像和道路检测提示；标注、类别与红色参考轮廓未作为模型输入。manifest.json保留源文件、窗口坐标和输入/标注哈希。官方类别对应焦点标注区域，不代表整张裁剪图。S07的Road Line不是官方负样本标签。黑色无数据区域不能当作真实塌陷。

这7张来自官方test目录，已用于调试和重复复测，应视为开发诊断集；以后不能把同一批图作为独立测试集报告泛化成绩。本次没有训练、没有计算准确率、召回率或IoU。

## 运行方式

真实推理使用本机Qwen3-VL-8B-Instruct Q4_K_M与SAM3，RTX 5060 Ti 16GB。Python复用 E:\\work\\competition\\combine\\env\\python.exe，尚未迁移为独立GPU运行环境。模型权重位于 E:\\model 和 E:\\SAM3_MAIN。道路初筛模型尚未接入；此次验证服务器二阶段单图分析。

保留baseline、fixed_v1、fixed_v2三轮原始结果，fixed_v2为最终配置。逐图运行时间5.17至13.67秒，仅统计模型加载后的单图流程，不包括冷启动，也不是摄像头到报警的端到端延迟。配置、模型路径、源代码哈希与每图耗时见各轮summary.json。

## 逐图结果

| 样例 | 官方焦点标注 | 最终状态 | 耗时/秒 | 人工诊断 |
|---|---|---|---:|---|
""" + "\n".join(rows) + """

原图总览见contact_sheet.jpg；逐图原图、参考标注和定位叠加图见同目录“逐图证据.html”。原始模型输出与掩码位于fixed_v2/S01至S07。没有异常掩码的样例不生成虚构定位图。

## 本次已修复

1. 跨风险SAM3任务编号重复会导致流程中断：增加命名空间并同步空间关系引用。基线6/7完成，修复后7/7完成。
2. 道路提示中残留施工防护语义：替换为道路专用复核说明，限制无证据推断。
3. 风险规范化可能抬高低置信度：道路模式保留原置信度，不自动补高分。
4. 固定定位任务与模型动态任务重复：保留动态目标，避免重复分割。
5. 合并复核可能丢失风险编号：改为逐风险复核，保留对应关系。
6. 事件框可能把整条道路主体纳入异常范围：改从异常掩码提取边界框。
7. 真实模型运行环境和本地服务配置已接通，首页更新为已开展小样例诊断、尚未正式评测。

修改没有取消空间关系门控，也没有把待复核候选写成确认风险。fixed_v1暴露的类别和编号问题保留在记录中，最终结果仍存在明显漏检与定位错误。

## 软件链路验证

通过桌面运行层的同源网关上传S02，以offline真实模型档完成检测，并成功同步道路业务库。任务JOB-20260913-034637-b34f5e，事件EVT-JOB-8fd6a863f4924607；保存1条事件、1条复核记录、0条自动工单。证据见api_smoke.json。该结果保留在软件中。这项检查不等于打包桌面窗口验收。

新增/更新的道路单元检查6项通过，相关安全守卫检查8项通过，前端构建通过。真实模型与临时服务已停止。

## 下一步修改顺序

| 优先级 | 修改 | 下一轮验证方式 |
|---|---|---|
| P0 | 增加无法判断、无数据和可见性不足状态，明确区分“未检出”和“安全” | 黑边、遮挡、阴影样例不得输出安全结论 |
| P0 | 统一道路风险目录与数据标注口径，分开阻塞、散落物、覆盖物和道路损伤 | 先冻结类别映射与人工判读规则，再评测 |
| P0 | 改善道路区域与异常对象定位，特别是淹水后的道路区域 | 检查道路及异常掩码，测定位质量，保留关系门控 |
| P1 | 补强道路破损识别，记录跨次推理的不稳定输出 | 使用独立道路损伤样本，分风险统计漏检 |
| P1 | 建立未参与本轮调试的独立验证集，人工确认正常对照 | 按原始场景隔离，固定参数后一次评估，不挑成功样例 |
| P2 | 接入高速摄像头一阶段模型，补视频去重、连续帧与延迟测试 | 在高速固定摄像头数据上单独验证，不以灾后航拍替代 |

个人微信渠道尚未接入；先完成识别与复核闭环，再测试通知。未发布新安装包，未将本次修改推送GitHub。

## 在本机复现

启动 E:\\work\\智慧交通\\启动路安智巡.cmd。默认仍为模拟联调档；真实检测需在模型配置中启动本地Qwen服务，并在检测入口选择offline档。输入使用本目录inputs中的原图，不使用references红色标注图。已归档的S02记录可按上述任务编号查找。

复测脚本为源码detectmodel/Site_Safety_OpenRisk/scripts/run_road_examples.py，可先使用 --help 查看参数；为保留证据，应使用新的运行目录名称，避免覆盖三轮既有记录。
"""
    (root / "检测诊断报告.md").write_text(report, encoding="utf-8")
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>CRASAR逐图证据</title><style>body{font-family:"Microsoft YaHei",sans-serif;max-width:1450px;margin:32px auto;padding:0 24px;background:#f4f6f9;color:#182230}article{background:white;padding:24px;margin:20px 0;border-radius:12px}.images{display:flex;gap:16px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:260px;max-width:600px}img{width:100%;height:380px;object-fit:contain;background:#e9edf2}figcaption{padding:10px 0;color:#526175}p{line-height:1.7}h1{font-size:28px}h2{font-size:20px}</style><h1>CRASAR道路样例 · 逐图诊断证据</h1><p>7张开发诊断样例，5张有待复核候选、2张无候选，自动确认风险0。不是完整评测或检测成功率。参考轮廓未提供给模型；模型叠加图保留原始输出，包括错误定位。</p><a href="检测诊断报告.md">完整诊断报告</a>' + ''.join(cards) + '</html>'
    (root / "逐图证据.html").write_text(page, encoding="utf-8")
    print(root / "检测诊断报告.md")
    print(root / "逐图证据.html")


if __name__ == "__main__":
    main()
