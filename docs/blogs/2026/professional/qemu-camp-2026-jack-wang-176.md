# QEMU 训练营 2026 专业阶段总结

!!! note "主要贡献者"

    - 作者：[@jack-wang-176](https://github.com/jack-wang-176)

---

## 背景介绍

作为一名软件工程专业的学生，我在学习后端开发的过程中逐渐对底层计算机系统产生了浓厚的兴趣。在群友的推荐下，我报名参加了 QEMU 训练营，并出于对硬件抽象与外设开发的兴趣，最终选择了 SoC 专业阶段方向。

本次专业阶段的实验可以清晰地划分为两个阶段：

1. **SoC 外设的建模与开发**：在这个阶段，我使用 Rust 语言对硬件外设进行了建模。最大的收获不仅在于掌握了如何利用 QEMU 提供的 API 进行外设开发，更在于深度体验了 C 与 Rust 混合编程的 FFI 边界处理。此外，通过阅读讲义，我对这套庞大系统的核心架构和特性实现有了实质性的理解。它让我明白了**“如何用高级软件语言去精准描述底层硬件的物理逻辑”**。
2. **基于虚拟主板的 Linux 内核引导**：在完成了基本的外设开发后，我成功在虚拟的 SoC 板子上跑通了从引导程序到 Linux 内核的启动全流程。这一部分从宏观系统的角度向我揭示了 Linux 内核的启动流程，也让我从应用层面理解了 QEMU 到底为系统级联铺平了哪些道路。

从底层的寄存器位运算，到高层的 Linux 终端字符跳动，当看到自己做出来的虚拟硬件真正支撑起一个 Linux 内核运行的那一刻，成就感油然而生。

## 专业阶段
 ### 一般外设建模流程和与 QEMU 底层实现思路的联系

 QEMU 提供的 API 和其底层架构是一脉相承的，这一点我在看讲义的时候得到了特别清晰的感受。回顾讲义和示例代码，无论是用 C 还是 Rust，外设建模的核心流程可以标准化为以下几部分：

 ```text
 1. TypeInfo 注册
 2. 外设结构体定义 (Object 数据)
 3. 初始化回调函数 (类初始化 Class_Init 与实例初始化 Instance_Init)
 4. 外部结构要求实现 (QOM 接口与属性)
 5. 中断函数以及读写函数 (MMIO 与 IRQ)
 ```
 这种标准化的结构完全基于 QEMU QOM (Qemu Object Model) 的底层原理，语言只是载体。

 #### 1. TypeInfo 的注册机理：`main` 函数之前的暗箱操作

 TypeInfo 是 QEMU 模拟面向对象的核心“图纸”。在 QEMU C 源码中，TypeInfo 会在整个程序的 `main` 函数执行之前完成全局的类型收集和注册。

 ```plantext
 [编译期/链接期] -> [程序启动 (main 之前)] -> [程序运行 (main 阶段)]
 
                  gcc `__attribute__((constructor))`
    TypeInfo A  ──┐      (对应 Rust 中的生命周期钩子)      全局哈希表 (Type Table)
                  │                                        ┌───────────────┐
    TypeInfo B  ──┼─────> qemu_register_type() ──────────> │ "gpio" -> Info│
                  │                                        ├───────────────┤
    TypeInfo C  ──┘                                        │ "uart" -> Info│
                                                           └───────────────┘
 ```
 **原理解析：** 就像内核编译时的 `.text` 和 `.data` 段一样，程序是以 ELF 文件格式加载到内存的。C 语言的 `type_init()` 宏利用了编译器的 `__attribute__((constructor))` 特性。这使得当操作系统把 QEMU 加载进内存时，在还没跳入 `main()` 入口点之前，这些注册函数就已经悄悄运行了。它们把所有散落在各个文件里的 `TypeInfo` 结构体，统一塞进了一个全局的哈希表中。这就是为什么在 `main` 函数里直接按名字就能动态实例化对象的底层秘密。
 
 #### 2. 三位一体的 QOM 架构：TypeInfo、ObjectClass 与 Object
 
 在这里注册的回调函数对应了类的初始化（`class_init`）和实例的初始化（`instance_init`）。你需要严格区分这三者在架构中的位置和生命周期：
 
 ```plantext
  1. 静态图纸层 (只读数据段)      2. 类方法层 (堆区，全局单例)      3. 实例数据层 (堆区，多实例)
  ┌─────────────────┐           ┌─────────────────┐             ┌─────────────────┐
  │ TypeInfo        │           │ ObjectClass     │            │ Object (State)  │
  │ - name="gpio"   │ 实例化类   │ - realize() 指针 │ 实例化对象    │ - 寄存器值      │
  │ - class_init    ├─────────> │ - reset() 指针   ├───────────> │ - MMIO 区域      │
  │ - instance_init │ (首次用到 │ - vmsd(热迁移)  │ (每次创建   │ - 中断引脚      │
  └─────────────────┘  时生成)  └─────────────────┘ 设备时生成) └─────────────────┘
 ```
 - **TypeInfo**：存在于只读数据段或静态内存中，它只是说明书，告诉你类有多大、实例有多大，该去调哪个函数初始化。它和另外两者的运行期是两个层次。
 - **ObjectClass**：它是 C 语言里的**虚函数表 (vtable)**。QEMU 是懒加载的，只有在第一次需要创建 `gpio` 设备时，才会根据 `TypeInfo` 里的 `class_init` 动态在堆上分配并初始化这个 Class 对象。它在整个 QEMU 进程中**只有一个全局单例**。
 - **Object (外设结构体)**：这是具体的硬件实例。每次你创建一个 GPIO 节点，QEMU 就会根据 `TypeInfo` 提供的大小分配一块内存，并调用 `instance_init` 来初始化它的私有数据（如寄存器值、中断线）。
 
 #### 3. 硬件逻辑的软件映射：MMIO 读写与 IRQ 中断线连线
 
 当实例创建出来后，它是怎么和 CPU 以及其他设备交互的呢？
 - **读写函数 (MMIO)**：通过 `MemoryRegionOps` 进行挂载。当 CPU 尝试读写特定的物理内存地址时，QEMU 的内存总线 (Memory API) 会拦截这个请求，并直接调用我们在 OPS 里填写的 `read/write` 函数。
 - **中断 (IRQ)**：在硬件层面，触发中断是“拉高引线（电平变化）”。而在 QEMU 的软件实现中，引线实际上就是一个**回调函数指针**
 
 ```plantext
 [ GPIO 外设 ]                                [ 虚拟主板 / 中断控制器 ]
 ┌─────────────┐                               ┌─────────────────────┐
 │ write() 逻辑│                               │                     │
 │ 1. 更新寄存器│    sysbus_connect_irq 连线    │ IRQ 处理逻辑 (PLIC)   │
 │ 2. 状态改变  │ ───────────────────────────> │ 1. 接收电平信号        │
 │ 3. irq.set()├─ (底层调用 qemu_set_irq) ───> │ 2. 注入异常到 CPU     │
 └─────────────┘                               └─────────────────────┘
 ```
 **连线机制：** 当我们在虚拟主板（如 g233 board 代码）中调用 `sysbus_connect_irq` 时，其实质是把中断控制器的某个输入函数地址，赋给了 GPIO 的 `InterruptSource` 对象。当 GPIO 的寄存器被写入并检测到符合触发条件时，调用 `irq.set(true)` 实际上就是执行了那根线上挂载的函数调用。这把复杂的硬件物理电平信号，优雅地抽象成了两个对象之间的方法调用。

### 外设添加到板子并在 fdt 中进行描述
在本次实验中我们所创建的设备都是通过 sysbus 进行 soc 的集成，因此在内核启动的时候需要通过对应的 fdt 来获得对应设备，而在进阶实验的网卡和硬盘搭载则是通过 virto-mmio 机制实现，在对应的 fdt 中只需要添加 virto-mmio 插槽。

> **补充：Virtio-MMIO 与 PCIe 的规范性探讨**
> 在企业级、成熟的生产环境板载架构中，挂载网卡和硬盘**更倾向于使用 PCIe 总线**而非 virtio-mmio。因为 PCIe 规范自带硬件级的“设备枚举与扫描机制 (Device Enumeration)”，操作系统启动时能够自动顺着总线发现设备；而 virtio-mmio 属于“静态盲插”，不具备自发现能力，必须由开发者手动在 FDT 设备树中硬编码配置插槽的内存基址和中断号。因此，使用 virtio-mmio 更多是为了虚拟化实验便捷而采用的轻量级方案，PCIe 才是现代更规范、更通用的标准。

首先我们需要在对应的内存分区进行 mmio 内存的规划，和对 plic 的中断线的规划。
```text
调用函数进行初始化
挂载内存空间和中断线
```
这里的代码实际上是一个很清晰的描述，就像实际上真正去把外设插入到对应的凹槽中。在对应的 machine 级别的初始化之后就要在 fdt 初始化代码中添加对应节点。

在内核中通过设备树来寻找相应设备，bootloader 会将 fdt 这么一个扁平数组根据 cpu 协议的不同放在不同的寄存器中，而在 qemu 进行 main 函数的第一步就是对这么一个寄存器的 fdt 设备进行加载和解析，在 qemu 中封装好了对应的添加节点的函数
```text
添加节点
添加 compatible 属性
添加 reg 属性
添加中断
```
这里对设备的添加和设备初始化的挂载结构很近似，因为 fdt 只是将设备当作整体进行处理，这一点和板载初始化时候的处理方式一致，因此自然而然在逻辑上也相似。

> **图例与补充解释：物理挂载与 FDT 声明的同构映射**
> 物理主板视角 (machine_init) 和内核软件视角 (FDT 生成) 是严格逻辑同构的：
> 1. 拿出一个芯片并分配物理内存 `0x10012000` -> 对应 FDT 中添加 `reg` 属性 `[0x10012000, 0x1000]`
> 2. 焊接中断引脚至 PLIC 的第 7 根线上 -> 对应 FDT 中添加 `interrupts` 属性 `[0x07]`
> 3. 贴上型号标签 "sifive,gpio0" -> 对应 FDT 中添加 `compatible` 属性
> 
> 在具体的 QEMU C 代码实现中，这体现为调用 `qemu_fdt_add_subnode` 以及 `qemu_fdt_setprop_string` / `qemu_fdt_setprop_sized_cells` 等封装函数来动态构建这棵设备树。
 ### Rust 和 C 的 FFI 边界跨越

 在这次实验中我使用了 Rust 进行外设的开发，而 g233 虚拟主板的架构是通过 C 语言定义的。因此，在开发过程中必须直面一个核心问题：C 和 Rust 这两门理念完全不同的语言，如何进行无缝的跨边界（FFI, Foreign Function Interface）交互？

 C 和 Rust 的交互主要体现在**底层数据结构对接**和**函数接口互相调用**上。

 #### 1. 数据结构对接：字符串与智能指针

 **字符串的碰撞：**
 C 语言和 Rust 语言在字符串的处理上有着本质的区别。C 语言的字符串是“以 NUL（`\0`）结尾的字符数组”，不记录长度；而 Rust 的字符串（`String` / `&str`）是“带有长度记录的 UTF-8 字节序列”，且不以 `\0` 结尾。为了跨越这个边界，我们必须使用标准库提供的转换接口：
 - **Rust 传给 C**：需要使用 `CString::new("gpio").unwrap()`，这会在 Rust 字符串末尾追加 `\0`，随后通过 `.as_ptr()` 将裸指针传给 C。
 - **C 传给 Rust**：需要使用 `CStr::from_ptr(c_char_ptr)`。Rust 会沿着 C 指针遍历直至遇到 `\0`，算出长度并封装成安全的 `&CStr`，供后续业务使用。在定义宏观常量时（如 `TYPE_GPIO`），我们也大量使用了 `c"gpio"` 这种特殊的 C 字符串字面量宏。

 **指针与生命周期的博弈（Owned vs Borrowed）：**
 Rust 的指针有着极度严格的可变与非可变别名规则，且默认拥有内存分配和回收的生命周期。在一般 FFI 项目中，传递给 C 语言时必须用 `Box::into_raw` 剥夺 Rust 的回收权。
 但在 QEMU 中，由于其底层自建了 QOM 面向对象系统，有一套类似引用计数的垃圾回收机制（`object_ref` / `object_unref`）。因此 QEMU 社区专门提供了一层抽象：`Owned<T>` 智能指针。
 当我们通过 API 获取子设备时，返回的是 `Owned<Clock>` 或 `Owned<IRQState>`。它巧妙地通过底层的 `from_raw` 和 Drop 机制接管了 C 框架抛来的对象引用，实现了 Rust 生命周期系统与 QEMU C 语言垃圾回收的协调运作。而在 C 语言部分则极少直接获取具体的设备指针，更多是通过传递不透明指针来对接标准接口。

 #### 2. 函数的互相调用：Bindgen 与“蹦床机制”

 **Rust 调用 C 语言：**
 通常依赖 Rust 官方的 `bindgen` 工具，在编译阶段解析 C 的头文件（如 `wrapper.h`），自动生成带有 `extern "C"` 的 Unsafe Rust 函数桩。

 **C 语言调用 Rust 语言（回调的核心）：**
 QEMU C 框架是不可能直接认出 Rust 的闭包或成员方法的。C 语言想要调用 Rust，通用做法是传递**不透明指针 (Opaque Pointer, `void *opaque`)** 和一个**蹦床函数 (Trampoline)**。
 以系统回调机制为例，Rust 底层会生成类似这样的代码来欺骗 C 语言：
 ```rust
 // 1. Rust 提供给 C 的纯净蹦床函数，签名完全符合 C 规范
 unsafe extern "C" fn rust_irq_handler<T, F: Fn(&T, u32, u32)>(
     opaque: *mut c_void,  // C 传来的黑盒指针
     line: c_int, 
     level: c_int
 ) {
     // 2. 将 C 世界的黑盒强转回 Rust 的具体设备类型指针
     let device = unsafe { &*(opaque.cast::<T>()) };
     // 3. 执行真正的 Rust 业务闭包/方法
     F::call(device, line as u32, level as u32)
 }
 ```
 通过这种优雅的泛型蹦床，C 语言依然在地调用一个普通的 C 函数原型，但底层其实已经完成了一次指针身份的降维打击与升维恢复，最终精准跳入到了 `GpioState::handle_gpio_in` 业务逻辑里。

 #### 3. QEMU 特供高级封装接口（宏与工具箱）

 在实际开发中，QEMU 社区已经帮我们铺平了绝大部分道路。作为开发者不需要每次都去手写危险的指针转换，直接使用以下封装好的 api 即可：

 - **`qom_isa!` 宏（跨界注册与安全向下转型）**：
   我们在定义结构体时写了 `qom_isa!(GpioState: SysBusDevice, ...)`。C 语言的继承是硬贴合的（子类第一个字段必须是父类）。这个宏的作用就是在 Rust 侧赋予了你安全进行 `self.upcast()` 或 `self.as_ref()` 的能力。底层自动利用 `ptr.cast::<$parent>()` 为你搭建了一条符合 C 内存布局的指针强转合法通道。

 - **`uninit_field_mut!` 宏（未初始化内存保护）**：
   当 C 语言把一块未初始化的脏内存分配给你时（如 `this` 初始化阶段），如果直接拿 Rust 引用去修改（如 `&mut this.mmio`），Rust 会尝试去调用脏内存里原有的析构逻辑，极易触发段错误（UB）。这个宏利用底层的 `std::ptr::addr_of_mut!`，仅计算偏移量而不解引用，配合 `.write()` 让你能够安全地写入初始化数据。

 - **`BqlRefCell<T>`（白嫖全局大锁）**：
   普通 Rust 并发需要加互斥锁（Mutex），但 QEMU 本质是单线程大锁架构（BQL）。这个数据结构利用 `assert!(bql::is_locked())` 进行运行时断言，只要持有大锁，就能通过内部的 `UnsafeCell` 安全地实现内部可变性，既免除了系统级锁调用的开销，又合法骗过了 Rust 的线程安全检查！

 ### 以 GPIO 为例子的 Rust 设备思路说明

 下面我将以 GPIO 作为例子，展示在完成实验阶段时具体的代码思路与底层实现细节。

 #### 1. 宏观构建架构与配置体系

 ```plantext
  gpio/                   [外设根目录] 自定义 GPIO 外设的工程目录
  ┃
  ┣━  构建与配置层 (The Build System)
  ┃  ┣━  Kconfig         [特性开关] 定义配置宏 (如 CONFIG_RUST_GPIO)
  ┃  ┣━  meson.build     [构建桥梁] QEMU 构建脚本，读取 Kconfig 并触发 Rust 编译
  ┃  ┗━  Cargo.toml      [Rust 包管理] 定义 Rust 侧依赖 (如 qemu_api)
  ┃
  ┣━  跨语言桥梁层 (The FFI Bridge)
  ┃  ┗━  wrapper.h       [C 语言头文件] 纯 C 文件，集中 #include 所需头文件
  ┃
  ┗━  src/                [核心源码区] Rust 业务逻辑
     ┃
     ┣━  bindings.rs     [接口字典] (bindgen 自动生成) 将 C 结构体翻译为 Rust unsafe 接口
     ┣━  gpio.rs         [核心逻辑] 物理行为模拟：寄存器状态、引脚电平、MMIO 回调
     ┗━  lib.rs          [注册中心] QOM (QEMU Object Model) 注册入口
 ```
 **配置嵌套与包管理解析：**
 在这里，底层 `Kconfig` 定义的开关状态会被上层主板 (如 `g233`) 的配置文件读取并依赖。当构建系统发现 `CONFIG_RUST_GPIO=y` 时，外层的 `meson.build` 就会唤醒内层的 Rust 包管理器 `cargo`，开始编译这个设备。
 `Cargo.toml` 不仅管理着 FFI 桥梁依赖（如 `qemu_api`），还决定了最终的编译输出类型——通常是一个 `.a` 静态链接库 (`staticlib`)。
 整个流程和早年 U-Boot 尝试引入 Rust 时的混合编程模式如出一辙：把 Rust 编译成静态库黑盒，最后由 C 语言的链接器 (Linker) 将其与主程序死死地连接在一起。

 #### 2. QEMU FFI 运行期全景调用流程

 我们可以通过下面这张图，清晰地看到虚拟外设在整个 QEMU 生命周期中的所处位置：

 ```plantext
 [访客操作系统]            [QEMU 核心引擎 (C)]          [你的 Rust 外设 (lib.rs/gpio.rs)]
   (Guest OS)                 (QOM & 内存总线)                  (libgpio.a)
 ================          ===================          =================================

                                  [启动与初始化]
                                        │
                                        ├─ 1. QEMU 启动，遍历设备树
                                        │
                                        ├───────────────────────> 2. 调用 lib.rs 中的 init 钩子
                                        │                         (注册设备类型、划定 MMIO)
                                        │
                                        │<─────────────────────── 3. 返回实例指针，挂载成功
                                        │

                                  [运行时交互 (MMIO)]
                                        │
 4. CPU 执行汇编指令                      │
    (如往 0x10012000 写入)               │
    ───────────────────────────────────>│ 5. 总线拦截物理地址，定位到 GPIO 外设
                                        │
                                        ├───────────────────────> 6. 触发 `write` 蹦床回调
                                        │                            (此时进入 Rust 世界)
                                        │                                 │
                                        │                            7. Rust 逻辑判断：
                                        │                               - 更新寄存器 UnsafeCell
                                        │                               - (如果满足) 触发虚拟中断
                                        │                                 │
                                        │<─────────────────────── 8. 业务执行完毕，返回 C 世界
                                        │
 9. 异常返回，内核继续运行 <───────────────┘
 ```

 #### 3. 设备注册与三阶段初始化

 让我们深入代码细节。首先是 QOM 对象的定义：
 ```rust
 pub const TYPE_GPIO: &CStr = c"gpio";
 qom_isa!(GpioState: SysBusDevice, DeviceState, Object);

 unsafe impl ObjectType for GpioState {
     type Class = <SysBusDevice as ObjectType>::Class;
     const TYPE_NAME: &'static CStr = TYPE_GPIO;
 }

 #[repr(C)]
 #[derive(qom::Object, hwcore::Device)]
 pub struct GpioState {
     parent_obj: ParentField<SysBusDevice>,
     mmio: MemoryRegion,
     dir: UnsafeCell<u32>,
     // ...其他寄存器
     irq: InterruptSource,
     outlines: [InterruptSource; 32],
 }
 ```
 接着是实现 `ObjectImpl` 强制要求的三个初始化钩子：
 ```rust
 impl ObjectImpl for GpioState {
     type ParentType = SysBusDevice;
     
     // 1. 类初始化 (Class Init)
     const CLASS_INIT: fn(&mut Self::Class) = Self::Class::class_init::<Self>;
     // 2. 实例内存分配后初始化 (Instance Init)
     const INSTANCE_INIT: Option<unsafe fn(ParentInit<Self>)> = Some(Self::init);
     // 3. 实例后续挂载 (Instance Post Init)
     const INSTANCE_POST_INIT: Option<fn(&Self)> = Some(Self::post_init);
 }
 ```
 **深度原理解析：**
 - **类初始化 (`CLASS_INIT`) 的自动生成**：它并非宏自动生成，而是 Rust 泛型 Trait（如 `SysBusDeviceClassExt`）提供的默认实现。QEMU 的 Rust 架构师提前写好了这个通用范式，它能在编译期提取你在 Rust 里定义的属性，自动填入 C 语言的 `TypeInfo` 虚函数表里。这是一种无开销的抽象。
 - **实例初始化 (`INSTANCE_INIT`) 的未初始化陷阱**：在 `Self::init` 函数里，C 语言分配好了一块脏内存交给你。此时不能使用 Rust 的常规赋值（如 `this.mmio = ...`），因为这会触发原脏内存地址上的 Drop 析构逻辑，直接导致段错误，我们必须使用底层封装好的 `uninit_field_mut!` 宏，安全地对那块 C 处女地进行原地构造。
 - **三阶段对应关系**：`CLASS_INIT` 在全局只执行一次，用于填表；`INSTANCE_INIT` 负责填入默认值和定义 MMIO Ops（通过 `MemoryRegionOpsBuilder` 将 Rust 读写函数绑定成 C 语言认可的形式）；`INSTANCE_POST_INIT` 则是等所有底层指针都稳定后，再向 QEMU 总线提交 `init_mmio` 和 `init_irq`。

 #### 4. 多线程声明与 MMIO 读写视角的本质

 为了让 QEMU 认可这是一个合法的设备，我们需要显式声明一些标记：
 ```rust
 // 强制骗过 Rust 编译器：虽然内部有 UnsafeCell，但在 BQL 大锁保护下，它是线程安全的！
 unsafe impl Send for GpioState {}
 unsafe impl Sync for GpioState {}

 impl DeviceImpl for GpioState {}
 impl ResettablePhasesImpl for GpioState {}
 impl SysBusDeviceImpl for GpioState {}
 ```
 **为何必须显式声明 Send/Sync？**
 QEMU 是多线程的架构（比如有专门处理 VCPU 循环的线程和专门处理 I/O 的线程），但对设备状态的访问是被 Big QEMU Lock (BQL) 全局锁死死守护的。由于我们结构体里用了 `UnsafeCell`，Rust 编译器会判定它不可跨线程。我们必须显式写下 `unsafe impl Send/Sync`，告诉编译器：外面有 QEMU 大锁保证并发安全，从而合法地绕过 Rust 的编译期线程安全检查。

 最后，最核心的读写逻辑被挂载：
 ```rust
 impl GpioState {
     fn read(&self, offset: hwaddr, _size: u32) -> u64 {
         match offset {
             0x00 => self.dir_val() as u64,
             0x04 => self.out_val() as u64,
             // ...
             _ => 0
         }
     }
     
     fn write(&self, offset: hwaddr, data: u64, _size: u32) {
         let val = data as u32;
         match offset {
             0x00 => {
                 unsafe { *self.dir.get() = val; }
                 // ...更新引脚电平和中断
                 self.update_irq();
             }
             // ...
             _ => {}
         }
     }
 }
 ```
 **地址偏移量的视角转换：**
 这里极度重要的一点是：在 `read` 和 `write` 函数里，你看到的 `offset` 只有 `0x00`, `0x04`。
 **外设的代码逻辑，永远是以自身的起始地址为 0x00 作为相对视角的** 外设绝不应该硬编码自己的物理地址（比如 `0x10012000`）。外设只是一块芯片，它究竟被插在主板的哪个内存段上，那是上层机器（Machine/Board C 代码）通过 `sysbus_mmio_map` 函数决定的。QEMU 的内存 API 拦截到 CPU 对 `0x10012004` 的写入后，会自动减去外设的基地址，抽出偏移量 `0x04`，再投递给你的 `write` 回调。这就是系统编程中解耦思想的最佳体现。
### 基于 g233 板子启动 Linux 内核

 在完成了对应的外设建模和挂载，并更新 FDT 设备树之后，现在我们已经有了基本的 SoC 模型。接下来的目标是依靠它来启动一个完整的 Linux 内核。

 为了支持网络和存储，在进阶实验部分我们采用了添加 `virtio-mmio` 插槽的方案。
 **直接用 PCIe 和 PL011 是更好的方案**
 - **PL011 串口**：这是 ARM 体系下非常成熟的 UART 标准硬件，生产环境和绝大多数 Linux 内核默认包含其驱动，比自己写一个 UART 兼容性更好。
 - **PCIe vs SysBus (MMIO)**：在企业级和成熟的 SoC 架构中，设备插拔通常使用 PCIe 总线。PCIe 自带**设备枚举与发现机制 (Device Enumeration)**，操作系统只要扫描 PCIe 总线就能知道挂载了什么网卡和硬盘。而 `virtio-mmio` 基于 SysBus，没有总线扫描能力，它是“静态盲插”的。
 
 正因为 `virtio-mmio` 没有自我发现能力，我们必须在 QEMU 的 C 语言主板代码中手动修改 FDT（设备树），明确告诉 Linux 内核：“在这个绝对物理地址上，插着一个 Virtio 设备，你去初始化它吧。”

 **FDT 设备树注入实例：**
 ```c
 // 在 g233_machine_init 函数中，为 Virtio-MMIO 动态生成 FDT 节点
 char *nodename = g_strdup_printf("/soc/virtio_mmio@%lx", base_addr);
 qemu_fdt_add_subnode(machine->fdt, nodename);
 qemu_fdt_setprop_string(machine->fdt, nodename, "compatible", "virtio,mmio");
 qemu_fdt_setprop_sized_cells(machine->fdt, nodename, "reg",
                              2, base_addr, 2, size);
 qemu_fdt_setprop_cells(machine->fdt, nodename, "interrupts", irq, 0x4);
 g_free(nodename);
 ```
 这段代码在 QEMU 启动时将硬件的内存范围和中断号写成扁平设备树数据结构。Linux 内核在启动时解析这段数据，才会去对应地址探测 `virtio` 前端驱动。

 ### initrd 启动内核 (内存文件系统)

 在下载并编译了 Linux 内核后，如何将内核、我们的虚拟硬件以及用户态工具链联系起来？
 最原始且最稳妥的方式是使用 **initrd (Initial RAM Disk)**。它的本质是把一个微型文件系统打包成文件，QEMU 在启动时将其强行塞入内存，内核启动后将其解压作为临时的根目录。

 为了构建这个流程，我们需要完成以下几个连贯的步骤：

 #### 1. 内核配置：开启半虚拟化支持
 我们必须在 Linux 内核的 `.config` 中开启 `CONFIG_VIRTIO_BLK=y`（硬盘）和 `CONFIG_VIRTIO_NET=y`（网卡）。
 Virtio 是一种半虚拟化（Para-virtualization）标准。和全模拟真实硬件（比如模拟一块极其复杂的物理网卡 RTL8139）不同，Virtio 驱动知道自己跑在虚拟机里，它直接通过共享内存环（Virtqueue）与 QEMU 宿主机进行高效的批量数据交换，省去了大量模拟真实物理寄存器的开销。

 #### 2. 用户态基石：BusyBox 交叉编译
 由于虚拟主板是 RISC-V 架构，我们需要用交叉编译工具链（如 `riscv64-unknown-linux-gnu-gcc`）静态编译 BusyBox。执行 `make install` 后，会生成一个包含 `bin`, `sbin`, `usr` 目录的文件夹，里面所有的常用命令（如 `ls`, `mount`, `sh`）实际上都是指向 `busybox` 可执行文件的软链接。这就是我们系统的根骨架（RootFS）。

 #### 3. 编写 `init` 引导脚本与三大文件系统
 我们在 RootFS 的根目录下创建一个 `init` 文件，这是内核完成初始化后执行的**第一个**用户态程序（PID=1）：
 ```bash
 #!/bin/sh 
 # 1. 挂载伪文件系统，这是 Linux 与内核/硬件交互的基石
 mount -t proc none /proc # 挂载 proc：向用户态暴露内核运行状态、进程信息 (如 /proc/cpuinfo)
 mount -t sysfs none /sys # 挂载 sysfs：向用户态暴露面向对象的硬件设备树层级结构和驱动状态
 mount -t devtmpfs none /dev # 挂载 devtmpfs：内核自动根据发现的硬件在这里创建对应的设备节点 (如 /dev/vda, /dev/ttyS0)
 
 # 2. 将当前 shell 替换为可交互的 sh
 exec /bin/sh
 ```
 这三个挂载动作使整个系统活过来。没有它们，在终端里连设备都看不到。

 #### 4. 使用 CPIO 打包归档
 ```bash
 find . | cpio -o -H newc > ../initrd.cpio
 ```
 **命令解析：** `cpio` 是一种极其古老但结构简单的磁带归档格式。`-o` 代表输出，`-H newc` 指定了 Linux initramfs 官方钦定的 SVR4 归档标准。Linux 内核只认这个格式的压缩或未压缩包。这条命令把刚刚准备的整个文件夹结构强行揉成了一个连续的二进制文件 `initrd.cpio`。

 #### 5. 启动时序与 QEMU 参数解析
 ```plantext
 [启动时序全景]
 
 1. QEMU 加载：将 Kernel、initrd.cpio、FDT 加载到分配好的虚拟物理内存中
       │
       ▼
 2. OpenSBI:   (M 态) 初始化陷阱、定时器等底层硬件抽象，将 CPU 权限降级，跳入 Kernel
       │
       ▼
 3. Linux 内核：(S 态) 解析 FDT，识别设备 -> 解压 initrd.cpio 到虚拟 RAM Disk -> 挂载为根文件系统
       │
       ▼
 4. 特权降级：内核打开 /dev/console (绑定 stdin/out/err) -> 切换页表 -> 降级跳入用户态 (U 态)
       │
       ▼
 5. 用户态 /init: (U 态 PID=1) 执行上面写的 shell 脚本 -> 挂载 /proc, /sys -> 呈现 sh 提示符！
 ```

 **QEMU 启动指令：**
 ```bash
 ./qemu-system-riscv64 -M g233 \
     -bios default \                     # 使用默认的 OpenSBI 作为固件
     -kernel arch/riscv/boot/Image \     # 指定编译好的内核镜像
     -initrd ../initrd.cpio \            # 指定刚刚打包的 CPIO 内存文件系统
     -append "console=ttyS0 earlycon=sbi loglevel=8" \ # 传给内核的 Cmdline (路标)
     -nographic                          # 关闭图形窗口，直接把虚拟机的串口重定向到当前终端
 ```

 ### U-Boot 启动内核 (持久化文件系统)

 Initrd 的致命劣势在于：**数据存放在 RAM 中，一断电/关机就全部丢失**。为了拥有一个真正持久化的 Linux 环境，我们需要引入独立的硬盘 (Disk) 和更高级的 Bootloader——**U-Boot**。

 **U-Boot 的核心优势：** 
 它像电脑主板上的 BIOS/UEFI。它可以扫描磁盘分区，支持网络启动 (TFTP/NFS)，认识各种文件系统 (FAT32/EXT4)，甚至能在引导内核前对硬件环境进行复杂的探测与设置。

 **OpenSBI 与 U-Boot 的职责划分：**
 - **OpenSBI (机器模式 M-mode)**：功能极简，贴近裸机。它只负责提供底层陷阱处理 (Trap) 和 SBI 标准调用（比如内核想关机，必须向 OpenSBI 发送调用，因为内核没权限直接断电）。
 - **U-Boot (主管模式 S-mode)**：功能庞大，体系复杂。它包含了完整的网络协议栈、各种驱动（包含 Virtio 驱动）和文件系统解析器。它负责把内核从硬盘深处“拽”到内存里。

 #### 操作流程与启动挂载

 1. **制作 EXT4 硬盘镜像**：使用 `dd` 创建一个空文件，用 `mkfs.ext4` 格式化，然后把编译好的根文件系统和 Linux `Image` 内核文件统统拷贝进这个硬盘里。
 2. **U-Boot 点火序列**：在 QEMU 启动进入 U-Boot 命令行后，执行：
 ```bash
 virtio scan                              # 驱动探测：让 U-Boot 扫描挂载的 virtio 块设备
 ext4load virtio 0:0 0x84000000 /boot/Image # 读取内核：从第一块 virtio 硬盘的 ext4 分区中，把 Image 读入内存 0x84000000
 setenv bootargs "root=/dev/vda rw console=ttyS0" # 关键路标：告诉 Linux 你的真根文件系统在虚拟硬盘 /dev/vda 上
 booti 0x84000000 - $fdtcontroladdr        # 终极点火：跳转到内核地址，并传递设备树地址
 ```

 **挂载硬盘的 QEMU 参数：**
 ```bash
 ./qemu-system-riscv64 -M g233 \
     -bios default \
     -kernel /home/wang/work/qemutest/u-boot/u-boot.bin \
     -drive file=testdisk.ext4,format=raw,if=none,id=hd0 \  # 声明宿主机的硬盘文件作为后端驱动
     -device virtio-blk-device,drive=hd0 \                  # 声明前端虚拟设备：把 hd0 作为 virtio-blk 暴露给虚拟机
     -netdev user,id=net0 \
     -device virtio-net-device,netdev=net0 \
     -nographic
 ```
 **核心区别：** 这里我们去掉了 `-initrd`，取而代之的是 `-drive` 和 `-device`。我们把 U-Boot 作为了 `-kernel` 启动入口，由 U-Boot 去负责加载 Linux。当 Linux 启动后，它会根据传入的 `bootargs` 去挂载真正的硬盘设备 `/dev/vda`。至此，一个功能完整、支持持久化存储的虚拟计算机系统就搭建完毕了！

## 总结
 
 在这些天的学习中我收获了很多。首先是熟悉了 C 语言的高级用法和底层数据流转，这极大地帮助了我阅读并理解 QEMU 庞大 codebase 的逻辑。其次，我掌握了使用 Rust 进行跨语言硬件外设模拟的黑魔法，深刻理解了“软件如何抽象物理硬件”。最后，我通过宏观的系统级联，在自己开发的板子上跑通了 `OpenSBI -> U-Boot -> Linux 内核 -> 用户态文件系统` 的全套启动流程，弄懂了硬件、固件和操作系统之间是如何握手连接的。
 
 在目前的学习中我也认识到了自己的不足：对 Rust 的高级 FFI 特性掌握仍显生疏，有时过度依赖 AI 的辅助，且项目的总线支持尚不完美。在后续阶段，我计划完成部分 rust 建模实验通过完全独立的 Rust 编码来加深对外设建模的理解，并尝试使用具有自动发现特性的 PCIe 总线来对现有的 SysBus 架构进行重构升级。
