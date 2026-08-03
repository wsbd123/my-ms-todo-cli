const chalk = require('chalk');
const { detectPython, installPythonDeps } = require('../lib/utils');

console.log(chalk.cyan('\n📦 Installing ms-todo-cli dependencies...\n'));

// 检测Python
const python = detectPython();
if (!python.found) {
  console.log(chalk.yellow('⚠️  Python 3 not detected'));
  console.log(chalk.gray('Python dependencies will be installed on first run'));
  console.log(chalk.gray('Install Python 3: https://www.python.org/downloads/\n'));
  process.exit(0);
}

console.log(chalk.green(`✅ Python ${python.version} detected`));

// 安装Python依赖
const success = installPythonDeps();

if (success) {
  console.log(chalk.green('\n✅ All dependencies installed successfully!\n'));
  console.log(chalk.cyan('Get started:'));
  console.log(chalk.gray('  mstodo config init'));
  console.log(chalk.gray('  mstodo auth login'));
  console.log(chalk.gray('  mstodo task list\n'));
} else {
  console.log(chalk.yellow('\n⚠️  Python dependencies installation incomplete'));
  console.log(chalk.gray('You can install them manually:'));
  console.log(chalk.gray('  pip3 install -r requirements.txt\n'));
}
