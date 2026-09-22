# 已验证环境快照

该文件用于告诉新部署者“什么组合已经实际跑通过”，不是强制锁死所有版本。

## v1.3 桌面 Demo／文档导入环境（2026-09-07）

| 组件 | 本次交付验证 |
|---|---|
| 随包 Python | 3.12.10 x64 |
| FastAPI | 0.141.1 |
| Demo 与 RAG 依赖 | 随包环境导入验证通过 |
| 前端／桌面版本 | 1.3.0 |
| 模型推理 | 本轮未运行；不据此更改下方 GPU 环境快照 |

来源：[v1.3 验证与交付记录](../docs/v1.3视觉验收记录.md)。Python 3.12 的桌面 Demo 环境与以下 Python 3.10 的历史 GPU 检测环境是不同用途，不能简单互换。

## 历史完整 GPU 检测环境

以下数值保留原有已验证记录；本轮视觉／文档更新未重新复验这一组模型。

| 组件 | 已验证版本/配置 |
|---|---|
| 操作系统 | Windows 10/11 x64（本机 build 26200） |
| Python | 3.10.20 x64 |
| PyTorch | 2.11.0+cu128 |
| torchvision | 0.26.0+cu128 |
| CUDA runtime | 12.8 |
| GPU | NVIDIA GeForce RTX 5060 Ti 16 GB |
| FastAPI | 0.140.0 |
| Uvicorn | 0.51.0 |
| Pydantic | 2.13.4 |
| Ultralytics | 8.4.106 |
| OpenCV | 5.0.0 |
| OpenCLIP | 3.3.0 |
| Node.js | 24.14.0（原开发机记录）；当前 Vite 声明条件为 `^20.19.0 || >=22.12.0`，CI 配置 Node 22 |
| Qwen | Qwen3-VL-8B-Instruct Q4_K_M GGUF + BF16 mmproj |
| Qwen上下文 | 8192，单 slot |
| SAM3 | `sam3.pt`，CUDA 实际推理通过 |

## 兼容原则

- PyTorch、torchvision 和 CUDA 必须作为一组匹配，不要分别随意升级。
- Qwen GGUF 与 mmproj 必须来自同一模型版本和修订。
- 更换任一视觉模型、量化等级、上下文或推理后端后，至少重跑八张示例。
- 更换最终算法配置后，应重跑 58 张正样本与 40 张控制候选全量回归。
- 不要只按 Node 的主版本号安装；应满足当前锁定 Vite 的最低小版本要求。完整桌面演示包不要求系统 Node。
