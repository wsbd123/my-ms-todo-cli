# Microsoft To Do CLI

> 原生支持 Agent 的 Microsoft To Do 命令行界面

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个强大的命令行工具，用于在终端中管理 Microsoft To Do 任务。完美适配自动化、AI Agent 和生产力工作流。

> **关于这个仓库**
>
> 这是 [zhenghaolong/ms-todo-cli](https://github.com/zhenghaolong/ms-todo-cli)
> 的个人 fork，自用为主，**未发布到 npm**。相对上游有大量本地改动
> （分页、原子写入、重试策略、undo 栈、非交互确认、JSON 错误契约等）。
>
> npm 上的 `ms-todo-cli` 是上游作者的包，内容与本仓库**不同**，
> 请勿用 `npm install -g ms-todo-cli` 安装本项目 —— 装到的会是上游版本。

## ✨ 功能特性

- 🚀 **快速设置** - 4 个简单步骤即可开始使用
- 🤖 **原生 Agent 支持** - 每个命令都输出 JSON；错误写入 stderr，失败时返回非零退出码
- 📋 **完整 CRUD** - 全功能任务和列表管理
- ⚡ **批量操作** - 一次完成或删除多个任务
- ↩️ **撤销功能** - 撤销最近的创建/更新/删除/完成/移动/重命名操作
- 🔄 **快照导出** - `mstodo sync` 将所有列表/任务的本地快照写入 `cache.json`
- 🔒 **默认隐私保护** - 凭证以 `0600` 权限存储，原子化写入
- 🎨 **精美界面** - 彩色、表情符号丰富的终端输出

## 📦 Installation

从本仓库直接全局安装（本项目未发布到 npm）：

```bash
npm install -g github:wsbd123/my-ms-todo-cli
```

或者克隆后从本地安装，便于修改代码：

```bash
git clone https://github.com/wsbd123/my-ms-todo-cli.git
cd my-ms-todo-cli
npm install -g .
```

安装后会提供 `mstodo` 和 `ms-todo` 两个命令。接着运行 `mstodo setup`
安装 Python 依赖（`npm install` **不会**自动装 Python 依赖）。

## 🚀 Quick Start

### 第一步：配置

```bash
mstodo config init
```

该命令将引导你注册 Azure 应用程序并输入你的 Client ID。

**Azure 注册步骤：**
1. 访问 [Azure 门户](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps)
2. 点击"新建注册"
3. 设置：
   - **名称**："My To Do CLI"
   - **受支持的账户类型**："个人 Microsoft 账户"
   - **重定向 URI**："公共客户端/本机" → `http://localhost`
4. 进入"API 权限"→ 添加：
   - `Tasks.ReadWrite`
   - `User.Read`
5. 复制**应用程序(客户端) ID**
6. 在 `mstodo config init` 提示时粘贴该 ID

### 第二步：登录

```bash
mstodo auth login
```

CLI 将：
- 显示设备码和登录 URL
- 自动将设备码复制到剪贴板并打开浏览器
- 等待你完成登录，然后确认成功

> **工作/学校账户**：默认端点针对个人 Microsoft 账户。如果需要用工作或学校账户登录，请先设置权限机构：
>
> ```bash
> mstodo config --authority "https://login.microsoftonline.com/common"
> ```

### 第三步：使用

```bash
# 列出所有任务
mstodo task list

# 创建任务
mstodo task add "Complete report" --due tomorrow --importance high

# 搜索任务
mstodo task search "report"

# 完成任务
mstodo task complete <task-id>
```

## 📖 使用说明

### 任务管理

```bash
# 创建包含完整详情的任务
mstodo task add "Team meeting" \
  --body "Discuss Q3 goals" \
  --due "2026-08-15" \
  --reminder "2026-08-15T09:00" \
  --importance high \
  --categories "work,meetings" \
  --json

# 重复任务（需要设置到期日期）
mstodo task add "Standup" --due tomorrow --recurrence "weekly:mon,wed,fri"
# 重复格式：daily | weekly:mon,wed | monthly:17 | yearly:09-17
# 工作日接受英文 (mon/monday) 或中文 (周一)。

# 按过滤条件列出任务
mstodo task list --filter incomplete
mstodo task list --filter today
mstodo task list --filter high
mstodo task list --filter overdue

# 更新任务（现已支持分类/重复）
mstodo task update <task-id> --title "New title" --importance low
mstodo task update <task-id> --categories "work,urgent"
# 通过传递 none/null/clear 来清除字段：
mstodo task update <task-id> --due none --reminder clear

# 完成/重新开启/删除
mstodo task complete <task-id>
mstodo task uncomplete <task-id>
mstodo task delete <task-id>

# 将任务移动到另一个列表（参见下面关于 --list 的说明）
mstodo task move <task-id> --from "Inbox" --to "Work"

# 子任务 / 检查项
mstodo task checklist add <task-id> "找房" --list "Work"
mstodo task checklist list <task-id> --list "Work"
mstodo task checklist check <task-id> <item-id>
mstodo task checklist uncheck <task-id> <item-id>
mstodo task checklist delete <task-id> <item-id>

# 撤销最后一次的创建/更新/删除/完成/重新开启/移动/重命名操作
mstodo undo
```

> **所有任务命令都在单个列表上运行**（默认：`Tasks`）。由于任务 ID 的作用范围限于其列表，当任务不在默认列表中时，请将 `--list "<name>"` 传递给 `info` / `update` / `complete` / `delete` / `move`。
> 参见 [已知限制](#-known-limitations)。

### 列表管理

```bash
# 创建列表
mstodo list-create "Work Tasks"

# 查看所有列表
mstodo lists

# 重命名列表
mstodo list-rename "Old Name" "New Name"

# 删除列表
mstodo list-delete "List Name" --yes
```

### 批量操作

```bash
# 完成标题包含 "test" 的所有未完成任务
mstodo task complete-all --match "test" --yes

# 删除标题包含 "draft" 的所有任务
mstodo task delete-all --match "draft" --yes
```

> `--filter` 在这里匹配任务**标题**的子字符串（不是状态）。
> 破坏性批量命令在交互模式下会提示确认；
> 在非交互式上下文中（无 TTY 或 `--json`），你**必须**传递 `--yes`，
> 否则命令会以 `confirmation_required` 错误退出，而不是挂在提示上。
> 部分失败通过结果中的 `failed` 字段和非零退出码报告。

### 状态和同步

```bash
# 检查身份验证状态
mstodo auth status

# 查看详细状态
mstodo status

# 登出（删除本地令牌缓存）
mstodo auth logout

# 将所有列表/任务的本地快照导出到 cache.json
mstodo sync
```

## 🤖 Agent 集成

所有命令都支持 `--json` 标志以获得结构化输出。它可以出现在命令行的**任何位置**（子命令前或后）：

```bash
mstodo task list --json
mstodo --json task list   # 等价
```

**输出协议：**
- 成功时，**stdout** 包含恰好一个 JSON 文档。
- 出错时，结构化错误写入 **stderr**，进程
  以**非零**码退出。（因此 `json.loads(stdout)` 无需
  处理混合的错误/结果输出。）

**输出示例：**

```json
{
  "tasks": [
    {
      "id": "AQMkADAwATNi...",
      "title": "Complete report",
      "status": "notStarted",
      "importance": "high",
      "due": "2026-08-15T00:00:00",
      "created": "2026-08-03T10:30:00"
    }
  ],
  "count": 1
}
```

### Python 集成

```python
import subprocess
import json

def mstodo(command: str) -> dict:
    result = subprocess.run(
        f"mstodo {command} --json",
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # 错误是 stderr 上的结构化 JSON
        try:
            raise RuntimeError(json.loads(result.stderr))
        except json.JSONDecodeError:
            raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)

# 创建任务
task = mstodo('task add "Meeting" --due tomorrow')
print(f"Created: {task['id']}")

# 列出今天的任务
today = mstodo('task list --filter today')
print(f"Today: {today['count']} tasks")
```

## 🔧 配置

配置存储在 `~/.config/ms-todo/` 中（目录 `0700`，敏感
文件 `0600`，原子化写入）：

```
~/.config/ms-todo/
├── config.json        # Client ID，可选的权限机构
├── token_cache.bin    # 身份验证令牌 (0600)
├── cache.json         # `mstodo sync` 写入的快照
└── undo_log.json      # `mstodo undo` 的操作历史
```

`config.json` 键：

| 键         | 描述                                                        |
|-------------|--------------------------------------------------------------------|
| `client_id` | Azure 应用程序(客户端) ID                                       |
| `authority` | 登录端点；默认为个人账户。对于工作/学校账户设置为 `.../common`（`mstodo config --authority ...`） |

## 🔐 Azure 应用程序设置

**所有用户必须：**

1. 访问 [Azure 门户](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps)
2. 点击"新建注册"
3. 设置：
   - **名称**："My To Do CLI"（或你喜欢的任何名称）
   - **受支持的账户类型**："个人 Microsoft 账户"
   - **重定向 URI**："公共客户端/本机" → `http://localhost`
4. 进入"API 权限"→ 添加：
   - `Tasks.ReadWrite`
   - `User.Read`
5. 复制**应用程序(客户端) ID**
6. 运行：`mstodo config init` 并粘贴 ID

**注意：** 每个用户都需要自己的 Azure 应用程序注册。这确保了你的数据安全并避免了 API 速率限制。

## ⚠️ 已知限制

- **单列表作用域。** `task list` 和 `task search` 一次对一个列表进行操作（默认 `Tasks`），
  任务 ID 仅在其列表内有意义。
  目前没有跨列表查询或基于 ID 的自动解析 — 在处理其他列表中的任务时传递
  `--list "<name>"`。
- **`task move` 是复制 + 删除。** Microsoft Graph 没有跨列表移动 API，
  所以移动操作在目标列表中创建新任务并删除原始任务。任务 **ID 会更改**，
  服务器管理的字段如 `createdDateTime` 不会被保留。（该操作可通过 `mstodo undo` 撤销。）
- **`lists` / `status` 对每个列表发出一个请求。** 在多个列表中列出任务计数时
  每个列表发出一个请求，因此这些命令按列表数量扩展。

## 📚 文档

- [QUICKSTART.md](./QUICKSTART.md) - 详细的快速入门指南
- [SKILL.md](./SKILL.md) - Agent 完整 API 参考

## 🛠️ 要求

- **Node.js** 14.0.0 或更高版本
- **Python** 3.7 或更高版本
- **pip** 用于 Python 包管理

## 🐛 故障排除

### 未找到 Python

```bash
# 安装 Python 3
# macOS
brew install python3

# Windows
# 从 https://www.python.org/downloads/ 下载

# Linux
sudo apt install python3 python3-pip
```

### 身份验证失败

```bash
# 重新身份验证
mstodo auth login

# 检查状态
mstodo auth status
```

### 依赖项错误

Python 依赖项由 `mstodo setup` 安装（它们**不会**在 `npm install`
期间自动安装）。如果 `setup` 因你的环境
外部管理 (PEP 668) 或 virtualenv 拒绝 `--user` 而失败，请手动安装它们 — 
最好在 virtualenv 中：

```bash
mstodo setup

# 或手动安装
python3 -m pip install -r requirements.txt
```

## 📄 许可证

MIT © Haolong Zheng（原作者）

本仓库为个人 fork，沿用上游的 MIT 许可与著作权署名，见 [LICENSE](LICENSE)。

## 🔗 链接

- [本仓库](https://github.com/wsbd123/my-ms-todo-cli)
- [上游项目](https://github.com/zhenghaolong/ms-todo-cli) · [上游 npm 包](https://www.npmjs.com/package/ms-todo-cli)（与本仓库内容不同）

---

**用心为开发者和 AI Agent 打造 ❤️**
