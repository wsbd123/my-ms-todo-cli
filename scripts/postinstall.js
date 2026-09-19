const chalk = require('chalk');
const { detectPython } = require('../lib/utils');

// 注意：不在 postinstall 阶段自动执行 `pip install`。
// 全局安装期间静默修改用户的 Python 环境会带来意外副作用，
// 且在 PEP 668「externally-managed-environment」的系统上会直接失败。
// Python 依赖的安装交由显式的 `mstodo setup` 命令完成。

console.log(chalk.cyan('\n📦 ms-todo-cli installed\n'));

const python = detectPython();
if (python.found) {
  console.log(chalk.green(`✅ Python ${python.version} detected`));
} else {
  console.log(chalk.yellow('⚠️  Python 3 not detected'));
  console.log(chalk.gray('   Install Python 3: https://www.python.org/downloads/'));
}

console.log(chalk.cyan('\nGet started:'));
console.log(chalk.gray('  mstodo setup           # install Python dependencies'));
console.log(chalk.gray('  mstodo config init'));
console.log(chalk.gray('  mstodo auth login'));
console.log(chalk.gray('  mstodo task list\n'));
