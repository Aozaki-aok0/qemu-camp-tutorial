本文档是专业阶段 CPU 方向的实验手册。

CPU 方向的核心任务：根据 [G233 CPU 指令扩展手册][5] 中的指令规格，在 QEMU TCG 前端为 Xg233ai 扩展实现指令翻译。整体流程为 Decodetree 译码 → Helper 实现 → 测试验证。

## 环境搭建

第一步，安装 QEMU 开发依赖和 RISC-V 交叉编译工具链。

```bash
# Ubuntu 24.04
sudo sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources
sudo apt-get update
sudo apt-get build-dep -y qemu

# 安装 RISC-V 裸机交叉编译器
sudo mkdir -p /opt/riscv
wget -q https://github.com/riscv-collab/riscv-gnu-toolchain/releases/download/2025.09.28/riscv64-elf-ubuntu-24.04-gcc-nightly-2025.09.28-nightly.tar.xz -O riscv-toolchain.tar.xz
sudo tar -xJf riscv-toolchain.tar.xz -C /opt/riscv --strip-components=1
sudo chown -R $USER:$USER /opt/riscv
export PATH="/opt/riscv/bin:$PATH"
echo 'export PATH="/opt/riscv/bin:$PATH"' >> ~/.bashrc
riscv64-unknown-elf-gcc --version  # 验证编译器是否可用

# 安装 Rust 工具链
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
. "$HOME/.cargo/env"
cargo install bindgen-cli
```

!!! note "提示"

    安装 QEMU 开发环境，请参考导学阶段的 [Step0: 搭建 QEMU 开发环境][1]。

    RISC-V 交叉编译工具链[下载地址][2]，要求安装 `riscv64-unknown-elf-` 类型，尽量选择最新版本。

第二步，点击 [GitHub Classroom 邀请链接][3] 加入实验，系统会自动在组织下为你创建专属仓库并赋予 maintainer 权限。

!!! warning "注意"

    请通过上方链接获取仓库，**不支持手动 fork**。

第三步，clone 仓库到本地：

```bash
git clone git@github.com:gevico/qemu-camp-2026-exper-<你的 github 用户名>.git
```

第四步，添加上游远程仓库，用于同步上游代码变更：

```bash
git remote add upstream git@github.com:gevico/gevico-classroom-qemu-camp-2026-exper-qemu-camp-2026-exper.git
git pull upstream main --rebase
```

!!! note "提示"

    使用 SSH 地址需要在 GitHub 上配置 SSH Key，请参考 [GitHub SSH Key 配置指南](https://docs.github.com/zh/authentication/connecting-to-github-with-ssh)。

第五步，配置并编译：

```bash
make -f Makefile.camp configure
make -f Makefile.camp build
```

## 提交代码

所有实验的测题源码，均放在仓库根目录路径： `tests/gevico/tcg/riscv64/` 。

先通读测题源码，搞清楚每道题在测什么，然后去 QEMU 本体里实现对应功能（不要改测题源码）。文末有每道题的简介，帮你快速定位。

实现完成后，提交代码到你的仓库：

```bash
git add .
git commit -m "feat: subject..."
git push origin main
```

!!! note

    请确保你的代码符合仓库的代码规范，包括代码格式、注释等。

## 测评验收

本地运行测题的方式：

```bash
make check-gevico-tcg
```

CPU 方向全部测题通过的情况下，你会看到如下输出：

```bash
  BUILD   riscv64-softmmu guest-tests
  RUN     riscv64-softmmu guest-tests
  TEST      1/10   test-insn-dma on riscv64
  TEST      2/10   test-insn-sort on riscv64
  TEST      3/10   test-insn-crush on riscv64
  TEST      4/10   test-insn-expand on riscv64
  TEST      5/10   test-insn-vdot on riscv64
  TEST      6/10   test-insn-vrelu on riscv64
  TEST      7/10   test-insn-vscale on riscv64
  TEST      8/10   test-insn-vmax on riscv64
  TEST      9/10   test-insn-gemm on riscv64
  TEST     10/10   test-insn-vadd on riscv64
```

如果你想运行某个测例，比如 `test-insn-dma`，可以使用如下命令：

```bash
make -C build/tests/gevico/tcg/riscv64-softmmu/  run-insn-dma
```

!!! note

    当你使用 `make -C` 指定了路径以后，你可以通过输入 `run-` 和 tab 键来查看可以运行的测题

如果你想调试某个测例，比如 `test-insn-dma`，可以使用如下命令启用 QEMU 的远程调试功能：

```bash
make -C build/tests/gevico/tcg/riscv64-softmmu gdbstub-insn-dma
```

同理，你也可以通过 `gdbstub-` 和 tab 键来查看可以远程调试的测例。

然后需要你本地另起一个终端，使用 riscv-elf-gdb 加载被调试客户机二进制程序，进行远程调试。

!!! note

    建议对照 [G233 CPU 指令扩展手册][5] 和测题源码一起看，理解测试意图后再动手写代码，调试效率会高很多。

每道测题 10 分，一共 10 道测题，共计 100 分，评分将显示到训练营的[CPU 方向专业阶段排行榜][4]。

## 实验介绍

Xg233ai 在 RISC-V custom-3 编码空间（opcode `0x7B`）内定义了 10 条 R-type 指令，分为通用数据处理和 AI 推理加速两类。编码格式、操作数约定和伪代码见 [G233 CPU 指令扩展手册][5]。

测题位于 `tests/gevico/tcg/riscv64/` 目录，文件名以 `test-insn-` 开头。

### 实验一 test-insn-dma

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-dma.c` |
| 指令助记符 | `dma` |
| 指令编码 | `.insn r 0x7b, 6, 6, rd, rs1, rs2` |
| 功能描述 | FP32 矩阵转置搬运，支持 8×8 / 16×16 / 32×32 三种粒度 |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.4 |

| 测试用例 | 测试内容 |
| --- | --- |
| `test_dma_grain_8x8` | 8×8 矩阵（粒度 0），输入按行优先填充 0-63，验证转置正确性 |
| `test_dma_grain_16x16` | 16×16 矩阵（粒度 1），输入 0-255，验证转置正确性 |
| `test_dma_grain_32x32` | 32×32 矩阵（粒度 2），输入 0-1023，验证转置正确性 |
| `custom_dma` | 内联汇编调用指令，参数：目标地址、源地址、粒度大小 |
| `compare` | 比较软件转置与硬件指令结果 |

### 实验二 test-insn-sort

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-sort.c` |
| 指令助记符 | `sort` |
| 指令编码 | `.insn r 0x7b, 6, 22, rd, rs1, rs2` |
| 功能描述 | INT32 数组升序冒泡排序，支持部分排序 |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.5 |

| 测试用例 | 测试内容 |
| --- | --- |
| `test_sort` | 32 元素数组 `{3, 7, 23, 9, 81, 33, ...}`，排序前 16 个元素（仅前 16 个参与排序，其余保持不变） |
| `bubble_sort` | 冒泡排序软件参考实现，提供对比基准 |
| `custom_sort` | 内联汇编调用指令，参数：排序长度、数组地址、数组大小 |
| `compare` | 比较软件排序与硬件指令结果 |

### 实验三 test-insn-crush

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-crush.c` |
| 指令助记符 | `crush` |
| 指令编码 | `.insn r 0x7b, 6, 38, rd, rs1, rs2` |
| 功能描述 | 8-bit → 4-bit 压缩打包，提取低 4 位两两合并 |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.6 |

| 测试用例 | 测试内容 |
| --- | --- |
| `pack_low4bits` | 输入 `{0xA, 0xB, ..., 0x4}`，预期输出 `{0xBA, 0xDC, 0xFE, 0x21, 0x43}` |
| `custom_crush` | 内联汇编调用指令，参数：目标地址、源地址、元素数量 |
| `compare` | 比较软件实现与硬件指令结果 |

### 实验四 test-insn-expand

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-expand.c` |
| 指令助记符 | `expand` |
| 指令编码 | `.insn r 0x7b, 6, 54, rd, rs1, rs2` |
| 功能描述 | 4-bit → 8-bit 解压展开，每字节拆为两个 4-bit 元素 |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.7 |

| 测试用例 | 测试内容 |
| --- | --- |
| `split_to_4bits` | 输入 `{0xAB, 0xBC, ...}`，拆分为 2 倍长度的 4-bit 数组 |
| `custom_expand` | 内联汇编调用指令，参数：目标地址、源地址、数据数量 |
| `compare` | 比较软件实现与硬件指令结果 |

### 实验五 test-insn-vdot

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-vdot.c` |
| 指令助记符 | `vdot` |
| 指令编码 | `.insn r 0x7b, 6, 70, rd, rs1, rs2` |
| 功能描述 | INT32[16] 向量点积归约，INT64 累加，标量结果写入 `gpr[rd]` |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.8 |

| 测试用例 | 测试内容 |
| --- | --- |
| `test_vdot_basic` | A=`{1..16}`, B=`{16..1}`，预期结果 `816` |
| `software_vdot` | INT64 累加器逐元素相乘求和，提供对比基准 |
| `custom_vdot` | 内联汇编调用指令，参数：目标寄存器、向量 A 地址、向量 B 地址 |
| `compare` | 比较软件实现与硬件指令结果 |

### 实验六 test-insn-vrelu

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-vrelu.c` |
| 指令助记符 | `vrelu` |
| 指令编码 | `.insn r 0x7b, 6, 86, rd, rs1, rs2` |
| 功能描述 | INT32 向量 ReLU 激活 `max(0, x)`，支持原地操作 |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.9 |

| 测试用例 | 测试内容 |
| --- | --- |
| `test_vrelu_mixed` | 输入 `{-5, 3, -1, 0, 7, -100, ...}`，预期负值全部置零 |
| `software_vrelu` | 逐元素判断，负值置零，提供对比基准 |
| `custom_vrelu` | 内联汇编调用指令，参数：目标地址、源地址、元素数量 |
| `test_vrelu_inplace` | 验证源和目标地址相同时（原地操作）的正确性 |
| `compare` | 比较软件实现与硬件指令结果 |

### 实验七 test-insn-vscale

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-vscale.c` |
| 指令助记符 | `vscale` |
| 指令编码 | `.insn r 0x7b, 6, 102, rd, rs1, rs2` |
| 功能描述 | INT32[16] 向量标量乘，INT64 中间精度，截断到 32 位 |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.10 |

| 测试用例 | 测试内容 |
| --- | --- |
| `test_vscale_basic` | 输入 `{1..16}`，标量 `3`，预期 `{3, 6, 9, ..., 48}` |
| `test_vscale_negative` | 正负混合数组 × 负数标量，验证符号处理 |
| `software_vscale` | INT64 中间精度逐元素相乘，提供对比基准 |
| `custom_vscale` | 内联汇编调用指令，参数：目标地址、源地址、标量乘数（寄存器值） |
| `compare` | 比较软件实现与硬件指令结果 |

### 实验八 test-insn-vmax

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-vmax.c` |
| 指令助记符 | `vmax` |
| 指令编码 | `.insn r 0x7b, 6, 118, rd, rs1, rs2` |
| 功能描述 | INT32 向量最大值归约，结果符号扩展后写入 `gpr[rd]` |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.11 |

| 测试用例 | 测试内容 |
| --- | --- |
| `test_vmax_positive` | 输入 `{5, 23, 1, 99, 42, ...}`，预期 `99` |
| `test_vmax_negative` | 输入 `{-5, -23, -1, -99, ...}`，预期 `-1`，验证符号扩展 |
| `software_vmax` | 遍历数组查找最大值，提供对比基准 |
| `custom_vmax` | 内联汇编调用指令，参数：目标寄存器、数组地址、元素数量 |
| `compare` | 比较软件实现与硬件指令结果 |

### 实验九 test-insn-gemm

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-gemm.c` |
| 指令助记符 | `gemm` |
| 指令编码 | `.insn r 0x7b, 6, 14, rd, rs1, rs2` |
| 功能描述 | INT32 4×4 矩阵乘法 C = A × B，行优先存储，INT64 累加 |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.12 |

| 测试用例 | 测试内容 |
| --- | --- |
| `test_gemm_basic` | A=`{{1..4},{5..8},...}`, B=`{{17..20},{21..24},...}`，验证乘积矩阵 |
| `test_gemm_identity` | A × 单位矩阵 = A，验证恒等性 |
| `software_gemm` | 三重循环标准矩阵乘法，INT64 累加器，提供对比基准 |
| `custom_gemm` | 内联汇编调用指令，参数：目标矩阵地址、矩阵 A 地址、矩阵 B 地址 |
| `compare` | 比较软件实现与硬件指令结果 |

### 实验十 test-insn-vadd

| 项目 | 内容 |
| --- | --- |
| 源码路径 | `tests/gevico/tcg/riscv64/test-insn-vadd.c` |
| 指令助记符 | `vadd` |
| 指令编码 | `.insn r 0x7b, 6, 30, rd, rs1, rs2` |
| 功能描述 | INT32[16] 向量逐元素加法，溢出按补码回绕，支持原地操作 |
| 详细规格 | [G233 CPU 指令扩展手册][5] §3.13 |

| 测试用例 | 测试内容 |
| --- | --- |
| `test_vadd_basic` | A=`{1..16}`, B=`{100, 200, ..., 1600}`，验证逐元素之和 |
| `test_vadd_overflow` | INT32 最大值附近加法，验证补码回绕行为 |
| `software_vadd` | 逐元素加法，提供对比基准 |
| `custom_vadd` | 内联汇编调用指令，参数：目标地址、向量 A 地址、向量 B 地址 |
| `test_vadd_inplace` | 验证目标与源地址相同时（原地操作）的正确性 |
| `compare` | 比较软件实现与硬件指令结果 |

## 进阶实验

!!! note "说明"

    进阶实验为开放题目，不计入 100 分基础测评，但会作为训练营评优与推荐的重要参考。鼓励在完成 10 道必做题后深入探索 TCG 前后端、翻译开销与多核语义。

### 进阶实验一 Helper → 内联 TCG IR 重写

基础实验中 Xg233ai 指令都通过 `gen_helper_*` 调用 C 实现，每次执行都要跨出翻译块、保存上下文、调用 helper、再返回。对计算密集型的循环而言，这笔开销相当可观。

挑战目标：从 `vadd`、`vrelu`、`vscale` 三条指令中任选 1~2 条，完全用 `tcg_gen_*` 原语在 decodetree 回调里直接生成 TCG IR，**不再调用 helper**。

参考方向：

- 学习 `tcg/tcg-op.h` 提供的整数/向量原语；查阅 `target/riscv/insn_trans/trans_rvv.c.inc` 中 RVV 指令的内联实现。
- 用 `tcg_gen_gvec_*` 接口把向量循环交给宿主机 SIMD 执行。
- 对比两个版本在 `test-insn-*` 上的实测耗时（可用 `time`、`perf stat`、或 `-d in_asm,out_asm` 查看生成代码规模）。

### 进阶实验二 基于 TCG Plugin 的翻译性能分析

QEMU 提供了 TCG Plugin 机制，可以在不修改核心翻译器的前提下，挂载到每条 guest 指令/TB 的执行路径，用来做剖析。

挑战目标：使用或扩展 `tests/tcg/plugins/` 下已有的 `hotblocks.c`、`insn.c`、`cache.c` 插件，对某个测题（推荐 `test-insn-gemm` 或 `test-insn-vdot`）输出以下数据：

- Xg233ai 自定义指令 vs. 普通 RISC-V 指令的执行占比。
- 翻译块（TB）命中率、链接命中率。
- 每条 Xg233ai 指令在生成代码中的 host 指令条数。

产出一份简短的分析报告，指出当前实现中开销最大的环节。

### 进阶实验三 MTTCG 下的正确性与性能

QEMU 默认的 TCG 后端是单线程模式（`thread=single`），对于 G233 这种多 hart 平台，可以启用多线程 TCG（`-accel tcg,thread=multi`）以获得真并行。

挑战目标：

- 让 10 道基础测题在 `-smp 4 -accel tcg,thread=multi` 下稳定通过（初次实现可能会暴露内存序、原子性相关的 bug）。
- 分析 `gemm`、`dma` 这类涉及大量 load/store 的指令，在 MTTCG 下是否存在对同一 guest 物理页的并发访问问题，必要时使用 `tcg_gen_qemu_ld_*` 的正确内存顺序标志。
- 记录多核相对单核的加速比。

### 进阶实验四 为自定义指令加装性能计数器

挑战目标：在自定义指令的实现中加入轻量级计数器（例如每条指令的执行次数、累计 cycle 估算值），可以是：

- 通过 `CPURISCVState` 中新增字段，导出到一组自定义 CSR，测试程序运行完后读出并通过 semihosting 打印。
- 或者挂载到 TCG Plugin 侧，按指令名聚合计数。

最终目标是在不修改测题源码的前提下，产出一张「Xg233ai 指令使用热度表」，为后续硬件设计/软件优化提供数据支撑。

[1]: https://qemu.readthedocs.io/en/v10.0.3/devel/build-environment.html
[2]: https://github.com/riscv-collab/riscv-gnu-toolchain/releases/
[3]: https://classroom.github.com/a/hwWFrmo_
[4]: ../../../../leaderboards/2026/professional/cpu.md
[5]: https://qemu.gevico.online/exercise/2026/stage1/cpu/cpu-datasheet/
