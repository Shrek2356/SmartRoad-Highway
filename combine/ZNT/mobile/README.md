# 道路值班移动端（H5）

整合原 `mobile`（UniApp 业务页）与 `mobile-preview`（Vite 预览）为单一可运行目录。

## 启动

```bash
cd mobile
npm install
npm run dev
```

浏览器会打开 `http://localhost:5175`，手机外框内可切换：首页 / 工单 / 案例 / 上报。

## 功能页

- 首页：工单提醒 + 告警弹窗
- 告警：处置页（`#/alarm`）
- 工单：整改闭环
- 案例：检索
- 上报：人工上报 + AI 辅助识别占位

## 对接入口

- 页面右上角“连接设置”：可配置业务后台、检测桥、账号密码及云端/离线/演示检测模式；保存到当前浏览器
- URL 快速配置：`?api=http://主机:8800&detect=http://主机:8810&username=safety&password=密码&profile=offline`
- 构建环境变量：`VITE_API_BASE`、`VITE_DETECT_API`、`VITE_MOBILE_USERNAME`、`VITE_MOBILE_PASSWORD`、`VITE_DETECT_PROFILE`
- 接口实现：`api/index.js`
- AI：`ai/index.js`
- Mock：`mock/index.js`

`profile` 支持 `standard`（云端）、`offline`（本地离线）、`demo`（演示）。首次运行仍保留原演示默认值；修改业务地址、账号或密码时会清除旧令牌并重新登录。
