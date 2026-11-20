# WORKFLOW.md — 开工 / 收工 操作规范

> 本文件是 `AGENTS.md` §0 的执行细则。
> **所有拉取本仓库的设备、所有人、所有 AI，都必须遵守这套规则。**
> 一句话版本：**开工只拉，收工只推，中间才是干活。**

---

## 1. 三个阶段的边界

| 阶段 | 触发词 | 允许做的事 | 绝对不许做的事 |
|---|---|---|---|
| **开工** | 「开工」 | `git fetch` / `git status` / `git pull --ff-only` | 改代码、编译、跑测试、提交、推送 |
| **干活** | 提需求 / 「实现 XXX」 | 改代码、编译、跑测试、出包 | 无（按 `AGENTS.md` 的硬约束执行） |
| **收工** | 「收工」 | `git add` / `git commit` / `git push` | 再改任何代码、强推、提交运行态污染 |

用户如果明确限定范围（例如"开工，仅拉取代码不做任何修改"），
**以用户当场说的为准**，字面执行，不要自作主张补充动作。

---

## 2. 开工标准流程

### 2.1 步骤

```bash
cd <仓库根目录>

# ① 先看本地状态：有没有未提交的改动？
git status -s
git log --oneline -3

# ② 拉取远程引用（不合并，安全）
git fetch origin

# ③ 看清楚差多少
git rev-list --left-right --count origin/main...HEAD
#   输出 "0 0"        = 已完全一致
#   输出 "N 0"        = 远程领先 N 条，需要快进
#   输出 "0 M"        = 本地有 M 条远程没有的提交（有分叉，停下问人）
#   输出 "N M"        = 双方都有新提交（有分叉，停下问人）

# ④ 快进到远程（无本地改动时）
git pull --ff-only origin main
```

### 2.2 遇到本地有未提交改动怎么办

**不要直接 `git reset --hard`。** 先判断这些改动是什么：

| 情况 | 处理 |
|---|---|
| 是程序跑出来的运行态（`adb_log_gui/adb_log_export.ini` 的 theme/accent/prefs） | `git checkout -- <文件>` 丢弃，再拉取 |
| 是上一轮忘了提交的成果 | **停下来问用户**：要保留就先 commit（或 stash），不要覆盖 |
| 是构建产物（`dist*/`、`*.exe`） | 本就不该进 Git，确认 `.gitignore` 已覆盖 |

### 2.3 开工后必须汇报

只汇报事实，不要顺手改任何东西：

- 当前 HEAD 短哈希 + 提交时间 + 提交标题
- 与 `origin/main` 是否一致（`0 0` 即一致）
- 工作区是否干净
- 如果领先/落后，列出差异提交清单

---

## 3. 收工标准流程

### 3.1 收工前自检（干活完成时）

```bash
# 编译（自动化环境必须加 NO_PAUSE，否则卡在 pause 上）
# Windows: set NO_PAUSE=1 && adb_log_gui\build_gui.bat

# 门禁
python verify_all.py --fast
```

两者都绿才能收工。门禁红灯不许提交。

### 3.2 提交前清理（关键）

```bash
git status -s
```

逐个确认改动文件，剔除以下三类：

1. **运行态污染**：`adb_log_gui/adb_log_export.ini`
   程序运行会改写 `theme=` / `accent=` / `prefs=`（含设备号与强调色）。
   那只是本机偏好，不是成果 → `git checkout -- adb_log_gui/adb_log_export.ini`
2. **构建产物**：`adb_log_gui/dist/`、`release/`、`*.exe`、`*.zip`
   已被 `.gitignore` 忽略，若出现在 `git status` 说明误加了，撤掉。
3. **临时脚本**：自己调试用的 `_tmp*.py`、截图、日志 —— 不要提交。

### 3.3 提交与推送

```bash
git add -A
git commit -m "feat(<范围>): <做了什么>；<附带影响>"
git push origin main
```

提交信息规范（延续本仓库既有风格）：

- `feat(投屏): ...` 新功能
- `fix(门禁): ...` 修缺陷
- `chore: ...` 清理、文档
- `docs: ...` 纯文档
- `perf: ...` 性能
- `refactor(...): ...` 重构（行为不变）

### 3.4 改动的连带更新（漏了门禁会红）

| 改了什么 | 必须同步 |
|---|---|
| 新增/改名分组、卡片 | `377/_test_ui_behavior.py`、`377/_check_ui.js`、`_check_a14.py` 里对应的数量/名称断言 |
| 新增命令（C# 内置 `:`） | `_cs/Prefix.cs` 路由 + `ui.html` 卡片 + 门禁不变量 |
| 新增命令（ini） | `cmds.ini` **和** `adb_log_gui/cmds.ini`（打包副本）两份都要改 |
| 可见交互变化 | `docs/用户使用手册.md` + 对应测试断言 |

> `cmds.ini` 有两份：根目录那份是开发用，`adb_log_gui/cmds.ini` 是打包进 exe 的副本。
> **只改一份 = 用户拿到的包没变化。** 改完必须 `cp cmds.ini adb_log_gui/cmds.ini`。

---

## 4. 常见错误清单

| 错误 | 后果 | 正确做法 |
|---|---|---|
| 开工时 `git reset --hard` 不看 status | 上一轮成果被静默丢弃 | 先 `git status -s`，有改动先问 |
| 收工把 `adb_log_export.ini` 提交了 | 别人的主题/强调色被你的偏好覆盖 | 提交前 `git checkout --` 该文件 |
| 只改根目录 `cmds.ini` | 打出来的包还是旧命令 | 同步到 `adb_log_gui/cmds.ini` |
| 改名/改数量却没改测试断言 | 门禁红，别人拉下来第一件事就是修红 | 按 3.4 连带更新 |
| 收工后又"顺手改一点" | 改了没提交、没验证，仓库处于脏状态 | 收工即收工，改动留到下一轮 |
| `git push --force` | 覆盖别人的提交 | 禁止；有冲突就合并解决 |

---

## 5. 给 AI 的提示词模板

新设备 / 新 AI 接入时，把这段直接贴给它：

```
你在维护 Adb_Tool 仓库。先读 AGENTS.md 和 WORKFLOW.md，遵守以下纪律：

1. 我说「开工」= 你只执行 git fetch + 对比 + 快进到 origin/main，不做任何修改、不编译、不跑测试。
   做完汇报：当前 HEAD、与远程是否一致、工作区是否干净。
2. 我说「收工」= 你只执行 git add + commit + push，不再改任何代码。
   提交前必须检查并丢弃 adb_log_gui/adb_log_export.ini 的运行态改动。
3. 中间的时段才是干活：改代码 → 编译 → 跑门禁 → 交付。
4. 硬约束见 AGENTS.md（C#5 语法、不引包、ui.html 分层注入、红线），不许违反。
```

---

## 6. 版本记录

| 日期 | 变更 |
|---|---|
| 2026-11-20 | 文件建立。确立「开工只拉、收工只推」纪律，写入 AGENTS.md §0 |
