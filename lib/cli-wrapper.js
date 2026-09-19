#!/usr/bin/env node

const chalk = require('chalk');
const prompts = require('prompts');
const ora = require('ora');
const open = require('open');
const clipboardy = require('clipboardy');
const cliProgress = require('cli-progress');
const { spawn } = require('child_process');
const path = require('path');

const {
  detectPython,
  installPythonDeps,
  loadConfig,
  saveConfig,
  callPython
} = require('./utils');

// ============================================================================
// Setup命令：初始化安装
// ============================================================================
async function setupCommand() {
  console.log(chalk.bold.cyan('\n🚀 Microsoft To Do CLI Setup'));
  console.log(chalk.cyan('━'.repeat(43)));

  // 1. 检测Python
  const python = detectPython();
  if (python.found) {
    console.log(chalk.green(`✅ Python ${python.version} detected`));
  } else {
    console.log(chalk.red('❌ Python 3 not found'));
    console.log('Please install Python 3: https://www.python.org/downloads/');
    process.exit(1);
  }

  // 2. 安装Python依赖
  const depsInstalled = installPythonDeps();
  if (!depsInstalled) {
    process.exit(1);
  }

  // 3. 完成
  console.log(chalk.cyan('\n' + '━'.repeat(43)));
  console.log(chalk.bold.green('✅ Setup complete!\n'));
  console.log('Next steps:');
  console.log(chalk.cyan('  1. mstodo config init'));
  console.log(chalk.cyan('  2. mstodo auth login'));
  console.log(chalk.cyan('  3. mstodo task list\n'));
  console.log('Documentation: https://github.com/zhenghaolong/ms-todo-cli');
}

// ============================================================================
// Config Init命令：配置凭证
// ============================================================================
async function configInitCommand() {
  console.log(chalk.bold.cyan('\n🔧 Configuration Setup'));
  console.log(chalk.cyan('━'.repeat(43)));

  const existingConfig = loadConfig();

  if (existingConfig && existingConfig.client_id) {
    console.log(chalk.yellow('⚠️  Configuration already exists'));
    const { overwrite } = await prompts({
      type: 'confirm',
      name: 'overwrite',
      message: 'Do you want to reconfigure?',
      initial: false
    });

    if (!overwrite) {
      console.log(chalk.gray('Configuration unchanged'));
      return;
    }
  }

  // 显示Azure注册指南
  console.log(chalk.cyan('\n📝 Azure App Registration Required'));
  console.log(chalk.gray('You need to register an Azure application to use this CLI.\n'));
  console.log('Steps:');
  console.log(chalk.gray('  1. Visit: https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps'));
  console.log(chalk.gray('  2. Click "New registration"'));
  console.log(chalk.gray('  3. Set:'));
  console.log(chalk.gray('     - Name: "My To Do CLI"'));
  console.log(chalk.gray('     - Supported account types: "Personal Microsoft accounts"'));
  console.log(chalk.gray('     - Redirect URI: "Public client/native" → http://localhost'));
  console.log(chalk.gray('  4. Go to "API permissions" → Add:'));
  console.log(chalk.gray('     - Tasks.ReadWrite'));
  console.log(chalk.gray('     - User.Read'));
  console.log(chalk.gray('  5. Copy the "Application (client) ID"\n'));

  const { openDocs } = await prompts({
    type: 'confirm',
    name: 'openDocs',
    message: 'Open Azure Portal in browser?',
    initial: true
  });

  if (openDocs) {
    try {
      await open('https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade');
      console.log(chalk.green('✅ Browser opened'));
    } catch (e) {
      console.log(chalk.yellow('⚠️  Please open manually'));
    }
  }

  console.log();
  const response = await prompts({
    type: 'text',
    name: 'clientId',
    message: 'Enter your Azure Application (client) ID:',
    validate: (value) => value.length > 0 ? true : 'Client ID is required'
  });

  if (!response.clientId) {
    console.log(chalk.red('\n❌ Configuration cancelled'));
    process.exit(1);
  }

  const clientId = response.clientId;

  // 保存配置
  saveConfig({
    client_id: clientId,
    configured_at: new Date().toISOString()
  });

  console.log(chalk.green('\n✅ Configuration saved'));
  console.log(chalk.gray('📝 Config saved to ~/.config/ms-todo/config.json'));
  console.log(chalk.cyan('\nNext step: mstodo auth login'));
}

// ============================================================================
// Auth Login命令：增强的登录流程
// ============================================================================
async function authLoginCommand() {
  console.log(chalk.bold.cyan('\n🔐 Authentication'));
  console.log(chalk.cyan('━'.repeat(43)));

  // 检查配置
  const config = loadConfig();
  if (!config || !config.client_id) {
    console.log(chalk.red('❌ Configuration not found'));
    console.log(chalk.yellow('Please run: mstodo config init'));
    process.exit(1);
  }

  console.log(chalk.cyan('\n🌐 Starting authentication flow...\n'));

  // 调用Python脚本进行认证
  const python = detectPython();
  if (!python.found) {
    console.log(chalk.red('❌ Python not found'));
    process.exit(1);
  }

  const scriptPath = path.join(__dirname, '..', 'todo_v2.py');

  return new Promise((resolve, reject) => {
    // 注意：spawn 无 encoding 选项，须 setEncoding，否则中文按块解码会乱码
    const proc = spawn(python.command, [scriptPath, 'auth', 'login'], { stdio: 'pipe' });
    proc.stdout.setEncoding('utf8');
    proc.stderr.setEncoding('utf8');

    let enhanced = false;
    let spinner = null;

    // 设备码信息可能出现在 stdout（Python 现打到 stdout）或 stderr；两路都扫描
    function scanForDeviceCode(text) {
      if (enhanced) return;
      const urlMatch = text.match(/(https?:\/\/\S*devicelogin\S*)/i) || text.match(/(https?:\/\/\S+)/);
      const codeMatch = text.match(/\b([A-Z0-9]{9})\b/);
      if (urlMatch && codeMatch) {
        enhanced = true;
        const url = urlMatch[1];
        const code = codeMatch[1];
        try {
          clipboardy.writeSync(code);
          console.log(chalk.gray('(device code copied to clipboard)'));
        } catch (e) { /* ignore */ }
        try { open(url); } catch (e) { /* ignore */ }
        // 真实的等待状态，不再伪造百分比进度
        spinner = ora('Waiting for you to finish signing in in the browser...').start();
      }
    }

    proc.stdout.on('data', (data) => {
      process.stdout.write(data);   // 透传原始输出（含设备码提示）
      scanForDeviceCode(data);
    });

    proc.stderr.on('data', (data) => {
      process.stderr.write(data);
      scanForDeviceCode(data);
    });

    // close 处理器注册在顶层，保证 Promise 总能 settle（旧代码嵌在 stdout 回调里，
    // 设备码走 stderr 时永不触发，导致既不 resolve 也不 reject）
    proc.on('close', (code) => {
      if (spinner) spinner.stop();
      if (code === 0) {
        console.log(chalk.green('\n✅ Authentication successful!'));
        callPython(['--json', 'status'])
          .then(({ stdout }) => {
            try {
              const status = JSON.parse(stdout);
              if (status.user) console.log(chalk.cyan(`👤 Logged in as: ${status.user}`));
            } catch (e) { /* ignore */ }
            console.log(chalk.cyan('\nNext step: mstodo task list'));
            resolve();
          })
          .catch(() => {
            console.log(chalk.cyan('\nNext step: mstodo task list'));
            resolve();
          });
      } else {
        console.log(chalk.red('\n❌ Authentication failed'));
        reject(new Error('Authentication failed'));
      }
    });

    proc.on('error', (error) => {
      if (spinner) spinner.stop();
      console.log(chalk.red('❌ Error:'), error.message);
      reject(error);
    });
  });
}

// ============================================================================
// Auth Status命令：显示认证状态
// ============================================================================
async function authStatusCommand() {
  console.log(chalk.bold.cyan('\n🔐 Authentication Status'));
  console.log(chalk.cyan('━'.repeat(43)));

  const spinner = ora('Checking authentication...').start();

  try {
    const { stdout } = await callPython(['--json', 'status']);
    spinner.stop();
    const status = JSON.parse(stdout);

    console.log(chalk.green('\n✅ Authenticated'));
    if (status.user) {
      console.log(chalk.cyan(`👤 User: ${status.user}`));
    }

    // 任务统计
    if (status.tasks) {
      console.log(chalk.cyan('📊 Quick Stats:'));
      console.log(chalk.gray(`   - Lists: ${status.lists || 0}`));
      console.log(chalk.gray(`   - Tasks: ${status.tasks.total || 0} (${status.tasks.incomplete || 0} incomplete, ${status.tasks.completed || 0} completed)`));
      if (status.tasks.high_priority) {
        console.log(chalk.gray(`   - High priority: ${status.tasks.high_priority}`));
      }
    }

    if (status.last_sync) {
      console.log(chalk.gray(`\nLast sync: ${status.last_sync}`));
    }

    console.log(chalk.cyan('\nCommands:'));
    console.log(chalk.gray('  mstodo task list       # View all tasks'));
    console.log(chalk.gray('  mstodo status          # Detailed status'));
    console.log(chalk.gray('  mstodo auth logout     # Sign out'));

  } catch (error) {
    spinner.stop();
    // 只有真正未认证才提示登录；其它错误（网络、解析等）如实呈现，避免误导
    const msg = (error && error.message) || '';
    const m = msg.match(/"error"\s*:\s*"([^"]+)"/);
    const code = m ? m[1] : '';
    if (code === 'not_authenticated' || /not_authenticated|no_client_id/.test(msg)) {
      console.log(chalk.red('\n❌ Not authenticated'));
      console.log(chalk.yellow('\nRun: mstodo auth login'));
    } else {
      console.log(chalk.red('\n❌ Unable to check authentication status'));
      const detail = msg.trim().slice(0, 400);
      if (detail) console.log(chalk.gray(detail));
    }
  }
}

// ============================================================================
// 主入口
// ============================================================================
async function main() {
  const args = process.argv.slice(2);
  const command = args[0];
  const subcommand = args[1];

  try {
    if (command === 'setup') {
      await setupCommand();
    } else if (command === 'config' && subcommand === 'init') {
      await configInitCommand();
    } else if (command === 'auth' && subcommand === 'login') {
      await authLoginCommand();
    } else if (command === 'auth' && subcommand === 'status') {
      await authStatusCommand();
    } else {
      console.log(chalk.yellow('Unknown command'));
      process.exit(1);
    }
  } catch (error) {
    if (error.message !== 'Authentication failed') {
      console.error(chalk.red('\n❌ Error:'), error.message);
    }
    process.exit(1);
  }
}

// 只在直接运行时执行
if (require.main === module) {
  main();
}

module.exports = { main };
