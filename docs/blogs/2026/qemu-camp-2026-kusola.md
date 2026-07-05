# QEMU 训练营 2026 专业阶段总结

!!! note "主要贡献者"

    - 作者：[@kusola](https://github.com/KeyBor)

---
## 背景介绍

我是从事芯片底软开发 2 年的工程师，日常工作覆盖 Codec、DSP 的 SDK 及底层驱动开发，熟悉 ROCm、IREE 相关技术栈，长期关注 GPU 架构方向，希望打通自己的知识体系。本次参加 2026 QEMU 训练营专业阶段，选择 SoC 建模与 GPGPU 方向，想通过实操来深入 gpu 领域并往 gpu 领域发展。


## 开发环境

| 环境 | 说明 |
|------|------|
| CNB | 方便就完事了 |
| AI | claude code + copilot-api 转发|

## 专业阶段

本次专业阶段学习路径为：RISC-V 指令翻译入门 → SoC 外设建模实践 → GPGPU 基础验证，简单走了一遍 QEMU 从底层指令到上层设备的模拟链路，打破了此前对 QEMU 的模糊认知，核心收获三点：

1. 掌握 QEMU TCG 指令翻译全流程，熟悉 RISC-V 指令集与自定义指令扩展方法
2. 理清 SoC 外设建模完整链路，熟悉了 QOM、MMIO、IRQ 等核心接口
3. 落地 SIMT 执行模型基础概念，掌握了一些低精度浮点量化/反量化原理

## 学习内容

### 1. RISC-V 指令翻译与自定义扩展

**1.1 Decodetree 解码框架**  
解决传统 switch-case 解码难维护问题，通过 Python 脚本解析.decode 定义文件自动生成解码器代码，核心包含 4 部分：Field 定义指令字段提取规则、Argument 保存字段值、Format 定义指令格式、Pattern 定义单条指令解码逻辑。

**1.2 自定义指令添加流程**  
标准 4 步：

1. 在 `target/riscv/insn32.decode` 定义指令格式
2. 在 `helper.h` 通过 `DEF_HELPER` 宏声明运行时 helper 函数
3. 在 `op_helper.c` 实现具体逻辑，注意内存操作位宽匹配、通过 `cpu_ldX_mmu` 访问 Guest 内存
4. 在 `trans_xxx.inc` 实现 TCG 翻译函数，通过 `gen_helper_xxx` 宏生成中间码

### 2. SoC 外设与 QOM 建模

**2.1 QOM 对象模型**  
QEMU 用 C 实现的面向对象框架，核心流程：编译期通过 `type_init` 宏完成类型注册，首次访问时触发类型初始化（递归初始化父类），对象创建时执行 `instance_init` 分配实例资源。类型层次遵循 `Object → Device → SysBusDevice → 具体设备` 的继承链。

**2.2 外设建模实践**  
标准流程为：新增设备建模文件、修改目标 Board 文件、更新编译配置。设备实现核心：

1. `class_init` 配置 `realize`/`reset` 等回调
2. `realize` 阶段通过 `memory_region_init_io` 注册 MMIO 回调、分配 IRQ/GPIO 资源
3. 机器挂载时通过 `sysbus_mmio_map` 映射物理地址、`sysbus_connect_irq` 连接中断

**2.3 QEMU 内存模型**  
核心结构：`AddressSpace` 为顶层地址空间，关联根 `MemoryRegion` 与 `FlatView`；`MemoryRegion` 以树形结构描述内存区域；`FlatView` 是 `MemoryRegion` 的平面化视图，用于地址翻译。Machine 初始化分为 `instance_init`（设置基础属性）和 `mc->init`（构建硬件拓扑）两个阶段。

### 3. GPGPU 与低精度浮点

**3.1 SIMT 执行模型**  
落地 GPU 线程层次（Grid/Block/Warp/Lane）模拟思路，理解 Warp 锁步执行、active mask 线程管理等核心概念。

**3.2 低精度浮点转换**  
掌握 FP32/BF16/E5M2 等格式的编码规则、指数重偏置计算、RNE（向最近偶数）舍入逻辑（使用 Guard/Sticky Bit 判断进位），以及 NaN/Inf 等特殊值的处理，实现 FP32 与 BF16 互转的舍入逻辑，适配 AI 计算场景的精度要求。


## 总结

通过本次 QEMU 训练营专业阶段的学习，我以 RISC-V 为切入点，完整走通了从指令翻译、外设建模到 GPGPU 基础验证的 QEMU 模拟链路。

更重要的是，本次训练营帮助我将日常工作中零散的底层经验串联成体系，每一个环节都帮助我补全对完整软硬件栈的认知盲区。感谢训练营提供的开源实践平台，后续我将继续围绕 GPGPU 方向完善 QEMU 设备模型，探索更多 AI 加速硬件的模拟实现。
