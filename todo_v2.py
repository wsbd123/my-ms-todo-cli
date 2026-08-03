#!/usr/bin/env python3
"""
Microsoft To Do CLI Harness - Agent-Native Interface
符合 CLI-Anything H=(S,C,I,R,V,D) 标准

用法示例:
  # 配置和认证
  todo config --client-id <ID>
  todo auth

  # 任务列表管理
  todo list-create "工作任务"
  todo list-rename "旧名称" "新名称"
  todo list-delete "列表名称"
  todo lists --json

  # 任务创建（完整字段支持）
  todo task add "完成报告" --body "详细描述" --due 2026-08-10 --importance high --json
  todo task add "会议" --reminder "2026-08-05T14:00" --json

  # 任务查询
  todo task list --json
  todo task list --filter incomplete --json
  todo task list --filter completed --json
  todo task list --filter today --json
  todo task info <task-id> --json
  todo task search "关键词" --json

  # 任务更新
  todo task update <task-id> --title "新标题" --body "新描述" --json
  todo task update <task-id> --due 2026-08-15 --importance low --json

  # 任务操作
  todo task complete <task-id> --json
  todo task uncomplete <task-id> --json
  todo task delete <task-id> --json

  # 批量操作
  todo task complete-all --filter "关键词" --json
  todo task delete-all --filter "关键词" --yes --json

  # 状态和同步
  todo status --json
  todo sync --json
"""

import argparse
import json
import sys
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import requests

# ═══════════════════════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG_DIR = Path.home() / ".config" / "ms-todo"
TOKEN_CACHE_FILE = CONFIG_DIR / "token_cache.bin"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_FILE = CONFIG_DIR / "cache.json"  # 本地缓存
UNDO_FILE = CONFIG_DIR / "undo_log.json"  # Undo历史

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Tasks.ReadWrite", "User.Read"]
AUTHORITY = "https://login.microsoftonline.com/consumers"

# ═══════════════════════════════════════════════════════════════════════════════
# S - State Management (状态管理)
# ═══════════════════════════════════════════════════════════════════════════════

def load_config() -> Dict:
    """加载配置"""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}

def save_config(data: Dict):
    """保存配置"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_cache() -> Dict:
    """加载本地缓存"""
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {"lists": {}, "tasks": {}, "last_sync": None}

def save_cache(cache: Dict):
    """保存本地缓存"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cache["last_sync"] = datetime.now().isoformat()
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

def load_undo_log() -> List:
    """加载undo历史"""
    if UNDO_FILE.exists():
        return json.loads(UNDO_FILE.read_text(encoding="utf-8"))
    return []

def save_undo_log(log: List):
    """保存undo历史（最多保留50条）"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    UNDO_FILE.write_text(json.dumps(log[-50:], indent=2, ensure_ascii=False), encoding="utf-8")

def record_undo(operation: str, data: Dict):
    """记录可撤销操作"""
    log = load_undo_log()
    log.append({
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "data": data
    })
    save_undo_log(log)

# ═══════════════════════════════════════════════════════════════════════════════
# 认证层
# ═══════════════════════════════════════════════════════════════════════════════

def _get_app(client_id: str):
    """初始化MSAL应用"""
    try:
        import msal
    except ImportError:
        return output_error("msal_not_installed", "请先安装依赖: pip install -r requirements.txt")

    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_FILE.exists():
        cache.deserialize(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(client_id, authority=AUTHORITY, token_cache=cache)
    return app, cache

def _save_cache_token(cache):
    """保存token缓存"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if cache.has_state_changed:
        TOKEN_CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")

def get_token(client_id: str, force_login: bool = False) -> str:
    """获取访问token"""
    app, cache = _get_app(client_id)
    result = None

    if not force_login:
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            return output_error("auth_flow_failed", flow.get("error_description", "无法发起授权"))
        print(f"\n{flow['message']}\n", file=sys.stderr)
        result = app.acquire_token_by_device_flow(flow)

    _save_cache_token(cache)

    if "access_token" not in result:
        return output_error("auth_failed", result.get("error_description", result.get("error", "认证失败")))

    return result["access_token"]

# ═══════════════════════════════════════════════════════════════════════════════
# Graph API 请求层（带错误处理）
# ═══════════════════════════════════════════════════════════════════════════════

def api(token: str, method: str, path: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """调用 Microsoft Graph API，返回JSON或None"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.request(
            method,
            f"{GRAPH_BASE}{path}",
            headers=headers,
            json=data,
            timeout=15
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {"status": "success"}

    except requests.exceptions.HTTPError as e:
        # 结构化错误处理
        error_data = {}
        try:
            error_data = e.response.json()
        except:
            pass

        return output_error(
            f"http_{e.response.status_code}",
            error_data.get("error", {}).get("message", str(e)),
            {"method": method, "path": path}
        )

    except requests.exceptions.RequestException as e:
        return output_error("network_error", str(e))

# ═══════════════════════════════════════════════════════════════════════════════
# I - Inspection (检查接口) - JSON输出优先
# ═══════════════════════════════════════════════════════════════════════════════

def output_json(data: Any, human_message: Optional[str] = None):
    """输出JSON（Agent模式）或人类可读信息"""
    # 检查是否请求JSON输出
    if '--json' in sys.argv:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        if human_message:
            print(human_message)
        else:
            # 降级到简单格式
            print(json.dumps(data, indent=2, ensure_ascii=False))

def output_error(code: str, message: str, context: Optional[Dict] = None):
    """输出结构化错误"""
    error = {
        "error": code,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    if context:
        error["context"] = context

    if '--json' in sys.argv:
        print(json.dumps(error, indent=2, ensure_ascii=False))
    else:
        print(f"❌ {message}", file=sys.stderr)

    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_list_by_name(token: str, list_name: str) -> Optional[Dict]:
    """根据名称获取列表完整信息"""
    lists = api(token, "GET", "/me/todo/lists")
    if not lists:
        return None

    for lst in lists.get("value", []):
        if lst["displayName"].lower() == list_name.lower():
            return lst

    # 找不到时返回默认列表
    for lst in lists.get("value", []):
        if lst.get("wellknownListName") == "defaultList":
            return lst

    return lists.get("value", [{}])[0] if lists.get("value") else None

def parse_datetime(s: str) -> datetime:
    """
    解析日期时间字符串，支持多种格式:
    - "09:00" → 今天或明天的9点
    - "2026-08-10" → 指定日期
    - "2026-08-10T14:00" → 完整日期时间
    - "tomorrow" → 明天
    - "today" → 今天
    """
    s = s.strip().lower()

    # 相对日期
    if s == "today":
        return datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    elif s == "tomorrow":
        return datetime.now().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)

    # HH:MM 格式
    if re.match(r'^\d{1,2}:\d{2}$', s):
        t = datetime.strptime(s, "%H:%M")
        candidate = datetime.now().replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if candidate <= datetime.now():
            candidate += timedelta(days=1)
        return candidate

    # ISO 格式
    try:
        return datetime.fromisoformat(s)
    except:
        pass

    # 日期格式
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(hour=9, minute=0, second=0, microsecond=0)
    except:
        pass

    raise ValueError(f"无法解析日期时间: {s}")

def format_task_output(task: Dict, include_body: bool = False) -> Dict:
    """格式化任务输出（统一结构）"""
    output = {
        "id": task["id"],
        "title": task["title"],
        "status": task["status"],
        "importance": task.get("importance", "normal"),
        "created": task.get("createdDateTime"),
        "lastModified": task.get("lastModifiedDateTime")
    }

    if include_body:
        output["body"] = task.get("body", {}).get("content", "")

    if task.get("isReminderOn"):
        output["reminder"] = task.get("reminderDateTime", {}).get("dateTime")

    if task.get("dueDateTime"):
        output["due"] = task.get("dueDateTime", {}).get("dateTime")

    if task.get("completedDateTime"):
        output["completed"] = task["completedDateTime"]["dateTime"]

    if task.get("categories"):
        output["categories"] = task["categories"]

    return output

# ═══════════════════════════════════════════════════════════════════════════════
# C - Commands: 任务列表管理
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_list_create(args, token):
    """创建新的任务列表"""
    result = api(token, "POST", "/me/todo/lists", {
        "displayName": args.name
    })

    if result:
        record_undo("list_create", {"list_id": result["id"], "name": args.name})
        output_json(
            {"id": result["id"], "name": result["displayName"], "created": result.get("createdDateTime")},
            f"✅ 已创建列表「{args.name}」"
        )

def cmd_list_rename(args, token):
    """重命名列表"""
    lst = get_list_by_name(token, args.old_name)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.old_name}」")

    record_undo("list_rename", {"list_id": lst["id"], "old_name": args.old_name, "new_name": args.new_name})

    result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}", {
        "displayName": args.new_name
    })

    if result:
        output_json(
            {"id": lst["id"], "old_name": args.old_name, "new_name": args.new_name},
            f"✅ 列表已重命名: 「{args.old_name}」→「{args.new_name}」"
        )

def cmd_list_delete(args, token):
    """删除列表"""
    lst = get_list_by_name(token, args.name)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.name}」")

    # 确认
    if not args.yes:
        print(f"⚠️  确认删除列表「{args.name}」？此操作不可撤销。", file=sys.stderr)
        confirm = input("输入列表名称以确认: ")
        if confirm != args.name:
            return output_json({"status": "cancelled"}, "已取消")

    record_undo("list_delete", {"list_id": lst["id"], "name": args.name})

    result = api(token, "DELETE", f"/me/todo/lists/{lst['id']}")
    if result:
        output_json(
            {"id": lst["id"], "name": args.name, "status": "deleted"},
            f"✅ 已删除列表「{args.name}」"
        )

def cmd_lists(args, token):
    """查看所有列表（带元数据）"""
    lists_data = api(token, "GET", "/me/todo/lists")
    if not lists_data:
        return

    lists = lists_data.get("value", [])

    # 获取每个列表的任务数量
    result = []
    for lst in lists:
        tasks = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
        task_list = tasks.get("value", []) if tasks else []

        incomplete = len([t for t in task_list if t.get("status") != "completed"])
        completed = len([t for t in task_list if t.get("status") == "completed"])

        result.append({
            "id": lst["id"],
            "name": lst["displayName"],
            "isDefault": lst.get("wellknownListName") == "defaultList",
            "tasks": {
                "total": len(task_list),
                "incomplete": incomplete,
                "completed": completed
            }
        })

    if '--json' in sys.argv:
        output_json({"lists": result, "count": len(result)})
    else:
        print(f"📋 任务列表 ({len(result)} 个)\n")
        for lst in result:
            default_mark = " [默认]" if lst["isDefault"] else ""
            print(f"  • {lst['name']}{default_mark}")
            print(f"    {lst['tasks']['incomplete']} 未完成 / {lst['tasks']['completed']} 已完成")
            print(f"    ID: {lst['id'][:30]}...\n")

# ═══════════════════════════════════════════════════════════════════════════════
# C - Commands: 任务管理（完整 CRUD）
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_task_add(args, token):
    """创建任务（支持完整字段）"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    task_data = {
        "title": args.title,
        "status": "notStarted"
    }

    # 描述
    if args.body:
        task_data["body"] = {
            "content": args.body,
            "contentType": "text"
        }

    # 优先级
    if args.importance:
        task_data["importance"] = args.importance

    # 截止日期
    if args.due:
        try:
            due_dt = parse_datetime(args.due)
            task_data["dueDateTime"] = {
                "dateTime": due_dt.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC"
            }
        except ValueError as e:
            return output_error("invalid_date", str(e))

    # 提醒时间
    if args.reminder:
        try:
            reminder_dt = parse_datetime(args.reminder)
            task_data["reminderDateTime"] = {
                "dateTime": reminder_dt.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC"
            }
            task_data["isReminderOn"] = True
        except ValueError as e:
            return output_error("invalid_reminder", str(e))

    # 分类
    if args.categories:
        task_data["categories"] = [c.strip() for c in args.categories.split(",")]

    result = api(token, "POST", f"/me/todo/lists/{lst['id']}/tasks", task_data)

    if result:
        record_undo("task_create", {
            "list_id": lst["id"],
            "task_id": result["id"],
            "title": args.title
        })

        output_json(
            format_task_output(result, include_body=True),
            f"✅ 已创建任务「{result['title']}」"
        )

def cmd_task_list(args, token):
    """列出任务（支持过滤）"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    tasks_data = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
    if not tasks_data:
        return

    tasks = tasks_data.get("value", [])

    # 过滤
    if args.filter:
        f = args.filter.lower()
        if f == "incomplete":
            tasks = [t for t in tasks if t.get("status") != "completed"]
        elif f == "completed":
            tasks = [t for t in tasks if t.get("status") == "completed"]
        elif f == "today":
            today = datetime.now().date()
            tasks = [t for t in tasks if t.get("dueDateTime") and
                     datetime.fromisoformat(t["dueDateTime"]["dateTime"].replace("Z", "")).date() == today]
        elif f == "overdue":
            now = datetime.now()
            tasks = [t for t in tasks if t.get("dueDateTime") and
                     datetime.fromisoformat(t["dueDateTime"]["dateTime"].replace("Z", "")) < now and
                     t.get("status") != "completed"]
        elif f == "high":
            tasks = [t for t in tasks if t.get("importance") == "high"]

    formatted_tasks = [format_task_output(t, include_body=args.verbose) for t in tasks]

    if '--json' in sys.argv:
        output_json({
            "list": lst["displayName"],
            "filter": args.filter,
            "count": len(formatted_tasks),
            "tasks": formatted_tasks
        })
    else:
        if not formatted_tasks:
            print("(无任务)")
            return

        filter_text = f" ({args.filter})" if args.filter else ""
        print(f"📋 {lst['displayName']}{filter_text}  ({len(formatted_tasks)} 项)\n")

        for t in formatted_tasks:
            status_icon = "✓" if t["status"] == "completed" else " "
            importance_icon = "⚡" if t["importance"] == "high" else ""
            print(f"  [{status_icon}] {importance_icon}{t['title']}")

            if t.get("due"):
                print(f"      📅 截止: {t['due'][:16]}")
            if t.get("reminder"):
                print(f"      🔔 提醒: {t['reminder'][:16]}")
            if args.verbose and t.get("body"):
                print(f"      💬 {t['body']}")

            print(f"      ID: {t['id'][:30]}...\n")

def cmd_task_info(args, token):
    """查看单个任务详情"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    result = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}")

    if result:
        output_json(
            format_task_output(result, include_body=True),
            None  # JSON模式优先
        )

def cmd_task_search(args, token):
    """搜索任务"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    tasks_data = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
    if not tasks_data:
        return

    keyword = args.keyword.lower()
    matching = [
        t for t in tasks_data.get("value", [])
        if keyword in t["title"].lower() or
           keyword in t.get("body", {}).get("content", "").lower()
    ]

    formatted = [format_task_output(t, include_body=True) for t in matching]

    output_json(
        {"keyword": args.keyword, "count": len(formatted), "tasks": formatted},
        f"找到 {len(formatted)} 个匹配的任务"
    )

def cmd_task_update(args, token):
    """更新任务"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    # 先获取当前任务（用于undo）
    current = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}")
    if not current:
        return

    update_data = {}

    if args.title:
        update_data["title"] = args.title
    if args.body is not None:  # 允许空字符串
        update_data["body"] = {"content": args.body, "contentType": "text"}
    if args.importance:
        update_data["importance"] = args.importance
    if args.due:
        try:
            due_dt = parse_datetime(args.due)
            update_data["dueDateTime"] = {
                "dateTime": due_dt.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC"
            }
        except ValueError as e:
            return output_error("invalid_date", str(e))

    if args.reminder:
        try:
            reminder_dt = parse_datetime(args.reminder)
            update_data["reminderDateTime"] = {
                "dateTime": reminder_dt.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC"
            }
            update_data["isReminderOn"] = True
        except ValueError as e:
            return output_error("invalid_reminder", str(e))

    if not update_data:
        return output_error("no_updates", "未指定任何更新字段")

    record_undo("task_update", {
        "list_id": lst["id"],
        "task_id": args.task_id,
        "old_data": current
    })

    result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}", update_data)

    if result:
        output_json(
            format_task_output(result, include_body=True),
            f"✅ 任务已更新"
        )

def cmd_task_complete(args, token):
    """标记任务为完成"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    current = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}")
    if not current:
        return

    record_undo("task_complete", {
        "list_id": lst["id"],
        "task_id": args.task_id,
        "old_status": current.get("status")
    })

    result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}", {
        "status": "completed"
    })

    if result:
        output_json(
            {"id": args.task_id, "status": "completed", "title": result["title"]},
            f"✅ 任务已完成"
        )

def cmd_task_uncomplete(args, token):
    """重新打开已完成的任务"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}", {
        "status": "notStarted"
    })

    if result:
        output_json(
            {"id": args.task_id, "status": "notStarted", "title": result["title"]},
            f"✅ 任务已重新打开"
        )

def cmd_task_delete(args, token):
    """删除任务"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    current = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}")
    if not current:
        return

    record_undo("task_delete", {
        "list_id": lst["id"],
        "task_id": args.task_id,
        "data": current
    })

    result = api(token, "DELETE", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}")

    if result:
        output_json(
            {"id": args.task_id, "status": "deleted"},
            f"✅ 任务已删除"
        )

# ═══════════════════════════════════════════════════════════════════════════════
# 批量操作
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_task_complete_all(args, token):
    """批量完成任务"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    tasks_data = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
    if not tasks_data:
        return

    tasks = tasks_data.get("value", [])

    # 过滤
    if args.filter:
        keyword = args.filter.lower()
        tasks = [t for t in tasks if keyword in t["title"].lower() and t.get("status") != "completed"]
    else:
        tasks = [t for t in tasks if t.get("status") != "completed"]

    if not tasks:
        return output_json({"count": 0, "message": "无匹配的未完成任务"}, "无匹配的未完成任务")

    # 确认
    if not args.yes:
        print(f"将完成 {len(tasks)} 个任务:", file=sys.stderr)
        for t in tasks[:5]:
            print(f"  • {t['title']}", file=sys.stderr)
        if len(tasks) > 5:
            print(f"  ... 还有 {len(tasks) - 5} 个", file=sys.stderr)

        confirm = input(f"\n确认？(y/N): ")
        if confirm.lower() != 'y':
            return output_json({"status": "cancelled"}, "已取消")

    completed = []
    for task in tasks:
        result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}/tasks/{task['id']}", {
            "status": "completed"
        })
        if result:
            completed.append(task["id"])

    output_json(
        {"completed": len(completed), "total": len(tasks)},
        f"✅ 已完成 {len(completed)} 个任务"
    )

def cmd_task_delete_all(args, token):
    """批量删除任务"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    tasks_data = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
    if not tasks_data:
        return

    tasks = tasks_data.get("value", [])

    # 过滤
    if args.filter:
        keyword = args.filter.lower()
        tasks = [t for t in tasks if keyword in t["title"].lower()]

    if not tasks:
        return output_json({"count": 0, "message": "无匹配的任务"}, "无匹配的任务")

    # 确认
    if not args.yes:
        print(f"⚠️  将删除 {len(tasks)} 个任务:", file=sys.stderr)
        for t in tasks[:5]:
            print(f"  • {t['title']}", file=sys.stderr)
        if len(tasks) > 5:
            print(f"  ... 还有 {len(tasks) - 5} 个", file=sys.stderr)

        confirm = input(f"\n确认删除？(y/N): ")
        if confirm.lower() != 'y':
            return output_json({"status": "cancelled"}, "已取消")

    deleted = []
    for task in tasks:
        result = api(token, "DELETE", f"/me/todo/lists/{lst['id']}/tasks/{task['id']}")
        if result:
            deleted.append(task["id"])

    output_json(
        {"deleted": len(deleted), "total": len(tasks)},
        f"✅ 已删除 {len(deleted)} 个任务"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# 状态和同步
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_status(args, token):
    """显示全局状态"""
    # 获取用户信息
    user = api(token, "GET", "/me")

    # 获取所有列表和任务统计
    lists_data = api(token, "GET", "/me/todo/lists")
    lists = lists_data.get("value", []) if lists_data else []

    total_tasks = 0
    incomplete_tasks = 0
    high_priority = 0

    for lst in lists:
        tasks_data = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
        if tasks_data:
            tasks = tasks_data.get("value", [])
            total_tasks += len(tasks)
            incomplete_tasks += len([t for t in tasks if t.get("status") != "completed"])
            high_priority += len([t for t in tasks if t.get("importance") == "high"])

    cache = load_cache()

    status = {
        "user": user.get("displayName") if user else "Unknown",
        "lists": len(lists),
        "tasks": {
            "total": total_tasks,
            "incomplete": incomplete_tasks,
            "completed": total_tasks - incomplete_tasks,
            "high_priority": high_priority
        },
        "last_sync": cache.get("last_sync"),
        "cache_size": len(str(cache))
    }

    output_json(status, None)

def cmd_sync(args, token):
    """同步本地缓存"""
    cache = {"lists": {}, "tasks": {}}

    lists_data = api(token, "GET", "/me/todo/lists")
    if not lists_data:
        return

    for lst in lists_data.get("value", []):
        cache["lists"][lst["id"]] = lst

        tasks_data = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
        if tasks_data:
            cache["tasks"][lst["id"]] = tasks_data.get("value", [])

    save_cache(cache)

    output_json(
        {"status": "synced", "timestamp": cache["last_sync"], "lists": len(cache["lists"])},
        f"✅ 同步完成"
    )

def cmd_undo(args, token):
    """撤销上一步操作"""
    log = load_undo_log()
    if not log:
        return output_json({"status": "no_history"}, "无可撤销操作")

    last = log[-1]
    operation = last["operation"]
    data = last["data"]

    # TODO: 实现具体的撤销逻辑
    # 这里只是示例框架
    output_json(
        {"message": "undo功能开发中", "last_operation": operation},
        "⚠️  Undo功能开发中"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# 配置命令
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_config(args, token=None):
    """配置管理"""
    cfg = load_config()

    if args.client_id:
        cfg["client_id"] = args.client_id
        save_config(cfg)
        output_json({"status": "saved", "client_id": args.client_id}, "✅ Client ID 已保存")
    elif args.show:
        output_json(cfg, None)
    else:
        output_json(cfg, None)

def cmd_auth(args, token=None):
    """认证"""
    cfg = load_config()
    client_id = cfg.get("client_id")

    if not client_id:
        return output_error("no_client_id", "请先配置: todo config --client-id <YOUR_CLIENT_ID>")

    get_token(client_id, force_login=True)
    output_json({"status": "authenticated"}, "✅ 认证成功")

# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Microsoft To Do CLI Harness (Agent-Native)",
        epilog="添加 --json 以获取结构化输出"
    )
    parser.add_argument("--json", action="store_true", help="输出JSON格式")

    sub = parser.add_subparsers(dest="cmd", help="子命令")

    # ─────────────────────────────────────────────────────────────────────
    # 配置和认证
    # ─────────────────────────────────────────────────────────────────────

    p = sub.add_parser("config", help="配置 Client ID")
    p.add_argument("--client-id", help="Azure 应用 Client ID")
    p.add_argument("--show", action="store_true", help="显示当前配置")

    sub.add_parser("auth", help="登录 / 重新授权")

    # ─────────────────────────────────────────────────────────────────────
    # 任务列表管理
    # ─────────────────────────────────────────────────────────────────────

    p = sub.add_parser("list-create", help="创建任务列表")
    p.add_argument("name", help="列表名称")

    p = sub.add_parser("list-rename", help="重命名列表")
    p.add_argument("old_name", help="旧名称")
    p.add_argument("new_name", help="新名称")

    p = sub.add_parser("list-delete", help="删除列表")
    p.add_argument("name", help="列表名称")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    sub.add_parser("lists", help="查看所有列表")

    # ─────────────────────────────────────────────────────────────────────
    # 任务管理
    # ─────────────────────────────────────────────────────────────────────

    task = sub.add_parser("task", help="任务操作")
    task_sub = task.add_subparsers(dest="task_cmd", help="任务子命令")

    # task add
    p = task_sub.add_parser("add", help="创建任务")
    p.add_argument("title", help="任务标题")
    p.add_argument("--body", "-b", help="任务描述")
    p.add_argument("--importance", "-i", choices=["low", "normal", "high"], help="优先级")
    p.add_argument("--due", "-d", help="截止日期 (YYYY-MM-DD 或 today/tomorrow)")
    p.add_argument("--reminder", "-r", help="提醒时间 (HH:MM 或 YYYY-MM-DDTHH:MM)")
    p.add_argument("--categories", "-c", help="分类（逗号分隔）")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")

    # task list
    p = task_sub.add_parser("list", help="列出任务")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")
    p.add_argument("--filter", "-f",
                   choices=["incomplete", "completed", "today", "overdue", "high"],
                   help="过滤条件")
    p.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")

    # task info
    p = task_sub.add_parser("info", help="查看任务详情")
    p.add_argument("task_id", help="任务ID")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")

    # task search
    p = task_sub.add_parser("search", help="搜索任务")
    p.add_argument("keyword", help="搜索关键词")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")

    # task update
    p = task_sub.add_parser("update", help="更新任务")
    p.add_argument("task_id", help="任务ID")
    p.add_argument("--title", "-t", help="新标题")
    p.add_argument("--body", "-b", help="新描述")
    p.add_argument("--importance", "-i", choices=["low", "normal", "high"], help="优先级")
    p.add_argument("--due", "-d", help="截止日期")
    p.add_argument("--reminder", "-r", help="提醒时间")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")

    # task complete
    p = task_sub.add_parser("complete", help="完成任务")
    p.add_argument("task_id", help="任务ID")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")

    # task uncomplete
    p = task_sub.add_parser("uncomplete", help="重新打开任务")
    p.add_argument("task_id", help="任务ID")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")

    # task delete
    p = task_sub.add_parser("delete", help="删除任务")
    p.add_argument("task_id", help="任务ID")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")

    # task complete-all
    p = task_sub.add_parser("complete-all", help="批量完成任务")
    p.add_argument("--filter", "-f", help="关键词过滤")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    # task delete-all
    p = task_sub.add_parser("delete-all", help="批量删除任务")
    p.add_argument("--filter", "-f", help="关键词过滤")
    p.add_argument("--list", "-l", default="Tasks", help="列表名称")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    # ─────────────────────────────────────────────────────────────────────
    # 状态和同步
    # ─────────────────────────────────────────────────────────────────────

    sub.add_parser("status", help="显示全局状态")
    sub.add_parser("sync", help="同步本地缓存")
    sub.add_parser("undo", help="撤销上一步操作 (实验性)")

    # ─────────────────────────────────────────────────────────────────────
    # 解析参数
    # ─────────────────────────────────────────────────────────────────────

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    # config 和 auth 不需要 token
    if args.cmd in ["config", "auth"]:
        if args.cmd == "config":
            cmd_config(args)
        else:
            cmd_auth(args)
        return

    # 其他命令需要认证
    cfg = load_config()
    client_id = cfg.get("client_id")

    if not client_id:
        return output_error("no_client_id", "请先运行: todo config --client-id <YOUR_CLIENT_ID>")

    token = get_token(client_id)

    # 路由到对应命令
    command_map = {
        "list-create": cmd_list_create,
        "list-rename": cmd_list_rename,
        "list-delete": cmd_list_delete,
        "lists": cmd_lists,
        "status": cmd_status,
        "sync": cmd_sync,
        "undo": cmd_undo,
    }

    # task 子命令
    task_command_map = {
        "add": cmd_task_add,
        "list": cmd_task_list,
        "info": cmd_task_info,
        "search": cmd_task_search,
        "update": cmd_task_update,
        "complete": cmd_task_complete,
        "uncomplete": cmd_task_uncomplete,
        "delete": cmd_task_delete,
        "complete-all": cmd_task_complete_all,
        "delete-all": cmd_task_delete_all,
    }

    if args.cmd == "task":
        if not args.task_cmd:
            parser.parse_args(["task", "--help"])
            return

        handler = task_command_map.get(args.task_cmd)
        if handler:
            handler(args, token)
        else:
            return output_error("unknown_task_command", f"未知任务命令: {args.task_cmd}")
    else:
        handler = command_map.get(args.cmd)
        if handler:
            handler(args, token)
        else:
            return output_error("unknown_command", f"未知命令: {args.cmd}")


if __name__ == "__main__":
    main()

