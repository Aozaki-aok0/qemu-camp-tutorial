# QEMU 训练营 2026 专业阶段总结

!!! note "主要贡献者"

    - 作者：[@srcres258](https://github.com/srcres258)

---

## 背景介绍

我是某中下 211, 区块链工程就读的大三本科生; 尽管日常学习区块链原理与网络安全相关知识，
但对计算机组成原理与体系结构兴趣颇丰。同期参加中国科学院大学 ["一生一芯" 项目][1],
后面自己认为[硬件虚拟化][2]是一门亟待研究的课题，而处理器辅助虚拟化也是互联网云服务时代一门重要核心技术;
思考至此，恰巧遇见朋友推荐此[QEMU 虚拟化技术训练营][3], 自己恰好需要学习此类知识，于是报名参加。希望通过学习，
提升自己对于虚拟化技术的掌握与认知的同时，也能将虚拟化技术融入体系结构设计，
在硬件辅助虚拟化的学术研究上贡献自己的力量。

同时感谢 [@zevorn][4] 老师提供这一笔记分享与展示交流平台，让我得以将自己在此过程中的所见所想所感与大家分享，
也希望能基于自己的见解，为大家带来一些启发。

## 专业阶段

综合自身情况 (希望了解硬件虚拟化体系结构设计), 我选择了 CPU 建模方向作为我的专业阶段选题。

本方向要求在 QEMU 的 RISC-V TCG（Tiny Code Generator）前端中实现一组自定义 ISA 扩展指令——**Xg233ai**，共计 10 条指令，涵盖矩阵转置、排序、数据压缩/展开、向量运算及矩阵乘法等操作。整个实现过程严格遵循 QEMU TCG 前端翻译流水线，从 decodetree 指令解码到 TCG 翻译函数再到 Helper 函数的语义模拟，逐步构建完整的指令模拟链路。

### Xg233ai 扩展总览

Xg233ai 是一个基于 RISC-V 自定义 opcode 空间的 ISA 扩展，10 条指令均使用 opcode `0x7b`（custom-3）、funct3 `6`，通过 funct7 字段区分具体操作。指令列表如下：

| 指令 | funct7 | 功能 | 类别 |
|------|--------|------|------|
| `dma` | 6 | 8×8/16×16/32×32 FP32 矩阵转置 | 内存→内存 |
| `sort` | 22 | INT32 数组冒泡排序 | 内存→内存 |
| `crush` | 38 | UINT8 数组 4-bit 压缩打包 | 内存→内存 |
| `expand` | 54 | UINT8 数组 4-bit 展开（crush 逆操作） | 内存→内存 |
| `vdot` | 70 | INT32[16] 向量点积，结果写回 GPR | 归约→GPR |
| `vrelu` | 86 | INT32 数组逐元素 ReLU 激活 | 内存→内存 |
| `vscale` | 102 | INT32[16] 向量标量乘法 | 内存→内存 |
| `vmax` | 118 | INT32 数组最大值，结果写回 GPR | 归约→GPR |
| `gemm` | 14 | INT32 4×4 矩阵乘法 | 内存→内存 |
| `vadd` | 30 | INT32[16] 向量逐元素加法 | 内存→内存 |

其中 8 条为"内存到内存"操作（不回写 GPR），2 条为"归约操作"（计算标量结果并写回 `gpr[rd]`）。

### TCG 前端翻译流水线

QEMU 的 TCG 采用二进制翻译方式模拟 guest 指令：guest 机器码先被解码为中间表示（IR），再由翻译函数生成 TCG 操作码，最终编译为 host 原生代码执行。Xg233ai 扩展的实现完整覆盖了这条流水线的每个环节：

**1. 扩展注册与 CPU 配置**

首先在 QEMU 的 RISC-V CPU 子系统中注册 Xg233ai 扩展：

- 在 `cpu_cfg_fields.h.inc` 中通过 `BOOL_FIELD(ext_xg233ai)` 添加扩展布尔字段
- 在 `cpu_cfg.h` 中通过 `MATERIALISE_EXT_PREDICATE(xg233ai)` 生成扩展谓词函数 `has_xg233ai_p()`
- 在 `cpu.c` 的 ISA 扩展注册表 `isa_edata_arr[]` 中注册扩展元数据，在用户可配置属性 `riscv_cpu_vendor_exts[]` 中添加 `"xg233ai"` 属性，在 GEVICO-CV1 CPU 型号定义中默认启用 `.cfg.ext_xg233ai = true`

**2. Decodetree 指令解码**

Decodetree 是 QEMU 的指令解码器生成工具，根据 `.decode` 文件中的编码模式描述自动生成 C 解码函数。Xg233ai 的 10 条指令共享 R-type 编码格式，解码文件 `xg233ai.decode` 中每条指令的描述格式为：

```
指令名 funct7 ..... ..... funct3 ..... opcode @r
```

例如 `dma` 的解码规则为 `dma 0000110 ..... ..... 110 ..... 1111011 @r`，其中 `.....` 表示通配的寄存器字段，`@r` 表示使用标准 R-type 操作数提取。

解码文件在 `meson.build` 中注册，由 Meson 构建系统在编译前自动生成 C 解码器代码。生成的解码函数 `decode_xg233ai()` 在主翻译循环 `translate.c` 中被调用，仅当 `has_xg233ai_p()` 返回 true 时激活。

**3. TCG 翻译函数**

每条指令对应一个 `trans_*` 翻译函数，定义在 `insn_trans/trans_xg233ai.c.inc` 中。翻译函数的职责是将 guest 指令的语义翻译为 TCG 中间操作。根据指令类别，翻译函数有两种模式：

- **模式 A（内存→内存）**：使用 `get_gpr(ctx, a->*, EXT_NONE)` 获取三个寄存器值（均为内存地址），调用 `gen_helper_*(tcg_env, rd, rs1, rs2)` 执行操作，不回写 GPR
- **模式 B（归约→GPR）**：使用 `dest_gpr(ctx, a->rd)` 为目标寄存器分配 TCGv，调用 `gen_helper_*(rd, tcg_env, rs1, rs2)`（第一个参数为返回值），然后通过 `gen_set_gpr(ctx, a->rd, rd)` 写回结果

**4. Helper 函数**

Helper 函数在 `op_helper.c` 中实现，负责实际的语义模拟。所有 Helper 均通过 `DEF_HELPER_FLAGS_*` 宏声明，`TCG_CALL_NO_WG` 标志表示不修改 guest 全局状态。内存访问统一使用 QEMU 的 guest 内存 API（如 `cpu_ldl_data()`、`cpu_stl_data()`、`cpu_ldub_data()` 等），这些函数自动处理 TLB 查找、MMU 权限检查和字节序转换。

### 指令实现详述

`plans/` 目录包含 10 个计划文件（`1.md` 至 `10.md`），对应 10 条指令的逐步实现方案。每条指令的实现遵循统一的流水线模式：**decodetree 解码 → TCG 翻译函数 → Helper 声明 → Helper 实现**。以下按计划顺序逐条叙述。

#### Plan 1：`dma`（矩阵转置）

`dma` 是实现工作量最大的一条指令，因为需要从零搭建 Xg233ai 扩展的完整基础设施，涉及 9 个文件的修改/创建。

功能：根据 grain 参数（rs2 寄存器值）对 8×8 / 16×16 / 32×32 的 FP32 矩阵执行转置操作，将源地址（rs1）的矩阵按行列互换写入目标地址（rd）。

Helper 实现通过 `sizes[]` 数组将 grain 值映射为矩阵维度，使用双重循环 `dst[j*N+i] = src[i*N+j]` 配合 `cpu_ldl_data()` / `cpu_stl_data()` 完成逐元素转置。翻译函数 `trans_dma()` 通过 `get_gpr()` 获取三个寄存器值后调用 `gen_helper_dma()`。

这一步完成后，后续每条指令只需修改 4 个文件：`xg233ai.decode`、`helper.h`、`op_helper.c`、`trans_xg233ai.c.inc`。

#### Plan 2：`sort`（冒泡排序）

功能：对内存中的 INT32 数组执行升序冒泡排序（部分排序），结果原地写回。

Helper 采用经典冒泡排序双重循环，使用 `cpu_ldl_data()` 读取 32 位有符号整数，比较相邻元素并在逆序时通过 `cpu_stl_data()` 交换。`rd` 寄存器传递参与排序的元素数量 K，`rs2` 传递数组总元素数量 N。

#### Plan 3：`crush`（4-bit 压缩）

功能：将源数组每个 UINT8 元素的低 4 位两两打包为一个 UINT8 元素，实现数据压缩。

Helper 循环处理 N/2 对元素，使用 `cpu_ldub_data()` 读取字节、`& 0x0F` 提取低 4 位、通过 `lo | (hi << 4)` 打包后用 `cpu_stb_data()` 写入。奇数个元素时单独处理最后一个元素。

#### Plan 4：`expand`（4-bit 展开）

功能：`crush` 的逆操作，将每个 8-bit 元素按 4-bit 拆分为两个 8-bit 元素。

Helper 循环 N 次，每次从源地址读取一字节，低 4 位写入 `dst[2*i]`，高 4 位写入 `dst[2*i+1]`。

#### Plan 5：`vdot`（向量点积）

功能：读取两个 16 元素 INT32 向量，计算点积，INT64 累加后截断为 target_ulong 写回 `gpr[rd]`。

**这是第一条"归约操作"类指令**，与前四条"内存到内存"操作有显著差异：

- Helper 声明使用 `DEF_HELPER_FLAGS_3`（3 参数而非 4 参数），返回类型为 `tl`（非 `void`）
- 翻译函数使用 `dest_gpr()` 分配目标 TCGv，`gen_helper_vdot(rd, tcg_env, rs1, rs2)` 的第一个参数为返回值，最后通过 `gen_set_gpr()` 写回 GPR

这一实现模式为后续的 `vmax` 指令建立了模板。

#### Plan 6：`vrelu`（向量 ReLU 激活）

功能：对 INT32 数组逐元素执行 `max(0, x)` 操作，支持原地操作。

回归"内存到内存"模式。Helper 使用三元运算符 `val > 0 ? val : 0` 实现 ReLU 激活。

#### Plan 7：`vscale`（向量标量乘法）

功能：对 INT32[16] 数组逐元素乘以一个标量值，INT64 中间精度，截断为 32-bit 写回。

#### Plan 8：`vmax`（向量最大值）

功能：从 INT32 数组中找出最大值，写回 `gpr[rd]`。

采用与 `vdot` 相同的"归约→GPR"模式。Helper 以第一个元素为初始最大值遍历更新，返回时通过 `(int32_t)` 再转 `(target_ulong)` 完成 32 位到 64 位的符号扩展。

#### Plan 9：`gemm`（4×4 矩阵乘法）

功能：INT32 4×4 矩阵乘法 C = A × B。

Helper 使用三重循环实现，行优先存储，`int64_t` 累加器防止中间溢出，`cpu_stl_data()` 截断写回。

#### Plan 10：`vadd`（向量加法）

功能：INT32[16] 向量逐元素加法，溢出按补码回绕。

`int32_t` 加法天然实现补码回绕，无需额外处理。

### 两种实现模式的对比

10 条指令可归纳为两种明确的实现模式：

| 特征 | 模式 A：内存→内存 | 模式 B：归约→GPR |
|------|------------------|------------------|
| 适用指令 | dma, sort, crush, expand, vrelu, vscale, gemm, vadd | vdot, vmax |
| Helper 宏 | `DEF_HELPER_FLAGS_4` | `DEF_HELPER_FLAGS_3` |
| Helper 返回 | `void` | `tl` |
| 目标寄存器 | `get_gpr()`（读取地址） | `dest_gpr()`（分配 TCGv） |
| 结果写回 | 无 | `gen_set_gpr()` |
| Helper 调用 | `gen_helper_*(tcg_env, rd, rs1, rs2)` | `gen_helper_*(rd, tcg_env, rs1, rs2)` |

两种模式的差异本质在于：模式 A 的 `rd` 寄存器仅传递目标内存地址，而模式 B 的 `rd` 寄存器需要接收 Helper 的返回值。在 TCG IR 层面，前者无需生成"写回 GPR"的 TCG 操作，后者则需要。

### 构建与测试验证

项目使用封装的 Makefile 进行构建和测试：

```bash
make -f Makefile.camp configure   # Meson 配置
make -f Makefile.camp build       # Ninja 编译
make -f Makefile.camp test-cpu    # 运行 CPU TCG 测试
```

配置参数为 `--target-list=riscv64-softmmu,riscv64-linux-user --extra-cflags='-O0 -g3' --enable-rust`。

CPU TCG 测试的执行方式较为特殊：测试用例使用 RISC-V 交叉编译器（`riscv64-unknown-elf-gcc`）编译为裸机 ELF，通过 QEMU 的 `-device loader` 加载到 G233 机器中执行，利用 semihosting 机制输出结果。10 个测试用例（`test-insn-*.c`）在实现过程中始终预先存在，每完成一条指令的实现即可运行对应测试验证正确性。这种"测试先行、实现跟进"的模式确保了每步实现的可验证性。

CI 评分方面，CPU 方向共 10 个测试，每个 10 分，满分 100 分。

### 关键文件修改清单

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| 新建 | `target/riscv/xg233ai.decode` | 10 条指令的 decodetree 解码描述 |
| 新建 | `target/riscv/insn_trans/trans_xg233ai.c.inc` | 10 个 TCG 翻译函数 |
| 修改 | `target/riscv/helper.h` | 10 个 Helper 函数声明 |
| 修改 | `target/riscv/op_helper.c` | 10 个 Helper 函数实现（约 128 行新增代码） |
| 修改 | `target/riscv/cpu_cfg_fields.h.inc` | 添加 `ext_xg233ai` 布尔字段 |
| 修改 | `target/riscv/cpu_cfg.h` | 添加 `has_xg233ai_p()` 谓词 |
| 修改 | `target/riscv/cpu.c` | 注册扩展、添加 CPU 默认配置 |
| 修改 | `target/riscv/translate.c` | 接入解码器和翻译函数 |
| 修改 | `target/riscv/meson.build` | 注册 decodetree 处理 |

### 开发过程回顾

整个实现过程遵循严格的渐进式开发策略：

1. **Plan 1（dma）** 是工作量最大的一步，需要从零搭建 Xg233ai 扩展的完整基础设施，涉及 9 个文件的修改/创建。
2. **Plan 2-4（sort/crush/expand）** 在已有框架上逐条添加"内存到内存"类指令，每条仅修改 4 个文件，每个文件增加约 1-15 行代码。
3. **Plan 5（vdot）** 引入了第二种实现模式——"归约操作"（写回 GPR），需要使用 `dest_gpr()` / `gen_set_gpr()` 和 `DEF_HELPER_FLAGS_3`，为后续 `vmax` 指令建立了模板。
4. **Plan 6-7（vrelu/vscale）** 回归"内存到内存"模式，重复巩固已有的实现流程。
5. **Plan 8（vmax）** 再次应用"归约操作"模式，验证了两种模式在项目中的一致性。
6. **Plan 9-10（gemm/vadd）** 完成了最后两条指令，至此 Xg233ai 扩展的 10 条指令全部实现完毕。

## 总结

参加训练营前觉得 QEMU 结构应该比较简单，无太深技术细节在其中，但深入学习后可见一斑，
在虚拟化方向上 QEMU 是开源技术界的集大成者，无疑是虚拟化技术入门的最佳标杆，
同时也为开放虚拟化技术奠定了坚实基础。作为体系结构设计者，即使理解软件架构没太大实际用途，
但其中的虚拟化概念与设计思想却能够深刻影响作为虚拟化初学者的思维发展方式与自身认知的逐渐形成。
未来有实际虚拟化参考需求时，我一定会首先想到 QEMU 中相关优秀设计模式方法论，
并以其为基准线在虚拟化领域探索新的路径与方式。总之这一趟学习路程下来，我的所学所见一定是值得的，
定会在之后的某一刻将我的所见所闻应用于生产实践中，为虚拟化技术的发展与进步贡献自己的力量。

[1]: https://ysyx.oscc.cc/
[2]: https://en.wikipedia.org/wiki/Hardware_virtualization
[3]: https://opencamp.cn/gevico/camp/2026
[4]: https://github.com/zevorn
