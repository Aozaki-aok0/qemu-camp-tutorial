# QEMU 训练营 2026 专业阶段总结

!!! note "主要贡献者"

```
- 作者：[@Aozaki-aok0](https://github.com/Aozaki-aok0)
```

---

## 背景介绍

信息与通信工程研一在读，本科电子信息。因为研究方向不怎么好找工作，所以想学习嵌入式，本科也有点基础。参加这个项目是学长推荐的，之前完全不知道 QEMU 这东西，想着做点项目到时候好写简历就参加了。

## 专业阶段

专业阶段共有四个方向。由于我对这些方向都不熟悉，因此选择了第一个 CPU 方向。

CPU 方向的核心任务是根据 G233 CPU 指令扩展手册中的指令规格，在 QEMU TCG 中为 Xg233ai 扩展实现 10 条自定义指令。

## QEMU TCG 介绍

QEMU 支持多种加速器，即 accelerator。加速器决定了虚拟 CPU 的执行方式，大致可以分为以下两类：

* 指令模拟技术，例如 TCG；
* 硬件虚拟化技术，例如 KVM、HVF。

当使用 TCG 时，QEMU 会将客户机代码动态翻译为宿主机可以执行的代码。

QEMU 在第一次遇到某段客户机代码时，会将其翻译成宿主机指令集对应的可执行代码，并缓存翻译结果。后续再次执行相同代码时，可以直接复用已经生成的翻译结果，从而减少重复翻译带来的开销。

## TCG IR 介绍

TCG IR 可以理解为 QEMU 内部使用的一种中间表示语言。

```text
Guest 指令
    ↓
翻译前端：分析 Guest 指令的语义
    ↓
TCG IR
    ↓
翻译后端：将 IR 生成为当前 Host 的可执行代码
    ↓
Host 机器码
```

通过引入 TCG IR，QEMU 不需要为每一种 Guest 和 Host 的组合分别编写一套完整的翻译器，而是可以将翻译过程拆分为两个阶段：

1. 将 Guest 指令翻译为 TCG IR；
2. 将 TCG IR 翻译为 Host 机器码。

例如，当 Guest 架构为 RISC-V、Host 架构为 x86 时，QEMU 只需要通过 RISC-V 前端将指令翻译为 TCG IR，再由 x86 后端将 TCG IR 转换为 x86 机器码。

## 自定义指令实现流程

QEMU 执行一条指令的简化流程如下：

```text
取指 → 译码 → 翻译 → 执行
```

各个阶段的作用如下：

* **取指：** 从模拟内存中读取 32 位机器码。
* **译码：** 根据机器码中的字段识别指令，并提取寄存器编号、立即数等操作数。
* **翻译：** 将 Guest 指令转换为等价的 TCG 操作，或者生成对 C Helper 函数的调用。
* **执行：** 执行生成的宿主机代码，或者进入 Helper 函数完成具体操作。

### 以实验一 `test-insn-dma` 为例

#### 第一步：添加译码规则

修改文件：

```text
target/riscv/insn32.decode
```

添加以下译码规则：

```text
dma  0000110 ..... ..... 110 ..... 1111011 @r
```

**作用：** 教会 QEMU 的译码器识别 `dma` 指令。

这一阶段属于指令执行流程中的译码阶段。

QEMU 会根据 `insn32.decode` 文件自动生成相应的译码代码。当译码器读取到一条机器码，并发现它满足以下条件时：

```text
opcode = 1111011
funct3 = 110
funct7 = 0000110
```

就会将其识别为 `dma` 指令。

其中，`@r` 表示这条指令采用类似 R 型指令的编码格式。译码器会从机器码中自动提取以下字段：

* `rd`
* `rs1`
* `rs2`

需要注意的是，虽然这些字段沿用了 R 型指令中的命名方式，但在部分自定义指令中，`rd` 对应寄存器中的值也可能被当作地址、长度或其他输入参数使用，而不一定只表示结果寄存器。

#### 第二步：添加翻译函数

在 `trans_rvi.c.inc` 中添加 `trans_dma` 函数：

```c
static bool trans_dma(DisasContext *ctx, arg_dma *a)
{
    TCGv dst = get_gpr(ctx, a->rd, EXT_NONE);
    TCGv src = get_gpr(ctx, a->rs1, EXT_NONE);
    TCGv grain = get_gpr(ctx, a->rs2, EXT_NONE);

    gen_helper_dma(tcg_env, dst, src, grain);
    return true;
}
```

**作用：** 定义 `dma` 指令对应的翻译行为。

这一阶段属于指令执行流程中的翻译阶段。

译码成功后，QEMU 会调用对应的 `trans_xxx` 函数。这里的参数：

```c
arg_dma *a
```

保存了译码阶段提取出的寄存器编号，例如：

```c
a->rd
a->rs1
a->rs2
```

`get_gpr` 用于获取相应 RISC-V 通用寄存器当前值所对应的 TCG 变量。

例如：

```c
TCGv src = get_gpr(ctx, a->rs1, EXT_NONE);
```

表示获取 `rs1` 对应寄存器中的值，并将其表示为一个 TCG 变量。

随后：

```c
gen_helper_dma(tcg_env, dst, src, grain);
```

会生成一条对 `helper_dma` 函数的调用。此时并不会立即执行 `helper_dma`，而是先生成对应的 TCG 中间代码。等到翻译块真正执行时，QEMU 才会进入该 Helper 函数。

#### 第三步：声明 Helper 函数

在 `helper.h` 中添加：

```c
DEF_HELPER_4(dma, void, env, tl, tl, tl)
```

**作用：** 为 `gen_helper_dma` 调用提供函数声明，并在 TCG 翻译代码与 C Helper 函数之间建立接口。

这一部分位于翻译阶段和执行阶段之间。

`DEF_HELPER_4` 会生成与 Helper 相关的声明。其对应的 C 函数形式可以近似理解为：

```c
void helper_dma(
    CPURISCVState *env,
    target_ulong arg1,
    target_ulong arg2,
    target_ulong arg3
);
```

各参数的含义如下：

* `4`：表示 Helper 函数共有 4 个参数；
* `void`：表示 Helper 函数没有返回值；
* `env`：表示当前 CPU 的架构状态；
* `tl`：表示 `target_ulong` 类型。

其中，`env` 指向当前模拟 CPU 的状态，包含寄存器、特权级以及其他架构相关信息。Helper 函数也可以借助 `env` 调用 QEMU 提供的内存访问接口。

三个 `tl` 参数分别对应传入的：

```text
dst
src
grain
```

#### 第四步：实现 Helper 函数

在 `op_helper.c` 中实现 `helper_dma`。

Helper 函数中包含矩阵转置算法的具体 C 语言代码。

**作用：** 完成 `dma` 指令的实际功能。

这一阶段属于指令执行流程中的执行阶段。

当生成的 TCG 代码执行到 Helper 调用位置时，QEMU 会进入 `helper_dma` 函数。

Helper 函数运行在 QEMU 进程中，因此可以使用完整的 C 语言逻辑，例如：

* 循环；
* 条件判断；
* 临时变量；
* QEMU 提供的内存读写函数。

但是，Helper 函数不能直接通过以下方式访问 Guest 内存：

```c
*(float *)addr
```

原因是 `addr` 表示 Guest 虚拟地址，而不是 QEMU 进程自身的 Host 地址。

因此，需要使用 QEMU 提供的内存访问函数，例如：

```c
cpu_ldl_data(env, addr)
cpu_stl_data(env, addr, value)
```

通过这些接口，Helper 函数可以安全地读取和写入模拟出来的 RISC-V 内存。

`dma` 指令的 Helper 函数最终完成了矩阵转置操作。

## 后续实验

### 2. `sort`

**编码：**

```text
funct7 = 0010110
```

**功能：** 对 `int32_t` 数组的前 `k` 个元素进行冒泡排序。

**参数：**

* `rd`：排序长度 `k`；
* `rs1`：数组基址；
* `rs2`：数组总长度，当前实现中未使用。

**实现：** Helper 函数从 Guest 内存中读取数组元素，完成冒泡排序，再将排序后的前 `k` 个元素写回 Guest 内存。

### 3. `crush`

**编码：**

```text
funct7 = 0100110
```

**功能：** 将 `uint8_t` 数组中每个元素的低 4 位两两打包为一个字节。

打包顺序为先低 4 位、后高 4 位。当元素数量为奇数时，最后一个元素单独保存。

**参数：**

* `rd`：目标地址；
* `rs1`：源地址；
* `rs2`：源数组的字节数 `n`。

**实现：** 使用 `cpu_ldub_data` 和 `cpu_stb_data` 逐字节读取、打包并写回。

### 4. `expand`

**编码：**

```text
funct7 = 0110110
```

**功能：** 将每个 `uint8_t` 元素的低 4 位和高 4 位拆分为两个独立字节。

**参数：**

* `rd`：目标地址；
* `rs1`：源地址；
* `rs2`：源数组的字节数 `n`。

**实现：** 使用 `cpu_ldub_data` 读取源字节，提取其高 4 位和低 4 位，再通过 `cpu_stb_data` 写入目标地址。

### 5. `vdot`

**编码：**

```text
funct7 = 1000110
```

**功能：** 计算两个 `int32_t` 向量的点积，并返回一个 64 位有符号整数。

**参数：**

* `rd`：结果寄存器；
* `rs1`：向量 A 的基址；
* `rs2`：向量 B 的基址。

**实现：** Helper 函数返回 `target_ulong` 类型结果。翻译函数中使用 `gen_helper_vdot` 生成 Helper 调用，并通过 `gen_set_gpr` 将结果写回 `rd`。

### 6. `vrelu`

**编码：**

```text
funct7 = 1010110
```

**功能：** 对 `int32_t` 向量中的每个元素执行 ReLU 操作：

```text
max(x, 0)
```

**参数：**

* `rd`：目标地址；
* `rs1`：源地址；
* `rs2`：向量长度 `n`。

**实现：** Helper 函数循环读取元素，判断元素是否小于 0，并将结果写入目标地址。该实现支持原地操作，即 source 和 destination 可以指向同一块内存。

### 7. `vscale`

**编码：**

```text
funct7 = 1100110
```

**功能：** 将 `int32_t` 向量中的每个元素乘以一个标量。

**参数：**

* `rd`：目标地址；
* `rs1`：源地址；
* `rs2`：标量乘数。

**实现：** Helper 函数逐元素执行：

```c
(int64_t)a[i] * scale
```

计算过程中使用 `int64_t` 保存中间结果，最终截断并以 `int32_t` 形式写回。

### 8. `vmax`

**编码：**

```text
funct7 = 1110110
```

**功能：** 返回 `int32_t` 向量中的最大值，并将其符号扩展为 64 位结果。

**参数：**

* `rd`：结果寄存器；
* `rs1`：源数组基址；
* `rs2`：元素个数 `n`。

**实现：** Helper 函数返回 `target_ulong` 类型结果。翻译函数中使用 TCG 临时变量接收返回值，并通过 `gen_set_gpr` 写回 `rd`。

### 9. `gemm`

**编码：**

```text
funct7 = 0001110
```

**功能：** 实现两个 4×4 的 `int32_t` 矩阵乘法：

```text
C = A × B
```

**参数：**

* `rd`：矩阵 C 的基址；
* `rs1`：矩阵 A 的基址；
* `rs2`：矩阵 B 的基址。

**实现：** Helper 函数使用三层循环完成矩阵乘法，并使用 `int64_t` 保存乘加过程中的中间结果，以降低中间计算溢出的风险。

### 10. `vadd`

**编码：**

```text
funct7 = 0011110
```

**功能：** 对两个 `int32_t` 向量执行逐元素加法。

**参数：**

* `rd`：目标地址；
* `rs1`：向量 A 的基址；
* `rs2`：向量 B 的基址。

**实现：** Helper 函数循环读取两个源向量的元素，将对应元素相加后写入目标地址。该实现支持原地操作。

## 总结

通过本次专业阶段的学习，我完成了以下内容：

* 掌握了在 QEMU TCG 中添加自定义指令的基本流程，即 `decode → trans → helper`。
* 理解了 `insn32.decode` 文件及其模板的作用。
* 理解了译码参数结构体、翻译函数以及 TCG 变量的基本使用方式。
* 理解了 Helper 函数的声明、生成和调用机制。
* 能够使用 `gen_helper_xxx` 生成对 Helper 函数的调用。
* 掌握了有返回值 Helper 的处理方式，例如 `vdot` 和 `vmax`。
* 能够使用 QEMU 提供的 `cpu_ld*` 和 `cpu_st*` 内存访问函数读写 Guest 内存。
* 使用 Helper 函数实现了矩阵转置、数组排序、数据压缩与展开、向量运算和矩阵乘法等功能。
* 对 QEMU 的取指、译码、翻译和执行流程有了更加直观的认识。

通过这些实验，我不仅了解了如何在 QEMU 中实现一条自定义指令，也进一步理解了动态二进制翻译、TCG 中间表示以及模拟器访问 Guest 内存的基本机制。
