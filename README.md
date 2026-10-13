# Insight Engine

本地优先的多源趋势研究引擎。公开产品形态：**上传或合规采集 → 关键词 → 完整报告**（中间分析过程对用户隐藏；分析后立即清除原文）。

代码仓库：[Comely123/Insight_engine](https://github.com/Comely123/Insight_engine)

## 产品入口（推荐）

```powershell
git clone https://github.com/Comely123/Insight_engine.git
cd Insight_engine
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\init_db.py
# 公开站（仅两页：数据采集 / 分析报告）
streamlit run src\insight_engine\ui\public_app.py
# 或: .\scripts\run_public.ps1
```

管理端（检索归档导出，不对公众开放）：

```powershell
streamlit run src\insight_engine\ui\admin_app.py
# 或: .\scripts\run_admin.ps1
```

研发完整工作台（多页，内部用）：

```powershell
streamlit run src\insight_engine\ui\workbench\app.py
```

## 产品约定

| 项 | 说明 |
|---|---|
| 数据来源 | 用户上传（含 PDF 文献）+ 已开放公开资讯；未授权平台不展示 |
| 原文策略 | 分析完成后**立即清除**正文；保留结构化结果与短摘录 |
| 报告 | 文字发现/建议/文献共性 + 多种图表；可导出 MD/PDF |
| 模型 | 规则 / **OpenAI** / DeepSeek / 自部署 / 自定义（会话填 Key） |
| 云部署 | 优先阿里云；见 `docs/CLOUD_DECISION.md` |

## 历史阶段能力

| 阶段 | 内容 |
|---|---|
| 1 | 导入 / SQLite FTS / 去重 / 检索 |
| 2 | 规则分析、可选 LLM、事件主张、核验、趋势 |
| 3 | 本地视频、字幕、ASR、关键帧、OCR |
| 4 | 研究工作台、行为阶段、预警、引用式报告 |
| 5 | 本地基准、备份恢复、日志脱敏、上云决策文档 |

状态见 [`PROJECT_STATUS.md`](PROJECT_STATUS.md)。运维见 [`docs/OPS.md`](docs/OPS.md)。

## 环境

- Windows 10/11，Python 3.12+
- 可选 FFmpeg / `requirements-media.txt`（视频证据）
- 可选本机 Ollama / vLLM 等 OpenAI 兼容服务（长文增强）

## 测试与运维

```powershell
pytest -q
python scripts\backup_db.py
python scripts\restore_db.py data\backups\<file>.db
python scripts\bench_local.py
```

## 安全

- 勿提交 `.env`、数据库、模型权重、媒体原片、用户上传原文
- API Key 仅会话输入或环境变量，不入库
- 不做登录绕过、验证码绕过或多平台非授权爬取
