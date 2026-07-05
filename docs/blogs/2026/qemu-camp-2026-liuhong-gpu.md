# QEMU 训练营 2026 专业阶段总结

!!! note "主要贡献者"

    - 作者：[@liuhong](https://github.com/LiuHongsGitHub)

---

## 背景介绍

上海某学校大数据技术与工程研二学生，对系统编程感兴趣，希望通过 QEMU 训练营寻找一些 idea，并且掌握一些 CPU、GPU 和模拟器的知识。

---

## 专业阶段

完成了 GPU 方向实验。

### GPU 实验理解概述

设备建模的核心是通过 MMIO 寄存器访问触发设备行为。GPGPU 实验的主要目标是模拟 RISC‑V 体系下的 GPU 寄存器读写、VRAM 访问、DMA 传输、SIMT 上下文调度，并实现一个简化的 RV32I/RV32F 指令解释器（含低精度浮点扩展）。

### 实验内容

17 道测试覆盖了：设备识别、全局控制、VRAM 访问、DMA 传输、中断模拟、SIMT 上下文与调度、kernel 执行、低精度浮点数格式转换。

以执行指令的全流程为脉络，串联实验。

**阶段 1：QEMU 设备注册与初始化**

1.1 `gpgpu.c` 中执行 `type_init()` 方法将 gpu 这个类型注册到类型系统，父类为 `TYPE_PCI_DEVICE`。

1.2 基于 QOM 的面向对象思想，调用 `gpgpu_class_init` 进行类初始化。

1.3 QEMU 命令行指定 `-device gpgpu` 时，会调用 `gpgpu_realize()`。

```c
static void gpgpu_realize(PCIDevice *pdev, Error **errp)
{
    GPGPUState *s = GPGPU(pdev);
    uint8_t *pci_conf = pdev->config;

    pci_config_set_interrupt_pin(pci_conf, 1);

    s->vram_ptr = g_malloc0(s->vram_size);

    /* BAR 0: control registers — 1MB MMIO */
    memory_region_init_io(&s->ctrl_mmio, OBJECT(s), &gpgpu_ctrl_ops, s,
                          "gpgpu-ctrl", GPGPU_CTRL_BAR_SIZE);
    pci_register_bar(pdev, 0, ... , &s->ctrl_mmio);

    /* BAR 2: VRAM — 64MB MMIO */
    memory_region_init_io(&s->vram, OBJECT(s), &gpgpu_vram_ops, s,
                          "gpgpu-vram", s->vram_size);
    pci_register_bar(pdev, 2, ... , &s->vram);

    /* BAR 4: doorbell — 64KB MMIO */
    memory_region_init_io(&s->doorbell_mmio, OBJECT(s), &gpgpu_doorbell_ops, s,
                          "gpgpu-doorbell", GPGPU_DOORBELL_BAR_SIZE);
    pci_register_bar(pdev, 4, ... , &s->doorbell_mmio);

    // MSI-X 初始化
    msix_init(pdev, GPGPU_MSIX_VECTORS, ...);

    s->dma_timer = timer_new_ms(QEMU_CLOCK_VIRTUAL, ...);

    s->global_status = GPGPU_STATUS_READY;
}
```

例如 Guest CPU 读写 BAR0 地址时，QEMU 会通过 `MemoryRegionOps`（即 `gpgpu_ctrl_ops`）自动调用回调函数 `gpgpu_ctrl_read/write`，传入 **BAR 内部偏移量** 和 **设备状态指针**。

**阶段 2：Guest 内核驱动初始化，进行 PCIe 设备发现/Probe。**

**阶段 3：用户态程序准备数据。**

**阶段 4：写 `GPGPU_REG_DISPATCH` 寄存器触发执行，对应实验 4。**

4.1 调用 `gpgpu_dispatch_kernel`，再调用
```c
int gpgpu_core_exec_kernel(GPGPUState *s)
{
    uint32_t grid_dim_x = s->kernel.grid_dim[0];
    uint32_t grid_dim_y = s->kernel.grid_dim[1];
    uint32_t grid_dim_z = s->kernel.grid_dim[2];
    uint32_t block_dim_x = s->kernel.block_dim[0];
    uint32_t block_dim_y = s->kernel.block_dim[1];
    uint32_t block_dim_z = s->kernel.block_dim[2];
    
    uint32_t threads_per_block = block_dim_x * block_dim_y * block_dim_z;
    uint32_t warps_per_block = (threads_per_block + 31) / 32;
    uint64_t kernel_addr = s->kernel.kernel_addr;
    
    GPGPUWarp *warps = g_malloc(sizeof(GPGPUWarp) * warps_per_block);
    ...
```
4.2 Warp 初始化

```c
void gpgpu_core_init_warp(GPGPUWarp *warp, uint32_t pc, uint64_t kernel_args,
                          uint32_t thread_id_base, const uint32_t block_id[3],
                          uint32_t num_threads,
                          uint32_t warp_id, uint32_t block_id_linear)
{
    // 清零 warp 结构
    memset(warp, 0, sizeof(*warp));
    // init warp meta data
    warp->active_mask = num_threads >= 32 ? 0xFFFFFFFF : (1U << num_threads) - 1;
    warp->thread_id_base = thread_id_base;
    warp->warp_id = warp_id;
    memcpy(warp->block_id, block_id, sizeof(warp->block_id));
    for (int i = 0; i < GPGPU_WARP_SIZE; i++) {
        GPGPULane *lane = &warp->lanes[i];
        lane->pc = pc;
        lane->mhartid = MHARTID_ENCODE(block_id_linear, warp_id, i);
        lane->fcsr = 0;
        lane->active = i < num_threads;
        if (lane->active) {
            lane->gpr[11] = thread_id_base + i;
            lane->gpr[10] = (uint32_t)kernel_args;
        }
        set_default_nan_mode(1, &lane->fp_status);
        set_float_default_nan_pattern(0b01000000, &lane->fp_status);
    }
}
```

使用了 RISC-V 的 `a0` 寄存器保存发送给 gpgpu 的指针，`a1` 保存线程 id。

4.3 执行每个 warp，核心方法是 `decode_and_exec`。

**阶段 5：译码 (decode)**

```c
static inline void decode_and_exec(GPGPUState *s, GPGPULane *lane, uint32_t inst)
{
    uint8_t opcode = inst & 0x7F;
    uint8_t rd = (inst >> 7) & 0x1F;
    uint8_t rs1 = (inst >> 15) & 0x1F;
    uint8_t rs2 = (inst >> 20) & 0x1F;
    uint8_t rs3 = (inst >> 27) & 0x1F;

    uint32_t imm_i = sext32(inst >> 20, 12);
    uint32_t imm_s = sext32(((inst >> 25) << 5) | ((inst >> 7) & 0x1F), 12);
    uint32_t imm_b = sext32(((inst >> 31) << 12) | ((inst >> 7) & 1) << 11 |
                           ((inst >> 25) & 0x3F) << 5 | ((inst >> 8) & 0xF) << 1, 13);
    uint32_t imm_u = inst & 0xFFFFF000;
    int32_t imm_j = sext32(((inst >> 31) << 20) | ((inst >> 12) & 0xFF) << 12 |
                           ((inst >> 20) & 1) << 11 | ((inst >> 21) & 0x3FF) << 1, 21);
    uint32_t shamt = (inst >> 20) & 0x1F;
    uint32_t funct3 = (inst >> 12) & 0x7;
    uint32_t funct7 = (inst >> 25) & 0x7F;
    switch (opcode) {
        case 0x37:
            if (rd != 0) lane->gpr[rd] = imm_u;
            return;
    ...
```

译码过程中使用了相当多的 `switch case` 语句，单纯堆代码不是好的选择。

**阶段 6：执行 (execute)**

6.1 模拟 `flw` 指令执行过程中，GPGPU 访问 VRAM 直接使用 `memcpy`。模拟 Host 访问 VRAM 的 DMA 数据搬运则通过 `MemoryRegionOps` 中的回调函数完成。

```c
case 0x07:
    {
        uint32_t addr = lane->gpr[rs1] + imm_i;
        if (addr < s->vram_size) {
            if (funct3 == 2) {          // FLW
                uint32_t val;
                memcpy(&val, s->vram_ptr + addr, 4);
                lane->fpr[rd] = val;
            }
        }
        return;
    }
    ...
```
6.2 模拟 fcvt.e2m1.s fd, fs1（FP32 → E2M1）。由于 E2M1 仅能表示 0/0.5/1.0/1.5/2.0/3.0/4.0/6.0 共 8 个正数值，转换时取 FP32 输入的绝对值的位模式（uint32_t），与各相邻 E2M1 代表值的 FP32 中点阈值做整数比较以确定所属区间。超出最大值 6.0 的输入饱和到 ±6.0，NaN/Inf 同样饱和。最后加回符号位得到 4-bit 结果。

区间划分 (正半轴)：

| 区间            | 映射值 | 说明                          |
|-----------------|--------|-------------------------------|
| `[0, 0.25)`     | 0      |                               |
| `[0.25, 0.75)`  | 0.5    | 中点在 0.5，0.25~0.75 选 0.5 |
| `[0.75, 1.25)`  | 1.0    |                               |
| `[1.25, 1.75)`  | 1.5    |                               |
| `[1.75, 2.5)`   | 2.0    |                               |
| `[2.5, 3.5)`    | 3.0    |                               |
| `[3.5, 5.0)`    | 4.0    |                               |
| `[5.0, +∞)`     | 6.0    |                               |

```c
case 1: {
    uint32_t f32_val = lane->fpr[rs1];
    bool sign = (f32_val >> 31) & 1;
    uint8_t exp32 = (f32_val >> 23) & 0xFF;
    uint32_t m23 = f32_val & 0x7FFFFF;
    uint32_t abs_val = f32_val & 0x7FFFFFFFU;
    uint8_t e2m1_result;
    if (exp32 == 0 && m23 == 0) {
        e2m1_result = sign ? 0x8 : 0x0;
    } else if (exp32 == 255) {
        e2m1_result = sign ? 0xF : 0x7;
    } else {
        if (abs_val < 0x3D800000U) {
            e2m1_result = 0x0; 
        } else if (abs_val < 0x3F400000U) { 
            e2m1_result = 0x1;  // 0.5
        } else if (abs_val < 0x3FA00000U) { 
            e2m1_result = 0x2;  // 1.0 (默认 RTZ/RNE)
        } else if (abs_val < 0x3FE00000U) { 
            e2m1_result = 0x3;  // 1.5
        } else if (abs_val < 0x40200000U) { 
            e2m1_result = 0x4;  // 2.0
        } else if (abs_val < 0x40600000U) {  
            e2m1_result = 0x5;  // 3.0
        } else if (abs_val < 0x40A00000U) { 
            e2m1_result = 0x6;  // 4.0
        } else {
            e2m1_result = 0x7;  // 6.0
        }
    }
    /* 加回符号位 */
    if (sign) e2m1_result |= 0x8;
    lane->fpr[rd] = e2m1_result;
}
break;
```

**阶段 7：所有 warp 执行完后，返回 `gpgpu_dispatch_kernel` 方法，调用 `msix_notify`，向 Guest 注入 MSI-X 中断。**

---

### 问题

1. 对一些元概念和建模思想（如 MemoryRegion）缺乏了解时直接使用 AI 工具效率很低，先建立概念体系才能真正加速。

2. 代码较为冗余，不够简洁，可以让 AI 重新审查代码。

3. 缺乏建模概念和架构体系知识，对于设备的行为和模拟器的行为不能很好地对应。

---

## 总结

理解了 QEMU 设备建模的核心机制（PCI 注册、MemoryRegion/BAR 映射、MMIO 回调），掌握了 SIMT 架构下 Grid/Block/Warp 的调度与 RV32I/RV32F 指令解释器的简单实现方法，熟悉了 VRAM 访问和 DMA 传输的模拟路径。初步掌握 GDB 调试复杂项目的方法。后续继续使用 AI 辅助，多读 QEMU 源码以加深理解。
