# Microsoft To Do CLI Skill

Agent-native interface for Microsoft To Do task management.

## 调用方式

本工具有两种等价的调用入口，下文示例统一使用 `python todo_v2.py`，可任意替换为 `mstodo` 或 `ms-todo`：

```bash
# 方式一：源码运行（开发时）
python todo_v2.py task add "任务" --json

# 方式二：npm 全局安装后的命令（二选一）
mstodo task add "任务" --json
ms-todo task add "任务" --json
```

## Quick Start

```bash
# 配置和认证
python todo_v2.py config --client-id <YOUR_CLIENT_ID>
python todo_v2.py auth

# 创建任务
python todo_v2.py task add "完成报告" --body "季度总结" --due tomorrow --importance high --json

# 查询任务
python todo_v2.py task list --filter incomplete --json
python todo_v2.py task search "报告" --json

# 完成任务
python todo_v2.py task complete <task-id> --json
```

## Core Capabilities

### Task List Management

```bash
# 创建列表
python todo_v2.py list-create "工作任务" --json
# → {"id": "...", "name": "工作任务", "created": "..."}

# 查看所有列表（带任务统计）
python todo_v2.py lists --json
# → {"lists": [...], "count": 5}

# 重命名列表
python todo_v2.py list-rename "旧名称" "新名称" --json

# 删除列表
python todo_v2.py list-delete "列表名" --yes --json
```

### Task Creation (Full Field Support)

```bash
# 基础任务
python todo_v2.py task add "任务标题" --json

# 完整字段
python todo_v2.py task add "重要会议" \
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
python todo_v2.py task list --filter incomplete --json

# 今日任务
python todo_v2.py task list --filter today --json

# 高优先级任务
python todo_v2.py task list --filter high --json

# 已完成任务
python todo_v2.py task list --filter completed --json

# 过期任务
python todo_v2.py task list --filter overdue --json

# 按列表查询（--list 指定列表名，默认列表名为 Tasks）
python todo_v2.py task list --list "工作" --json
# → {"list": "工作", "filter": null, "count": 28, "tasks": [...]}

# 查看单个任务详情
python todo_v2.py task info <task-id> --json
# → {"id": "...", "title": "...", "body": "...", "due": "...", ...}

# 搜索任务
python todo_v2.py task search "关键词" --json
# → {"keyword": "关键词", "count": 3, "tasks": [...]}
```

### Task Update

```bash
# 更新标题和描述
python todo_v2.py task update <task-id> \
  --title "新标题" \
  --body "新描述" \
  --json

# 更新截止日期和优先级
python todo_v2.py task update <task-id> \
  --due "2026-08-20" \
  --importance low \
  --json

# 添加提醒
python todo_v2.py task update <task-id> \
  --reminder "2026-08-18T10:00" \
  --json
```

### Task State Management

```bash
# 完成任务
python todo_v2.py task complete <task-id> --json
# → {"id": "...", "status": "completed", "title": "..."}

# 重新打开已完成的任务
python todo_v2.py task uncomplete <task-id> --json
# → {"id": "...", "status": "notStarted", "title": "..."}

# 删除任务
python todo_v2.py task delete <task-id> --json
# → {"id": "...", "status": "deleted"}
```

### Subtask / Checklist

```bash
# 给任务添加子任务
python todo_v2.py task checklist add <task-id> "子任务标题" --list "工作任务" --json
# → {"id": "...", "displayName": "子任务标题", "isChecked": false}

# 列出任务的子任务
python todo_v2.py task checklist list <task-id> --json
# → {"task_id": "...", "count": 2, "items": [{"id": "...", "displayName": "...", "isChecked": false}, ...]}

# 勾选 / 取消勾选子任务
python todo_v2.py task checklist check <task-id> <item-id> --json
python todo_v2.py task checklist uncheck <task-id> <item-id> --json

# 删除子任务
python todo_v2.py task checklist delete <task-id> <item-id> --json
```

### Batch Operations

```bash
# 批量完成包含关键词的任务
python todo_v2.py task complete-all --match "测试" --yes --json
# → {"completed": 5, "total": 5}

# 批量删除匹配的任务
python todo_v2.py task delete-all --match "临时" --yes --json
# → {"deleted": 3, "total": 3}

# 完成所有未完成任务（需确认）
python todo_v2.py task complete-all --json
```

### Status and Sync

```bash
# 查看全局状态
python todo_v2.py status --json
# → {
#   "user": "用户名",
#   "lists": 5,
#   "tasks": {"total": 50, "incomplete": 20, "completed": 30, "high_priority": 5},
#   "last_sync": "2026-08-02T10:30:00",
#   "cache_size": 12345
# }

# 同步本地缓存
python todo_v2.py sync --json
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
python todo_v2.py task list --json
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
python todo_v2.py task list
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
2. 执行前可先用 `python todo_v2.py status --json` 检查认证与同步状态。
3. 运行需要读写 `~/.config/ms-todo/`（缓存、token、undo_log）。在受限/sandbox 环境下若报 `PermissionError: ... .undo_log.json.tmp`，请授予该目录写权限（或关闭沙箱限制）。

## Azure App Registration

1. 访问 https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps
2. 新建应用注册
3. 选择 "Accounts in any organizational directory and personal Microsoft accounts"
4. 重定向URI: "Public client/native (mobile & desktop)" → http://localhost
5. API权限: Microsoft Graph → Delegated → Tasks.ReadWrite, User.Read
6. 复制 Application (client) ID

```bash
python todo_v2.py config --client-id <YOUR_CLIENT_ID>
python todo_v2.py auth
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
