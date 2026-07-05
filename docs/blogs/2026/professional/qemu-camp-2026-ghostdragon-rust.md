# Qemu RUST 方向

!!! note "主要贡献者"

    - 作者：[@ghostdragonzero](https://github.com/ghostdragonzero)

---

## 背景介绍

机械工程专业已毕业，工作转码 5 年牛马现在在从事嵌入式 liunx 驱动开发。因为在找工作的过程中发现自己对于软硬件的交互理解并不充足，对于整个系统的运行也有限。
所以想通过 qemu 进一步了解软件与硬件的交互方式，以便自己后续的工作选择。

## 专业阶段

这份笔记聚焦在 AI 在这个任务中的使用，主要记录我自己在使用不同编程工具在解决这个项目中遇到的一些情况。

### 从零开始的错误

在最一开始的使用中我使用 claude code cli + GLM4.7 直接将通过测试作为了提示词，最终结果是成功完成了单元测试。后续的测试中虽然一直在提示已经编程完成，但是查看修改
实际上这个所生成的是根据要求实现的 C 版本，即便我添加了要求但是依旧是运行一段时间后依旧会用 C 语言版本交差。我认为是因为制定的目标是通过测试，所以在修改 rust 版本的过程
出现较多报错于是还是用了更简单的版本。

### 从 C 版本理解设备建模

因为从初步尝试来看大模型对于 C 的 qemu 建模更好，而自己也基本忘记之前参与 qemu 学习的过程。就先看视频 <https://www.bilibili.com/video/BV1kQwTzmEGc/?spm_id_from=333.1387.upload.video_card.click&vd_source=5f44f76cdabc0e0d5367c0e8f3e119cc> 结合讲义先了解了 qemu 的初始化流程。之后就是沿着
`gpio->i2c` 从简单无需总线抽象的设备到需要总线抽象的设备建模。从这个过程了解了建模主要实现的内容
以 gpio 为例
一、qemu 设备建模框架
①添加配置选项 `->` 确保自己的驱动可以编译到
需要再 hw/gpio/Kconfig 文件添加 自己设备的 config

```Kconfig
config GEVICO_GPIO
    bool
```

hw/gpio/meson.build 文件 添加打开配置的情况需要编译的文件

```meson
system_ss.add(when: 'CONFIG_GEVICO_GPIO', if_true: files('gevico_gpio.c'))
```

在板子相关的 hw/riscv/Kconfig 选项中选择自己 config 板子才能知道打开了

```Kconfig
config GEVICO_G233
    bool
    default y
    depends on RISCV32 || RISCV64
    select RISCV_ACLINT
    select SIFIVE_PLIC
    select GEVICO_GPIO
    select SIFIVE_PWM
    select PL011
```

二、qemu 设备抽象接口实现

```c
static void gevico_gpio_realize(DeviceState *dev, Error **errp)；

static void gevico_gpio_class_init(ObjectClass *klass, const void *data)；

static const TypeInfo gevico_gpio_info；

static void gevico_gpio_register_types(void)
{
    type_register_static(&gevico_gpio_info);
}

type_init(gevico_gpio_register_types)
```

这些接口是设备建模中最重要的接口
在这些接口之外需要实现的就是 寄存器的读写接口与具体功能逻辑
（从使用来看这部分 AI 实现最好即便一开始测试不通过也会根据结果来改正）

三、板端初始化设备
这部分也比较简单，主要就是分配地址并且初始化设备

```c
/* Create Gevico GPIO device */
    DeviceState *gpio_dev;
    SysBusDevice *gpio_sysbus;

    gpio_dev = qdev_new(TYPE_GEVICO_GPIO);
    qdev_prop_set_uint32(gpio_dev, "ngpio", 32);
    gpio_sysbus = SYS_BUS_DEVICE(gpio_dev);
    sysbus_realize_and_unref(gpio_sysbus, &error_fatal);
    sysbus_mmio_map(gpio_sysbus, 0, s->memmap[VIRT_GPIO0].base);
    sysbus_connect_irq(gpio_sysbus, 0, qdev_get_gpio_in(mmio_irqchip, GPIO0_IRQ));
```

### 迁移 RUST 版本驱动

在基本了解 qemu 的 C 设备建模之后我开始继续进行 rust 模型的编写，我参考了提供的 pl011，但是和我需要实现的 I2C 及 SPI 设备来说有些差距。
于是我先去实现了 gpio 模型，我查看了讲义 <https://qemu.gevico.online/tutorial/2026/ch2/qemu-rust-ffi/> 其实没有特别理解，
以为这个 FEI 是 qemu 特别的实现后面我查看了这篇博客 <https://qemu.gevico.online/tutorial/2026/ch2/qemu-rust-ffi/>。理解这个 FEI
实际上只是转换一些 C 的头文件，方便 RUST 和 C 进行相互调用其他并不做更多的内容。
于是我理解对于 rust 建模 ①qemu 设备建模框架（编译到我的代码） ②FEI 暴露 C 有文件（参考 timer/hpet 如果不用引入特别的 C 接口也可不用）
③qemu 设备接口的 rust 版本 ④板端初始化（通过查看 pl011 的板端初始化这部分与 C 版本驱动无差别）
基于理解我完善了 I2C 设备 FEI 内容就让 AI 开始帮我继续完成剩下的目标，这次直接通过了测试。同样的我让 AI 继续帮我完成了 SPI 也同样通过了测试
<https://github.com/gevico/qemu-camp-2026-exper-ghostdragonzero/commit/d88f02bd18d7bd4f381d61587d0c2add08aafb8a>
我首先查看了是否真的调用了 rsut 的版本✅️
之后我查看了代码发现了问题

### 设备模型抽象

在查看实现发现 AI 直接将测试设备也变成了一种我理解的硬编码的方式，并没有对于 I2CBUS、I2CSLAVE 的抽象，这个是不符合我预期的。
所以我通过让参考 hw/i2c/core.c  hw/ssi/ssi.c 完善了这部分抽象，但是也让我想了一些之前没有去想的事情。
对于设备模型抽象出的控制器+bus+ 外设的整个驱动框架，其实只是为了更好的理解，实际上都是对于控制器的一些操作。

## 总结

这个阶段我大部分代码逻辑都是基于 AI 生成的，对于整个框架理解还算不上透彻，所有只说一下对于 AI 在代码实现的一些总结。
①给 AI 制定目标的时候避免直接告诉最终目标，可以自己分解或者让 ai 先分解任务并首先制定实现目标计划。
②框架的部分尽量自己先去搭建完成，让 AI 完成从设备手册->代码实现的内容。
③对于一些代码结构抽象 需要提前告知 AI。

并且这次使用 AI 直接给我生成了一个无抽象的 I2C 设备，让我觉得后续利用 AI 是可以生成很多针对嵌入式平台的定制版本驱动。
对于确定的产品形态完全可以舍弃 bus、slave 的抽象只针对确定的设备进行编码。
