# QEMU 训练营基础阶段 Rust

基础阶段 Rust 练习仓库 [qemu_camp_basic_rust](https://classroom.github.com/a/Itda1slF)，基于 Rustlings 题库，包含练习题、命令行工具和自动评分流程。共 `95` 题。

GitHub Classroom 邀请链接：[https://classroom.github.com/a/Itda1slF](https://classroom.github.com/a/Itda1slF)

## 题库概览

### 基础信息

- 题库类型：完整 Rustlings 题库
- 练习总数：`95`
- 练习索引文件：`info.toml`
- 适用阶段：基础阶段

### 练习覆盖主题

变量、函数、所有权、借用、生命周期、结构体、枚举、模式匹配、集合、字符串、错误处理、泛型、trait、宏、测试、并发、智能指针、迭代器等。

## 目录结构

```text
qemu_camp_basic_rust/
├── Cargo.toml                  # Rustlings 工具依赖配置
├── info.toml                   # 练习索引与提示信息
├── README.md                   # 仓库使用说明
├── exercises/                  # Rust 练习题与章节说明
├── src/                        # Rustlings 命令行工具源码
├── tests/                      # 集成测试与评测入口
└── .github/workflows/rust.yml  # GitHub Actions 自动评测流程
```

## 开始练习

### 1. 准备 Rust 环境

请参考此文档完成 Rust 环境配置：[ArceOS Tutorial Book - 实验环境配置](https://rcore-os.cn/arceos-tutorial-book/ch01-02.html)

请先在 Linux / WSL2 / macOS 环境中完成 Rust 工具链安装，确保至少可以正常使用：

```bash
rustc --version
cargo --version
```

### 2. clone 仓库并进入目录

通过上方 Classroom 链接领取仓库后：

```bash
git clone <你的仓库地址>
cd qemu_camp_basic_rust
```

### 3. 安装 rustlings

用锁定依赖方式安装，避免版本漂移：

```bash
cargo install --force --path . --locked
```

### 4. 开始做题

在仓库根目录执行：

```bash
rustlings watch    # 自动定位当前练习，保存文件后自动重新检查
rustlings list     # 查看全部练习及完成状态
```

## 常用命令

```bash
cargo install --force --path . --locked   # 安装本仓库里的 rustlings
rustlings watch                           # 自动监听并按顺序推进练习
rustlings run 练习名称                    # 单独运行某一道练习
rustlings hint 练习名称                   # 查看指定练习的提示
rustlings list                            # 查看全部练习与完成状态
rustlings reset 练习名称                  # 将指定练习恢复到初始状态
cargo test --test cicv --verbose          # 执行仓库评测入口
```

## 自动评测说明

仓库已接入 GitHub Actions（`.github/workflows/rust.yml`）。push 到主分支后会执行 `cargo test --test cicv --verbose`，汇总通过题数并回传成绩到 OpenCamp（需配置 secrets）。PR 只跑评测，不回传。

评分状态会在 workflow summary 中显示（`reported` / `failed` / `skipped` 等）。

本地评测输出：`.github/result/check_result.json`（供 CI 解析，无需手动改）。

基础阶段 Rust 排行榜见：[Rust 基础阶段排行榜](../../../leaderboards/2026/basic/rust.md)。

## 速览

```bash
cd qemu_camp_basic_rust
cargo install --force --path . --locked
rustlings list
rustlings watch
```
