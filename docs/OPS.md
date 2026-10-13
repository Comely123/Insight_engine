# Insight Engine 运维说明（本地）

## 备份

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\backup_db.py
```

备份目录：`data/backups/`（gitignore）。备份前/后执行 `PRAGMA integrity_check`。

## 恢复

```powershell
python scripts\restore_db.py data\backups\insight_XXXX.db
```

默认会先对当前库做一次 `pre_restore` 安全备份。

## 性能基准

```powershell
python scripts\bench_local.py
```

结果写入 `data/benchmarks/bench_result_*.json`。  
**单次结果不是 SLA**，仅用于本机对比优化前后。

## 日志

路径：`data/logs/insight_engine.log`（轮转约 1MB × 5）。  
日志会尝试脱敏 `api_key` / `sk-` 等模式；仍勿把真实密钥写入命令行历史。

## 媒体依赖（ASR / FFmpeg / OCR）

公开站上传音视频且无字幕时会尝试 ASR。一键安装：

```powershell
.\scripts\setup_media.ps1
python scripts\check_media_deps.py
```

- Python：`requirements-media.txt`（faster-whisper、pytesseract、Pillow）
- 系统：FFmpeg 必须（PATH 上有 `ffmpeg`/`ffprobe`）
- 模型缓存：`data/models/faster-whisper`（gitignore）
- 环境变量：`INSIGHT_ASR_ENABLED=1`、`INSIGHT_ASR_MODEL=tiny`（见 `.env.example`）

## 媒体重复处理保护

同一 `media_id` 若已有成功处理记录，默认跳过再次处理。  
强制重跑：处理时使用 `force=True` 或 `allow_reprocess=True`。

## 密钥与模型

仅通过环境变量、本地 `.env` 或公开站会话输入（勿提交）。见 `.env.example`。

- 默认自部署：`INSIGHT_LLM_BASE_URL`（默认 `http://127.0.0.1:11434/v1`）+ `INSIGHT_LLM_MODEL`
- 可选用户自有 Key：UI 填写后加密存入 SQLite（`app_secrets`）；本地 Fernet 密钥：`data/.fernet_key`（gitignore）
- 也可环境变量 `INSIGHT_LLM_API_KEY`（勿提交）

## 公开站与管理端

```powershell
.\scripts\run_public.ps1          # 仅两页：数据采集 / 分析报告
.\scripts\run_admin.ps1
# 内部工作台（勿对公众）:
# streamlit run src\insight_engine\ui\workbench\app.py
```

原文清除：`ops/ephemeral.py` 在公开流水线分析后执行。归档表：`search_sessions`。  
采集：默认「公开资讯检索」RSS；未授权平台不在 UI 展示。DeepSeek 等 API 只做分析，不负责爬取。
