# 训练营常见问答（FAQ）

!!! note "主要贡献者"

    - 整理：[@zevorn](https://github.com/zevorn)

本页汇总 QEMU 训练营 2026 导学阶段群聊中出现频率较高的问题与解答，便于新学员快速定位答案。问题来源为 QQ 群 `1032308510` 的值周答疑汇总，按四个板块归档共性议题。

!!! tip "如何使用这份 FAQ"

    - 遇到问题时，先按下面四个板块快速定位：环境搭建、OpenCamp 与 Classroom、专业阶段实验、训练营组织与答疑。
    - 答案中的 **Ref.** 指向讲义内对应章节或群内答疑时间，可按图索骥回到原文。
    - 若问题未收录或已过时，欢迎向 [`gevico/qemu-camp-tutorial`](https://github.com/gevico/qemu-camp-tutorial) 提交 PR 更新本文。

## 环境搭建

!!! question "Q01 · CNB 工作区每次打开都要重下源码？"

    **问题**：CNB 云原生开发环境每次打开都要重新下载 QEMU 源码吗？上次下载的代码、构建产物还在吗？

    **解答**：

    1. CNB 工作区目前不提供用户自定义的持久化存储卷，每次新开环境确实会丢失本地修改。
    2. 推荐做法：Fork `qemu-lab` 仓库，把 QEMU 源码作为 submodule 引入自己的仓库，每次启动自动拉取。
    3. 或直接使用训练营专业阶段实验仓库 `qemu-camp-2026-exper`，内置统一的 `make` 命令。
    4. 关键：所有修改必须及时 `git commit && git push` 到远端，关闭网页 IDE 即丢失。

    **Ref.** `docs/blogs/misc/qemu-cnb-dev.md` · `docs/tutorial/2026/ch0/qemu-dev-env.md#附录：CNB qemu-lab 云原生一键开发`

!!! question "Q02 · Mac 上能直接编译 QEMU 吗？"

    **问题**：Mac 上能不能直接编译 QEMU？我想用 Rust 写 QEMU 代码。

    **解答**：

    1. 不推荐在 macOS 上直接编译 QEMU — 虽官方支持，但工具链/依赖坑多，复现成本高。
    2. 推荐两条路：① `Ubuntu 22.04+` / `WSL2` 本地环境；② CNB 云原生开发环境（零配置）。
    3. QEMU 是 C 与 Rust 混合编译，Rust 支持由内置 `meson + bindgen` 完成，不需要额外做 wasm。
    4. 从零搭建开发环境请翻阅 [QEMU 编译开发环境搭建](qemu-dev-env.md)。

    **Ref.** `docs/tutorial/2026/ch0/qemu-dev-env.md#系统要求`

!!! question "Q03 · C 与 Rust 文档里的 target-list 不一致？"

    **问题**：C 语言和 Rust 开发环境搭建时配置的 target-list 架构不一样，需要统一吗？

    **解答**：

    1. 训练营最终只需要 `riscv64-softmmu` 这一个 target。
    2. Rust 环境文档里写的 `aarch64` / `x86_64` 组合，是 Rust 工具链示例的默认值，而非训练营要求。
    3. 建议统一为：`--target-list=riscv64-softmmu --enable-slirp`。
    4. 欢迎向讲义仓库 `gevico/qemu-camp-tutorial` 提交 PR 统一文档说明，成为贡献者。

    **Ref.** `docs/tutorial/2026/ch0/qemu-dev-env.md#配置编译选项`

!!! question "Q04 · CNB fork 时要求填写“组织”填什么？"

    **问题**：CNB fork 仓库时要求填组织，该填什么？

    **解答**：

    1. 在 CNB 上 fork 时，若需要组织，请创建一个属于自己的个人组织（例如以昵称 / GitHub ID 命名）。
    2. 直接 fork 到个人账号在部分场景下会有权限限制，放自建组织里后续协作也更方便。
    3. 注意：GitHub Classroom 邀请链接会自动 fork 到 `gevico` 组织下，不需要自己选。

    **Ref.** `docs/exercise/2026/stage1/index.md#获取实验仓库`

## OpenCamp 与 Classroom

!!! question "Q05 · Action 已跑，OpenCamp 为何零分？"

    **问题**：GitHub Action 都跑过了，OpenCamp 成绩为什么不显示？

    **解答**：

    1. 需要在 OpenCamp 个人中心绑定 GitHub 用户名 — 填 `username`，不是主页链接。
    2. 未绑定 GitHub 时，CI 跑再多次也不会上分。
    3. 绑定后需要再 push 一次触发 Action，或到 Actions 页面手动 Re-run。
    4. 仍然 0 分时：确认 CI 真的绿了，并检查是否生成 `test_results_summary.json`。

    **Ref.** `docs/exercise/2026/stage0/index.md` · 群内 FAQ

!!! question "Q06 · Classroom 邀请链接 500 错误怎么办？"

    **问题**：Classroom 邀请链接点了之后 500 Internal Server Error / something went wrong。

    **解答**：

    1. GitHub Classroom 偶发性故障，通常等 1–5 分钟刷新即可恢复。
    2. 若之前误取消了邀请导致无法再次进入，请联系讲师重新下发邀请链接。
    3. 进不去 Classroom 时可以先到 <https://github.com/orgs/gevico/repositories> 用自己的 GitHub ID 搜索仓库，确认是否已经生成。

    **Ref.** 群内通知（04-10 15:25）

!!! question "Q07 · OpenCamp 的 secret 在哪里获取？"

    **问题**：OpenCamp 的 secret 怎么获取？

    **解答**：

    1. 不需要自己配 secret — Classroom 给你 fork 的仓库里 CI 已经配置好。
    2. 直接 `git push` 到自己的仓库即可自动评分。
    3. 如果确有手动需要：OpenCamp 个人中心有 API Token 入口，但训练营流程用不到。

    **Ref.** 群内回答（04-10 12:54）

## 专业阶段实验

!!! question "Q08 · 四个方向都必须做吗？Rust 呢？"

    **问题**：专业阶段是选做吗？四个方向都要做吗？Rust 项目必须做吗？

    **解答**：

    1. 专业阶段共 `4` 个方向：CPU、SoC、GPGPU、Rust；选择任一方向满分通过即可晋级。
    2. 鼓励多方向尝试，但不是必须。
    3. 进入项目阶段的条件：① 任一方向满分；② 贡献一篇总结博客。
    4. 博客路径：Fork `qemu-camp-tutorial` → `docs/blogs/2026/qemu-camp-2026-<你的 GitHub 名>.md` → 在 `mkdocs.yml` 的 `训练营 2026 / 专业阶段` 下用 GitHub 名作为导航标题 → 提交 PR。

    **Ref.** `docs/exercise/2026/stage1/index.md#晋级项目阶段`

!!! question "Q09 · git pull upstream 报 multiple branches？"

    **问题**：`git pull upstream main --rebase` 报错 _Cannot rebase onto multiple branches_。

    **解答**：

    1. 远程仓库地址错了，请使用 `gevico/qemu-camp-2026-exper`（旧地址/克隆路径可能指向 Classroom 自动生成的长名仓库）。
    2. 正确命令：`git remote add upstream git@github.com:gevico/qemu-camp-2026-exper.git`（讲义已更新）。
    3. 第四步非必须，本地能 build/test 即可，后续需要同步上游修复时再执行。
    4. 如仍报错，先 `git branch -a` 确认当前 main 分支是否存在，再重试 rebase。

    **Ref.** `docs/exercise/2026/stage1/gpu/gpu-exper-manual.md` · 群内答疑（04-14 19:40）

!!! question "Q10 · Ubuntu 20.04 能编译 GPU 实验吗？"

    **问题**：GPU 实验编译报错，Ubuntu 20.04 能用吗？是否只能用 CNB？

    **解答**：

    1. 官方推荐 `Ubuntu 22.04 LTS` 及以上。20.04 上 glib / pixman 版本偏老，容易导致 meson 报错。
    2. GPU 方向暂时没有官方 CNB 镜像，需要自己构建环境。
    3. 可以用 docker 起一个 `ubuntu:24.04` 容器，按 `gpu-exper-manual.md` 的依赖清单安装。
    4. 环境搞通后欢迎把流程补充到讲义仓库，成为新的贡献者。

    **Ref.** `docs/exercise/2026/stage1/gpu/gpu-exper-manual.md#环境搭建`

!!! question "Q11 · build 目录下测题 stdout 不显示？"

    **问题**：build 目录下测题的 stdout 都看不见，怎么让它输出？

    **解答**：

    1. 批量跑测时 stdout 被重定向到 log 文件，默认不在终端打印。
    2. 在 `build/tests/gevico/` 下会有 log / out 文件，`cat` 即可查看。
    3. 单独调试某题时，直接用 `qos-test -p 路径` 单独运行，终端会实时输出。
    4. 这是一个优化点 — 欢迎提 PR 让单题调试默认打印 stdout。

    **Ref.** `docs/exercise/2026/stage1/gpu/gpu-exper-manual.md#测评验收`

## 训练营组织与答疑

!!! question "Q12 · 训练营的时间线、阶段安排？"

    **问题**：训练营的时间线、阶段安排是怎样的？

    **解答**：

    1. 共 16 周：`2026-04-05` 开营，`2026-08-09` 结营。
    2. `04/06 – 04/26` 导学阶段。
    3. `04/27 – 05/10` 基础阶段 · `05/11 – 06/14` 专业阶段。
    4. `06/28` 选题会 · `06/29 – 08/08` 项目阶段。
    5. 每周四 20:00–20:30 在线交流会，腾讯会议 `449-3341-6333`。

    **Ref.** `docs/tutorial/2026/ch0` · 群内日程

!!! question "Q13 · 项目阶段当本科毕设够吗？"

    **问题**：项目阶段的项目当本科毕设够吗？有什么参考？

    **解答**：

    1. 够用 — 去年已有多位学员以项目阶段成果作为毕设 / 研究课题。
    2. 参考：开营仪式回放 + 《2026 年课程内容介绍：四个阶段（六个实验、四个项目）》。
    3. 进入项目阶段会有专属导师带队。
    4. 方向包括：AI 加速硬件建模、CXLMemSim、hetGPU、machina（Rust QEMU 重写）等。

    **Ref.** [bilibili BV1CSSQByEDB](https://www.bilibili.com/video/BV1CSSQByEDB) · <https://qemu.gevico.online/tutorial/2026/ch3>

!!! question "Q14 · 如何把博客推送到讲义网站？"

    **问题**：如何贡献博客？如何推送到讲义网站？

    **解答**：

    1. Fork `gevico/qemu-camp-tutorial` 仓库。
    2. 在 `docs/blogs/2026/` 新建 `qemu-camp-2026-<你的 GitHub 名>.md`；同一账号多篇文章可增加方向或主题后缀。
    3. 按模板填写：背景介绍 / 专业阶段 / 总结；并同步更新 `mkdocs.yml` 导航。导航中 `训练营 2026` 分为 `专业阶段` 和 `项目阶段`，专业阶段文章标题统一使用 GitHub 名；同一账号多篇文章放在该 GitHub 名的下一级目录。当前项目阶段暂无博客文章。
    4. PR 标题：`docs/blogs: add stage1 summary by <你的 GitHub 名>`。
    5. 审核合入后自动上站：<https://qemu.gevico.online/blogs/>。

    **Ref.** `docs/exercise/2026/stage1/index.md#博客贡献流程`

!!! question "Q15 · 导学阶段到什么时候？应该重点掌握什么？"

    **问题**：导学阶段是到 26 号吗？这个阶段重点应该掌握哪些内容？

    **解答**：

    1. 导学阶段按课程日程到 `04/26`。
    2. 建议结合导学阶段视频教程学习，先建立整体认知。
    3. 可以提前对照项目阶段看自己想做的方向，前几个阶段和项目阶段是对应衔接的。
    4. 优先掌握：开发环境、课程节奏、QEMU 学习路径与项目方向选择。

    **Ref.** `docs/tutorial/2026/ch0` · 群内答疑

!!! question "Q16 · 提示失去 assignment 仓库权限怎么办？"

    **问题**：出现 `You no longer have access to your assignment repository. Contact your teacher for support`，是要重新邀请吗？

    **解答**：

    1. 先检查邮箱里是否有 Classroom 邀请或权限变更通知。
    2. 到 `gevico` 组织下检索自己的 GitHub ID，确认仓库是否已成功创建。
    3. 若仓库不存在或权限异常，再联系讲师协助重新邀请或修复权限。

    **Ref.** 群内答疑

!!! question "Q17 · 我们项目阶段什么时候截止？"

    **问题**：项目阶段截止时间是什么时候？

    **解答**：

    1. 项目阶段整体截止到 `8` 月（以课程最终通知为准）。
    2. 建议按周推进里程碑，避免在截止前集中堆积任务。

    **Ref.** `docs/tutorial/2026/ch3` · 群内答疑

!!! question "Q18 · 专业阶段有单独的群吗？"

    **问题**：专业阶段有单独的群吗？

    **解答**：

    1. 前三个阶段（导学、基础、专业）都在当前大群统一答疑。
    2. 进入项目阶段后会有单独项目群。

    **Ref.** 群内答疑

!!! question "Q19 · 还没确定方向，哪个方向更容易上手？"

    **问题**：还没确定方向，哪个方向相对简单？

    **解答**：

    1. 通常建议先看 `CPU` 和 `SoC` 两个方向，入门门槛相对更低。
    2. `CPU` 方向主要聚焦指令模拟。
    3. `SoC` 方向主要聚焦外设建模与 CPU 集成。
    4. 建议先选一个方向跑通完整流程，再决定是否扩展到其他方向。

    **Ref.** `docs/exercise/2026/stage1` · 群内答疑

!!! question "Q20 · 专业阶段实验是只能考一次吗？"

    **问题**：实验可以无限刷吗，还是只有一次通过机会？

    **解答**：

    1. 专业阶段实验可以反复提交，不限制尝试次数。
    2. 建议每次提交前先本地自测并记录问题，迭代效率更高。

    **Ref.** `docs/exercise/2026/stage1` · 群内答疑

!!! question "Q21 · 做完基础阶段题目后能直接做专业实验吗？"

    **问题**：做完基础阶段题目之后，可以直接上手专业阶段实验吗？感觉中间还有点没打通。

    **解答**：

    1. 基础阶段题目主要帮助你掌握语言与基础编程能力。
    2. 进入专业实验前，还需要系统学习课程讲义与视频中的 QEMU 基础知识。
    3. 如果只刷题不看讲义，常见现象就是“会写代码但不了解 QEMU 机制”。
    4. 建议按“讲义/视频 -> 小实验 -> 专业题目”的节奏衔接。

    **Ref.** `docs/tutorial/2026/ch1` · `docs/tutorial/2026/ch2` · 群内答疑

!!! question "Q22 · 光看讲义还是迷茫，应该怎么办？"

    **问题**：我光看讲义还是容易迷茫，应该怎么办？

    **解答**：

    1. 刚开始面对大型项目时感到迷茫是正常现象。
    2. 建议先挑一个更简单、边界清晰的小任务作为入口。
    3. 先跑通一个最小闭环（环境、构建、调试、提交），再逐步扩展难度。
    4. 遇到卡点及时在群里提问，用反馈缩短摸索时间。

    **Ref.** `docs/tutorial/2026/ch0` · 群内答疑

!!! question "Q23 · 如何通过学习本课程提升就业竞争力？"

    **问题**：如何才能通过学习本课程来让自己更好地转行到相关行业，或者说怎么让自己的经历更有含金量？

    **解答**：

    1. 仅学习本课程本身无法直接帮助你找到一份优秀的工作。
    2. 更重要的是：编写符合规范的优质代码，并努力将你的代码贡献到优秀的开源仓库上游。
    3. 参与开源项目、积累实际贡献记录，是提升个人含金量的一条有效途径。

    **Ref.** 群内答疑
