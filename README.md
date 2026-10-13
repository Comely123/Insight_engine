# Insight Engine

本地优先的多源趋势研究引擎。公开产品形态：**上传或合规采集 → 关键词 → 完整报告**（中间分析过程对用户隐藏；分析完成后立即清除原文）。

代码仓库：[Comely123/Insight_engine](https://github.com/Comely123/Insight_engine)

## 产品入口（推荐）

**一键安装并启动**（含音视频 ASR / FFmpeg / Whisper；建议管理员 PowerShell）：

```powershell
git clone https://github.com/Comely123/Insight_engine.git
cd Insight_engine
powershell -ExecutionPolicy Bypass -File .\一键安装启动.ps1
```

脚本会：建虚拟环境 → 装依赖 → 装 FFmpeg（及 OCR）→ 下载 Whisper 模型 → 初始化数据库 → 打开公开站（`http://localhost:8501`）。  
只要安装不启动：`.\一键安装启动.ps1 -NoLaunch`

分步手动安装（同上效果）：

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

> **说明**：一键脚本已包含音视频转写栈。若只用手动步骤，基础 `pip install` **不含** ASR/FFmpeg，见下一节。

管理端（检索归档导出，不对公众开放）：

```powershell
streamlit run src\insight_engine\ui\admin_app.py
# 或: .\scripts\run_admin.ps1
```

研发完整工作台（多页，内部用）：

```powershell
streamlit run src\insight_engine\ui\workbench\app.py
```

## 可选：音视频 ASR / FFmpeg / OCR（快速脚本）

上传 **视频/音频** 且没有同名字幕（`.srt` / `.vtt`）时，系统会尝试 **ASR**（`faster-whisper`）。这需要额外系统组件与模型缓存。

一键安装（推荐）：

```powershell
.\scripts\setup_media.ps1
# 只要包装包、不预拉模型：
.\scripts\setup_media.ps1 -SkipModelDownload
# 换模型尺寸（默认 tiny，体积小）：
.\scripts\setup_media.ps1 -ModelSize base
```

检查是否就绪：

```powershell
python scripts\check_media_deps.py
```

| 依赖 | 是否必须 | 用途 | 怎么装 |
|---|---|---|---|
| `requirements.txt` | 是 | 公开站、PDF 文献、报告导出 | `pip install -r requirements.txt` |
| **FFmpeg**（`ffmpeg`/`ffprobe`） | 音视频建议必须 | 探测媒体、抽音频/关键帧 | `winget install Gyan.FFmpeg` 或 `choco install ffmpeg` |
| `requirements-media.txt`（含 **faster-whisper**） | 无字幕 ASR 时必须 | 语音转文字 | 由 `setup_media.ps1` 安装 |
| Whisper 权重 | ASR 首次需要 | 模型文件缓存到 `data/models/faster-whisper`（已 gitignore） | `setup_media.ps1` 预下载，或首次转写时自动下 |
| **Tesseract** + `pytesseract` | 可选 | 关键帧 OCR（公开站默认不强制） | `winget install UB-Mannheim.TesseractOCR` |

本地 `.env` 建议（勿提交真实密钥；模板见 `.env.example`）：

```env
INSIGHT_ASR_ENABLED=1
INSIGHT_ASR_MODEL=tiny
# INSIGHT_OCR_ENABLED=1
```

关闭 ASR：`INSIGHT_ASR_ENABLED=0`。无 ASR 时请同时上传与媒体**同名**的字幕文件（如 `clip.mp4` + `clip.srt`）。

## 产品约定

| 项 | 说明 |
|---|---|
| 数据来源 | 用户上传 + 公开资讯 RSS + 免费学术 API（OpenAlex / Semantic Scholar / Crossref / arXiv / Europe PMC / PubMed / OpenAIRE）；CORE、YouTube 可自填 API Key；未授权社交平台不展示 |
| 原文策略 | 分析完成后**立即清除**正文；保留结构化结果与短摘录 |
| 报告 | 文字发现/建议/文献共性 + 多种图表；可导出 MD/PDF |
| 模型 | 规则 / OpenAI / DeepSeek / 通义 / 智谱 / Kimi / 豆包 / 混元 / 百川 / Yi / 硅基流动 / 自部署 |
| API Key | 提交分析后**加密写入本地库**（Fernet；密钥文件 `data/.fernet_key`，勿提交）；下次默认沿用 |
| 异步任务 | 「开始分析」立即返回；切换页面后台继续，结果在「分析报告」自动刷新 |
| 文献批次 | 自动拆解共性 / 差异 / 创新线索，并导出 CSV 对照表 |
| 加速 | 逐篇仅规则分析；大模型只做一次汇总。音视频 ASR 可用 GPU：`INSIGHT_ASR_DEVICE=cuda` |
| 上传 | 支持 PDF 文献（`pypdf` 抽文本）；扫描件纯图片 PDF 需先 OCR |
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
- 基础：`requirements.txt`（含 `pypdf`、`fpdf2` 等）
- 音视频可选：FFmpeg + `.\scripts\setup_media.ps1`
- 可选本机 Ollama / vLLM，或 UI 内填 OpenAI / DeepSeek Key

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
