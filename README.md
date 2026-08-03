# Microsoft To Do CLI

> Agent-native command-line interface for Microsoft To Do

[![npm version](https://badge.fury.io/js/ms-todo-cli.svg)](https://www.npmjs.com/package/ms-todo-cli)
[![Downloads](https://img.shields.io/npm/dm/ms-todo-cli.svg)](https://www.npmjs.com/package/ms-todo-cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A powerful CLI tool for managing Microsoft To Do tasks from your terminal. Perfect for automation, AI agents, and productivity workflows.

## ✨ Features

- 🚀 **Quick Setup** - Get started in 4 simple steps
- 🤖 **Agent-Native** - JSON output for all commands
- 📋 **Complete CRUD** - Full task and list management
- ⚡ **Batch Operations** - Complete or delete multiple tasks at once
- 🔄 **Smart Sync** - Local caching for faster queries
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
- Automatically open your browser
- Copy the device code to clipboard
- Show a progress bar while waiting
- Confirm successful authentication

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
  --json

# List tasks by filter
mstodo task list --filter incomplete
mstodo task list --filter today
mstodo task list --filter high
mstodo task list --filter overdue

# Update task
mstodo task update <task-id> --title "New title" --importance low

# Complete task
mstodo task complete <task-id>

# Delete task
mstodo task delete <task-id>
```

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
# Complete all tasks matching keyword
mstodo task complete-all --filter "test" --yes

# Delete all completed tasks
mstodo task delete-all --filter "completed" --yes
```

### Status & Sync

```bash
# Check authentication status
mstodo auth status

# View detailed status
mstodo status

# Sync local cache
mstodo sync
```

## 🤖 Agent Integration

All commands support `--json` flag for structured output:

```bash
mstodo task list --json
```

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
        text=True
    )
    return json.loads(result.stdout)

# Create task
task = mstodo('task add "Meeting" --due tomorrow')
print(f"Created: {task['id']}")

# List today's tasks
today = mstodo('task list --filter today')
print(f"Today: {today['count']} tasks")
```

## 🔧 Configuration

Configuration is stored in `~/.config/ms-todo/`:

```
~/.config/ms-todo/
├── config.json        # Client ID and settings
├── token_cache.bin    # Authentication token
├── cache.json         # Local task cache
└── undo_log.json      # Operation history
```

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

```bash
# Manually install Python dependencies
pip3 install -r requirements.txt
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

MIT © [Your Name]

## 🔗 Links

- [GitHub Repository](https://github.com/yourusername/ms-todo-cli)
- [npm Package](https://www.npmjs.com/package/ms-todo-cli)
- [Report Issues](https://github.com/yourusername/ms-todo-cli/issues)

## ⭐ Support

If you find this tool useful, please consider giving it a star on GitHub!

---

**Made with ❤️ for developers and AI agents**
