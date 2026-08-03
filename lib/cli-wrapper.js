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
  console.log('Documentation: https://github.com/yourusername/ms-todo-cli');
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
    const proc = spawn(python.command, [scriptPath, 'auth'], {
      stdio: 'pipe',
      encoding: 'utf-8'
    });

    let deviceCodeUrl = '';
    let deviceCode = '';
    let authStarted = false;

    proc.stdout.on('data', (data) => {
      const text = data.toString();

      // 检测设备码流程
      if (text.includes('https://microsoft.com/devicelogin') || text.includes('microsoft.com/devicelogin')) {
        const urlMatch = text.match(/(https?:\/\/[^\s]+)/);
        if (urlMatch) {
          deviceCodeUrl = urlMatch[1];
        }
      }

      if (text.includes('enter the code')) {
        const codeMatch = text.match(/code ([A-Z0-9]{9})/);
        if (codeMatch) {
          deviceCode = codeMatch[1];
        }
      }

      // 如果检测到设备码流程且还未开始，触发增强体验
      if (deviceCodeUrl && deviceCode && !authStarted) {
        authStarted = true;

        console.log(chalk.gray('If browser doesn\'t open automatically, visit:'));
        console.log(chalk.cyan(deviceCodeUrl));
        console.log(chalk.gray(`\nDevice code: ${deviceCode}`));

        // 自动复制设备码
        try {
          clipboardy.writeSync(deviceCode);
          console.log(chalk.gray('(Auto-copied to clipboard)\n'));
        } catch (e) {
          // 复制失败不影响流程
        }

        // 自动打开浏览器
        try {
          open(deviceCodeUrl);
        } catch (e) {
          // 打开失败不影响流程
        }

        // 显示等待进度
        console.log(chalk.cyan('⏳ Waiting for authentication...'));

        const progressBar = new cliProgress.SingleBar({
          format: chalk.cyan('[{bar}]') + ' {percentage}%',
          barCompleteChar: '█',
          barIncompleteChar: '░',
          hideCursor: true
        });

        progressBar.start(100, 0);

        // 模拟进度（设备码通常5分钟过期，所以300秒）
        let progress = 0;
        const interval = setInterval(() => {
          progress += 2;
          if (progress > 90) progress = 90; // 最多到90%，等实际认证完成
          progressBar.update(progress);
        }, 3000); // 每3秒更新

        // 监听认证完成
        proc.on('close', (code) => {
          clearInterval(interval);
          progressBar.update(100);
          progressBar.stop();

          if (code === 0) {
            console.log(chalk.green('\n✅ Authentication successful!'));

            // 尝试获取用户信息
            callPython(['--json', 'status'])
              .then(({ stdout }) => {
                try {
                  const status = JSON.parse(stdout);
                  if (status.user) {
                    console.log(chalk.cyan(`👤 Logged in as: ${status.user}`));
                  }
                } catch (e) {
                  // 解析失败不影响
                }
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
      } else {
        // 其他输出直接显示
        process.stdout.write(text);
      }
    });

    proc.stderr.on('data', (data) => {
      process.stderr.write(data);
    });

    proc.on('error', (error) => {
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
    const status = JSON.parse(stdout);

    spinner.stop();

    if (status.error) {
      console.log(chalk.red('\n❌ Not authenticated'));
      console.log(chalk.yellow('\nRun: mstodo auth login'));
      return;
    }

    console.log(chalk.green('\n✅ Authenticated'));
    if (status.user) {
      console.log(chalk.cyan(`👤 User: ${status.user}`));
    }

    // Token信息（如果有）
    console.log(chalk.cyan('🔑 Token: Valid'));

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
    console.log(chalk.red('\n❌ Not authenticated'));
    console.log(chalk.yellow('\nRun: mstodo auth login'));
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
