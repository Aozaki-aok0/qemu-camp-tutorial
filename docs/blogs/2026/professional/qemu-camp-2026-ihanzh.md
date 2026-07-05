
# QEMU 训练营 2026 专业阶段总结

!!! note "主要贡献者"

    - 作者：[@ihanzh](https://github.com/ihanzh)

---

## 背景介绍

计算机科学与工程专业研一学生，由于研究生阶段的研究方向是系统安全，经常使用 qemu 进行环境搭建，希望通过参加训练营来深入理解 qemu，提高自己的系统编程能力。

这次训练营主要学习 GPGPU 相关知识，以及希望使用 Rust 来做一些真实需求，提高 Rust 的系统编程能力，这篇笔记主要记录 Rust 设备建模的实现过程。

## 专业阶段

这份笔记聚焦 Rust 建模（FFI）的实现：

- 一条是 G233 Rust I2C 控制器通过 I2C bus 驱动 AT24C02

- 另一条是 G233 Rust SPI 控制器通过 DR 传输驱动 AT25 风格 flash 状态机

### 整体架构

整个系统运行时的流程是：“qtest 写 MMIO -> 控制器寄存器译码 -> 协议后端状态机”。I2C 路径落到 I2CBus+AT24C02，SPI 路径落到 At25flash。

板级接线入口在 hw/riscv/g233.c 中完成，I2C/SPI 映射和创建调用如下。

```c
[VIRT_I2C] = { 0x10013000, 0x20 },
[VIRT_SPI] = { 0x10019000, 0x10 },
...
G233i2c_create(s->memmap[VIRT_I2C].base, NULL);
G233spi_create(s->memmap[VIRT_SPI].base, NULL);
```

FDT 节点同时创建，保证 guest 侧可发现两类控制器。

```c
name = g_strdup_printf("/soc/i2c@%"HWADDR_PRIx, s->memmap[VIRT_I2C].base);
qemu_fdt_setprop_string(ms->fdt, name, "compatible", "gevico,g233-i2c");
qemu_fdt_setprop(ms->fdt, name, "i2c-controller", NULL, 0);

name = g_strdup_printf("/soc/spi@%"HWADDR_PRIx, s->memmap[VIRT_SPI].base);
qemu_fdt_setprop_string(ms->fdt, name, "compatible", "gevico,g233-spi");
qemu_fdt_setprop(ms->fdt, name, "spi-controller", NULL, 0);
```

### I2C 设备实现

#### I2C 控制器实现

一个可用的 QEMU Rust SysBus 设备，最小必须项包括对象定义、MMIO 回调、生命周期回调、状态存储、创建函数导出。缺任一项，都可能只“能编译”但“不可驱动”。

设备状态在 rust/hw/i2c/g233-i2c/src/device.rs 定义，包含 MMIO region、寄存器镜像、总线实例。

```rust
#[derive(qom::Object)]
pub struct G233i2cState {
    parent_obj: ParentField<SysBusDevice>,
    pub iomem: MemoryRegion,
    pub regs: BqlRefCell<G233i2cRegisters>,
    pub i2c_bus: BqlRefCell<I2CBus>,
}
```

SysBus 基础生命周期路径齐全。

```rust
unsafe fn init(mut this: ParentInit<Self>) {
    MemoryRegion::init_io(..., &G233I2C_OPS, ..., 0x20);
    uninit_field_mut!(*this, regs).write(Default::default());
    uninit_field_mut!(*this, i2c_bus).write(BqlRefCell::new(I2CBus::new()));
}

fn post_init(&self) { self.init_mmio(&self.iomem); }
fn realize(&self) -> util::Result<()> { ... }
fn reset_hold(&self, _type: ResetType) {}
```

C 侧创建入口与导出头文件一一对应。

- 头文件定义 include/hw/i2c/g233-i2c.h: `DeviceState *G233i2c_create(hwaddr addr, qemu_irq irq);`
- Rust 导出 rust/hw/i2c/g233-i2c/src/device.rs: `pub unsafe extern "C" fn G233i2c_create(...)`

控制器寄存器逻辑集中在 write 的 CTRL 分支，采用“EN 检查 -> START -> STOP -> 数据阶段”顺序，保持状态机可读。

CTRL 核心分支如下。

```rust
// 先检查 EN 位，关闭时直接清 BUSY/ACK，置 DONE
if (value & I2C_CTRL_EN) == 0 {
    Self::set_status_bit(&mut regs.i2c_status, I2C_ST_BUSY | I2C_ST_ACK, false);
    Self::set_status_bit(&mut regs.i2c_status, I2C_ST_DONE, true);
    return;
}

// EN 置位后，清除 DONE
Self::set_status_bit(&mut regs.i2c_status, I2C_ST_DONE, false);
let is_recv = (value & I2C_CTRL_RW) != 0;

// 如果是 START，先通过 bus 发起传输，更新 ACK/BUSY，再置 DONE
if (value & I2C_CTRL_START) != 0 {
    let addr = (regs.i2c_addr & 0x7f) as u8;
    let ack = bus.start_transfer(addr, is_recv) == 0;
    Self::set_status_bit(&mut regs.i2c_status, I2C_ST_ACK, ack);
    Self::set_status_bit(&mut regs.i2c_status, I2C_ST_BUSY, bus.is_busy());
    Self::set_status_bit(&mut regs.i2c_status, I2C_ST_DONE, true);
    return;
}

// 如果是 STOP，直接结束传输，清 BUSY/ACK，置 DONE
if (value & I2C_CTRL_STOP) != 0 {
    bus.end_transfer();
    Self::set_status_bit(&mut regs.i2c_status, I2C_ST_BUSY | I2C_ST_ACK, false);
    Self::set_status_bit(&mut regs.i2c_status, I2C_ST_DONE, true);
    return;
}

// 如果既不是 START 也不是 STOP，根据 RW 位调用 send/recv，更新 ACK/BUSY/DONE
let ack = if is_recv {
    regs.i2c_data = u32::from(bus.recv());
    true
} else {
    bus.send((regs.i2c_data & 0xff) as u8) == 0
};
Self::set_status_bit(&mut regs.i2c_status, I2C_ST_ACK, ack);
Self::set_status_bit(&mut regs.i2c_status, I2C_ST_BUSY, bus.is_busy());
Self::set_status_bit(&mut regs.i2c_status, I2C_ST_DONE, true);
```

> 从设备 AT24C02 注册进入总线的时机放在控制器 realize，而不是 ADDR 寄存器写路径；ADDR 只表达“访问目标地址”，不表达“创建拓扑”。

```rust
fn realize(&self) -> util::Result<()> {
    let mut bus = self.i2c_bus.borrow_mut();
    if bus.device_count() == 0 {
        bus.attach(Box::new(At24c02::new(AT24C02_ADDR)));
    }
    Ok(())
}
```

#### I2C bus 的能力与实现方式

I2C bus 不是“附属工具”，而是控制器与从设备之间的协议边界。它负责地址选择、方向选择、事务生命周期，而不是 MMIO 细节。

把能力收敛到 I2CSlave trait + I2CBus 结构体，控制器只调用 API，不管理设备私有状态机。

能力接口定义在 rust/hw/i2c/src/lib.rs。

```rust
pub trait I2CSlave {
    fn address(&self) -> u8;
    fn event(&mut self, event: I2CEvent) -> i32 { 0 }
    fn send(&mut self, data: u8) -> i32;
    fn recv(&mut self) -> u8;
}

pub struct I2CBus {
    devices: Vec<Box<dyn I2CSlave>>,
    current_addr: Option<u8>,
    is_recv: bool,
}
```

总线能力由五个关键方法覆盖。

```rust
pub fn attach(&mut self, device: Box<dyn I2CSlave>)
pub fn start_transfer(&mut self, address: u8, is_recv: bool) -> i32
pub fn send(&mut self, data: u8) -> i32
pub fn recv(&mut self) -> u8
pub fn end_transfer(&mut self)
```

语义上，start_transfer 负责地址阶段 ACK/NACK；send/recv 负责字节阶段；end_transfer 负责 FINISH 事件与总线释放。这样控制器的 STATUS 位更新可以稳定映射 bus 结果。

#### 从设备 AT24C02 的实现

目标器件参数是地址 0x50、容量 256 字节、页大小 8 字节。实现重点是“首字节作为内部地址”和“页内回绕”。

从设备拆到独立文件 rust/hw/i2c/g233-i2c/src/at24c02.rs，并通过 I2CSlave trait 接口接入，不与控制器寄存器代码混写。

数据结构与参数。

```rust
const AT24C02_SIZE: usize = 256;
const AT24C02_PAGE_SIZE: usize = 8;

pub struct At24c02 {
    addr: u8,
    regs: [u8; AT24C02_SIZE],
    pointer: u8,
    page_base: u8,
    page_off: u8,
    first_byte: bool,
}
```

其中 pointer 是当前访问地址，page_base 是当前页起始地址，page_off 是当前页内偏移，first_byte 标记是否正在接收首字节。


开始发送时重置状态，准备接收地址字节。

```rust
fn event(&mut self, event: I2CEvent) -> i32 {
    if event == I2CEvent::StartSend {
        self.first_byte = true;
    }
    0
}
```

write 路径只会在 START 之后被调用，首字节更新 pointer 和页地址，后续字节写入当前地址并更新页内偏移，并且只会在页内循环，不会跨页写入。

```rust
fn send(&mut self, data: u8) -> i32 {
    if self.first_byte {
        self.pointer = data;
        self.page_base = data & !((AT24C02_PAGE_SIZE as u8) - 1);
        self.page_off = data & ((AT24C02_PAGE_SIZE as u8) - 1);
        self.first_byte = false;
    } else {
        let write_addr = self.page_base | self.page_off;
        self.regs[write_addr as usize] = data;
        self.page_off = (self.page_off + 1) & ((AT24C02_PAGE_SIZE as u8) - 1);
        self.pointer = self.page_base | self.page_off;
    }
    0
}
```

```rust
fn recv(&mut self) -> u8 {
    let val = self.regs[self.pointer as usize];
    self.pointer = self.pointer.wrapping_add(1);
    val
}
```

### SPI 设备实现

#### SPI 控制器实现

在 rust/hw/spi/g233-spi/src/device.rs 保持寄存器模型，在 rust/hw/spi/g233-spi/src/at25flash.rs 放置数据语义；控制器通过 DR 写触发一次 `xfer`，并把返回值写回 DR 与 RXNE。

SPI 控制器状态定义与 MMIO 寄存器映射。

其中 cr1 包含使能位和主从位，sr 包含 TXE/RXNE 位，dr 是读写数据寄存器，cs 是片选寄存器。

TXE（Transmit Buffer Empty）表示数据寄存器空，可以写入新数据；RXNE（Receive Buffer Not Empty）表示数据寄存器有新数据可以读取。

```rust
pub struct G233spiRegisters {
    pub rspi_cr1: u32, // control register 1
    pub rspi_sr: u32,  // status register
    pub rspi_dr: u32,  // data register
    pub rspi_cs: u32,  // chip select
}

pub enum RegisterOffset {
    CR1 = 0x00,
    SR = 0x04,
    DR = 0x08,
    CS = 0x0c,
}
```

CR1 使能逻辑与 SR 状态位同步（关闭时清 TXE/RXNE，开启时置 TXE，表示可以写入新数据）。

```rust
RegisterOffset::CR1 => {
    regs.rspi_cr1 = value;
    let enabled = (value & RSPI_CR1_SPE) != 0;
    if enabled {
        regs.rspi_sr |= RSPI_SR_TXE;
    } else {
        regs.rspi_sr &= !(RSPI_SR_TXE | RSPI_SR_RXNE);
    }
}
```

SR 和 CS 直接更新寄存器值，没有副作用。

DR 写触发 SPI 传输，满足 `SPE && MSTR && CS==0` 才访问 flash 后端。

```rust
RegisterOffset::DR => {
    regs.rspi_dr = value;
    let tx = (value & 0xff) as u8;
    let enabled = (regs.rspi_cr1 & RSPI_CR1_SPE) != 0;
    let master = (regs.rspi_cr1 & RSPI_CR1_MSTR) != 0;
    let cs0 = regs.rspi_cs == 0;

    let rx = if enabled && master && cs0 {
        self.flash.borrow_mut().xfer(tx)
    } else {
        0
    };

    regs.rspi_dr = u32::from(rx);
    regs.rspi_sr |= RSPI_SR_RXNE;
    if enabled {
        regs.rspi_sr |= RSPI_SR_TXE;
    }
}
```

#### at25flash 从设备实现

AT25 风格后端具备基础存储和命令状态机（WREN/RDSR/READ/WRITE）。

```rust
pub enum At25State {
    Idle,
    ReadStatus,             // 读状态寄存器，返回 WEL 位
    ReadAddr,               // 读命令地址阶段，等待地址字节
    ReadData { addr: u8 },  // 读命令数据阶段，连续返回数据直到 CS 上升沿
    WriteAddr,              // 写命令地址阶段，等待地址字节
    WriteData { addr: u8 }, // 写命令数据阶段，连续接收数据直到 CS 上升沿，写入当前地址
}

pub struct At25flash {
    mem: [u8; 256],
    wel: bool,
    state: At25State,
}

pub fn xfer(&mut self, tx: u8) -> u8 {
    match tx {
        // WREN 命令表示写使能
        AT25_CMD_WREN => { self.wel = true; self.state = At25State::Idle; return 0; }
        // RDSR 命令进入读状态寄存器状态
        AT25_CMD_RDSR => { self.state = At25State::ReadStatus; return 0; }
        // READ 命令进入读数据状态
        AT25_CMD_READ => { self.state = At25State::ReadAddr; return 0; }
        // WRITE 命令进入写数据状态
        AT25_CMD_WRITE => { self.state = At25State::WriteAddr; return 0; }
        _ => {}
    }
    match self.state {
        // 空闲状态不响应数据
        At25State::Idle => 0,
        // 读状态寄存器返回 WEL 位
        At25State::ReadStatus => self.status(),
        // 读地址阶段接收地址字节，进入读数据状态
        At25State::ReadAddr => {
            self.state = At25State::ReadData { addr: tx };
            0
        }
        // 读数据阶段返回当前地址数据，并自动地址递增
        At25State::ReadData { addr } => {
            let out = self.mem[addr as usize];
            self.state = At25State::ReadData {
                addr: addr.wrapping_add(1),
            };
            out
        }
        // 写地址阶段接收地址字节，进入写数据状态
        At25State::WriteAddr => {
            self.state = At25State::WriteData { addr: tx };
            0
        }
        // 写数据阶段如果 WEL 置位则写入当前地址，并自动地址递增；否则丢弃数据
        At25State::WriteData { addr } => {
            if self.wel {
                self.mem[addr as usize] = tx;
                self.state = At25State::WriteData {
                    addr: addr.wrapping_add(1),
                };
            }
            0
        }
    }
}
```

## 总结

整个设备建模流程可以参考 pl011 设备的实现，重点和区别在于读写寄存器后触发的协议行为（I2C bus 事务和 SPI 状态机）以及状态位更新。设备本身的框架（对象定义、生命周期、MMIO 回调）是通用的，但协议细节和状态管理需要根据设备特性定制，这一部分是比较好理解的。

但由于我之前没有这些设备的建模经验，所以在实现过程需要通过 vibe coding 来阅读测试用例，从而理解设备行为和协议细节，再把这些行为映射到控制器寄存器的读写路径上。并且由于这两个控制设备都需要自己组织目录结构并加入到 QEMU 构建系统中，这一部分也是比较困难的，但 ai 还是太好用了，我基本上是通过 ai 来完成目录结构和构建系统的修改的。总的来说，这次设备建模的过程虽然有挑战，但也非常有成就感，尤其是当测试用例能够成功运行时，还是非常满足的。
