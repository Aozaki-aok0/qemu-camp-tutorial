本阶段包含四个实验方向，所有方向共用同一个实验仓库，均基于 RISC-V 架构。

## 实验方向

| 方向 | 测试框架 | 测试位置 | 满分 |
|------|---------|---------|------|
| [CPU 建模](cpu/index.md) | TCG 测题 | `tests/gevico/tcg/` | 100 |
| [SoC 建模](soc/index.md) | QTest | `tests/gevico/qtest/` | 100 |
| [GPGPU 建模](gpu/index.md) | QTest (QOS) | `tests/qtest/gpgpu-test.c` | 100 |
| [Rust 建模](rust/index.md) | QTest + 单元测试 | `rust/hw/i2c/src/lib.rs` + `tests/gevico/qtest/` | 100 |

## 获取实验仓库

所有方向共用同一个实验仓库 `qemu-camp-2026-exper`。

**第一步**，通过 GitHub Classroom 邀请链接加入实验（链接由讲师提供），系统会自动将仓库 fork 到组织下并赋予你 maintainer 权限。

!!! warning "注意"

    请通过 Classroom 邀请链接获取仓库，不支持手动 fork。

**第二步**，clone 仓库到本地：

```bash
git clone git@github.com:gevico/qemu-camp-2026-exper-<你的 github 用户名>.git
```

**第三步**，添加上游远程仓库，用于同步上游代码变更：

```bash
git remote add upstream git@github.com:gevico/gevico-classroom-qemu-camp-2026-exper-qemu-camp-2026-exper.git
git pull upstream main --rebase
```

!!! note "提示"

    使用 SSH 地址需要在 GitHub 上配置 SSH Key，请参考 [GitHub SSH Key 配置指南](https://docs.github.com/zh/authentication/connecting-to-github-with-ssh)。

## 环境搭建

参考各方向实验手册中的环境搭建说明。统一的编译配置命令：

```bash
make -f Makefile.camp configure
make -f Makefile.camp build
```

## 运行测试

```bash
make -f Makefile.camp test-cpu    # CPU 方向
make -f Makefile.camp test-soc    # SoC 方向
make -f Makefile.camp test-gpgpu  # GPGPU 方向
make -f Makefile.camp test-rust   # Rust 方向
make -f Makefile.camp test        # 全部方向
```

## 评分规则

- 每次推送到 `main` 分支，CI 自动编译、运行测试并计算得分
- 测试失败不会导致 CI 报错，只会降低得分
- 得分为 0 时不上传到排行榜

## 晋级项目阶段

完成以下两项即可进入项目阶段（ch3）：

1. **完成任一方向的专业阶段实验**（满分通过）
2. **贡献一篇专业阶段总结博客**到本站博客专栏

### 博客贡献流程

**第一步**，Fork 本文档仓库 [qemu-camp-tutorial](https://github.com/gevico/qemu-camp-tutorial)。

**第二步**，在 `docs/blogs/2026/` 目录下新建博客文件，文件命名格式：

```
qemu-camp-2026-<你的 GitHub 名>.md
```

例如 GitHub 用户名为 `zhangsan`，则文件名为 `qemu-camp-2026-zhangsan.md`。如果同一个 GitHub 账号需要提交多篇文章，可以在文件名后增加方向或主题后缀，例如 `qemu-camp-2026-zhangsan-soc.md`。

**第三步**，按照以下固定格式编写博客内容：

```markdown
# QEMU 训练营 2026 专业阶段总结

!!! note "主要贡献者"

    - 作者：[@你的 GitHub ID](https://github.com/你的 GitHub ID)

---

## 背景介绍

（个人背景、参加训练营的动机等）

## 专业阶段

（你选择的实验方向、实验过程中的学习记录与心得）

## 总结

（收获、感想、对后续学员的建议等）
```

然后更新 `mkdocs.yml` 文件，在博客专栏的 `训练营 2026` 下按阶段添加文章：

- 专业阶段总结放在 `专业阶段` 下
- 项目阶段文章后续合入后放在 `项目阶段` 下；当前暂无项目阶段博客文章
- 导航标题统一使用 GitHub 名，不再使用 `专业阶段总结 <GitHub 名>` 的格式
- 如果同一个 GitHub 账号下有多篇文章，将文章放到该 GitHub 名的下一级目录中

```
  - 博客:
    - 介绍页: blogs/index.md
    - 训练营 2026:
      - 专业阶段:
        - dingtao1: blogs/2026/qemu-camp-2026-dingtao1.md
        - <你的 GitHub 名>: blogs/2026/qemu-camp-2026-<github_name>.md
        - <已有多篇文章的 GitHub 名>:
          - CPU 方向: blogs/2026/qemu-camp-2026-<github_name>.md
          - SoC 方向: blogs/2026/qemu-camp-2026-<github_name>-soc.md
      - 项目阶段:
        - 暂无文章: blogs/2026/project-stage.md
```

!!! note "参考博客"

    - [dingtao1](../../../blogs/2026/qemu-camp-2026-dingtao1.md)
    - [LordaeronESZ（2025）](../../../blogs/2025/qemu-camp-2025-LordaeronESZ.md)

**第四步**，提交 Pull Request，PR 标题格式：

```
docs/blogs: add stage1 summary by <你的 GitHub 名>
```

审核通过后，博客将发布到本站博客专栏，晋级条件达成。
