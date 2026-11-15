# 把这份项目放进 GitHub：手册评估 + 本项目的落地步骤

> 参照物：`从零开始完整操作手册.md`（v2.1，三机接力 + 私有仓库 + WorkBuddy 开工/收工）。
> 本文做两件事：**① 逐条判断哪些对本项目多余、哪些手册没覆盖；② 给出可以直接照着敲的落地步骤。**
> 已随本文落地的东西：`.gitignore`、`.gitattributes`、`AGENTS.md`、`STATE.md`、首次 commit。

---

## 一、先说结论

手册的**骨架是对的**（单一远端 `main`、开工先验收、收工必回读、同一时间只有一台机器写代码）。
但它假设的是一个**有环境变量、有依赖安装、有多台机器同时接力**的典型 Web 项目。
我们这个是**单机、无依赖、单 exe 交付、还带 100MB 二进制**的项目，直接照抄会带来三个负担：
每次提交都要处理一堆不该进库的文件、`.env` 那套完全空转、以及"多机接力"里大部分步骤用不上。

按下面的裁剪版走，**一次性动作从 9 件压到 5 件**，日常还是两个词：「开工」「收工」。

---

## 二、手册里「对本项目多余」的部分

| 手册位置 | 内容 | 为什么多余 | 建议 |
|---|---|---|---|
| 4.6 / 5.5 / 第六阶段 | 每台 `.env` + 密码管理器取值 | 本项目**没有任何密钥**：不连数据库、不调云 API、不读 token。唯一的"凭据"是 GitHub 自己那把 key | 整段删除。真要放什么私密配置，就放 `%LOCALAPPDATA%\adb_Tool\`，不进仓库 |
| 1.3–1.4 | 每台生成一把 SSH key | 逻辑对，但**本项目只有 1~2 台机器**（公司/家里），"每台一把"照做即可，不需要三把 | 保留，删掉 B/C 的说法 |
| 第七阶段 | A→B→C→A 接力验证 | 单机项目没有"接力"这回事 | 降级成「换机验证一次」：在公司机 `git pull` 能编译能过门禁即可 |
| 第十阶段 10.2 | `git bundle` 月度冷备 | 我们本来每次发版就出三个 zip（`release.py`），冷备天然存在 | 删除；改成"把成品 zip 留一份在移动硬盘" |
| 附录 B | GitHub 切中文 | 与开发无关 | 删除 |
| 附录 C | 打印打勾表 | 一次性动作只剩 5 件，不需要表 | 删除 |
| 3.1 | 复制"总提示词"给 AI | 我们的规则已经写成 `AGENTS.md` 入库了，AI 读文件比读提示词可靠 | 保留概念，改成"让 AI 先读 `AGENTS.md` + `STATE.md`" |

---

## 三、手册「没覆盖、但本项目必须有」的部分（这是重点）

### 1. 100MB 级二进制会让仓库直接废掉

`ffmpeg.exe` 105MB、`dist/` 104MB、`release/` 41MB。Git 一旦把这些收进历史，**永远删不掉**（只能重写历史），
clone 一次要几百 MB，push 会超时。

→ 已用 `.gitignore` 排除，并且明确：**ffmpeg 只在出包时拷进 dist，不进 Git**。
换机器后第一次构建前，需要手动把 `ffmpeg.exe` 放到 `adb_log_gui/` 下（成品包里有）。

### 2. `ui.html` 是"生成物"，但它必须入库 —— 而且要和源文件一起入

`ui.html` 里 4 段代码（V14~V17）是由 `_v14..v17.js/.css` 注入拼出来的。

- 只入 `ui.html` → 下一个人改不动（源文件不在）；
- 只入源文件 → 下一个人 clone 下来直接跑，页面是旧的（注入没跑）。

→ 规则写进 `AGENTS.md` §3：**两者都入库**；改前端只能改 `_vNN`，然后跑注入，再 commit（两者一起）。

### 3. 测试会生成 800KB×N 的 HTML，属于生成物

`377/test_*.html` 每次跑测试都从 `ui.html` 重新生成，加起来 15MB+。

→ `.gitignore` 里 `377/test_*.html`，只入库 `377/*.py` 和 `377/_check_ui.js`。

### 4. 门禁就是手册里那"三段验收"，而且只需要一条命令

手册要求每次开工做「装依赖 → 构建 → 测试」三段。本项目：

| 手册的三段 | 我们的对应 |
|---|---|
| 装依赖 | **没有依赖**（不用包管理器，WebView2 DLL 随包） |
| 构建 | `cmd //c "_cs\\build.bat" < /dev/null` + `NO_PAUSE=1 cmd //c "adb_log_gui\\build_gui.bat"` |
| 测试 | `python verify_all.py`（26 项） |

→ `STATE.md` 的「现在能跑吗」那张表就是验收基线，收工前把数字更新掉。

### 5. CRLF / 编码：Git 默认配置会把这个项目改坏

- `.bat` 必须是 **CRLF + 全 ASCII**（`build_gui.bat` 带 `/codepage:65001`，中文注释会被当源码读）；
- 如果本机 `core.autocrlf=true`，checkout 会把 `.py/.js/.md` 也改成 CRLF，diff 全是噪音。

→ 已用 `.gitattributes` 逐类钉死（`.bat` = CRLF，源码 = LF，二进制 = binary），不依赖本机配置。

### 6. 运行态 ini 会让工作区天天 dirty

程序运行时会往 `adb_log_export.ini` 写 `accent=` / `prefs=` / 设备信息。根目录那份是**运行产物**，
`adb_log_gui/adb_log_export.ini` 才是**构建用模板**。

→ `.gitignore` 忽略根目录那份，保留 `adb_log_gui/` 那份。提交前 `git status` 不该出现 ini。

### 7. 中文文件名与中文路径

`docs/用户使用手册.md`、`参考-Edge主题设置与同类实现.md` 都是中文名；本机用户名也是中文（`C:\Users\李亦`）。

→ 建议一次性设：`git config core.quotepath false`（否则 `git status` 里显示成 `\344\275\240...`）。
路径本身 Git 支持，但 `.bat` 里不要拼中文路径，一律 `%~dp0`。

### 8. **GitHub 已经不支持用账号密码 push**（这条最要紧）

手册 1.5 的退路 B 写的是"HTTPS + token"，是对的；但很多人会误以为能用账号密码。
现实是：**2021-08-13 起 GitHub 移除了密码认证**，`git push` 用密码会直接 403。

所以只有两条路：

| 方式 | 要不要动手 | 适合谁 |
|---|---|---|
| **SSH key**（推荐） | 本机生成一对 key → 把**公钥**贴到 GitHub | 自己的机器，长期用 |
| HTTPS + PAT | 网页生成 Fine-grained token → 当密码用 | 临时机器 / 公司电脑不让加 key |

> 账号密码只在**网页登录**时用，`git` 命令用不了。这不是配置问题，是平台策略。

---

## 四、裁剪后的落地步骤（5 步，一次性）

> 前置：`git --version` 有输出。全部在 **Git Bash** 里敲。

### 步骤 1：建私有空仓库

网页 → https://github.com/new

- Repository name：`Adb_Tool`（或 `adb-tool`）
- **Private**（必选）
- **不要**勾 README / .gitignore / license（勾了会先有一个 commit，push 时要先 pull 合，麻烦）

### 步骤 2：本机生成 SSH key 并贴到 GitHub

```bash
ssh-keygen -t ed25519 -C "liyiadbtool-adbtool"     # 一路回车
cat ~/.ssh/id_ed25519.pub                          # 复制整行
```

网页 → 头像 → Settings → SSH and GPG keys → New SSH key →
Title 填 `工作机`，Key type 选 **Authentication Key**，粘贴，Add。

验证：

```bash
ssh -T git@github.com
# 期望：Hi liyiadbtool! You've successfully authenticated...
```

> 22 端口被封时（公司网络常见）改走 443，见手册 1.5 退路 A，地址不用改。

### 步骤 3：把本目录变成仓库并首次提交

**已经做完了**（本文落地时执行过）：

```bash
git init -b main
git config core.quotepath false
git config user.name  "liyiadbtool"
git config user.email "<你的 GitHub 邮箱>"
git add -A
git commit -m "chore: 首次入库（A17 基线，门禁 26 项 0 失败）"
```

检查一下**有没有误入大文件**：

```bash
git count-objects -vH        # size-pack 应该在 20MB 以内
git ls-files | grep -Ei "\.exe$|\.zip$|ffmpeg"   # 期望：无输出
```

### 步骤 4：接远端并推

```bash
git remote add origin git@github.com:liyiadbtool/Adb_Tool.git
git push -u origin main
```

### 步骤 5：换机器（第二台）的标准动作

```bash
git clone git@github.com:liyiadbtool/Adb_Tool.git
cd Adb_Tool
# 把 ffmpeg.exe 放进 adb_log_gui/（不进 Git，从成品包或旧机器拷）
cmd //c "_cs\\build.bat" < /dev/null
NO_PAUSE=1 cmd //c "adb_log_gui\\build_gui.bat"
python verify_all.py          # 必须 26 项 0 失败才算这台机器能用
```

---

## 五、日常怎么用（还是两个词）

| 你说 | AI 该做的 |
|---|---|
| **开工** | `git pull` → `git status` → 跑 `python verify_all.py` → 报"基线是否仍然成立"→ 给出本轮计划 |
| **收工** | 跑门禁 → 更新 `STATE.md` 的三个数字 → `git add -A` → 贴出拟提交清单 → `git commit` → `git push` → **`git log origin/main -1` 回读确认** |
| **状态** | 只回一张表：门禁数字 / 未提交文件 / 远端落后几提交 |

三条铁律（沿用手册，仍然有效）：

1. 离开任何一台机器前，必须「收工」并看到 commit 短号 + 回读确认。
2. 门禁没通过不许开始写新功能。
3. 同一时间只有一台机器在写。

---

## 六、本项目的"完成定义"（补手册的空白）

一次改动算完成，必须同时满足：

1. `python verify_all.py` **26 项 0 失败**；
2. 新增的 id / 按钮 / 消息 kind 已在 `_gate_invariants.py` 的 `A1x_ADDS` 登记；
3. 若改了需求落点 → `_check_features.json` 有对应条目（含锚点与测试文件）；
4. 若改了可见行为 → `docs/功能清单.md` / `docs/UI-RESKIN-INVENTORY.md` / `docs/用户使用手册.md` 三份同步；
5. `STATE.md` 的验收基线数字是新的。

> 这 5 条比手册的"装依赖/构建/测试"更严格，但**执行成本只有一条命令**，这就是这个项目能保持
> 26 项门禁全绿的原因。

---

## 七、还没做、要不要做由你定

| 项 | 说明 |
|---|---|
| GitHub Actions | 可以在 push 时自动跑 `verify_all.py`。但 Windows runner 要装 .NET Framework 4.0 csc，跑一次 6~8 分钟，私有仓库每月有免费额度上限。**建议先不接**，本机门禁已经够快（约 3 分钟） |
| Release 附件 | 每次出包把三个 zip 传到 GitHub Release，比塞进仓库历史干净得多。**建议接**，`release.py` 之后加一步 `gh release create` 即可 |
| Issue 模板 | 如果以后要把禅道的 bug 同步过来，可以先建两个模板（Bug / 需求）。现在没必要 |
