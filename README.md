# Microsoft To Do CLI

> Agent-native command-line interface for Microsoft To Do

[![npm version](https://badge.fury.io/js/ms-todo-cli.svg)](https://www.npmjs.com/package/ms-todo-cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A powerful CLI tool for managing Microsoft To Do tasks from your terminal. Perfect for automation, AI agents, and productivity workflows.

## ✨ Features

- 🚀 **Quick Setup** - Get started in 4 simple steps
- 🤖 **Agent-Native** - JSON output for every command; errors on stderr, non-zero exit on failure
- 📋 **Complete CRUD** - Full task and list management
- ⚡ **Batch Operations** - Complete or delete multiple tasks at once
- ↩️ **Undo** - Reverse recent create / update / delete / complete / move / rename operations
- 🔄 **Snapshot Export** - `mstodo sync` writes a local snapshot of all lists/tasks to `cache.json`
- 🔒 **Private by Default** - Credentials stored with `0600` permissions, written atomically
- 🎨 **Beautiful UI** - Colorful, emoji-rich terminal output

## 📦 Installation

### Quick Start (Recommended)

```bash
npx ms-todo-cli@latest setup
```

### Global Installation

```bash
npm install -g ms-todo-cli
```

## 🚀 Quick Start

### Step 1: Configure

```bash
mstodo config init
```

This will guide you through registering an Azure application and entering your Client ID.

**Azure Registration Steps:**
1. Visit [Azure Portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps)
2. Click "New registration"
3. Set:
   - **Name**: "My To Do CLI"
   - **Supported account types**: "Personal Microsoft accounts"
   - **Redirect URI**: "Public client/native" → `http://localhost`
4. Go to "API permissions" → Add:
   - `Tasks.ReadWrite`
   - `User.Read`
5. Copy the **Application (client) ID**
6. Paste it when prompted by `mstodo config init`

### Step 2: Login

```bash
mstodo auth login
```

The CLI will:
- Display the device code and sign-in URL
- Copy the device code to your clipboard and open the browser automatically
- Wait for you to finish signing in, then confirm success

> **Work / school accounts:** the default endpoint targets personal Microsoft
> accounts. To sign in with a work or school account, set the authority first:
>
> ```bash
> mstodo config --authority "https://login.microsoftonline.com/common"
> ```

### Step 3: Use

```bash
# List all tasks
mstodo task list

# Create a task
mstodo task add "Complete report" --due tomorrow --importance high

# Search tasks
mstodo task search "report"

# Complete a task
mstodo task complete <task-id>
```

## 📖 Usage

### Task Management

```bash
# Create task with full details
mstodo task add "Team meeting" \
  --body "Discuss Q3 goals" \
  --due "2026-08-15" \
  --reminder "2026-08-15T09:00" \
  --importance high \
  --categories "work,meetings" \
  --json

# Recurring task (a due date is required for recurrence)
mstodo task add "Standup" --due tomorrow --recurrence "weekly:mon,wed,fri"
# Recurrence formats: daily | weekly:mon,wed | monthly:17 | yearly:09-17
# Weekdays accept English (mon/monday) or Chinese (周一).

# List tasks by filter
mstodo task list --filter incomplete
mstodo task list --filter today
mstodo task list --filter high
mstodo task list --filter overdue

# Update task (now also supports categories / recurrence)
mstodo task update <task-id> --title "New title" --importance low
mstodo task update <task-id> --categories "work,urgent"
# Clear a field by passing none/null/clear:
mstodo task update <task-id> --due none --reminder clear

# Complete / reopen / delete
mstodo task complete <task-id>
mstodo task uncomplete <task-id>
mstodo task delete <task-id>

# Move a task to another list (see note about --list below)
mstodo task move <task-id> --from "Inbox" --to "Work"

# Undo the last create / update / delete / complete / uncomplete / move / rename
mstodo undo
```

> **All task commands operate on a single list** (default: `Tasks`). Because a
> task id is scoped to its list, pass `--list "<name>"` to `info` / `update` /
> `complete` / `delete` / `move` when the task is not in the default list.
> See [Known Limitations](#-known-limitations).

### List Management

```bash
# Create list
mstodo list-create "Work Tasks"

# View all lists
mstodo lists

# Rename list
mstodo list-rename "Old Name" "New Name"

# Delete list
mstodo list-delete "List Name" --yes
```

### Batch Operations

```bash
# Complete all incomplete tasks whose title contains "test"
mstodo task complete-all --match "test" --yes

# Delete all tasks whose title contains "draft"
mstodo task delete-all --match "draft" --yes
```

> `--filter` here matches a substring of the task **title** (not a status).
> Destructive batch commands prompt for confirmation when run interactively;
> in a non-interactive context (no TTY, or `--json`) you **must** pass `--yes`,
> otherwise the command exits with a `confirmation_required` error instead of
> hanging on a prompt. Partial failures are reported via `failed` in the result
> and a non-zero exit code.

### Status & Sync

```bash
# Check authentication status
mstodo auth status

# View detailed status
mstodo status

# Sign out (removes the local token cache)
mstodo auth logout

# Export a local snapshot of all lists/tasks to cache.json
mstodo sync
```

## 🤖 Agent Integration

All commands support the `--json` flag for structured output. It may appear
**anywhere** on the command line (before or after the subcommand):

```bash
mstodo task list --json
mstodo --json task list   # equivalent
```

**Output contract:**
- On success, **stdout** contains exactly one JSON document.
- On error, the structured error is written to **stderr** and the process
  exits with a **non-zero** code. (So `json.loads(stdout)` never has to cope
  with mixed error/result output.)

**Example output:**

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

### Python Integration

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
        # Errors are structured JSON on stderr
        try:
            raise RuntimeError(json.loads(result.stderr))
        except json.JSONDecodeError:
            raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)

# Create task
task = mstodo('task add "Meeting" --due tomorrow')
print(f"Created: {task['id']}")

# List today's tasks
today = mstodo('task list --filter today')
print(f"Today: {today['count']} tasks")
```

## 🔧 Configuration

Configuration is stored in `~/.config/ms-todo/` (directory `0700`, sensitive
files `0600`, written atomically):

```
~/.config/ms-todo/
├── config.json        # Client ID, optional authority
├── token_cache.bin    # Authentication token (0600)
├── cache.json         # Snapshot written by `mstodo sync`
└── undo_log.json      # Operation history for `mstodo undo`
```

`config.json` keys:

| Key         | Description                                                        |
|-------------|--------------------------------------------------------------------|
| `client_id` | Azure application (client) ID                                       |
| `authority` | Login endpoint; default is personal accounts. Set to `.../common` for work/school accounts (`mstodo config --authority ...`) |

## 🔐 Azure App Setup

**Required for all users:**

1. Visit [Azure Portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps)
2. Click "New registration"
3. Set:
   - **Name**: "My To Do CLI" (or any name you prefer)
   - **Supported account types**: "Personal Microsoft accounts"
   - **Redirect URI**: "Public client/native" → `http://localhost`
4. Go to "API permissions" → Add:
   - `Tasks.ReadWrite`
   - `User.Read`
5. Copy the **Application (client) ID**
6. Run: `mstodo config init` and paste the ID

**Note:** Each user needs their own Azure application registration. This ensures your data security and avoids API rate limits.

## ⚠️ Known Limitations

- **Single-list scope.** `task list` and `task search` operate on one list at a
  time (default `Tasks`), and a task id is only meaningful within its list.
  There is currently no cross-list query or id-based auto-resolution — pass
  `--list "<name>"` to address tasks in other lists.
- **`task move` is copy + delete.** Microsoft Graph has no cross-list move API,
  so a move creates a new task in the target list and deletes the original. The
  task **id changes** and server-managed fields like `createdDateTime` are not
  preserved. (The operation is undoable via `mstodo undo`.)
- **`lists` / `status` make one request per list.** Listing task counts across
  many lists issues a request per list, so these commands scale with the number
  of lists.

## 📚 Documentation

- [QUICKSTART.md](./QUICKSTART.md) - Detailed quick start guide
- [SKILL.md](./SKILL.md) - Complete API reference for agents

## 🛠️ Requirements

- **Node.js** 14.0.0 or higher
- **Python** 3.7 or higher
- **pip** for Python package management

## 🐛 Troubleshooting

### Python not found

```bash
# Install Python 3
# macOS
brew install python3

# Windows
# Download from https://www.python.org/downloads/

# Linux
sudo apt install python3 python3-pip
```

### Authentication failed

```bash
# Re-authenticate
mstodo auth login

# Check status
mstodo auth status
```

### Dependencies error

Python dependencies are installed by `mstodo setup` (they are **not** installed
automatically during `npm install`). If `setup` fails because your environment
is externally managed (PEP 668) or a virtualenv rejects `--user`, install them
manually — ideally inside a virtualenv:

```bash
mstodo setup

# or manually
python3 -m pip install -r requirements.txt
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

MIT © Haolong Zheng

## 🔗 Links

- [GitHub Repository](https://github.com/zhenghaolong/ms-todo-cli)
- [npm Package](https://www.npmjs.com/package/ms-todo-cli)
- [Report Issues](https://github.com/zhenghaolong/ms-todo-cli/issues)

## ⭐ Support

If you find this tool useful, please consider giving it a star on GitHub!

---

**Made with ❤️ for developers and AI agents**
