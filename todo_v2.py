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
import os
import sys
import re
import time
from functools import wraps
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

import requests

# 是否以 JSON 模式输出（在 main() 解析参数后设置）
JSON_MODE = False
# 是否已发生（非致命）错误，用于在 main() 结束时决定退出码
_ERROR_EMITTED = False

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
# 默认针对个人 Microsoft 账户；可用 config.json 的 "authority" 覆盖
# （例如 https://login.microsoftonline.com/common 以支持工作/学校账户）
DEFAULT_AUTHORITY = "https://login.microsoftonline.com/consumers"

# ═══════════════════════════════════════════════════════════════════════════════
# S - State Management (状态管理)
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_config_dir():
    """确保配置目录存在且权限私有 (0o700)"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass

def _write_private(path: Path, content: str):
    """原子地写入含敏感数据的文件并设置 0o600 权限。

    先写临时文件（同目录）再 os.replace，避免写入中途崩溃截断
    token_cache.bin / undo_log.json 等文件。
    """
    _ensure_config_dir()
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(content, encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

def _read_json(path: Path, default):
    """读取 JSON 文件；不存在或损坏时返回 default（不抛异常）。"""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"⚠️ 文件损坏或不可读，已忽略: {path}", file=sys.stderr)
        return default

def load_config() -> Dict:
    """加载配置"""
    return _read_json(CONFIG_FILE, {})

def save_config(data: Dict):
    """保存配置"""
    _write_private(CONFIG_FILE, json.dumps(data, indent=2, ensure_ascii=False))

def load_cache() -> Dict:
    """加载本地缓存"""
    return _read_json(CACHE_FILE, {"lists": {}, "tasks": {}, "last_sync": None})

def save_cache(cache: Dict):
    """保存本地缓存"""
    cache["last_sync"] = datetime.now().isoformat()
    _write_private(CACHE_FILE, json.dumps(cache, indent=2, ensure_ascii=False))

def load_undo_log() -> List:
    """加载undo历史"""
    log = _read_json(UNDO_FILE, [])
    return log if isinstance(log, list) else []

def save_undo_log(log: List):
    """保存undo历史（最多保留50条）"""
    _write_private(UNDO_FILE, json.dumps(log[-50:], indent=2, ensure_ascii=False))

def _require_yes_if_noninteractive():
    """非交互环境（无 TTY 或 --json）下缺少 --yes 时报错退出，避免 input() 抛 EOFError。"""
    if JSON_MODE or not sys.stdin.isatty():
        output_error("confirmation_required",
                     "非交互环境需显式添加 --yes 以确认此操作")

def pop_undo_log():
    """撤销成功后弹出最近一条记录，使 undo 表现为真正的栈。"""
    log = load_undo_log()
    if log:
        log.pop()
        save_undo_log(log)

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

def _get_authority() -> str:
    """从配置读取 authority，缺省为个人账户端点。"""
    return load_config().get("authority") or DEFAULT_AUTHORITY

def _get_app(client_id: str):
    """初始化MSAL应用"""
    try:
        import msal
    except ImportError:
        return output_error("msal_not_installed", "请先安装依赖: pip install -r requirements.txt")

    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_FILE.exists():
        try:
            cache.deserialize(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("⚠️ token 缓存损坏，将需要重新登录", file=sys.stderr)

    app = msal.PublicClientApplication(client_id, authority=_get_authority(), token_cache=cache)
    return app, cache

def _save_cache_token(cache):
    """保存token缓存（含刷新令牌，权限 0o600）"""
    if cache.has_state_changed:
        _write_private(TOKEN_CACHE_FILE, cache.serialize())

def get_token(client_id: str, force_login: bool = False, interactive: bool = False) -> str:
    """获取访问token。

    interactive=False（默认，供 agent / 脚本 / 非 auth 命令使用）时只做静默获取，
    失败即返回 not_authenticated 并退出，绝不进入阻塞式设备码轮询。
    只有显式的 `auth` / `auth login`（interactive=True）才允许交互登录。
    """
    app, cache = _get_app(client_id)
    result = None

    if not force_login:
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        if not interactive:
            return output_error(
                "not_authenticated",
                "未认证或凭证已过期，请运行: mstodo auth login"
            )
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            return output_error("auth_flow_failed", flow.get("error_description", "无法发起授权"))
        # 设备码信息打到 stdout：既让用户可见，也便于 Node 包装器解析增强
        print(f"\n{flow['message']}\n", flush=True)
        result = app.acquire_token_by_device_flow(flow)

    _save_cache_token(cache)

    if "access_token" not in result:
        return output_error("auth_failed", result.get("error_description", result.get("error", "认证失败")))

    return result["access_token"]

# ═══════════════════════════════════════════════════════════════════════════════
# Graph API 请求层（带错误处理）
# ═══════════════════════════════════════════════════════════════════════════════

MAX_RETRY_AFTER = 60  # Retry-After 上限（秒），避免服务端要求长时间阻塞
# 幂等方法：超时 / 5xx 可安全重试；POST 非幂等，重试可能造成重复创建
IDEMPOTENT_METHODS = {"GET", "HEAD", "PUT", "DELETE", "PATCH"}

def _parse_retry_after(value) -> int:
    """解析 Retry-After 头，支持秒数或 HTTP-date，带上限与下限。"""
    if not value:
        return 1
    try:
        secs = int(value)
    except (TypeError, ValueError):
        # HTTP-date 形式
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(value)
            secs = int((dt - datetime.now(dt.tzinfo)).total_seconds())
        except Exception:
            secs = 1
    return max(1, min(secs, MAX_RETRY_AFTER))

def _request(token: str, method: str, url: str, data: Optional[Dict] = None,
             quiet: bool = False) -> Optional[Dict]:
    """向一个完整 URL 发起 Graph 请求，返回 JSON 或 None（带重试）。

    失败时不再退出进程：调用 emit_error 记录错误并返回 None，
    由调用方决定如何处理（单命令经 main() 统一置退出码；批量循环可继续）。
    quiet=True 时不打印错误（批量循环用聚合结果汇报，避免逐条刷屏）。
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    report = (lambda *a, **k: None) if quiet else emit_error
    idempotent = method.upper() in IDEMPOTENT_METHODS

    for attempt in range(3):
        try:
            resp = requests.request(method, url, headers=headers, json=data, timeout=15)

            # 处理 rate limiting
            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp.headers.get('Retry-After'))
                if attempt < 2:
                    print(f"⚠️ 请求频率限制，等待 {retry_after} 秒...", file=sys.stderr)
                    time.sleep(retry_after)
                    continue
                return report("rate_limited", "多次请求频率限制，请稍后重试",
                              {"method": method, "url": url})

            resp.raise_for_status()
            return resp.json() if resp.content else {"status": "success"}

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            # 仅对幂等方法的 5xx 重试（POST 重试可能重复创建任务）
            if status >= 500 and idempotent and attempt < 2:
                wait_time = 2 ** attempt
                print(f"⚠️ 服务器错误 ({status})，{wait_time}秒后重试...", file=sys.stderr)
                time.sleep(wait_time)
                continue

            error_data = {}
            try:
                error_data = e.response.json()
            except Exception:
                pass

            return report(
                f"http_{status}",
                error_data.get("error", {}).get("message", str(e)),
                {"method": method, "url": url}
            )
        except requests.exceptions.Timeout as e:
            # 超时后无法确定服务端是否已处理：仅对幂等方法重试
            if idempotent and attempt < 2:
                print(f"⚠️ 请求超时，{2**attempt}秒后重试...", file=sys.stderr)
                time.sleep(2 ** attempt)
                continue
            return report("timeout", f"请求超时: {str(e)[:50]}")
        except requests.exceptions.ConnectionError:
            if attempt < 2:
                print(f"⚠️ 网络连接失败，重试中...", file=sys.stderr)
                time.sleep(2 ** attempt)
                continue
            return report("connection_error", "网络连接失败，请检查网络")
        except requests.exceptions.RequestException as e:
            return report("network_error", str(e))

    return None

def api(token: str, method: str, path: str, data: Optional[Dict] = None,
        quiet: bool = False) -> Optional[Dict]:
    """调用 Microsoft Graph API，返回JSON或None（带重试，失败不退出进程）"""
    return _request(token, method, f"{GRAPH_BASE}{path}", data, quiet=quiet)

def api_with_pagination(token: str, method: str, path: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """带分页处理的 API 调用，解决任务数超过 30 时数据丢失问题。

    每页复用 _request，因而与普通请求共享重试 / 429 / 错误处理逻辑。
    任一页失败即返回 None（错误已由 _request 汇报）。
    """
    all_items = []
    next_link = f"{GRAPH_BASE}{path}"

    while next_link:
        result = _request(token, method, next_link, data)
        if result is None:
            return None
        all_items.extend(result.get("value", []))
        next_link = result.get("@odata.nextLink")

    return {"value": all_items, "@odata.count": len(all_items)}

# ═══════════════════════════════════════════════════════════════════════════════
# I - Inspection (检查接口) - JSON输出优先
# ═══════════════════════════════════════════════════════════════════════════════

def output_json(data: Any, human_message: Optional[str] = None):
    """输出JSON（Agent模式）或人类可读信息"""
    # 检查是否请求JSON输出
    if JSON_MODE:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        if human_message:
            print(human_message)
        else:
            # 降级到简单格式
            print(json.dumps(data, indent=2, ensure_ascii=False))

def emit_error(code: str, message: str, context: Optional[Dict] = None):
    """输出结构化错误但不退出进程；标记发生过错误（影响退出码）。返回 None。"""
    global _ERROR_EMITTED
    _ERROR_EMITTED = True

    error = {
        "error": code,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    if context:
        error["context"] = context

    # 错误一律写 stderr：保持 stdout 的 --json 契约干净（只含一个结果文档）
    if JSON_MODE:
        print(json.dumps(error, indent=2, ensure_ascii=False), file=sys.stderr)
    else:
        print(f"❌ {message}", file=sys.stderr)
    return None

def output_error(code: str, message: str, context: Optional[Dict] = None):
    """输出结构化错误并立即退出（用于命令级校验错误，如参数非法）。"""
    emit_error(code, message, context)
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_list_by_name(token: str, list_name: str) -> Optional[Dict]:
    """根据名称获取列表完整信息。

    - 精确匹配（忽略大小写）优先。
    - 仅当请求的是默认列表名 "Tasks"（argparse 默认值）时，才回退到
      wellknownListName == "defaultList"，以兼容本地化的默认列表名。
    - 其它情况下未找到即返回 None（由调用方报错），避免把操作静默落到错误列表。
    """
    lists = api(token, "GET", "/me/todo/lists")
    if not lists:
        return None

    values = lists.get("value", [])
    for lst in values:
        if lst["displayName"].lower() == list_name.lower():
            return lst

    # 仅对默认名回退到系统默认列表；显式指定的错误名不回退
    if list_name.strip().lower() == "tasks":
        for lst in values:
            if lst.get("wellknownListName") == "defaultList":
                return lst

    return None

def _local_to_utc_str(dt: datetime) -> str:
    """把本地朴素(naive)时间转换为 UTC 并格式化为 Graph 需要的字符串。"""
    if dt.tzinfo is None:
        dt = dt.astimezone()  # 视为本地时间
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000")

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
    except ValueError:
        pass

    # 日期格式
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(hour=9, minute=0, second=0, microsecond=0)
    except ValueError:
        pass

    raise ValueError(f"无法解析日期时间: {s}")

def parse_recurrence(rec_str: str) -> Optional[Dict]:
    """解析重复规则字符串"""
    if not rec_str:
        return None

    rec_str = rec_str.strip().lower()

    # 基本模式
    patterns = {
        "daily": {"type": "daily", "interval": 1},
        "weekly": {"type": "weekly", "interval": 1, "daysOfWeek": ["monday"]},
        "monthly": {"type": "absoluteMonthly", "interval": 1, "dayOfMonth": 1},
        "yearly": {"type": "absoluteYearly", "interval": 1, "dayOfMonth": 1, "month": 1}
    }

    if rec_str in patterns:
        return {
            "pattern": patterns[rec_str],
            "range": {"type": "noEnd", "startDate": datetime.now().strftime("%Y-%m-%d")}
        }

    # weekly:周一,周三 或 weekly:mon,wed / monday,wednesday
    if rec_str.startswith("weekly:"):
        days = [d.strip() for d in rec_str.replace("weekly:", "").split(",") if d.strip()]
        day_map = {
            "周一": "monday", "周二": "tuesday", "周三": "wednesday", "周四": "thursday",
            "周五": "friday", "周六": "saturday", "周日": "sunday", "周天": "sunday",
            "mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday",
            "fri": "friday", "sat": "saturday", "sun": "sunday",
        }
        valid = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        days_en = []
        for d in days:
            en = day_map.get(d, d)
            if en not in valid:
                return None  # 非法星期名
            days_en.append(en)
        if not days_en:
            return None
        return {"pattern": {"type": "weekly", "interval": 1, "daysOfWeek": days_en},
                "range": {"type": "noEnd", "startDate": datetime.now().strftime("%Y-%m-%d")}}

    # monthly:17
    if rec_str.startswith("monthly:"):
        try:
            day = int(rec_str.replace("monthly:", ""))
        except ValueError:
            return None
        if not 1 <= day <= 31:
            return None
        return {"pattern": {"type": "absoluteMonthly", "interval": 1, "dayOfMonth": day},
                "range": {"type": "noEnd", "startDate": datetime.now().strftime("%Y-%m-%d")}}

    # yearly:09-17
    if rec_str.startswith("yearly:"):
        parts = rec_str.replace("yearly:", "").split("-")
        try:
            month = int(parts[0])
            day = int(parts[1]) if len(parts) > 1 else 1
        except (ValueError, IndexError):
            return None
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        return {"pattern": {"type": "absoluteYearly", "interval": 1, "dayOfMonth": day, "month": month},
                "range": {"type": "noEnd", "startDate": datetime.now().strftime("%Y-%m-%d")}}

    return None

def _restore_payload(task: Dict) -> Dict:
    """从一个完整任务对象构造用于「重新创建」的请求体（撤销删除/移动共用）。

    保留所有可写字段（title/status/body/importance/due/reminder/recurrence/categories），
    丢弃 id、时间戳等只读字段。
    """
    payload = {
        "title": task.get("title", "Restored Task"),
        "status": task.get("status", "notStarted"),
    }
    for k in ("body", "importance", "dueDateTime", "recurrence", "categories"):
        if task.get(k) is not None:
            payload[k] = task[k]
    if task.get("reminderDateTime"):
        payload["reminderDateTime"] = task["reminderDateTime"]
        payload["isReminderOn"] = task.get("isReminderOn", True)
    return payload

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

    result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}", {
        "displayName": args.new_name
    })

    if result:
        # 成功后再记账，避免把失败的操作写入 undo 栈
        record_undo("list_rename", {"list_id": lst["id"], "old_name": args.old_name, "new_name": args.new_name})
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
        _require_yes_if_noninteractive()
        print(f"⚠️  确认删除列表「{args.name}」？此操作不可撤销。", file=sys.stderr)
        confirm = input("输入列表名称以确认: ")
        if confirm != args.name:
            return output_json({"status": "cancelled"}, "已取消")

    # 删除列表会连带删除其中所有任务，无法恢复；不记录到 undo 栈
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
        tasks = api_with_pagination(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
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

    if JSON_MODE:
        output_json({"lists": result, "count": len(result)})
    else:
        print(f"📋 任务列表 ({len(result)} 个)\n")
        for lst in result:
            default_mark = " [默认]" if lst["isDefault"] else ""
            print(f"  • {lst['name']}{default_mark}")
            print(f"    {lst['tasks']['incomplete']} 未完成 / {lst['tasks']['completed']} 已完成")
            print(f"    ID: {lst['id']}\n")

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
                "dateTime": _local_to_utc_str(due_dt),
                "timeZone": "UTC"
            }
        except ValueError as e:
            return output_error("invalid_date", str(e))

    # 提醒时间
    if args.reminder:
        try:
            reminder_dt = parse_datetime(args.reminder)
            task_data["reminderDateTime"] = {
                "dateTime": _local_to_utc_str(reminder_dt),
                "timeZone": "UTC"
            }
            task_data["isReminderOn"] = True
        except ValueError as e:
            return output_error("invalid_reminder", str(e))

    # 分类
    if args.categories:
        task_data["categories"] = [c.strip() for c in args.categories.split(",")]

    # 重复规则（Graph 要求重复任务必须带 dueDateTime）
    if args.recurrence:
        recurrence = parse_recurrence(args.recurrence)
        if not recurrence:
            return output_error("invalid_recurrence", f"无效的重复规则: {args.recurrence}")
        if "dueDateTime" not in task_data:
            return output_error("recurrence_requires_due",
                                "重复任务必须同时指定 --due 截止日期")
        task_data["recurrence"] = recurrence

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

def _parse_graph_datetime(dt_str):
    """解析 Microsoft Graph 返回的日期时间字符串（UTC，朴素 datetime）。

    兼容有/无小数秒、有/无 Z 后缀等形式，例如：
      2026-08-10T14:30:00.0000000 / 2026-08-10T14:30:00Z / 2026-08-10T14:30:00
    """
    if not dt_str:
        return None
    dt_str = dt_str.replace("Z", "")
    # 截断小数秒部分，避免 rstrip('0') 误删秒位导致解析失败
    if "." in dt_str:
        dt_str = dt_str.split(".", 1)[0]
    return datetime.fromisoformat(dt_str)

def _graph_utc_to_local_date(dt_str):
    """把 Graph 的 UTC 时间字符串转换为本地日期。"""
    dt = _parse_graph_datetime(dt_str)
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone().date()

def cmd_task_list(args, token):
    """列出任务（支持过滤）"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    tasks_data = api_with_pagination(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
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
                     _graph_utc_to_local_date(t["dueDateTime"]["dateTime"]) == today]
        elif f == "overdue":
            now = datetime.utcnow()  # Graph 的 due 为 UTC，比较也用 UTC
            tasks = [t for t in tasks if t.get("dueDateTime") and
                     _parse_graph_datetime(t["dueDateTime"]["dateTime"]) < now and
                     t.get("status") != "completed"]
        elif f == "high":
            tasks = [t for t in tasks if t.get("importance") == "high"]

    formatted_tasks = [format_task_output(t, include_body=args.verbose) for t in tasks]

    if JSON_MODE:
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

            print(f"      ID: {t['id']}\n")

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

    tasks_data = api_with_pagination(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
    if not tasks_data:
        return

    keyword = args.keyword.lower()
    matching = [
        t for t in tasks_data.get("value", [])
        if keyword in t.get("title", "").lower() or
           keyword in t.get("body", {}).get("content", "").lower()
    ]

    formatted = [format_task_output(t, include_body=True) for t in matching]

    output_json(
        {"keyword": args.keyword, "count": len(formatted), "tasks": formatted},
        f"找到 {len(formatted)} 个匹配的任务"
    )

def cmd_task_move(args, token):
    """移动任务到其他列表（复制+删除）"""
    # 获取源列表
    src_list_name = getattr(args, 'from', 'Tasks') or 'Tasks'
    src_lst = get_list_by_name(token, src_list_name)
    if not src_lst:
        return output_error("list_not_found", f"未找到源列表「{src_list_name}」")

    # 获取目标列表
    dst_lst = get_list_by_name(token, args.to)
    if not dst_lst:
        return output_error("list_not_found", f"未找到目标列表「{args.to}」")

    # 获取源任务
    task = api(token, "GET", f"/me/todo/lists/{src_lst['id']}/tasks/{args.task_id}")
    if not task:
        return output_error("task_not_found", f"未找到任务 {args.task_id}")

    # 构建新任务数据（保留关键属性）
    new_task = {
        "title": task.get("title"),
        "status": task.get("status", "notStarted"),
    }

    if task.get("body"):
        new_task["body"] = task["body"]
    if task.get("importance"):
        new_task["importance"] = task["importance"]
    if task.get("dueDateTime"):
        new_task["dueDateTime"] = task["dueDateTime"]
    if task.get("reminderDateTime"):
        new_task["reminderDateTime"] = task["reminderDateTime"]
        new_task["isReminderOn"] = task.get("isReminderOn", True)
    if task.get("recurrence"):
        new_task["recurrence"] = task["recurrence"]
    if task.get("categories"):
        new_task["categories"] = task["categories"]

    # 创建新任务
    result = api(token, "POST", f"/me/todo/lists/{dst_lst['id']}/tasks", new_task)
    if not result:
        return output_error("create_failed", "在新列表中创建任务失败")

    # 删除原任务；若删除失败，回滚新建的副本以免留下重复任务
    del_result = api(token, "DELETE", f"/me/todo/lists/{src_lst['id']}/tasks/{args.task_id}")
    if not del_result:
        api(token, "DELETE", f"/me/todo/lists/{dst_lst['id']}/tasks/{result['id']}", quiet=True)
        return output_error("move_failed", "删除源任务失败，已回滚新建的副本",
                            {"task_id": args.task_id})

    # 记录可撤销：删除新任务并在源列表重建原任务
    record_undo("task_move", {
        "src_list_id": src_lst["id"],
        "dst_list_id": dst_lst["id"],
        "new_task_id": result["id"],
        "old_task": task
    })

    return output_json(
        {"id": result["id"], "title": result["title"], "from": src_lst["displayName"], "to": dst_lst["displayName"]},
        f"✅ 任务已移动到「{dst_lst['displayName']}」"
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

    _CLEAR = {"none", "null", "clear", ""}
    update_data = {}

    if args.title is not None:  # 允许显式设置为空标题
        update_data["title"] = args.title
    if args.body is not None:  # 允许空字符串
        update_data["body"] = {"content": args.body, "contentType": "text"}
    if args.importance:
        update_data["importance"] = args.importance

    # due：传 none/null/clear 可清空
    if args.due is not None:
        if args.due.strip().lower() in _CLEAR:
            update_data["dueDateTime"] = None
        else:
            try:
                due_dt = parse_datetime(args.due)
                update_data["dueDateTime"] = {"dateTime": _local_to_utc_str(due_dt), "timeZone": "UTC"}
            except ValueError as e:
                return output_error("invalid_date", str(e))

    # reminder：传 none/null/clear 可清空
    if args.reminder is not None:
        if args.reminder.strip().lower() in _CLEAR:
            update_data["reminderDateTime"] = None
            update_data["isReminderOn"] = False
        else:
            try:
                reminder_dt = parse_datetime(args.reminder)
                update_data["reminderDateTime"] = {"dateTime": _local_to_utc_str(reminder_dt), "timeZone": "UTC"}
                update_data["isReminderOn"] = True
            except ValueError as e:
                return output_error("invalid_reminder", str(e))

    if getattr(args, "categories", None) is not None:
        cats = args.categories.strip()
        update_data["categories"] = [] if cats.lower() in _CLEAR else [c.strip() for c in cats.split(",")]

    if getattr(args, "recurrence", None):
        recurrence = parse_recurrence(args.recurrence)
        if recurrence is None:
            return output_error("invalid_recurrence", f"无效的重复规则: {args.recurrence}")
        update_data["recurrence"] = recurrence

    if not update_data:
        return output_error("no_updates", "未指定任何更新字段")

    # 仅记录可写字段，避免撤销时把只读属性 PATCH 回去导致 400
    writable_fields = ["title", "body", "importance", "status", "dueDateTime",
                       "reminderDateTime", "isReminderOn", "categories", "recurrence"]
    old_data = {k: current.get(k) for k in writable_fields if k in current}

    result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}", update_data)

    if result:
        # 成功后再记账
        record_undo("task_update", {
            "list_id": lst["id"],
            "task_id": args.task_id,
            "old_data": old_data
        })
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

    old_status = current.get("status")

    result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}", {
        "status": "completed"
    })

    if result:
        record_undo("task_complete", {
            "list_id": lst["id"],
            "task_id": args.task_id,
            "old_status": old_status
        })
        output_json(
            {"id": args.task_id, "status": "completed", "title": result["title"]},
            f"✅ 任务已完成"
        )

def cmd_task_uncomplete(args, token):
    """重新打开已完成的任务"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    current = api(token, "GET", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}")
    if not current:
        return

    old_status = current.get("status")

    result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}", {
        "status": "notStarted"
    })

    if result:
        record_undo("task_uncomplete", {
            "list_id": lst["id"],
            "task_id": args.task_id,
            "old_status": old_status
        })
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

    result = api(token, "DELETE", f"/me/todo/lists/{lst['id']}/tasks/{args.task_id}")

    if result:
        record_undo("task_delete", {
            "list_id": lst["id"],
            "task_id": args.task_id,
            "data": current
        })
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

    tasks_data = api_with_pagination(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
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
        _require_yes_if_noninteractive()
        print(f"将完成 {len(tasks)} 个任务:", file=sys.stderr)
        for t in tasks[:5]:
            print(f"  • {t['title']}", file=sys.stderr)
        if len(tasks) > 5:
            print(f"  ... 还有 {len(tasks) - 5} 个", file=sys.stderr)

        confirm = input(f"\n确认？(y/N): ")
        if confirm.lower() != 'y':
            return output_json({"status": "cancelled"}, "已取消")

    completed = []
    failed = []
    for task in tasks:
        result = api(token, "PATCH", f"/me/todo/lists/{lst['id']}/tasks/{task['id']}", {
            "status": "completed"
        }, quiet=True)
        if result:
            completed.append(task["id"])
        else:
            failed.append(task["id"])

    if failed:
        emit_error("partial_failure", f"{len(failed)} 个任务处理失败",
                   {"failed": failed})

    output_json(
        {"completed": len(completed), "failed": len(failed), "total": len(tasks)},
        f"✅ 已完成 {len(completed)} 个任务" + (f"（{len(failed)} 个失败）" if failed else "")
    )

def cmd_task_delete_all(args, token):
    """批量删除任务"""
    lst = get_list_by_name(token, args.list)
    if not lst:
        return output_error("list_not_found", f"未找到列表「{args.list}」")

    tasks_data = api_with_pagination(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
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
        _require_yes_if_noninteractive()
        print(f"⚠️  将删除 {len(tasks)} 个任务:", file=sys.stderr)
        for t in tasks[:5]:
            print(f"  • {t['title']}", file=sys.stderr)
        if len(tasks) > 5:
            print(f"  ... 还有 {len(tasks) - 5} 个", file=sys.stderr)

        confirm = input(f"\n确认删除？(y/N): ")
        if confirm.lower() != 'y':
            return output_json({"status": "cancelled"}, "已取消")

    deleted = []
    failed = []
    for task in tasks:
        result = api(token, "DELETE", f"/me/todo/lists/{lst['id']}/tasks/{task['id']}", quiet=True)
        if result:
            deleted.append(task["id"])
        else:
            failed.append(task["id"])

    if failed:
        emit_error("partial_failure", f"{len(failed)} 个任务删除失败",
                   {"failed": failed})

    output_json(
        {"deleted": len(deleted), "failed": len(failed), "total": len(tasks)},
        f"✅ 已删除 {len(deleted)} 个任务" + (f"（{len(failed)} 个失败）" if failed else "")
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
        tasks_data = api_with_pagination(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
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
        "cache_bytes": CACHE_FILE.stat().st_size if CACHE_FILE.exists() else 0
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

        tasks_data = api_with_pagination(token, "GET", f"/me/todo/lists/{lst['id']}/tasks")
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

    if operation == "task_create":
        # 删除刚创建的任务
        task_id = data.get("task_id")
        list_id = data.get("list_id")
        if task_id and list_id:
            result = api(token, "DELETE", f"/me/todo/lists/{list_id}/tasks/{task_id}")
            if result:
                pop_undo_log()
                return output_json(
                    {"status": "undone", "operation": operation, "task_id": task_id},
                    f"✅ 已撤销任务创建: {data.get('title', task_id)}"
                )
    
    elif operation == "task_update":
        # 恢复任务到旧状态
        task_id = data.get("task_id")
        list_id = data.get("list_id")
        old_data = data.get("old_data", {})
        if task_id and list_id and old_data:
            result = api(token, "PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", old_data)
            if result:
                pop_undo_log()
                return output_json(
                    {"status": "undone", "operation": operation, "task_id": task_id},
                    f"✅ 已撤销任务更新"
                )
    
    elif operation == "task_delete":
        # 重新创建被删除的任务（保留全部可写字段）
        task_data = data.get("data", {})
        list_id = data.get("list_id")
        if task_data and list_id:
            result = api(token, "POST", f"/me/todo/lists/{list_id}/tasks", _restore_payload(task_data))
            if result:
                pop_undo_log()
                return output_json(
                    {"status": "undone", "operation": operation},
                    f"✅ 已恢复已删除任务: {task_data.get('title', '未知')}"
                )
    
    elif operation == "task_complete":
        # 恢复到完成前的状态（notStarted / inProgress）
        task_id = data.get("task_id")
        list_id = data.get("list_id")
        old_status = data.get("old_status") or "notStarted"
        if task_id and list_id:
            result = api(token, "PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", {
                "status": old_status
            })
            if result:
                pop_undo_log()
                return output_json(
                    {"status": "undone", "operation": operation, "task_id": task_id},
                    f"✅ 已撤销任务完成"
                )

    elif operation == "task_uncomplete":
        # 恢复到重新打开前的状态（通常是 completed）
        task_id = data.get("task_id")
        list_id = data.get("list_id")
        old_status = data.get("old_status") or "completed"
        if task_id and list_id:
            result = api(token, "PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", {
                "status": old_status
            })
            if result:
                pop_undo_log()
                return output_json(
                    {"status": "undone", "operation": operation, "task_id": task_id},
                    f"✅ 已撤销重新打开"
                )

    elif operation == "task_move":
        # 删除移动后生成的新任务，并在源列表重建原任务
        src_list_id = data.get("src_list_id")
        dst_list_id = data.get("dst_list_id")
        new_task_id = data.get("new_task_id")
        old_task = data.get("old_task", {})
        if src_list_id and dst_list_id and new_task_id and old_task:
            api(token, "DELETE", f"/me/todo/lists/{dst_list_id}/tasks/{new_task_id}", quiet=True)
            result = api(token, "POST", f"/me/todo/lists/{src_list_id}/tasks", _restore_payload(old_task))
            if result:
                pop_undo_log()
                return output_json(
                    {"status": "undone", "operation": operation},
                    f"✅ 已撤销任务移动: {old_task.get('title', '未知')}"
                )

    elif operation == "list_create":
        # 删除刚创建的列表
        list_id = data.get("list_id")
        if list_id:
            result = api(token, "DELETE", f"/me/todo/lists/{list_id}")
            if result:
                pop_undo_log()
                return output_json(
                    {"status": "undone", "operation": operation, "list_id": list_id},
                    f"✅ 已撤销列表创建: {data.get('name', list_id)}"
                )
    
    elif operation == "list_rename":
        # 恢复旧名称
        list_id = data.get("list_id")
        old_name = data.get("old_name")
        if list_id and old_name:
            result = api(token, "PATCH", f"/me/todo/lists/{list_id}", {
                "displayName": old_name
            })
            if result:
                pop_undo_log()
                return output_json(
                    {"status": "undone", "operation": operation},
                    f"✅ 已撤销列表重命名"
                )

    # 走到这里：要么是已知操作但 API 调用失败，要么是未知/不可撤销操作
    known_ops = {"task_create", "task_update", "task_delete", "task_complete",
                 "task_uncomplete", "task_move", "list_create", "list_rename"}
    if operation in known_ops:
        # 已知操作但撤销失败：保留记录，允许重试（错误已由 api 汇报）
        return output_json(
            {"status": "undo_failed", "operation": operation},
            f"⚠️ 撤销失败，请稍后重试: {operation}"
        )
    # 未知/不可撤销：丢弃该记录以让 undo 栈继续前进
    pop_undo_log()
    return output_json(
        {"status": "unsupported", "operation": operation},
        f"⚠️ 不支持撤销、已跳过: {operation}"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# 配置命令
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_config(args, token=None):
    """配置管理"""
    cfg = load_config()

    changed = {}
    if args.client_id:
        cfg["client_id"] = args.client_id
        changed["client_id"] = args.client_id
    if getattr(args, "authority", None):
        cfg["authority"] = args.authority
        changed["authority"] = args.authority

    if changed:
        save_config(cfg)
        output_json({"status": "saved", **changed}, "✅ 配置已保存")
    else:
        # --show 与无参数行为一致：显示当前配置
        output_json(cfg, None)

def cmd_logout(args=None):
    """登出：删除本地 token 缓存。"""
    existed = TOKEN_CACHE_FILE.exists()
    if existed:
        try:
            TOKEN_CACHE_FILE.unlink()
        except OSError as e:
            return output_error("logout_failed", f"无法删除 token 缓存: {e}")
    output_json(
        {"status": "logged_out", "was_authenticated": existed},
        "✅ 已登出" if existed else "（当前未登录）"
    )

def cmd_auth(args, token=None):
    """认证：login(默认) / logout / status。"""
    action = getattr(args, "action", "login") or "login"

    if action == "logout":
        return cmd_logout(args)

    cfg = load_config()
    client_id = cfg.get("client_id")
    if not client_id:
        return output_error("no_client_id", "请先配置: todo config --client-id <YOUR_CLIENT_ID>")

    if action == "status":
        # 非交互：仅静默获取，失败则 not_authenticated 退出
        tok = get_token(client_id, interactive=False)
        return cmd_status(args, tok)

    # login
    get_token(client_id, force_login=True, interactive=True)
    output_json({"status": "authenticated"}, "✅ 认证成功")

# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    global JSON_MODE
    # 先从任意位置提取并剥离 --json，使其在子命令前后皆可用，
    # 且仅匹配完整参数（避免任务标题/描述中的 "--json" 误触发）
    argv = sys.argv[1:]
    # `--` 之后的一律视为字面值，不参与剥离：
    # 否则 `task add -- --json`（标题就叫 "--json"）会被吃掉。
    cut = argv.index("--") if "--" in argv else len(argv)
    if "--json" in argv[:cut]:
        JSON_MODE = True
        argv = [a for a in argv[:cut] if a != "--json"] + argv[cut:]

    parser = argparse.ArgumentParser(
        description="Microsoft To Do CLI Harness (Agent-Native)",
        epilog="添加 --json 以获取结构化输出"
    )
    parser.add_argument("--json", action="store_true", help="输出JSON格式（可置于任意位置）")

    sub = parser.add_subparsers(dest="cmd", help="子命令")

    # ─────────────────────────────────────────────────────────────────────
    # 配置和认证
    # ─────────────────────────────────────────────────────────────────────

    p = sub.add_parser("config", help="配置 Client ID / authority")
    p.add_argument("--client-id", help="Azure 应用 Client ID")
    p.add_argument("--authority", help="登录端点，如 https://login.microsoftonline.com/common（支持工作/学校账户）")
    p.add_argument("--show", action="store_true", help="显示当前配置")

    p = sub.add_parser("auth", help="登录 / 登出 / 查看认证状态")
    p.add_argument("action", nargs="?", default="login",
                   choices=["login", "logout", "status"], help="login(默认)/logout/status")

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
    p.add_argument("--recurrence", help="重复规则 (daily/weekly/monthly:17/yearly:09-17)")
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

    # task move
    p = task_sub.add_parser("move", help="移动任务到其他列表")
    p.add_argument("task_id", help="任务ID")
    p.add_argument("--to", "-t", required=True, help="目标列表名称")
    p.add_argument("--from", "-f", default="Tasks", help="源列表名称")

    # task update
    p = task_sub.add_parser("update", help="更新任务")
    p.add_argument("task_id", help="任务ID")
    p.add_argument("--title", "-t", help="新标题（传空字符串可清空）")
    p.add_argument("--body", "-b", help="新描述")
    p.add_argument("--importance", "-i", choices=["low", "normal", "high"], help="优先级")
    p.add_argument("--due", "-d", help="截止日期（none/null/clear 清空）")
    p.add_argument("--reminder", "-r", help="提醒时间（none/null/clear 清空）")
    p.add_argument("--categories", "-c", help="分类（逗号分隔；none/clear 清空）")
    p.add_argument("--recurrence", help="重复规则 (daily/weekly:mon,wed/monthly:17/yearly:09-17)")
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

    args = parser.parse_args(argv)

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
        "move": cmd_task_move,
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

    # 请求层遇到过（非致命）错误时，以非零退出码结束，便于脚本 / agent 判断
    if _ERROR_EMITTED:
        sys.exit(1)


if __name__ == "__main__":
    # 兜底：未预期异常若以 traceback 形式冒到 stdout/stderr，会破坏 --json 契约。
    # SystemExit 继承自 BaseException，不会被这里拦住，output_error 的退出码照常生效。
    try:
        main()
    except KeyboardInterrupt:
        emit_error("interrupted", "已取消")
        sys.exit(130)
    except Exception as e:
        if os.environ.get("MSTODO_DEBUG"):
            raise
        emit_error("internal_error", f"{type(e).__name__}: {e}",
                   {"hint": "设置 MSTODO_DEBUG=1 可查看完整 traceback"})
        sys.exit(1)

