# Insight Engine

本地优先的多源趋势研究引擎（MVP **Phase 5**）。

代码仓库：[Comely123/Insight_engine](https://github.com/Comely123/Insight_engine)

## 能力概览

| 阶段 | 内容 |
|---|---|
| 1 | 导入 / SQLite FTS / 去重 / 检索 |
| 2 | 规则分析、可选 LLM、事件主张、核验、趋势 |
| 3 | 本地视频、字幕、ASR、关键帧、OCR |
| 4 | 研究工作台、行为阶段、预警、引用式报告 |
| 5 | 本地基准、备份恢复、日志脱敏、上云决策文档（**默认不上云**） |

状态见 [`PROJECT_STATUS.md`](PROJECT_STATUS.md)。运维见 [`docs/OPS.md`](docs/OPS.md)。云决策见 [`docs/CLOUD_DECISION.md`](docs/CLOUD_DECISION.md)。

## 环境

- Windows 10/11，Python 3.12+
- FFmpeg（视频阶段）
- 可选：`requirements-media.txt`（faster-whisper / pytesseract）

## 快速开始

```powershell
git clone https://github.com/Comely123/Insight_engine.git
cd Insight_engine
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\init_db.py
python scripts\load_samples.py
streamlit run src\insight_engine\ui\app.py
```

## Phase 5 常用命令

```powershell
python scripts\backup_db.py
python scripts\restore_db.py data\backups\<file>.db
python scripts\bench_local.py
pytest -q
```

## 安全

- 勿提交 `.env`、数据库、模型权重、媒体原片
- API Key 仅环境变量
- 日志尝试脱敏，仍勿把密钥打进命令行

## 已知限制

- 基准为单次本机测量，非 SLA
- 默认不上云；多人并发写需另评估
- 媒体重复处理默认跳过，需 force 重跑
