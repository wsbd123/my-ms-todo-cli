const { spawn, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

// 检测Python命令
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
        const match = version.match(/Python (\d+\.\d+\.\d+)/);
        return {
          command: cmd,
          version: match ? match[1] : 'unknown',
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

  try {
    const result = spawnSync(python.command, [
      '-m', 'pip', 'install', '-r', requirementsPath, '--user', '--quiet'
    ], {
      stdio: 'pipe',
      encoding: 'utf-8'
    });

    if (result.status === 0) {
      spinner.succeed(chalk.green('Python dependencies installed'));
      return true;
    } else {
      spinner.fail(chalk.red('Failed to install Python dependencies'));
      console.error(result.stderr);
      return false;
    }
  } catch (error) {
    spinner.fail(chalk.red('Failed to install Python dependencies'));
    console.error(error.message);
    return false;
  }
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

// 保存配置
function saveConfig(config) {
  const configDir = getConfigDir();
  const configPath = getConfigPath();

  if (!fs.existsSync(configDir)) {
    fs.mkdirSync(configDir, { recursive: true });
  }

  fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf-8');
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
    const proc = spawn(python.command, [scriptPath, ...args], {
      stdio: 'pipe',
      encoding: 'utf-8'
    });

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
