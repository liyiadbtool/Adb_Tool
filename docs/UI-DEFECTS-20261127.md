# 缺陷记录（2026-11-27）

> 仅记录，未改代码。每条含：现象 / 设备实测 / 根因判断 / 影响 / 修法建议。

---

## D5 车机「车型 / SOC 版本 / MCU 版本」三项整体错位一格

**现象**：诊断页「车机」卡片三行值对不上标签。

截图显示：

```
车型        GAC_T68_IDC_S1B4_261126_1258F_D
SOC 版本    T68_IC2015_01_21.777_261125_R
MCU 版本    12
```

**设备实测**（当前连接设备 `b09acfa2`，逐条 `getprop`）：

| 属性 | 实际值 | 应属字段 |
|---|---|---|
| `sys.product.gacvehicleplatform` | `110` | ？（见“待确认”） |
| `ro.product.version.short_name` | `GAC_T68_IDC_S1B4_261126_1258F_D` | 车型 |
| `sys.vehicle.mcu.version` | `T68_IC2015_01_21.777_261125_R` | MCU 版本 |
| `ro.build.version.release` | `12` | Android 版本 |
| `ro.product.version.tier1.hw.platform` | `GACNE_8295_DESAY` | ？（SOC 平台） |

**对照结论：三行整体上移了一格**

```
界面上「车型」显示的是 keys[1]（short_name）
界面上「SOC 版本」显示的是 keys[2]（mcu.version）
界面上「MCU 版本」显示的是 keys[3]（ro.build.version.release = 12）
```

`12` 正好是 Android 版本值 —— 这是错位一格的直接证据（不是“MCU 真的返回 12”）。

**根因判断（高置信）**

`CarInfo.LoadCarInfo()` 用 `##i` 标记切分：

```csharp
sb.Append("echo '##").Append(i).Append("'; ");
sb.Append("getprop ").Append(CAR_KEYS[i]).Append("; ");
...
string[] parts = ParseMarkedTextN(all, CAR_TOTAL + 1);
for (int i = 0; i < CAR_TOTAL; i++) CAR_VALS[i] = parts[i];
```

若 `ParseMarkedTextN` 把**第一个标记之前的空串**算作 `parts[0]`，
则 `CAR_VALS[i] = parts[i]` 整体前移一格，与现象完全吻合。
（同样的风险点：`echo` 输出的 `\r\n` 未 trim 时，值会带尾随 `\r`。）

**待确认（需要业务口径）**

1. 「车型」到底取 `short_name` 还是 `gacvehicleplatform`？
   - `short_name` = `GAC_T68_IDC_S1B4_261126_1258F_D`（看着像车型+日期版本）
   - `gacvehicleplatform` = `110`（看着像平台代号）
2. 「SOC 版本」取哪个？
   - 候选 `ro.product.version.tier1.hw.platform` = `GACNE_8295_DESAY`
   - 或 `ro.soc.model` / `ro.board.platform`
3. 若确认车型=SOC 用同一条 `short_name`，则需拆成两个字段分别取。

**影响范围**

- 诊断页「车机」卡片三行全部错误
- 顶栏车型显示（`DEV_PLAT/DEV_SOC` 按索引取 `CAR_VALS[0]/[1]`）同样错位
- 「环境诊断 → 对比」里 SOC/MCU 参与比较，结论不可信

**修法建议（待确认后再动）**

```
① 先修 ParseMarkedTextN 的下标基准（parts[0] 应为 key0 的值）
② 逐个字段 trim() 去掉 \r
③ 按确认后的口径调整 CAR_KEYS 与 CAR_LABELS 的对应关系
④ 加一条自检：解析后每个值必须“不像属性名、不含 ##”，否则判失败
```

**优先级**：高（信息全错，且会误导排查结论）

---

## D6 文件页右侧「设备」读不到目录：显示「设备 0 项 / 目录不存在: /」

**现象**：文件 → 数据互传，右侧设备栏空白，提示「目录不存在: /」；标题栏写「设备 0 项」。

**设备实测**（同一台 `b09acfa2`，刚从 PC 侧执行）：

```
adb shell "ls -la '/' 2>&1"      → 正常输出 36 项（acct/apex/avm_config/bin/…）
```

说明 **`ls` 命令本身没问题**，问题不在列目录实现。

**判断：不是“目录不存在”，是程序没识别到设备**

```
"设备 0 项"  ← App.DEVN == 0
```

程序在 `DEVN == 0` 时仍会发 `fslist`，adb 无 `-s` 目标 → 返回空/报错，
前端按 `FsDeviceList` 里的关键字判断（`no such file` → 「目录不存在」），
于是把“没连上设备”显示成了“目录不存在”。**文案误导，掩盖了真实原因。**

**可能原因（按可能性）**

1. **启动时设备未连接**：程序启动即统计一次设备数，之后只有「设置 → 设备管理 → 刷新」或重连才更新
2. **adb server 冲突**：程序自带 `platform-tools\adb.exe`，与外部 adb（版本不同）抢 server，端口占用时列表为空
3. **多设备/授权**：`adb devices` 显示 `unauthorized` 或离线时同样计入 0 项

**核实方法（不改代码）**

```
① 设置 → 设备管理：看设备数量与序列号是否为 0
② 点「刷新」：能否出现 b09acfa2
③ 若仍是 0：PC 上执行 platform-tools\adb.exe kill-server，再回程序刷新
```

**建议修法（记录，未执行）**

```
① DEVN == 0 时不要发 fslist，前端直接提示"未连接设备，点此刷新"
② 错误文案区分三态：未连接 / 无权限 / 真的不存在
③ 设备上线后自动触发右侧刷新（fsOnDeviceOnline 已有钩子，确认是否被调用）
④ 启动时若检测到 0 设备，后台每 5 秒重试一次，最多 3 次
```

**优先级**：高（功能不可用，且错误提示指向错误方向）

---

## D7 设置里「设备端日志等级」点击 V/D/I/W/E 无效（选中态不变）

**现象**：点齿轮浮层里的 D，按钮不切换，设备端也没变化；「本工具显示」同理。

**根因（代码层，已定位到行）**

`initLogPill()` 里：

```js
var pop = $('v15-logpop');
if (!pop) { pop = buildLogPop(); }      // ← 只创建，没有 append 到 document
pop.addEventListener('click', function(ev){ ... });   // ← 监听绑在这个游离节点上
```

`buildLogPop()` 返回的是**尚未挂到文档**的节点，`$()` 用的是 `getElementById`，
游离节点查不到。于是：

```
① init 时创建 popA（游离），把 click 监听绑在 popA
② 打开时 $('v15-logpop') 返回 null → buildLogPop() 再建 popB
③ attachPop(popB) 把 popB 挂到 body —— popB 没有任何 click 监听
④ 用户点按钮 → 无监听 → 什么都不发生
```

`attachPop()` 的注释也写明“弹窗已经挂到 body，不再是 pill 的后代”，
监听本应绑在“挂载之后”的节点上，实际绑在了被丢弃的那一个。

**对照**：同一段代码里 `p.onclick = function(ev){ ev.stopPropagation(); }` 是
在 `buildLogPop()` 内部设置的，所以 popB 有 stopPropagation、没有业务逻辑 ——
表现为“点了没反应，但也不会把浮层关掉”。

**影响**

- 设备端 `persist.log.tag` 设置不了（功能完全不可用）
- 本工具显示级别也切不了
- 界面上没有任何错误提示，用户只能以为“点错了”

**建议修法（记录，未执行）**

```
① buildLogPop 里直接绑定业务 click（与 p.onclick 同处），或
② attachPop 成功后统一 addEventListener，或
③ 改 document 级委托：closest('#v15-logpop') 再判断 BUTTON
④ 顺带检查 v15-devpop 是否同一写法（设备管理浮层）
```

**验证方式**：打开浮层点 D，按钮 `on` 类应切换，且发出 `logset` 请求。

**优先级**：高（功能不可用 + 静默失败）

---

## D8 APK 管理「卸载」不生效：命令用了 `adb uninstall`，但工具在设备 shell 里执行

**现象**：APK 管理 → 选应用 → 卸载APK，界面报「卸载失败」。

**根因（已定位 + 设备实测）**

工具执行 shell 命令的方式是（`Adb.cs ShellCall`）：

```csharp
full = "cd '" + cur + "' && " + cmd;
AdbCall(new List<string> { "shell", full }, ...)
```

即所有命令都在**设备的 shell** 里跑。而 `ApkCmds.UninstallPkg` 用的是：

```csharp
int rc = ShellCall(CUR, "adb uninstall " + pkg, out o, out e);
```

设备 shell 里**没有 `adb` 这个命令**。设备实测：

```
$ adb shell "adb uninstall com.example.foo"
/system/bin/sh: adb: inaccessible or not found

$ adb shell "pm uninstall com.example.foo"
Failure [DELETE_FAILED_INTERNAL_ERROR]   ← pm 命令本身存在、能执行
```

**为何 fallback 也没救回来**：代码里确实写了“adb 失败就退 pm”：

```csharp
if (rc != 0 && (o + e).Trim().Length == 0)   // ← 条件太窄
    rc = ShellCall(CUR, "pm uninstall " + pkg, out o, out e);
```

但 `adb: inaccessible or not found` 会写入 stderr → `(o+e)` **非空** →
退 pm 的分支**永远不触发** → `UninstallSucceeded("adb: inaccessible...")` = false → 卸载失败。

**结论**：不是“卸载该用什么命令”的问题，是**执行环境与命令不匹配**：
设备端卸载应直接用 `pm uninstall`，不是 `adb uninstall`。

**对照（同文件其它动作都正确）**

| 动作 | 命令 | 是否正确 |
|---|---|---|
| 清理数据 | `pm clear` | ✓ 设备端命令 |
| 关闭进程 | `am force-stop` | ✓ 设备端命令 |
| 卸载 | `adb uninstall` | ✗ 主机端命令，设备 shell 没有 adb |
| 查询路径 | `pm path` | ✓ |

**建议修法（记录，未执行）**

```
① UninstallPkg 直接用 ShellCall(CUR, "pm uninstall " + pkg, ...)
② 若担心某些机型 pm 不支持，fallback 条件改成「输出含 not found / inaccessible」
   而不是「输出为空」
③ UninstallSucceeded 的正反向判定保留（pm 输出同样是 Success / Failure）
```

**优先级**：高（功能完全不可用）

---

## D9 全仓扫描：还有 8 处「主机命令误在设备 shell 执行」

**排查方法**：`ShellCall`/`ShellCapture` 都走 `adb shell "cd ... && cmd"`（设备端执行），
`AdbCall` 才是主机端 adb。据此把所有“命令对、环境错”的地方筛出来。

**结论：共 9 处**（含 D8 的 uninstall）。设备 shell 里没有 adb/root/remount/disable-verity/pull 这些命令。

| 文件 | 行 | 实际命令 | 应为（主机端） | 影响 |
|---|---|---|---|---|
| ApkCmds.cs | 116 | `adb uninstall` | `pm uninstall`（设备端） | 卸载无效（D8） |
| AutoTask.cs | 369 | `pull` | `adb pull`（AdbCall） | 拉文件失败 |
| HeapDump.cs | 271 | `pull` | `adb pull`（AdbCall） | 堆栈拉取失败 |
| Voice.cs | 789 | `remount` | `adb remount`（AdbCall） | remount 失败 |
| Voice.cs | 802 | `disable-verity` | `adb disable-verity`（AdbCall） | 失败 |
| Voice.cs | 782 | `root` | `adb root`（AdbCall） | 提权失败 |
| Cluster.cs | 217 | `root` | `adb root`（AdbCall） | 提权失败 |
| MapCmds.cs | 234 / 358 | `root`（ShellCapture） | `adb root`（AdbCall） | 提权失败 |
| MapCmds.cs | 237 / 362 | `remount`（ShellCapture） | `adb remount`（AdbCall） | remount 失败 |

**为什么多数是“静默失败”**

- `root` / `remount` 的调用处大多只 `Hint(输出)` 或 `try{}catch{}`，输出为空就跳过；
- 设备 shell 报 `/system/bin/sh: root: not found`，但很多地方没做 rc 判定，
  于是既不报错也不生效 —— 比 uninstall 更隐蔽。

**正确映射（供修复参考）**

```
主机端命令（用 AdbCall，不套 shell）：
  adb root / remount / disable-verity / enable-verity / pull / push /
  install / uninstall / forward / reverse / tcpip / connect / reboot / devices

设备端命令（用 ShellCall，即 adb shell 里）：
  pm / am / getprop / setprop / settings / dumpsys / ls / find / rm /
  mv / mkdir / cat / stat / test / sync / whoami / id / ps / kill /
  logcat / wm / monkey / tc / ifconfig / df / awk / grep / tr
```

**建议修法**

```
① 主机命令统一改 AdbCall（注意带 -s SERIAL 定位设备）
② 补自检：扫描 ShellCall 参数是否以 主机命令词 开头，是则报警
③ root/remount 调用处补 rc 判定，失败要有明确提示（不能吞）
```

**优先级**：高（影响 VR 提权、地图、堆栈拉取、卸载等多条链路）

---

## D12 设备离线时点指令，卡片永久停在「执行中/加载中」，切页才恢复

**现象**：设备不在线（已识别为离线）时点指令卡片 → 卡片转圈 + 副标题"执行中…"，
一直不结束；切一次页面（重渲染）就恢复正常。

**根因（代码定位到行，100% 可复现）**

`runQuickAt()`（`ui.html:15466` 起）里，**先**把卡片置为 running，**后**才判断设备是否在线：

```js
if(card){
  _quickRunningCard = card;                 // 15476
  card.classList.remove('done');
  card.classList.remove('error');
  card.classList.add('running');            // ← 先标"执行中"
  setCardIcon(card, 'running');
}

// R1 兜底：设备未连接
var _c = String(it.cmd || '');
if (!_online && _c.indexOf(':url') !== 0) {
  toast('设备未连接');
  return;                                   // ← 直接 return，没有回滚上面三件事
}

_busy[0] = true;
addPendingRow(it.cmd);
post('quick', it.cmd);                      // ← 因为 return，这句根本没执行
```

于是形成死锁：

```
① 卡片被标 running（转圈 + "执行中…"）
② 走到离线判断 → toast → return
③ running 没撤、_quickRunningCard 没清、_busy 没置
④ 没发 post('quick') → 后端不会回 begin/end
⑤ endRun 永远不执行 → 卡片永久"执行中"
⑥ 切页触发 renderQuickItems 重建 DOM → 状态"看起来"恢复
```

**为什么"切页就好了"**：切页会把卡片 DOM 整体重建，class 上的 `running` 随旧节点一起丢弃，
看起来恢复；但这是**假恢复**——`_quickRunningCard` 仍指向被丢弃的旧节点。

**连带风险**

```
· _quickRunningCard 残留指向已脱离文档的节点
· 下一次真正执行时，endRun 可能对这些旧节点做 classList 操作（无效）
· 若用户连续快速点击，可能出现"上一张卡还在转"的错觉
```

**修法建议（记录，未执行）**

```
① 把「设备在线判断」提到置 running 之前（最简单、最安全）
② 或在离线分支里显式回滚：
     card.classList.remove('running'); setCardIcon(card,'idle');
     _quickRunningCard = null;
③ 统一收口：任何 early return 都要走同一个"撤销 pending 态"的函数
④ 加一条自检：离线点击后卡片不含 running 类、_quickRunningCard 为 null
```

**优先级**：高（离线是常见状态，且表现为"卡死"，用户会以为工具坏了）

---

## D13 全屏态下任务栏收起/展开后，窗口脱离工作区（界面超出屏幕）

**现象**（截图）：全屏 → 鼠标移到任务栏 → 任务栏收起 → 再展开 → 全屏界面异常：

- 内容整体贴左上，左侧导航被裁掉一截
- 底部状态栏被任务栏压住（截图底部能同时看到应用状态行和任务栏图标）
- 窗口矩形明显大于工作区

**触发路径**

```
① 最大化（全屏）
② 任务栏自动隐藏收起（WorkingArea 变大）
③ 任务栏再次展开（WorkingArea 变小）
④ 窗口仍保持 ② 时候的矩形 → 超出屏幕
```

**与 D2 的关系**

D2 修的是**进入最大化那一刻**的边界（`WM_GETMINMAXINFO`）；
但这条路是**最大化之后工作区发生变化**，`WM_GETMINMAXINFO` 不会再被调用，
窗口也不会自己缩回来。

**为什么现有的事件订阅没兜住**

`GuiWeb.cs` 里订阅的是：

```csharp
SystemEvents.DisplaySettingsChanged += ...   // 分辨率/DPI 变化才触发
```

而**任务栏自动隐藏/展开、任务栏高度变化不会触发 `DisplaySettingsChanged`**，
Windows 是通过 `WM_SETTINGCHANGE`（`lParam = "TraySettings"`）通知的。
所以这条路径完全没有被监听 → 窗口不会重算边界。

**建议修法（记录，未执行）**

```
① WndProc 处理 WM_SETTINGCHANGE，lParam 为 "TraySettings" 时：
     重算 Screen.WorkingArea → 若最大化态且越界，SetWindowPos 到工作区
② 或（更稳）在最大化态监听 WM_WINDOWPOSCHANGED / WM_SIZE，
     发现 Bounds 超出 WorkingArea 就纠正一次（带重入锁，避免 D2 那种自激闪烁）
③ 加防抖：任务栏动画期间会连续发消息，200ms 内只纠正一次
④ 复用 D2 的 _fixingMax 重入锁，避免又出现"上下闪"
```

**优先级**：高（全屏是常用状态，界面被裁会影响操作）
