# packaging

## 怎么打开

1. 双击 `start-platform.bat`  
2. 选模式：`1` 演示 Mock / `2` 本地离线 / `3` 云端标准  
3. 保留黑色窗口，浏览器登录  

Python 查找顺序：`env\` → `D:\Anaconda\envs\torch` → 系统 python。

---

1. 安装 Node.js LTS  
2. 双击 `requirements\setup_env.bat`（生成 `env\` 并装依赖）  
3. 权重放到仓库根目录：`sam3.pt`、`sam3-main/`、`ViT-L-14.pt`（可与代码包分开拷贝）  
4. 本地离线模式填写`LOCAL_QWEN_*`；云端标准模式填写`DASHSCOPE_API_KEY`  
5. 双击 `start-platform.bat`  
6. 可用 `requirements\check_weights.bat` 自检权重  

仅体验界面：直接 `start-platform.bat` 选 **1 Mock** 即可，无需权重。

---

## 三端入口

| 端 | 入口 |
|----|------|
| PC | `start-platform.bat` → http://localhost:5173 |
| 大屏 | `cd big-screen && npm run dev` → :5174 |
| 移动端 | `cd mobile && npm run dev` → :5175 |

---

## 依赖目录

所有 Python 依赖清单在 `requirements/`（`detect-bridge.txt` / `detect-full.txt`）。
