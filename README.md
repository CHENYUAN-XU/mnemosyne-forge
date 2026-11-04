# 造枝 Mnemosyne Forge

造枝是忆界生态中的本地原创角色创作工具。输入灵感后，可通过多轮对话补全设定，也可以一次生成角色草稿。草稿支持手动修改和历史恢复，可导出 Character Card V2 JSON 和 Markdown。

## 首次启动

在 Windows PowerShell 中进入仓库根目录。需要 Python 3.11 或更新版本。

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path config.yaml)) { Copy-Item config.example.yaml config.yaml }
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

默认模型使用 DeepSeek。在 `.env` 中填入 `DEEPSEEK_API_KEY`，或在 `config.yaml` 中选择其他已配置的模型，并填写对应的环境变量。网页和注册可以在未配置密钥时启动，生成角色需要可用的模型密钥。

```powershell
.\run_dev.ps1
```

打开 [本地工作台](http://127.0.0.1:8010)，注册本地账号后开始创作。终端按 `Ctrl+C` 停止服务。端口已占用时可用 `.\run_dev.ps1 -Port 8011`，开发时可加 `-Reload`。

## 可选功能

| 功能 | 启用方式 |
| --- | --- |
| 联网搜索 | 设置 `features.search_enabled: true`。默认按 Serper、Tavily、SearXNG、DuckDuckGo、Bing 的顺序选择可用后端。 |
| 角色立绘 | 设置 `features.image_enabled: true`。可在网页选择 Pollinations、Stability、OpenAI、Seedream 或自定义接口。供应商的模型、密钥和服务可用性决定实际结果。 |
| 角色试音 | 将 `voice.provider` 设为 `elevenlabs`、`edge_tts` 或 `fish_audio`。ElevenLabs 的专属音色在试听前需要先生成并选定。 |
| 导入忆界树 | 设置 `mnemosyne_bridge.enabled: true` 和接收端 `base_url`，并启动支持角色导入的忆界树服务。需要共享登录时，再配置 `auth.shared_db_path`。 |

世界观生成保留为实验 API。设置 `features.world_enabled: true` 可在 `/docs` 调用；生成结果目前不会保存到草稿或进入角色卡。图像评审检查提示词，实际成图由用户挑选。

## 验收与备份

安装开发依赖和 Node.js 后可运行离线检查。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m scripts.check
```

如果 Node.js 不在 PATH，可先设置 `$env:NODE_EXE = "C:\Program Files\nodejs\node.exe"`。统一检查涵盖角色会话、中文卡片下载、资产、搜索和声音。用真实服务验收时，从创建一个测试角色开始，刷新并从角色库恢复，再导出并打开 JSON 卡片。已启用的图片、声音或桥接可以在同一角色上分别验收。

备份时先停止服务，再保存 `data/`、`exports/` 和本地 `config.yaml`。如果共享了忆界树账号库，请一并按忆界树的流程备份。API 密钥单独保存在本地 `.env` 中。部分历史资产记录使用绝对路径，迁移目录后应打开旧角色检查图像和音频引用。
