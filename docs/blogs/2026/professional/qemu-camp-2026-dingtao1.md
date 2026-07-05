# QEMU 训练营 2026 专业阶段总结

!!! note "主要贡献者"

    - 作者：[@dingtao1](https://github.com/dingtao1)

---

## 背景介绍

这里是一名工作一坤年的 ICer。去年 9 月在 B 站大学学习 QEMU 时，看到有开源社区的学习机会，抱着「免费的不要白不要」的心态参加了 **2025 年 QEMU 训练营**。因中途加入，只完成了基础部分与专业阶段。

今年参加 **2026 QEMU 训练营**，希望进入项目阶段实践：一方面继续巩固 QEMU 相关能力，另一方面也想接触 **vibe coding** 的技巧。

---

## 开发环境

| 项目 | 说明 |
|------|------|
| 主机 | Windows（方便玩游戏） |
| 开发机 | Linux VMware（方便配开发环境） |
| AI 搭子 | Cursor（Remote SSH 连接 Linux VMware） |

---

## 专业阶段

今年专业阶段可选方向更多，打算以 **SoC 建模** 和 **GPU 建模** 为主。

与去年相比：

- **SoC 建模**：去年对新手难度偏大，测试前要先搭 G233 board；今年已直接提供 board。去年测试多为类似 bare metal 让 CPU 来执行；今年通过 **qtest**，对硬件访问更直观。


下文记录 SoC 实验里学习过程。

对实验硬件的建模，主要涉及 **三类文件的增改**：

1. 新增的设备建模文件
2. 修改的 G233 board 文件
3. 修改的编译配置文件

### 建模思路简述

对设备建模需要先熟悉 QEMU 中的 **QOM**（导学资料与 B 站课程）。即便现在可以借助 AI 生成代码，**理清每一段代码在做什么**仍然必要。接着是模拟对设备寄存器的访问：通过 **MMIO 回调**实现；按硬件手册落实寄存器读写触发的行为；中断通过 **qemu_irq** 传递。

**以 gpio 的建模为例**

**类初始化 `g233_gpio_class_init`** 中配置 `DeviceClass`：

- `dc->realize` → `g233_gpio_realize`（分配 MMIO、IRQ、GPIO 线）
- `dc->vmsd` → `vmstate_g233_gpio`（迁移）
- `device_class_set_legacy_reset` → `g233_gpio_reset`
- `dc->desc` → 人类可读描述

> 从 QOM 视角：**类型是 SysBus 上的 GPIO 设备类；`realize` 把抽象设备变成可映射、可连线的具体对象。**


1. **实例指针**：MMIO 与 GPIO in 回调里的 `opaque` 均指向 **`G233GPIOState`**，通过 `G233_GPIO()` 宏（`OBJECT_CHECK`）转换，与头文件中 `DECLARE_INSTANCE_CHECKER` 一致。
2. **SysBus 暴露**：仅通过 `sysbus_init_mmio` / `sysbus_init_irq` 声明资源；**基地址由机器/SoC 创建设备时 `sysbus_mmio_map` 决定**，本文件不写死物理地址。
3. **GPIO 方向**：`qdev_init_gpio_in` 提供 32 根输入；`qdev_init_gpio_out` 提供 32 根输出线，供 `qemu_irq` 连接网络使用。

**qom 类的注册和实例化**
```text
type_init(g233_gpio_register_types)
  → type_register_static(&g233_gpio_info)
       → g233_gpio_class_init
            → realize: g233_gpio_realize
            → reset:   g233_gpio_reset
            → vmsd:    vmstate_g233_gpio

g233_gpio_realize
  → memory_region_init_io(..., &g233_gpio_ops, s)
  → sysbus_init_mmio / sysbus_init_irq
  → qdev_init_gpio_in(..., g233_gpio_set, ...)
  → qdev_init_gpio_out(..., s->output, ...)
```

### 在 machine 中的创建和中断连接

1. **`qdev_new(TYPE_…)`** — 按 QOM 类型名创建未 realize 的 `DeviceState`。
2. **`sysbus_realize_and_unref`** — 触发各设备 `DeviceClass::realize`（分配 MMIO、`sysbus_init_irq` 等），并释放创建时的引用。
3. **`memory_region_add_subregion(system_memory, base, region)`** — 把该设备 **MMIO region 0** 映射到机器 `memmap` 里为该外设预留的物理基址（如 `VIRT_G233_GPIO`）。
4. **`sysbus_connect_irq(dev, 0, …)`** — 把设备 **IRQ 输出 0** 连到 **`mmio_irqchip`** 上对应线


## 调试手段

用 gdb 来对某个测试用例进行断点调试。
```
QTEST_QEMU_BINARY="gdb --args ./qemu-system-riscv64 ./tests/gevico/qtest/test-flash-read"
```


---

## 实验中遇到的问题

### GPIO 建模

在 Cursor 协助下很快完成建模，并人工审查了一遍。AI 还发现手册与测试用例不一致之处，例如：

- **GPIO_ITP 寄存器**：手册描述与 qtest 中的设置相反。
- **`test_gpio_plic`**：测试点有误，无法有效清除 PLIC 的 pending 中断。

另外发现 AI 为让测试通过，会去修改 PLIC 代码——**不合适**。

### SPI 建模

SPI master 对从设备的事务访问与手册描述有出入。手册侧典型流程如下：

```text
读取 JEDEC ID：激活 CS → 发送 0x9F → 读取 3 字节 → 取消 CS。
扇区擦除：激活 CS → 发送 0x06 (WREN) → 取消 CS → 激活 CS → 发送 0x20 + 3 字节地址 → 取消 CS → 轮询 BUSY 直到完成。
页编程：激活 CS → 发送 0x06 (WREN) → 取消 CS → 激活 CS → 发送 0x02 + 3 字节地址 + 数据（最多 256 字节）→ 取消 CS → 轮询 BUSY 直到完成。
数据读取：激活 CS → 发送 0x03 + 3 字节地址 → 连续读取 N 字节 → 取消 CS。
```

**问题**：qtest 中缺少对 CS 的取消与激活。

## 总结

专业阶段下来，最大的收获是把 **QOM → realize → MMIO/IRQ/GPIO** 这条链路从「看过文档」变成了能对着代码说清每一步在干什么。SoC 建模表面上是在补设备与 board，实质上是在 QEMU 里把 **手册里的寄存器语义** 落到 **可测试、可迁移、可接线** 的对象上；`sysbus_mmio_map` 与 `sysbus_connect_irq` 则把「设备自己」和「整颗 SoC 的地址与中断拓扑」接起来。

接下来进项目阶段，会带着这套建模与调试习惯，少在脚手架里打转，多在需求与验证闭环里迭代；同时也想继续练 **vibe coding**，探索 ai 对复杂模型的建模能力。
