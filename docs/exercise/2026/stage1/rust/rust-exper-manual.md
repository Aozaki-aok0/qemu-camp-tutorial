本文档是专业阶段 Rust 方向的实验手册。

Rust 方向的核心任务：用 Rust 在 QEMU 中实现 I2C 总线、GPIO I2C 控制器和 SPI 控制器，挂载到 G233 SoC 上。评测分两部分——Rust 单元测试验证总线核心逻辑，QTest 验证设备寄存器行为和外设通信。

## 环境搭建

第一步，安装 QEMU 开发依赖和 Rust 工具链。

```bash
# Ubuntu 24.04
sudo sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources
sudo apt-get update
sudo apt-get build-dep -y qemu

# 安装 Rust 工具链（版本要求 >= 1.85）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
. "$HOME/.cargo/env"
cargo install bindgen-cli
```

!!! note "提示"

    安装 QEMU 开发环境，请参考导学阶段的 Step0。

    Rust 方向**必须使用 Rust** 实现设备模型，可参考 `rust/hw/char/pl011/` 中的 PL011 Rust 实现。

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

## 实验内容

### I2C 总线（Rust 单元测试）

文件 `rust/hw/i2c/src/lib.rs` 中已经定义好 trait 和 struct 的框架，标记了 TODO 的方法需要你来填充：

- `I2CSlave` trait：`address()`、`event()`、`send()`、`recv()` 方法
- `I2CBus` struct：`attach` 挂载设备、`start_transfer` 地址匹配与事件分发、`send`/`recv` 读写转发
- NACK 处理：访问不存在的地址时返回失败

这部分通过 **Rust 单元测试** 验证（3 题）：

| # | 测试名 | 验证内容 |
|---|--------|---------|
| 1 | `test_i2c_bus_create` | 创建总线，挂载设备，验证设备计数 |
| 2 | `test_i2c_bus_read_write` | 挂载 EEPROM 设备，写入后读回验证 |
| 3 | `test_i2c_bus_nack` | 访问不存在的地址，验证返回 NACK |

### GPIO I2C 控制器（QTest）

需要新建一个 Rust SysBus 设备，挂载到 G233 SoC，基地址 `0x10013000`。可参考 `rust/hw/char/pl011/` 中 PL011 的写法。

寄存器映射：

| 偏移 | 名称 | 说明 |
|------|------|-----|
| 0x00 | I2C_CTRL | bit0: EN, bit1: START, bit2: STOP, bit3: RW (0=写，1=读) |
| 0x04 | I2C_STATUS | bit0: BUSY, bit1: ACK, bit2: DONE |
| 0x08 | I2C_ADDR | 7 位从设备地址 |
| 0x0C | I2C_DATA | 数据寄存器 |
| 0x10 | I2C_PRESCALE | 时钟分频器 |

连接的 I2C 设备：AT24C02 EEPROM（地址 `0x50`，容量 256 字节，页大小 8 字节）

这部分通过 **QTest** 验证（4 题）：

| # | 测试名 | 验证内容 |
|---|--------|---------|
| 4 | `test-i2c-gpio-init` | 寄存器复位值，分频器配置 |
| 5 | `test-i2c-gpio-bitbang` | START/STOP/ACK 协议 |
| 6 | `test-i2c-eeprom-rw` | EEPROM 单字节写入和读回 |
| 7 | `test-i2c-eeprom-page` | EEPROM 页写入和边界回绕 |

### Rust SPI 控制器（QTest）

同样新建一个 Rust SysBus 设备，基地址 `0x10019000`。

寄存器映射：

| 偏移 | 名称 | 说明 |
|------|------|-----|
| 0x00 | RSPI_CR1 | bit0: SPE, bit2: MSTR |
| 0x04 | RSPI_SR | bit0: RXNE, bit1: TXE, bit4: OVERRUN |
| 0x08 | RSPI_DR | 数据寄存器 |
| 0x0C | RSPI_CS | 片选 |

连接的 SPI 设备：AT25 EEPROM（256 字节）

这部分通过 **QTest** 验证（3 题）：

| # | 测试名 | 验证内容 |
|---|--------|---------|
| 8 | `test-spi-rust-init` | 寄存器复位值，使能配置 |
| 9 | `test-spi-rust-transfer` | SPI 数据传输，TXE/RXNE 状态 |
| 10 | `test-spi-rust-flash` | AT25 EEPROM 状态寄存器、写入和读回 |

## 提交代码

改完之后提交：

```bash
git add .
git commit -m "feat: subject..."
git push origin main
```

涉及的文件：

- `rust/hw/i2c/src/lib.rs` — I2C 总线核心逻辑（填充 TODO）
- 新建 Rust SysBus 设备文件（GPIO I2C 控制器、SPI 控制器）
- `hw/riscv/g233.c` — 在 SoC 中实例化你的 Rust 设备

!!! note

    核心逻辑必须用 Rust 写，单元测试会检查这一点。

## 测评验收

本地运行全部测题：

```bash
make -f Makefile.camp test-rust
```

共 10 道题（3 道 Rust 单元测试 + 7 道 QTest），每题 10 分，满分 100 分。

每次 push 到 `main` 会触发 CI 评测，得分更新到[Rust 方向专业阶段排行榜][4]。

## 进阶实验

!!! note "说明"

    进阶实验为开放题目，不计入 100 分基础测评，但会作为训练营评优与推荐的重要参考。基础实验聚焦于总线/字符类外设（I2C、SPI），进阶方向则把 Rust 设备建模推进到块设备、PCIe、virtio 等 QEMU 中更复杂、更贴近生产环境的子系统。

### 进阶实验一 Rust 实现 virtio-mmio 传输层

挑战目标：用 Rust 重写 virtio-mmio 传输层的核心逻辑，并挂载到 G233 SoC（或 `riscv/virt` machine）上，对接 QEMU 现有的 virtio 设备后端（virtio-blk / virtio-net）。

参考方向：

- 阅读 `hw/virtio/virtio-mmio.c`，理清 MMIO 寄存器布局（`QueueSel`、`QueueNotify`、`InterruptStatus` 等）、virtqueue 的 kick / callback 生命周期。
- 在 `rust/hw/virtio/` 下新建 crate，实现一个 `VirtioMmioTransport` 结构，暴露给 C 端的 VTable。
- 最小验收：启动一个 Linux guest，能识别 Rust transport 下挂的 virtio-blk 设备并完成读写。

### 进阶实验二 Rust 实现 virtio-blk 后端

挑战目标：在进阶实验一的 transport 基础上，用 Rust 写一个完整的 virtio-blk 设备后端，复用 QEMU 的 `BlockBackend` 作为后端存储。

关键点：

- 处理 virtio-blk 的 feature negotiation（`VIRTIO_BLK_F_SEG_MAX`、`VIRTIO_BLK_F_FLUSH` 等）。
- 正确使用 QEMU 的 AIO 线程池提交异步 I/O，用 Rust 的 `unsafe` + bindings 封装 `blk_aio_preadv` / `blk_aio_pwritev`。
- 处理请求的描述符链解析、GPA → HVA 地址转换、状态字节写回。
- 验收：挂一个 rootfs 镜像，让 Linux guest 能 `mount` 并读写。

### 进阶实验三 Rust 实现 PCIe 设备建模

挑战目标：参考 `hw/misc/edu.c`、`hw/misc/pci-testdev.c`，用 Rust 写一个挂在 PCIe 总线上的设备（可以是简易计算加速器、或最小的 NIC 原型）。

要求至少覆盖以下 PCIe 特性：

- PCI 配置空间（Vendor/Device ID、Class Code、BAR 规划）。
- 至少一个 MMIO BAR 与一个可选的 I/O BAR，寄存器读写正确。
- **MSI-X 中断**：实现 MSI-X Capability 和至少 4 个向量，设备内部事件能路由到 guest 中断。
- **DMA**：设备能主动访问 guest 物理内存（用 `pci_dma_read` / `pci_dma_write` 对应的 Rust bindings）。

验收：在 `riscv/virt` 或 `x86_64 pc` machine 上插入该设备，用一段小程序（可以是 QTest）验证 MMIO、MSI-X、DMA 三条链路。

### 进阶实验四 把 GPGPU 方向的设备用 Rust 重写

如果你同时完成了 GPU 方向，可以把 `hw/gpgpu/gpgpu.c`（PCIe 前端、BAR、DMA、MSI-X）或 `hw/gpgpu/gpgpu_core.c`（SIMT 解释器）移植到 Rust。

建议先迁移前端的寄存器逻辑与 DMA 引擎，把 SIMT 执行后端留作 C，通过 Rust ↔ C FFI 互相调用；随后再尝试把 RV32I/RV32F 解释器也用 Rust 重写。

评估维度：迁移范围、`unsafe` 使用是否克制、与原 C 实现的功能等价性（能否通过 GPGPU 方向的 17 道 QTest）。

[3]: https://classroom.github.com/a/hwWFrmo_
[4]: ../../../../leaderboards/2026/professional/rust.md
