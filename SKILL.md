---
name: ms-todo
description: >-
  微软待办（Microsoft To Do）任务管理 CLI 技能，命令入口为 mstodo / ms-todo。
  用于创建、查询、更新、完成、删除任务，管理任务列表与子任务（检查项），
  支持批量删除/移动、到期日与提醒、优先级、关键词搜索、结构化 JSON 输出。
  当用户提到"待办"、"任务"、"提醒我"、"创建任务"、"今天要做的事"、"待办清单"、
  "Microsoft To Do"、"微软待办"、"子任务"、"检查项"、"待办列表"、"任务完成情况"时使用此 Skill。
---

# Microsoft To Do CLI Skill

Agent-native interface for Microsoft To Do task management.

## 调用方式

本机已通过 npm 全局安装，命令入口为 `mstodo`（等价别名 `ms-todo`）。下文示例统一使用 `mstodo`。

```bash
mstodo task add "任务" --json
ms-todo task add "任务" --json   # 等价别名
```

若 `mstodo` 不在 PATH 中（或需要源码开发调试），可直接调用已安装脚本：

```bash
python3 /Users/my-mini/.npm-global/lib/node_modules/ms-todo-cli/todo_v2.py task add "任务" --json
```

## Quick Start

```bash
# 配置和认证
mstodo config --client-id <YOUR_CLIENT_ID>
mstodo auth

# 创建任务
mstodo task add "完成报告" --body "季度总结" --due tomorrow --importance high --json

# 查询任务
mstodo task list --filter incomplete --json
mstodo task search "报告" --json

# 完成任务
mstodo task complete <task-id> --json
```

## Core Capabilities

### 列表定位（`--list` 默认值，重要）

`task` 下所有需要定位任务的子命令（`list` / `search` / `update` / `complete` / `uncomplete` / `delete` / `info` / `checklist`）
都受 `--list/-l` 影响，**默认值为 `Tasks`**：不带 `--list` 时，只作用于名为 `Tasks` 的默认列表。

- 跨列表操作必须显式指定，如 `mstodo task update <task-id> --title "新标题" --list "工作" --json`
- `task search` 同样是**单列表**搜索，默认只搜 `Tasks`；目标任务在其它列表时返回 `{"count": 0}` 而非报错，静默空结果容易被误判为"任务不存在"
- 排查顺序：先 `mstodo lists --json` 确认列表名，再带上 `--list "列表名"` 重试

### Task List Management

```bash
# 创建列表
mstodo list-create "工作任务" --json
# → {"id": "...", "name": "工作任务", "created": "..."}

# 查看所有列表（带任务统计）
mstodo lists --json
# → {"lists": [...], "count": 5}

# 重命名列表
mstodo list-rename "旧名称" "新名称" --json

# 删除列表
mstodo list-delete "列表名" --yes --json
```

### Task Creation (Full Field Support)

```bash
# 基础任务
mstodo task add "任务标题" --json

# 完整字段
mstodo task add "重要会议" \
  --body "讨论Q3目标" \
  --due "2026-08-15" \
  --reminder "2026-08-15T09:00" \
  --importance high \
  --categories "工作,会议" \
  --list "工作任务" \
  --json

# → {"id": "...", "title": "重要会议", "importance": "high", ...}
```

### Task Query (Structured Output)

```bash
# 列出所有未完成任务
mstodo task list --filter incomplete --json

# 今日任务
mstodo task list --filter today --json

# 高优先级任务
mstodo task list --filter high --json

# 已完成任务
mstodo task list --filter completed --json

# 过期任务
mstodo task list --filter overdue --json

# 按列表查询（--list 指定列表名，默认列表名为 Tasks）
mstodo task list --list "工作" --json
# → {"list": "工作", "filter": null, "count": 28, "tasks": [...]}

# 有到期日 / 有提醒 的任务
mstodo task list --list "工作" --has-due --json
mstodo task list --list "工作" --has-reminder --json

# 查看单个任务详情
mstodo task info <task-id> --json
# → {"id": "...", "title": "...", "body": "...", "due": "...", ...}

# 搜索任务
mstodo task search "关键词" --json
# → {"keyword": "关键词", "count": 3, "tasks": [...]}
```

### Task Update

```bash
# 更新标题和描述
mstodo task update <task-id> \
  --title "新标题" \
  --body "新描述" \
  --json

# 更新截止日期和优先级
mstodo task update <task-id> \
  --due "2026-08-20" \
  --importance low \
  --json

# 添加提醒
mstodo task update <task-id> \
  --reminder "2026-08-18T10:00" \
  --json
```

### Task State Management

```bash
# 完成任务
mstodo task complete <task-id> --json
# → {"id": "...", "status": "completed", "title": "..."}

# 重新打开已完成的任务
mstodo task uncomplete <task-id> --json
# → {"id": "...", "status": "notStarted", "title": "..."}

# 删除任务
mstodo task delete <task-id> --json
# → {"id": "...", "status": "deleted"}
```

### Subtask / Checklist

```bash
# 给任务添加子任务
mstodo task checklist add <task-id> "子任务标题" --list "工作任务" --json
# → {"id": "...", "displayName": "子任务标题", "isChecked": false}

# 列出任务的子任务
mstodo task checklist list <task-id> --json
# → {"task_id": "...", "count": 2, "items": [{"id": "...", "displayName": "...", "isChecked": false}, ...]}

# 勾选 / 取消勾选子任务
mstodo task checklist check <task-id> <item-id> --json
mstodo task checklist uncheck <task-id> <item-id> --json

# 删除子任务
mstodo task checklist delete <task-id> <item-id> --json
```

### Batch Operations

```bash
# 批量完成包含关键词的任务（或全部未完成）
mstodo task complete-all --match "测试" --yes --json

# 批量删除：按状态过滤（completed/incomplete/today/overdue/high）
mstodo task delete-all --filter completed --list "工作" --yes --json
mstodo task delete-all --filter overdue --list "工作" --yes --json

# 批量删除：按优先级过滤
mstodo task delete-all --importance low --list "工作" --yes --json

# 批量删除：仅匹配有子任务（检查项）的任务
mstodo task delete-all --has-checklist --list "工作" --yes --json

# 批量删除：按标题关键词匹配
mstodo task delete-all --match "临时" --list "工作" --yes --json

# 批量删除：过滤条件可组合（取交集）
mstodo task delete-all --filter completed --match "报告" --list "工作" --yes --json
# → {"deleted": 22, "failed": 0, "total": 22}

# 清空整个列表（需显式 --all，谨慎使用）
mstodo task delete-all --all --list "工作" --yes --json

# 批量移动：按过滤条件移动到目标列表
mstodo task move-all --from "工作" --to "归档" --filter completed --yes --json
mstodo task move-all --from "工作" --to "归档" --has-checklist --yes --json
# → {"moved": 5, "failed": 0, "total": 5, "from": "工作", "to": "归档"}
```

批量删除（`delete-all`）/批量移动（`move-all`）共用同套过滤参数，可组合取交集：

- `--filter/-f` 状态枚举：`incomplete` / `completed` / `today` / `overdue` / `high`（语义同 `task list --filter`）
- `--importance/-i` 优先级：`low` / `normal` / `high`
- `--has-checklist` 仅匹配有子任务（检查项）的任务
- `--has-due` 仅匹配有到期日的任务
- `--has-reminder` 仅匹配有提醒的任务
- `--match/-m` 标题关键词子串

> 移动（`move` / `move-all`）会连同子任务一起搬移，不再丢失检查项。
> 批量删除/移动是破坏性操作：交互模式会提示确认；非交互（无 TTY 或 `--json`）需显式 `--yes`，
> 否则以 `confirmation_required` 错误退出。`delete-all` 不记 undo、不可恢复；`move-all` 每次成功移动记 undo。
> 部分失败通过 `failed` 字段和非零退出码报告。

### Status and Sync

```bash
# 查看全局状态
mstodo status --json
# → {
#   "user": "用户名",
#   "lists": 5,
#   "tasks": {"total": 50, "incomplete": 20, "completed": 30, "high_priority": 5},
#   "last_sync": "2026-08-02T10:30:00",
#   "cache_size": 12345
# }

# 同步本地缓存
mstodo sync --json
# → {"status": "synced", "timestamp": "...", "lists": 5}
```

## Agent Patterns

### Pattern 1: User Says "提醒我X"

```python
# 解析意图
intent = "提醒我明天9点开会"
title = "开会"
reminder = "tomorrow 09:00"  # 或 parse_to_iso_format()

# 创建任务
result = run_cli(f'task add "{title}" --reminder "{reminder}" --json')
task_id = result['id']

# 确认
say(f"已设置提醒: {result['title']} at {result['reminder']}")
```

### Pattern 2: Daily Task Review

```python
# 获取今日任务
today_tasks = run_cli('task list --filter today --json')

# 获取过期任务
overdue = run_cli('task list --filter overdue --json')

# 获取高优先级任务
high_priority = run_cli('task list --filter high --json')

# 生成报告
report = f"""
今日任务: {today_tasks['count']} 项
过期任务: {overdue['count']} 项
高优先级: {high_priority['count']} 项
"""
```

### Pattern 3: Smart Task Creation

```python
# 用户: "帮我创建一个任务：下周五前完成报告，高优先级"
# Agent解析:
title = "完成报告"
due = "2026-08-09"  # 下周五
importance = "high"

result = run_cli(f'task add "{title}" --due {due} --importance {importance} --json')

# 验证
info = run_cli(f'task info {result["id"]} --json')
assert info['importance'] == 'high'
assert info['due'].startswith('2026-08-09')
```

### Pattern 4: Batch Cleanup

```python
# 用户: "删除所有包含'测试'的已完成任务"
# Step 1: 查询
completed = run_cli('task list --filter completed --json')
test_tasks = [t for t in completed['tasks'] if '测试' in t['title']]

# Step 2: 确认
say(f"找到 {len(test_tasks)} 个匹配任务，确认删除？")

# Step 3: 批量删除
for task in test_tasks:
    run_cli(f'task delete {task["id"]} --json')
```

## Date/Time Parsing

支持多种日期时间格式:

```bash
# 相对日期
--due today
--due tomorrow

# 绝对日期
--due 2026-08-15

# 完整时间
--reminder "2026-08-15T14:00"

# 时间（自动推到未来）
--reminder 09:00  # 如果已过9点则为明天9点
```

## Error Handling

所有错误返回结构化JSON:

```json
{
  "error": "list_not_found",
  "message": "未找到列表「工作任务」",
  "timestamp": "2026-08-02T10:30:00",
  "context": {"list_name": "工作任务"}
}
```

常见错误码:
- `no_client_id` - 未配置Client ID
- `auth_failed` - 认证失败
- `list_not_found` - 列表不存在
- `task_not_found` - 任务不存在
- `invalid_date` - 日期格式错误
- `network_error` - 网络错误
- `http_4xx` / `http_5xx` - API错误

## Output Modes

### JSON Mode (Agent-Native)

```bash
# 添加 --json 获取结构化输出
mstodo task list --json
```

使用说明：

- `--json` 是全局开关，可放在命令的任意位置（如 `task list 工作 --json` 或 `task list --json --list 工作`）。
- `task list` 额外提供 `--verbose/-v`，用于在结果中附带 `body` 详情；可与 `--json` 叠加（`task list --json --verbose`），此时每个任务对象会多出 `body` 字段。
- 两者职责不同：`--json` 控制输出为 JSON，`--verbose` 控制是否包含 `body` 详情。

所有输出字段:
- `id` - 任务ID（完整）
- `title` - 标题
- `status` - 状态 (notStarted/completed)
- `importance` - 优先级 (low/normal/high)
- `body` - 描述内容
- `due` - 截止日期
- `reminder` - 提醒时间
- `created` - 创建时间
- `lastModified` - 最后修改时间
- `completed` - 完成时间
- `categories` - 分类列表

### Human-Readable Mode

```bash
# 不加 --json 则为人类可读格式
mstodo task list
# → 
# 📋 Tasks  (5 项)
#
#   [ ] ⚡重要会议
#       📅 截止: 2026-08-15T09:00
#       🔔 提醒: 2026-08-15T09:00
#       ID: AQMkADAwATNiZmYAZC02...
```

## Prerequisites

```bash
pip install msal requests
```

运行前置条件：

1. 首次使用先配置并认证（见下方 "Azure App Registration"），否则会报 `no_client_id` / `auth_failed`。
2. 执行前可先用 `mstodo status --json` 检查认证与同步状态。
3. 运行需要读写 `~/.config/ms-todo/`（缓存、token、undo_log）。在受限/sandbox 环境下若报 `PermissionError: ... .undo_log.json.tmp`，请授予该目录写权限（或关闭沙箱限制）。
4. 若 `mstodo` / `python3` 报 `command not found`，多半是终端 PATH 注入不完整（命令其实已安装），用绝对路径兜底即可：
   - `mstodo`：`/Users/my-mini/.npm-global/bin/mstodo`
   - `python3`：`/opt/homebrew/opt/python@3.10/libexec/bin/python3`
   - `node`：`/opt/homebrew/bin/node`

   例：`/opt/homebrew/opt/python@3.10/libexec/bin/python3 /Users/my-mini/.npm-global/lib/node_modules/ms-todo-cli/todo_v2.py task list --json`

## Azure App Registration

1. 访问 https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps
2. 新建应用注册
3. 选择 "Accounts in any organizational directory and personal Microsoft accounts"
4. 重定向URI: "Public client/native (mobile & desktop)" → http://localhost
5. API权限: Microsoft Graph → Delegated → Tasks.ReadWrite, User.Read
6. 复制 Application (client) ID

```bash
mstodo config --client-id <YOUR_CLIENT_ID>
mstodo auth
```

## State Management (H = S, C, I, R, V, D)

### S - State
```
~/.config/ms-todo/
├── config.json        # Client ID配置
├── token_cache.bin    # MSAL token缓存
├── cache.json         # 本地任务缓存（带时间戳）
└── undo_log.json      # 操作历史（最多50条）
```

### C - Commands
54 个命令涵盖完整 CRUD + 批量操作 + 状态管理

### I - Inspection
所有命令支持 `--json`，输出结构化数据

### R - Rendering
委托给 Microsoft Graph API（云端真实数据）

### V - Verification
- 结构化错误处理
- API调用自动重试
- 字段验证（日期格式、优先级枚举）

### D - Discovery
- 本 SKILL.md 文档
- `--help` 内置帮助
- 结构化错误信息

## Comparison with Original todo.py

| 功能 | todo.py | todo_v2.py |
|------|---------|-----------|
| 命令数量 | 6 | 54 |
| JSON输出 | ❌ | ✅ |
| 完整CRUD | ❌ | ✅ |
| 列表管理 | ❌ | ✅ |
| 字段覆盖率 | 15% | 90%+ |
| 批量操作 | ❌ | ✅ |
| 错误处理 | Traceback | 结构化JSON |
| 状态管理 | Token only | 缓存 + Undo |
| Agent-Ready | ❌ | ✅ |

## License

MIT
