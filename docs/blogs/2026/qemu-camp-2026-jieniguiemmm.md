# QEMU 训练营 2026 专业阶段总结

!!! note "主要贡献者"

    - 作者：[@jieniguiemmm](https://github.com/jieniguiemmm)

---

## 背景介绍

本人网安大三，去年也参加了qemu训练营，不过由于和期末撞车了遗憾没有完成，看到这次不仅项目丰富了许多而且时间上也宽裕了不少，没有和学校的事撞车。狠狠报名，势必要完成项目阶段。专业阶段这里我选择的是 **SOC** 一方面去年接触了一点点，另一方面项目阶段的大模型建模外设比较吸引我。

## 专业阶段

### 1. 借助 QTest 理解 SoC 实验

#### 原理

SoC 建模的核心是“把一块芯片的可观察行为模拟出来”。对于软件来说，外设通常不是通过函数调用访问的，而是通过 **MMIO** 访问的，即CPU 对某个物理地址读写，硬件外设根据这个地址和数据改变内部状态，或者返回某个寄存器值。

QEMU 里的外设模型也是如此。我们需要在 QEMU 的 system memory 中挂载 `MemoryRegion`。当测试或 guest 对这个地址范围执行读写时，QEMU 会回调我们实现的 `read` / `write` 函数。外设模型内部保存寄存器状态，并在合适时机拉高中断线。

QTest 则是 QEMU 的一种测试方式。它不需要启动完整客户机操作系统，而是由测试程序直接控制 QEMU，执行类似下面的操作：

```c
qtest_writel(qts, GPIO_DIR, 0x1);
g_assert_cmpuint(qtest_readl(qts, GPIO_DIR), ==, 0x1);
```

所以，QTest 实际上把硬件需求变成了一组非常直接的断言：某个寄存器写入后应该读回什么值，某个事件发生后中断是否 pending，某个状态位是否能被清除。

#### 实现细节

SoC 实验的测试入口是：

```bash
make -f Makefile.camp test-soc
```

这个目标会运行 10 个测试：

```text
test-board-g233
test-gpio-basic
test-gpio-int
test-pwm-basic
test-wdt-timeout
test-spi-jedec
test-flash-read
test-flash-read-interrupt
test-spi-cs
test-spi-overrun
```

我首先阅读 `tests/gevico/qtest/` 目录，把每个测试访问的地址和寄存器行为整理出来。测试中用到的 G233 外设 MMIO 地址如下：

```text
WDT   0x10010000
GPIO  0x10012000
PWM   0x10015000
SPI   0x10018000
```

项目中已经存在 G233 machine：

```text
hw/riscv/g233.c
include/hw/riscv/g233.h
```

原始 `g233.c` 已经有 DRAM、CLINT、PLIC、UART、RTC、VirtIO、PCIe、pflash 等基础设施，还没有实现测试需要的 G233 专用 GPIO、PWM、WDT 和 SPI 控制器。因此我的主要改动集中在：

```text
hw/riscv/g233.c
```

### 2. 总体结构

#### 原理

在 QEMU 中，一个 machine 负责搭建整块虚拟主板。它会创建 CPU、内存、中断控制器和各种外设，并把外设映射到物理地址空间。对于 MMIO 外设来说，关键步骤是：

```text
定义设备内部状态
定义 MemoryRegionOps
初始化 MemoryRegion
把 MemoryRegion 添加到 system memory
把设备 IRQ 连接到中断控制器
```

中断连接同样重要。设备内部设置了状态位并不代表 CPU 能看到中断。设备模型必须通过 `qemu_set_irq()` 或类似接口把中断线拉到 PLIC，PLIC 才会在 pending 寄存器中体现出来。

#### 实现细节

这里我选择把这几个教学外设作为 G233 板卡私有的 MMIO 模型集中写在 `g233.c` 中，而不是为每个外设单独新建 QOM 设备文件。这个选择更适合本阶段，因为测试范围明确，外设规模较小，集中实现更方便对照测试。

新增的状态结构包括：

```text
G233GpioState
G233PwmState
G233WdtState
G233SpiState
G233SpiFlash
```

新增统一初始化函数：

```c
static void g233_create_mmio_devices(RISCVG233State *s, DeviceState *irqchip)
```

它负责：

```text
创建 GPIO / PWM / WDT / SPI 的 MemoryRegion
映射到 G233 手册和测试要求的 MMIO base
把 GPIO / WDT / SPI 的 IRQ 接到 PLIC
初始化两片 SPI Flash 的内存状态
```

最后在 G233 machine 初始化流程中调用：

```c
g233_create_mmio_devices(s, mmio_irqchip);
```

### 3. GPIO
#### 原理

GPIO 是最基础的 SoC 外设之一。它的作用是让软件控制芯片引脚，或者读取外部引脚电平。一个 GPIO 控制器通常至少需要保存三类信息：

```text
方向：当前 pin 是输入还是输出
数据：输出值或输入值
中断：某个 pin 的电平或边沿是否触发中断
```

GPIO 中断一般分为两种：

```text
边沿触发：只在 0->1 或 1->0 的瞬间触发
电平触发：只要电平保持在目标状态，中断就保持有效
```

这两种模式的差别非常关键。边沿触发需要比较旧值和新值；电平触发只看当前值。

#### 细节

GPIO 的寄存器布局如下：

```text
base: 0x10012000

0x00  GPIO_DIR   direction, 0=input, 1=output
0x04  GPIO_OUT   output data
0x08  GPIO_IN    input data
0x0C  GPIO_IE    interrupt enable
0x10  GPIO_IS    interrupt status, write-1-to-clear
0x14  GPIO_TRIG  trigger type, 0=edge, 1=level
0x18  GPIO_POL   polarity, 0=low/falling, 1=high/rising
```

基础测试会检查 reset value、方向寄存器、输出寄存器和多 pin 写入。这里最重要的是 `GPIO_IN`。测试会先把 pin 配成 output，然后写 `GPIO_OUT`，再从 `GPIO_IN` 读回。因此我们让输入值反映输出方向上的输出状态：

```c
GPIO_IN = GPIO_OUT & GPIO_DIR
```

中断实现中，我保存旧输入值，再根据写入后的新输入值判断触发条件：

```text
TRIG=0, POL=1：上升沿触发
TRIG=0, POL=0：下降沿触发
TRIG=1, POL=1：高电平触发
TRIG=1, POL=0：低电平触发
```

`GPIO_IE` 用来屏蔽未使能的 pin。`GPIO_IS` 是中断状态寄存器，支持 write-1-to-clear。GPIO 的 PLIC 中断号是 2，因此只要 `GPIO_IS` 非 0，就拉高中断线：

```c
qemu_set_irq(s->irq, s->is != 0);
```

### 4. PWM

#### 原理

PWM 的本质是周期性计数和比较。真实硬件中，PWM 计数器会按时钟递增，当计数值达到周期或比较值时，输出波形或设置状态位。软件通过配置 period 和 duty 来控制波形。

在本实验里，测试并不观察真实波形，只观察：

```text
寄存器能否保存 period / duty
channel enable 后全局寄存器是否反映 enable
counter 是否随着虚拟时间前进
周期完成后 DONE 标志是否置位
DONE 是否能被 write-1-to-clear
```

因此我们不需要模拟完整 PWM 输出，只需要用 QEMU virtual clock 推导计数器和 DONE 状态。

#### 实现细节

PWM 的 MMIO base 是：

```text
0x10015000
```

测试关注 4 个 channel：

```text
0x00  PWM_GLB

CHn at 0x10 + n * 0x10:
  +0x00 CHn_CTRL
  +0x04 CHn_PERIOD
  +0x08 CHn_DUTY
  +0x0C CHn_CNT
```

`PWM_GLB` 的低 4 位是各 channel 的 enable 镜像，高 4 位是 DONE 标志：

```text
bits[3:0]  CHn_EN
bits[7:4]  CHn_DONE, write-1-to-clear
```

counter 的计算方式：

```text
ticks = (now - start_ns) / G233_TICK_NS
counter = ticks % period
```

我的定义：

```c
#define G233_TICK_NS 1000000ULL
```

也就是 1 tick = 1 ms。测试只要求 `qtest_clock_step()` 后 counter 大于 0，所以这个精度已经足够。

第一次实现后，`test_pwm_done_clear` 失败了。原因是写 `PWM_GLB` 清除 DONE 后，下一次读寄存器时又根据旧 `start_ns` 发现 elapsed time 已经超过 period，于是 DONE 立即重新置位。

修复方法是：清 DONE 的同时重置对应 channel 的计时起点：

```c
s->done &= ~clear;
s->ch[i].start_ns = now;
```

这个细节说明，计时类设备清状态位时，通常还要考虑下一次事件从什么时候重新开始计算。

### 5. WDT
#### 原理

WDT，也就是 watchdog timer，通常用于检测系统是否卡死。软件需要周期性“喂狗”。如果长时间没有喂狗，计数器归零，硬件会触发中断或复位。

本实验的 WDT 需要模拟这些行为：

```text
enable 后开始倒计时
读 VAL 能看到剩余值减少
写 feed key 能重新加载计数
写 lock key 后配置不能再被修改
超时后设置 TIMEOUT
如果 INTEN 打开，则触发 PLIC 中断
```

同样，测试不要求真实硬件 timer 后台持续运行；只要读寄存器或推进 QTest 时钟后，模型能根据 virtual clock 算出正确状态即可。

#### 实现细节

WDT 的 MMIO base 是：

```text
0x10010000
```

测试使用的寄存器：

```text
0x00  WDT_CTRL
0x04  WDT_LOAD
0x08  WDT_VAL
0x0C  WDT_SR
0x10  WDT_KEY
```

`WDT_CTRL` 中：

```text
bit0 EN
bit1 INTEN
```

`WDT_LOAD` 设置倒计时初值，`WDT_VAL` 根据 virtual clock 计算剩余值。当经过的 tick 大于等于 load 时，`WDT_SR.TIMEOUT` 置位。如果同时打开 `INTEN`，则拉高 PLIC IRQ 4。

WDT 支持两个 key：

```text
0x5A5A5A5A  feed
0x1ACCE551  lock
```

feed 的语义是重新喂狗：

```text
start_ns = now
sr.TIMEOUT = 0
irq = low
```

lock 的语义是锁定配置。测试会 lock 后尝试写 `WDT_CTRL = 0`，期望 enable bit 仍然保持，因此实现中在 locked 状态下忽略对 `CTRL` 和 `LOAD` 的修改。

WDT 也遇到了和 PWM 一样的状态位清除问题：`test_wdt_timeout_clear` 失败。原因是清除 `WDT_SR.TIMEOUT` 后，下一次读 `WDT_SR` 又因为旧 elapsed time 超过 load 而重新 timeout。修复方法是清标志时刷新计时基准：

```c
s->sr &= ~(uint32_t)value;
if (!(s->sr & 1)) {
    s->start_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    qemu_set_irq(s->irq, 0);
}
```

### 6. SPI
#### 原理

SPI 是一种主从式串行总线。主机通过片选 CS 选择某个从设备，然后一边发送字节，一边接收字节。在 QEMU 模型里，不需要真的模拟每一根时钟线和 MOSI/MISO 电平。对本实验来说，只需要在每次写 `SPI_DR` 时处理一个字节，并根据当前命令 phase 返回一个接收字节。

#### 实现细节

SPI 的 MMIO base 是：

```text
0x10018000
```

寄存器：

```text
0x00  SPI_CR1
0x04  SPI_CR2
0x08  SPI_SR
0x0C  SPI_DR
```

测试使用的关键 bit：

```text
CR1:
  bit0 SPE
  bit2 MSTR
  bit5 ERRIE
  bit6 RXNEIE
  bit7 TXEIE

CR2:
  bits[1:0] CS select

SR:
  bit0 RXNE
  bit1 TXE
  bit4 OVERRUN, write-1-to-clear
```

测试里的 SPI 传输函数基本是：

```c
spi_wait_txe(qts);
qtest_writel(qts, SPI_DR, tx);
spi_wait_rxne(qts);
return qtest_readl(qts, SPI_DR);
```

所以可以简化为：

```text
TXE 初始为 1
写 SPI_DR 后立即生成一个 RX byte
设置 RXNE
读 SPI_DR 返回 RX byte，并清 RXNE
```

overrun 测试会故意在 RXNE 未清除时继续写 DR。实现中只要写 DR 时发现 `RXNE` 已经为 1，就设置 `OVERRUN`：

```c
if (s->sr & SPI_SR_RXNE) {
    s->sr |= SPI_SR_OVERRUN;
}
```

SPI 的 PLIC IRQ 是 5。中断条件包括：

```text
TXEIE  && TXE
RXNEIE && RXNE
ERRIE  && OVERRUN
```

每次写 CR1、写 DR、读 DR 或清 SR 后，都重新计算 IRQ level。

### 7. SPI Flash

#### 原理

SPI Flash 本质上是挂在 SPI 总线后的存储设备。软件不是直接读写它的内存数组，而是通过命令协议访问它。例如读 JEDEC ID 要发送 `0x9F`，读数据要发送 `0x03 + 地址`，写数据前要先发送 write enable。

真实 NOR Flash 还有一个重要特性：写入只能把 bit 从 1 变成 0，不能直接从 0 变回 1。要把 bit 恢复成 1，需要先擦除 sector。

本实验测试了两个片选：

```text
CS0: W25X16, 2MB
CS1: W25X32, 4MB
```

因此 SPI 控制器内部需要为两片 flash 分别保存独立数据和命令状态。

#### 实现细节

我在 `G233SpiState` 中维护了两个简化的 flash：

```text
CS0: W25X16, 2MB, JEDEC EF 30 15
CS1: W25X32, 4MB, JEDEC EF 30 16
```

每片 flash 用一块内存数组表示，初始化为 `0xFF`。支持测试需要的命令：

```text
0x9F  JEDEC ID
0x05  Read Status
0x06  Write Enable
0x20  Sector Erase
0x02  Page Program
0x03  Read Data
```

`0x9F` 后返回 JEDEC ID。`0x06` 设置 write enable latch。`0x20` 按 4KB sector 擦除。`0x02` 执行 page program。为了更贴近 NOR Flash，program 使用：

```c
data[addr] &= tx;
```

也就是说只能把 bit 从 1 写成 0。测试在 program 前都会 erase，所以读回结果能和写入 buffer 一致。

双片选测试会在 CS0 和 CS1 之间反复切换，因此每次 `SPI_CR2` 改变 CS 时，都需要重置当前 flash 的命令状态，避免上一片 flash 的命令 phase 影响下一片。

### 8. symlink 问题

QEMU 源码里有不少符号链接，尤其是子项目中会通过 symlink 引用顶层目录的公共头文件。在 Linux 环境中，这通常没有问题。但如果仓库在 Windows 或某些配置下检出，Git 可能把 symlink 检出成普通文本文件，文件内容只是目标路径。

一旦这种情况发生，编译器会把路径文本当成 C 代码读取，于是出现非常诡异的语法错误，或者找不到原本应该通过 symlink 指向的头文件。

#### 实现细节

第一次构建时，我遇到的错误是 QEMU 子项目头文件找不到：

```text
fatal error: standard-headers/linux/virtio_ring.h: No such file or directory
fatal error: linux-headers/linux/virtio_ring.h: No such file or directory
subprojects/libvduse/include/atomic.h: expected identifier before '.' token
```

检查后发现，一些 Git symlink 被检出成了普通文本文件。例如 `subprojects/libvduse/include/atomic.h` 的内容是一行路径：

```text
../../../include/qemu/atomic.h
```

这说明 Git 配置中 `core.symlinks=false`。修复方式是把这些 Git 索引中类型为 `120000` 的路径恢复成真实 symlink：

```bash
git config core.symlinks true
git checkout -- <symlink paths>
```

恢复后，构建继续进行并通过。

### 9. 测试迭代和最终结果

写设备模型时，很难一次就完全正确。QTest 的价值在于它能给出非常具体的失败点。与其猜测哪里错了，不如先跑测试，看哪条断言失败，再回到对应的寄存器语义上检查模型。

对于本实验，失败点主要集中在计时状态位清除后又立刻被重新置位。这类问题从代码上看可能不明显，但从测试断言能很快定位。


第一次完整跑 `test-soc` 时，结果是：

```text
--- SoC experiment: 8/10 tests passed ---
```

失败项：

```text
test-pwm-basic
test-wdt-timeout
```

具体失败点：

```text
test_pwm_done_clear
test_wdt_timeout_clear
```

这两个问题本质相同：

```text
状态位已经被 W1C 清除
但计时基准没有更新
下一次读寄存器时，时间条件仍然成立
状态位马上又被置位
```

修复后再次运行：

```bash
make -f Makefile.camp test-soc
```

最终结果：

```text
test-board-g233             OK   4 subtests passed
test-gpio-basic             OK   4 subtests passed
test-gpio-int               OK   5 subtests passed
test-pwm-basic              OK   7 subtests passed
test-wdt-timeout            OK   7 subtests passed
test-spi-jedec              OK   3 subtests passed
test-flash-read             OK   4 subtests passed
test-flash-read-interrupt   OK   4 subtests passed
test-spi-cs                 OK   6 subtests passed
test-spi-overrun            OK   2 subtests passed

--- SoC experiment: 10/10 tests passed ---
```

## 总结

这次 SoC 实验让我对 QEMU 硬件建模有了更具体的理解。之前看 QEMU 时，很容易被庞大的目录结构和各种抽象吓住；但通过这个实验，我从一个很小的切口进入：一个 MMIO 地址、一组寄存器、一个中断号、一条测试断言，逐渐弄清楚了QEMU 硬件建模的细节和原理。

我最大的收获有几点：

第一，测试是理解硬件模型需求的最好入口。手册告诉我们设备应该是什么样，测试则告诉我们当前阶段必须实现哪些行为。先读测试，可以避免一开始就陷入过度设计。

第二，MMIO 外设建模的本质是状态机。GPIO 要记录 DIR、OUT、IE、IS；SPI 要记录 RXNE、TXE、OVERRUN 和当前 flash 命令 phase；WDT 和 PWM 要记录计时起点和状态位。只要状态设计清楚，读写寄存器的逻辑就会自然很多。

第三，中断建模一定要把设备侧状态和中断控制器连接起来。设备内部设置了状态位还不够，还要通过 `qemu_set_irq()` 把中断线拉到 PLIC，否则测试读取 pending bit 时不会看到变化。

第四，计时类设备要特别注意“清标志”和“重新计时”的关系。PWM DONE 和 WDT TIMEOUT 的失败都来自同一个原因：状态位虽然清了，但时间条件仍然成立，导致下一次读寄存器又触发。

对后续同学的建议是：不要一开始就试图“完整模拟硬件”，先从测试出发，把每个寄存器的读写语义实现准确。QEMU 的抽象很多，但每个 QTest 断言背后其实都是一个很具体的问题。把这些具体问题一个一个解决，整个设备模型就会慢慢长出来。
完结撒花！！！