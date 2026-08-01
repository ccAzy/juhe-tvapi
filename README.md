# juhe-tvapi

聚合 TV API 源配置管理项目。定时从多个上游源抓取配置，自动去重、测速、过滤成人源，生成可供 TV 播放器（如影视仓 / TvBox 类应用）直接使用的 `config.json`。

## 功能特性

- 🌐 **多上游聚合**：从多个远程源抓取配置（智能识别 Base58 编码 / 明文 JSON / TVBox `sites` 格式 / 多仓 `urls` 递归展开，列表自动转字典）
- 🔍 **白名单过滤**：仅保留 `cache_time` 与 `api_site` 两个顶层键
- ✂️ **深度去重**：标准化 URL（忽略空格、末尾斜杠及 http/https 差异）去除重复源
- ⚡ **并发测速**：20 线程并发检测 API 连通性与响应格式，自动移除失效源
- 🚫 **成人源过滤**：按关键词识别并直接删除成人源，仅保留正常源
- 🤖 **全自动流水线**：GitHub Actions 每日 UTC 0 点自动执行并提交更新

## 文件结构

```
├── update_config.py            # 步骤1：抓取上游并合并生成 config.json
├── test_api_availability.py    # 步骤2：深度去重 + 并发测速，清理失效源
├── separate_sources.py         # 步骤3：按关键词识别并删除成人源
├── config.json                 # 过滤后的正常源配置
├── requirements.txt            # 依赖：requests、base58
└── .github/workflows/update_config.yml  # 每日自动更新流水线
```

## 工作流程

流水线按以下顺序执行（对应 `update_config.yml`）：

1. **`update_config.py`** — 抓取 `URLS_TO_FETCH` 中的上游源，合并去重键，自动提取 `detail` 字段，生成 `config.json`
2. **`test_api_availability.py --yes`** — 深度去重 + 并发测速，移除 `config.json` 中的失效源
3. **`separate_sources.py`** — 按 `ADULT_KEYWORDS` 关键词识别并删除成人源，仅将正常源覆盖写回 `config.json`（被删除的源会在日志中列出）
4. 提交并推送 `config.json`

## 本地使用

```bash
# 安装依赖
pip install -r requirements.txt

# 步骤1：生成配置
python update_config.py

# 步骤2：测试并清理 config.json（-y 跳过交互确认）
python test_api_availability.py --yes

# 步骤3：过滤成人源
python separate_sources.py
```

> 生成的 `config.json` 可直接配置到支持 TV API 的播放器中使用。

## 配置说明

### 修改上游源

- **方式一（推荐）**：设置环境变量 `SOURCE_URLS`，支持逗号或换行分隔多个 URL：

  ```bash
  # PowerShell
  $env:SOURCE_URLS = "https://example.com/a.json,https://example.com/b.json"
  python update_config.py
  ```

- **方式二**：直接编辑 `update_config.py` 中的 `DEFAULT_URLS_TO_FETCH` 列表。

默认上游源（9 个）：

| 上游 | 格式 | 说明 |
|------|------|------|
| cmliu/cmliu | Base58 | 聚合配置 |
| 666zmy/MoonTV | 明文 JSON | appleCMS 标准格式 |
| hafrey1/LunaTV-config | Base58 | 聚合配置 |
| rapier15sapper/ew | 明文 JSON 列表 | 列表自动转字典 |
| anaer/Meow | TVBox `sites` 字段 | 约 77 个站点，自动转换为 `api_site` |
| 小盒子4K (xhztv.top) | TVBox `sites` 字段 | 影视仓配置 |
| 小盒子多仓 (xhztv.top/dc) | 多仓 `urls` 字段 | 18 个子配置，递归展开 |
| 挺好分享多仓 (ztha.top) | 多仓 `urls` 字段 | 32 个子配置，递归展开 |
| 拾光多仓 (xmbjm.fh4u.org) | 多仓 `urls` 字段 | 多个子配置，递归展开 |

> 多仓展开的每个子配置源名会带上子配置名前缀（如 `肥猫·xxx`），便于区分来源；多仓嵌套递归深度上限为 3 层（`MAX_MULTI_STORE_DEPTH`），防止无限递归。

### 支持的配置格式

`update_config.py` 会自动识别以下四种上游格式并统一转换为 `api_site` 字典：

1. **appleCMS 标准**：顶层含 `api_site` 字典（`{key: {name, api}}`）
2. **纯列表**：顶层为 JSON 数组（`[{name, api, ...}]`），自动提取 `api`/`baseUrl`/`url` 字段
3. **TVBox `sites` 字段**：顶层含 `sites` 列表（`[{key, name, api}]`），自动跳过 JS 规则 / jar 包等非 http 采集接口源
4. **多仓 `urls` 字段**：顶层含 `urls` 列表（`[{name, url}]`），自动递归抓取每个子配置并合并

> 自动清洗 JSON 头部常见的 BOM（`\ufeff`）与 `//`/`#` 注释行；解析失败时自动提取第一个完整 JSON 对象（容忍尾部杂散内容）。

### 调整过滤关键词

编辑 `separate_sources.py` 中的 `ADULT_KEYWORDS` 列表（不区分大小写），命中任一关键词的源将被直接删除。

### 调整测速参数

`test_api_availability.py` 支持 `--config` 指定配置文件路径，`-y/--yes` 跳过所有交互确认（供 CI 使用）。

## GitHub Actions 自动更新

推送 `main` 分支或每日 UTC 0 点（北京时间 8:00）自动触发流水线，检测到配置变化后自动提交。

手动触发：仓库 **Actions → Update, Test, and Filter Configs → Run workflow**。