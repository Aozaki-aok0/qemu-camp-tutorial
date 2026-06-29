# 基于勘智 K230 卫星星务计算单元的 QEMU 建模

!!! tip "项目简介"

    星务计算单元是人造卫星星务分系统的核心计算模块，完成遥测数据的采集和下传、星上网络管理、平台实践管理、整星安全等卫星的核心功能，并具备在轨程序注入的能力。基于中高端物联网芯片 Kendryte K230，RISC-V 开源的星务计算机将具有广阔的应用场景。本次任务专注于使用 K230 星务计算单元的硬件建模，将从 K230 的基本支持出发，直到能够支持星务系统基本安全模块的正常运转。

    ![](../../../image/qemu-k230-board.png)

!!! info "QEMU K230 上游补丁"

    K230 的 QEMU 板级支持已经合入上游。相关讨论见 [[PATCH v8 0/5] Add support for K230 board](https://lore.kernel.org/qemu-devel/cover.1781246408.git.chao.liu@processmission.com/)，合入后的官方文档见 [QEMU `k230` machine 文档](https://gitlab.com/qemu-project/qemu/-/blob/master/docs/system/riscv/k230.rst)。

    这组补丁由 Chao Liu 于 2026 年 6 月 12 日发送到 `qemu-devel` 和 `qemu-riscv` 邮件列表，在 QEMU 中新增了 `k230` machine，使其能够运行 U-Boot、OpenSBI 和标准 Linux kernel。当前上游实现支持 1 个 C908 little core、CLINT、PLIC、2 个 K230 WDT 和 5 个 UART。直接启动 Linux 的示例命令如下：

    ```shell
    $QEMU -M k230 \
          -kernel [Image] \
          -dtb [k230-qemu.dtb] \
          -initrd [rootfs.cpio.gz] \
          -nographic
    ```

    该 patch series 主要包含 5 个部分：

    1. `target/riscv`：添加 T-Head C908 / C908v CPU 支持。
    2. `hw/riscv`：添加 K230 board 的初始支持。
    3. `hw/watchdog`：添加 K230 WDT 初始模型。
    4. `tests/qtest`：添加 K230 watchdog 的 QTest 测试。
    5. `docs/system/riscv`：添加 `k230` machine 的官方文档。

    对本项目来说，已合入的 `k230` machine 提供了 K230 QEMU 建模的上游基线。后续 RustSBI 适配、外设模型补全、安全实验支撑等工作，应尽量基于该上游实现继续演进，并按 QEMU 社区规范整理 patch 和测试结果。

!!! note "项目方向"

    项目仓库：[gevico/qemu-camp-2026-k230.git](https://github.com/gevico/qemu-camp-2026-k230.git)

    1. RustSBI 适配 K230
        - 适配 K230 启动流程、内存布局和 DTB 传递。
        - 在 QEMU `k230` machine 下完成从 BootROM、RustSBI 到下一阶段 U-Boot / Linux 的启动验证。
        - 相关适配成果期望直接贡献到 [rustsbi/rustsbi.git](https://github.com/rustsbi/rustsbi.git)。
    2. 完善 K230 外设建模
        - 围绕 Timer、RTC、GPIO、I2C、SPI、PWM、SD/eMMC、Mailbox 等外设补充 QEMU 模型。
        - 按照 Issue 认领任务，补充 MMIO、IRQ / 中断、reset 行为、trace 支持和测试用例。
        - 优先实现 SDK 或系统软件会访问的寄存器与功能，从最小可用模型开始渐进完善。
    3. 面向星务安全模块的仿真支撑
        - 构建可观测、可注入、可验证的最小安全实验场景。
        - 通过 trace、QMP、GDB、QTest 等工具观察关键寄存器、事件、中断和 MMIO 访问行为。
        - 支持篡改关键数据或寄存器、触发 Watchdog 超时、模拟中断风暴或丢失、存储 / 通信异常注入等实验，并验证检测、响应与恢复流程。

!!! question "考核标准"

    1. 可运行代码：主要功能正确，能够在 K230 QEMU 环境中运行并完成对应方向的验证。
    2. 测试与验证：提供单元测试或集成测试，覆盖正常场景和必要的异常场景，保留可复现的验证日志。
    3. 工程质量：代码风格符合 QEMU / RustSBI 等相关项目规范，注释清晰，提交记录和 Issue / PR 进展可追踪。
    4. 进阶成果加分：性能优化、故障注入与恢复验证、自动化回归测试、整理 patch 并尝试向上游贡献。

!!! info "QEMU 上游"

    QEMU 相关代码贡献请参考 [QEMU Submitting a Patch](https://www.qemu.org/docs/master/devel/submitting-a-patch.html) 和 [QEMU Coding Style](https://www.qemu.org/docs/master/devel/style.html)，本项目按以下标准准备 patch：

    1. 基于 QEMU 当前 `master` 分支开发，避免基于旧版本提交无法合入的 patch。
    2. 将改动拆分为逻辑清晰的 patch series，每个 patch 都应能独立编译和验证；不要混入无关格式化、空白或重构改动。
    3. Commit message 使用 `subsystem: single line summary` 格式，说明改动原因；每个提交必须包含 `Signed-off-by: Your Name <email>`。
    4. 提交前运行 `scripts/checkpatch.pl <patchfile>`，并完成对应的构建、单元测试、QTest 或集成验证。
    5. 使用 `git format-patch` / `git send-email`、`b4` 或 `git-publish` 生成并发送邮件形式的 patch，不要以附件方式发送。
    6. Patch 发送到 `qemu-devel@nongnu.org`，并通过 `MAINTAINERS` 或 `scripts/get_maintainer.pl` 抄送相关维护者。
    7. 保持参与 review，按反馈修订后使用 `v2`、`v3` 等版本号重新发送，并在 cover letter 或 patch 注释中说明版本变化。

!!! info "本仓库贡献规范"

    本仓库用于任务认领、阶段性协作和训练营成果沉淀。贡献代码或文档时请遵循以下规范：

    1. 分支命名使用 `<type>/<scope>-<short-name>` 格式，例如 `docs/k230-rustsbi`、`feat/k230-gpio`、`fix/k230-uart`。
    2. Commit message 使用 `<type>(<scope>): <summary>` 格式，例如 `docs(k230): update project directions`、`feat(k230): add gpio model skeleton`。
    3. 常用 `type` 包括 `docs`、`feat`、`fix`、`test`、`refactor`、`ci`、`chore`；`summary` 使用简短英文描述，保持单行清晰。
    4. 代码类提交建议带上 `Signed-off-by: Your Name <email>`，可使用 `git commit -s` 自动添加。
    5. 一个 PR 聚焦一个任务或一个 Issue，避免把多个无关方向混在同一个 PR 中。
    6. 提交 PR 前同步最新 `main` 分支并解决冲突，确保本地构建、格式检查和相关测试通过。
