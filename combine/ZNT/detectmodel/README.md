# detectmodel 交付说明

队名：嘉然今天也在守护工地

## 目录

| 目录 | 用途 |
|------|------|
| `Site_Safety_OpenRisk/` | 检测算法最终版（含 Agent、桥接服务；PC「实时检测」对接此目录） |

成果文档：仓库根目录 `Outcomes/`。  
本地权重：仓库根目录 `sam3.pt`、`sam3-main/`、`ViT-L-14.pt`（不随代码包分发时可单独提供）。

## 启动检测桥接

推荐在仓库根目录双击 `start-platform.bat`，按提示选择检测模式。

也可手动：

```bat
cd detectmodel\Site_Safety_OpenRisk
run_bridge.bat <python.exe> configs\default.yaml 8810
```

## 依赖与权重

- Python 依赖：`requirements/`（`setup_env.bat` / `check_weights.bat`）
- 环境变量：`Site_Safety_OpenRisk/.env`
- 权重路径（相对算法包）：`../../sam3-main`、`../../sam3.pt`、`../../ViT-L-14.pt`

本机若已有 Anaconda 环境 `torch`，`start-platform.bat` 会自动使用它。

算法细节见 `Site_Safety_OpenRisk/README.md`。
