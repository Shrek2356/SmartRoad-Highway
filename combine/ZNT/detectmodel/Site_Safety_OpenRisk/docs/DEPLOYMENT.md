# 部署与硬化指南

## 1. 两个后端的定位

| | serve_demo.py (:8765) | app_server.py (:8800) |
|---|---|---|
| 用途 | 比赛演示、快速联调 | 正式/试运行部署 |
| 存储 | frontend目录JSON | SQLite（app_data/site_safety.db） |
| 鉴权 | 无 | 三级角色（viewer/safety_officer/admin） |
| 实时 | 60s轮询 | WebSocket推送 |
| 前端 | demo_ui（同一套，自动适配） | 同左 |

## 2. 正式启动

```bash
python app_server.py --port 8800 --db app_data/site_safety.db
```

首次启动自动从 `--data-dir`（默认 outputs/eval_v1/frontend）导入历史数据并创建种子账号；
之后SQLite是唯一事实源，每次启动自动在线备份到 `app_data/backups/`（保留最近20份），
也可由管理员随时 `POST /api/admin/backup`。

## 3. 硬化检查清单（上线前必做）

- [ ] **改默认密码**：种子账号 admin/safety/viewer（密码=账号+123）仅供首次登录；
      登录admin后在"系统配置→用户管理"逐个改密，或按需删表重建；
- [ ] **启用HTTPS**：
  ```bash
  # 自签测试证书（openssl）：
  openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -subj "/CN=site-safety"
  python app_server.py --host 0.0.0.0 --port 8443 --ssl-certfile cert.pem --ssl-keyfile key.pem
  ```
  内网正式部署建议 mkcert 或企业CA签发；公网部署置于Nginx/Caddy反代之后终止TLS；
- [ ] **绑定地址**：默认只监听127.0.0.1；对外服务显式 `--host 0.0.0.0` 并配合防火墙白名单；
- [ ] **密钥管理**：`.env`（DASHSCOPE/GLM key）与 `SAFETY_WEBHOOK_URL` 不入库不入git；
- [ ] **备份外置**：把 `app_data/backups/` 同步到独立存储（网盘/NAS），SQLite单文件拷贝即恢复；
- [ ] **知识库审核**：`knowledge_base/` 内文件全员可检索，放入前确认无敏感信息。

## 4. 数据恢复

```bash
# 停服后用备份覆盖即可
copy app_data\backups\site_safety-YYYYMMDD-HHMMSS.db app_data\site_safety.db
```

## 5. 与检测链路的衔接

- 实时流：`run_stream_inspection.py` 产出的事件可改为 `POST /api/ingest/event`
  （safety_officer及以上token）直接入库并触发WebSocket推送；
- 批量检测：`build_events.py` 产出目录后，用空库启动一次即自动导入。
