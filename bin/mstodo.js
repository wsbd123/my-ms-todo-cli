#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// 获取Python脚本的路径
const scriptPath = path.join(__dirname, '..', 'todo_v2.py');

// 检查Python脚本是否存在
if (!fs.existsSync(scriptPath)) {
  console.error('❌ Error: todo_v2.py not found');
  console.error('Please reinstall the package: npm install -g ms-todo-cli');
  process.exit(1);
}

// 检查Python是否可用
function checkPython() {
  const pythonCommands = ['python3', 'python'];

  for (const cmd of pythonCommands) {
    try {
      const result = require('child_process').spawnSync(cmd, ['--version'], {
        stdio: 'pipe',
        encoding: 'utf-8'
      });

      if (result.status === 0) {
        return cmd;
      }
    } catch (e) {
      // 继续尝试下一个命令
    }
  }

  return null;
}

// 特殊命令处理：setup, config init, auth login, auth status
const args = process.argv.slice(2);
const command = args[0];
const subcommand = args[1];

// 如果是特殊命令，使用Node.js包装器
if (command === 'setup' ||
    (command === 'config' && subcommand === 'init') ||
    (command === 'auth' && (subcommand === 'login' || subcommand === 'status'))) {
  const { main } = require('../lib/cli-wrapper.js');
  main().catch((error) => {
    console.error('Error:', error.message);
    process.exit(1);
  });
  return;
}

// 其他命令：直接调用Python脚本
const pythonCmd = checkPython();

if (!pythonCmd) {
  console.error('❌ Error: Python 3 is required but not found');
  console.error('Please install Python 3: https://www.python.org/downloads/');
  process.exit(1);
}

// 执行Python脚本
const python = spawn(pythonCmd, [scriptPath, ...args], {
  stdio: 'inherit',
  env: process.env
});

python.on('error', (error) => {
  console.error('❌ Failed to start Python process:', error.message);
  process.exit(1);
});

python.on('exit', (code) => {
  process.exit(code || 0);
});
