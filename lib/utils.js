const { spawn, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

// 检测Python命令（要求 major >= 3；退出码为 0 但版本是 Python 2 时跳过）
function detectPython() {
  const pythonCommands = ['python3', 'python'];

  for (const cmd of pythonCommands) {
    try {
      const result = spawnSync(cmd, ['--version'], {
        stdio: 'pipe',
        encoding: 'utf-8'
      });

      if (result.status === 0) {
        const version = result.stdout || result.stderr;
        const match = version.match(/Python (\d+)\.(\d+)\.(\d+)/);
        // 只解析出退出码不足以判断：Python 2 也返回 0，会用 py2 跑 f-string 脚本直接 SyntaxError
        if (!match || parseInt(match[1], 10) < 3) {
          continue;  // 不是 Python 3，继续尝试下一个命令
        }
        return {
          command: cmd,
          version: `${match[1]}.${match[2]}.${match[3]}`,
          found: true
        };
      }
    } catch (e) {
      // 继续尝试
    }
  }

  return { found: false };
}

// 安装Python依赖
function installPythonDeps() {
  const chalk = require('chalk');
  const ora = require('ora');

  const requirementsPath = path.join(__dirname, '..', 'requirements.txt');
  const python = detectPython();

  if (!python.found) {
    console.error(chalk.red('❌ Python 3 is required but not found'));
    console.error('Please install Python 3: https://www.python.org/downloads/');
    return false;
  }

  const spinner = ora('Installing Python dependencies...').start();

  // 先尝试 --user；在 venv / PEP 668「externally-managed」环境下 --user 会被拒，
  // 此时回退为不带 --user 的安装。
  const attempts = [
    ['-m', 'pip', 'install', '-r', requirementsPath, '--user', '--quiet'],
    ['-m', 'pip', 'install', '-r', requirementsPath, '--quiet'],
  ];

  let lastErr = '';
  for (const args of attempts) {
    try {
      const result = spawnSync(python.command, args, { stdio: 'pipe', encoding: 'utf-8' });
      if (result.status === 0) {
        spinner.succeed(chalk.green('Python dependencies installed'));
        return true;
      }
      lastErr = result.stderr || result.stdout || '';
      // 仅当疑似 --user 相关限制时才回退，其它错误直接失败
      if (!/--user|externally-managed|can not perform a/i.test(lastErr)) break;
    } catch (error) {
      lastErr = error.message;
      break;
    }
  }

  spinner.fail(chalk.red('Failed to install Python dependencies'));
  console.error(lastErr);
  console.error(chalk.gray('You can install manually, e.g. inside a virtualenv:'));
  console.error(chalk.gray(`  ${python.command} -m pip install -r ${requirementsPath}`));
  return false;
}

// 获取配置目录
function getConfigDir() {
  return path.join(os.homedir(), '.config', 'ms-todo');
}

// 获取配置文件路径
function getConfigPath() {
  return path.join(getConfigDir(), 'config.json');
}

// 读取配置
function loadConfig() {
  const configPath = getConfigPath();
  if (!fs.existsSync(configPath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(configPath, 'utf-8'));
  } catch (e) {
    return null;
  }
}

// 保存配置（合并已有键，避免覆盖 Python 写入的其它字段；权限收紧到 0600 / 目录 0700）
function saveConfig(config) {
  const configDir = getConfigDir();
  const configPath = getConfigPath();

  if (!fs.existsSync(configDir)) {
    fs.mkdirSync(configDir, { recursive: true });
  }
  try { fs.chmodSync(configDir, 0o700); } catch (e) { /* ignore */ }

  const existing = loadConfig() || {};
  const merged = { ...existing, ...config };

  fs.writeFileSync(configPath, JSON.stringify(merged, null, 2), 'utf-8');
  try { fs.chmodSync(configPath, 0o600); } catch (e) { /* ignore */ }
}

// 调用Python脚本
function callPython(args) {
  return new Promise((resolve, reject) => {
    const python = detectPython();
    if (!python.found) {
      reject(new Error('Python not found'));
      return;
    }

    const scriptPath = path.join(__dirname, '..', 'todo_v2.py');
    // 注意：spawn 不支持 encoding 选项；须显式 setEncoding，否则多字节字符
    // （如中文）在 chunk 边界被切开会解码错乱。
    const proc = spawn(python.command, [scriptPath, ...args], { stdio: 'pipe' });
    proc.stdout.setEncoding('utf8');
    proc.stderr.setEncoding('utf8');

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
      stdout += data;
    });

    proc.stderr.on('data', (data) => {
      stderr += data;
    });

    proc.on('close', (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
      } else {
        reject(new Error(stderr || stdout));
      }
    });

    proc.on('error', reject);
  });
}

module.exports = {
  detectPython,
  installPythonDeps,
  getConfigDir,
  getConfigPath,
  loadConfig,
  saveConfig,
  callPython
};
