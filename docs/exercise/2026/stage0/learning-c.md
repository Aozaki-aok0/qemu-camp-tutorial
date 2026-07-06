# QEMU 训练营基础阶段 C 语言

基础阶段 C 语言练习仓库 [qemu_camp_basic_c](https://classroom.github.com/a/AgHjM77H)，整合了 OpenCamp 基础和进阶两个阶段的 C 题目，共 `40` 题。

GitHub Classroom 邀请链接：[https://classroom.github.com/a/AgHjM77H](https://classroom.github.com/a/AgHjM77H)

## 快速开始

### 0. 一键配置基础环境

如果你使用的是 Ubuntu / WSL2 Ubuntu 环境，可以先执行下面的命令，一次性安装做题所需的基础工具：

```bash
sudo apt update
sudo apt install -y git gcc g++ make gdb clang-format jq curl pkg-config
```

### 1. 进入目录

```bash
cd qemu_camp_basic_c
```

### 2. 查看可用命令

```bash
make help
```

### 3. 编译检查器并列出全部题目

```bash
make c-checker
make list
```

### 4. 检查单道题

可以使用编号，也可以使用完整题目名。

```bash
make check 01
make check 21_singly_linked_list_josephus
```

### 5. 查看提示

```bash
make hint 14
make hint 40_bloom_filter_bitmap
```

### 6. 检查全部题目

```bash
make check-all
```

### 7. 运行单道题程序

```bash
cd c_exercise
./run.sh 01_insert_sort
./run.sh 20_mybash
```

### 8. 启动持续检查

```bash
make watch
```

## 题库结构

### 基础信息

- 总题数：`40`
- 计分方式：每题 `5` 分，满分 `200` 分
- 题目来源：OpenCamp 基础阶段 + 专业阶段 C 题库整合

### 阶段划分

| 编号范围 | 阶段 | 说明 |
| --- | --- | --- |
| `01-20` | 基础阶段 | 数据结构、基础算法、字符串与文件处理、命令解释器 |
| `21-40` | 进阶阶段 | 链表、树、哈希、位图、线程安全、宏技巧、系统编程 |

### 题目主题分组

#### 01-10：基础算法与字符串

1. `01_insert_sort` - 插入排序
2. `02_merge_sort` - 归并排序
3. `03_quick_sort` - 快速排序
4. `04_linear_search` - 线性查找
5. `05_binary_search` - 折半查找
6. `06_stack_maze` - 栈解决迷宫问题
7. `07_queue_maze` - 队列实现广度搜索迷宫问题
8. `08_circular_queue` - 环形队列实现约瑟夫环问题
9. `09_word_counter` - 统计单词个数
10. `10_my_strcpy` - 字符串拷贝

#### 11-20：解释器、文件与工具实现

1. `11_command_interpreter` - 命令解释器
2. `12_student_management` - 学生信息管理
3. `13_universal_sorter` - 通用排序接口
4. `14_calculator` - 四则运算
5. `15_url_parser` - URL 参数解析器
6. `16_mysed` - 简单流处理器
7. `17_myfile` - ELF 文件头查看
8. `18_mywc` - 词频统计器
9. `19_mytrans` - 查字典翻译
10. `20_mybash` - 命令解释器项目

#### 21-30：链表、树与底层基础能力

1. `21_singly_linked_list_josephus` - 单链表约瑟夫环
2. `22_doubly_circular_queue` - 双向循环链表队列
3. `23_circular_linked_list_josephus` - 环形链表约瑟夫环
4. `24_prev_binary_tree` - 二叉树前序遍历
5. `25_counter_letter` - 排序二叉树字母统计
6. `26_hash_counter` - Hash 表词频统计
7. `27_asm_gcd` - 内联汇编求最大公约数
8. `28_operator_overflow` - 无符号运算溢出检测
9. `29_swap_endian` - 字节序转换
10. `30_debug_print` - 调试宏 `DEBUG_PRINT`

#### 31-40：工程能力与系统编程进阶

1. `31_event_handler` - 简单事件处理器
2. `32_container_of_macro` - `container_of` 宏实现
3. `33_garray_dynamic_array` - 动态数组
4. `34_protocol_header_parser` - 协议头解析器
5. `35_elf_info_parser` - ELF 信息查看工具
6. `36_lru_cache` - LRU 缓存淘汰算法
7. `37_bitmap_operations` - 位图操作
8. `38_thread_safe_ring_buffer` - 线程安全环形缓冲区
9. `39_strtok_r_thread_safe` - 线程安全字符串分割器
10. `40_bloom_filter_bitmap` - Bloom 过滤器

## 常用命令速查

```bash
# 在 qemu_camp_basic_c 目录执行
make help                 # 查看题库支持的全部命令
make c-checker            # 编译 C 语言检查器
make list                 # 列出全部题目及当前完成状态
make check 01             # 检查编号为 01 的练习题
make check 15_url_parser  # 检查指定名称的练习题
make hint 15              # 查看编号为 15 的题目提示
make check-all            # 检查全部练习题
make watch                # 监听文件变化并自动重新检查
make clean                # 清理检查器和构建产物
```

## 自动评测说明

仓库已接入 GitHub Actions。push 到主分支后会自动编译 `c-checker`、执行 `check-all`、汇总结果并回传成绩（需配置 OpenCamp secrets）。PR 只跑评测，不回传。

基础阶段 C 语言排行榜见：[C 语言基础阶段排行榜](../../../leaderboards/2026/basic/c.md)。

## 速览

```bash
cd qemu_camp_basic_c
make c-checker
make list
make check 01
make check-all
```
