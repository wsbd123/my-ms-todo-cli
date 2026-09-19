# Microsoft To Do CLI v2 - 快速开始

## 🚀 5分钟上手

### 步骤 1: 安装依赖

```bash
cd ~/ms-todo-cli
pip install -r requirements.txt
```

### 步骤 2: 获取 Azure Client ID

1. 访问 https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps
2. 点击 "新建注册"
3. 填写：
   - **名称**: "My To Do CLI"
   - **支持的账户类型**: "任何组织目录中的账户和个人 Microsoft 账户"
   - **重定向URI**: 选择 "公共客户端/原生(移动和桌面)" → `http://localhost`
4. 创建后，复制 **应用程序(客户端) ID**
5. 进入 "API 权限" → "添加权限" → "Microsoft Graph" → "委托的权限"
   - 添加: `Tasks.ReadWrite`
   - 添加: `User.Read`
6. 点击 "授予管理员同意"

### 步骤 3: 配置和认证

```bash
# 配置 Client ID
python todo_v2.py config --client-id <粘贴你的Client ID>

# 认证（会弹出设备码登录）
python todo_v2.py auth
# 按提示打开浏览器，输入设备码，登录你的 Microsoft 账号
```

### 步骤 4: 开始使用

```bash
# 创建第一个任务
python todo_v2.py task add "测试任务" --json

# 查看所有任务
python todo_v2.py task list --json

# 查看系统状态
python todo_v2.py status --json
```

---

## 📖 常用命令速查

### 任务管理

```bash
# 创建任务（完整字段）
python todo_v2.py task add "写周报" \
  --body "总结本周工作" \
  --due tomorrow \
  --importance high \
  --reminder "09:00" \
  --json

# 列出未完成任务
python todo_v2.py task list --filter incomplete --json

# 搜索任务
python todo_v2.py task search "周报" --json

# 完成任务
python todo_v2.py task complete <task-id> --json

# 更新任务
python todo_v2.py task update <task-id> --title "新标题" --json

# 删除任务
python todo_v2.py task delete <task-id> --json
```

### 列表管理

```bash
# 创建列表
python todo_v2.py list-create "工作任务" --json

# 查看所有列表
python todo_v2.py lists --json

# 重命名列表
python todo_v2.py list-rename "旧名称" "新名称" --json

# 删除列表
python todo_v2.py list-delete "列表名" --yes --json
```

### 批量操作

```bash
# 批量完成包含"测试"的任务
python todo_v2.py task complete-all --match "测试" --yes --json

# 批量删除已完成任务
python todo_v2.py task list --filter completed --json  # 先查看
python todo_v2.py task delete-all --match "..." --yes --json
```

---

## 🤖 Agent 使用示例

### Python 集成

```python
import subprocess
import json

def todo(command: str) -> dict:
    """调用 CLI 并返回 JSON"""
    cmd = f"python ~/ms-todo-cli/todo_v2.py {command} --json"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return json.loads(result.stdout)

# 使用示例
# 1. 创建任务
new_task = todo('task add "开会" --reminder "14:00"')
print(f"创建任务: {new_task['id']}")

# 2. 查询今日任务
today = todo('task list --filter today')
print(f"今天有 {today['count']} 个任务")

# 3. 完成任务
result = todo(f"task complete {new_task['id']}")
print(f"任务状态: {result['status']}")
```

### Bash 脚本

```bash
#!/bin/bash

# 每日任务统计
TODO="python ~/ms-todo-cli/todo_v2.py"

echo "📊 今日任务统计"
echo "==============="

# 获取状态
STATUS=$($TODO status --json)
INCOMPLETE=$(echo $STATUS | jq -r '.tasks.incomplete')
HIGH=$(echo $STATUS | jq -r '.tasks.high_priority')

echo "未完成: $INCOMPLETE 项"
echo "高优先级: $HIGH 项"

# 列出今日任务
echo -e "\n📅 今日任务:"
$TODO task list --filter today --json | jq -r '.tasks[] | "  - \(.title)"'
```

---

## 🔍 常见问题

### Q: 如何获取完整的 task ID？

**问题**: `task list` 输出的 ID 被截断了

**解决方案**: 使用 JSON 输出
```bash
python todo_v2.py task list --json | jq -r '.tasks[0].id'
# → AQMkADAwATNiZmYAZC02YzY1LWZkMzYtMDACLTAwCgBGAAADww_fnLMp40SBS9j14nap7wcADwf...
```

### Q: 认证失败怎么办？

1. 检查 Client ID 是否正确
2. 确认 API 权限已授予
3. 尝试重新认证：
```bash
python todo_v2.py auth
```

### Q: 如何查看所有字段？

```bash
# 使用 task info 查看单个任务的完整信息
python todo_v2.py task info <task-id> --json | jq
```

### Q: 如何在特定列表中操作？

所有 `task` 命令都支持 `--list` 参数：
```bash
python todo_v2.py task add "任务" --list "工作任务" --json
python todo_v2.py task list --list "工作任务" --json
```

### Q: 日期格式支持哪些？

```bash
--due today              # 今天
--due tomorrow           # 明天
--due 2026-08-15         # 指定日期
--reminder 09:00         # 今天或明天9点
--reminder "2026-08-15T14:00"  # 完整时间
```

---

## 📊 性能提示

### 1. 使用本地缓存

```bash
# 首次同步
python todo_v2.py sync --json

# 之后查询会更快（使用缓存）
python todo_v2.py status --json
```

### 2. 批量操作替代循环

❌ **不推荐**:
```bash
for id in $(get_task_ids); do
    python todo_v2.py task complete $id --json
done
```

✅ **推荐**:
```bash
python todo_v2.py task complete-all --match "关键词" --yes --json
```

### 3. 使用 jq 处理 JSON

```bash
# 安装 jq
brew install jq  # macOS
sudo apt install jq  # Linux

# 提取特定字段
python todo_v2.py task list --json | jq -r '.tasks[] | "\(.title) - \(.importance)"'

# 过滤高优先级任务
python todo_v2.py task list --json | jq '.tasks[] | select(.importance=="high")'

# 统计任务数
python todo_v2.py task list --json | jq '.count'
```

---

## 🎯 与原版对比

| 操作 | 原版 todo.py | 新版 todo_v2.py |
|------|-------------|----------------|
| 创建任务 | `python todo.py add "标题"` | `python todo_v2.py task add "标题" --json` |
| 查看任务 | `python todo.py list` | `python todo_v2.py task list --json` |
| 完成任务 | `python todo.py complete <full-id>` | `python todo_v2.py task complete <id> --json` |
| JSON输出 | ❌ | ✅ 所有命令支持 |
| 字段支持 | 标题+提醒 | 标题+描述+优先级+截止日期+提醒+分类 |
| 错误处理 | Python Traceback | 结构化 JSON |

---

## 📚 完整文档

- **SKILL.md** - Agent 使用模式和完整 API
- **UPGRADE_REPORT.md** - 详细升级报告
- **原版 todo.py** - 保留作为参考

---

## 💡 下一步

1. **阅读 SKILL.md** 了解所有功能
2. **查看 UPGRADE_REPORT.md** 了解技术细节
3. **集成到你的 Agent 中**
4. **提供反馈和建议**

---

## 🆘 获取帮助

```bash
# 查看所有命令
python todo_v2.py --help

# 查看任务子命令
python todo_v2.py task --help

# 查看特定命令帮助
python todo_v2.py task add --help
```

---

**开始使用吧！** 🎉
