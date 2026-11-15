# SynTestUtil 功能逆向分析 · 需求源文档

> **来源**：`C:\Users\zuo20\Downloads\SynTestUtil\SynTestUtil\`
> **分析对象**：`SynTestUtil.exe` v1.0.39（PyInstaller 打包，Python 3.12 + PySide6）
> **分析日期**：2026-11-03
> **用途**：作为我方 adb 工具的需求来源，逐条对照取舍
> **性质**：**未获得源码**，结论全部来自运行产物（日志、数据库、配置、打包物）
> **可信度标记**：【实测】有日志/文件为证 ｜【推断】由命名或上下文推得 ｜【未知】无法确认

---

## 0. 分析方法与可信度

| 证据 | 文件 | 提供的信息 |
|---|---|---|
| 运行日志 | `SynTestUtil/log/polaris-info.log`（3.5 MB，15384 条 adb 命令） | **功能名、执行顺序、实际命令、返回值** |
| 运行日志 | `polaris-error.log`（417 KB） | 失败模式、异常栈 |
| 另一份日志 | `test_tools/dist/log.txt`（302 KB） | `main.py` 的函数名与行号 |
| 本地数据库 | `_internal/syntest.db` | 表结构、路径配置、设备绑定 |
| 配置 | `pz.json` | 9 个输出路径 |
| 弱网脚本 | `temp_mitmproxy_script.py` | 弱网参数与实现方式 |
| 产物目录 | `_internal/data/*` | 8 类采集产物的命名规则 |
| 打包信息 | `main.spec`、`_internal/` | 依赖清单与运行形态 |

**局限**：没有源码，UI 的按钮文字、布局、交互流程无法完全还原；下文凡涉及 UI 的地方均为【推断】。

---

## 1. 工具概览

### 1.1 定位

**面向广汽车机（GXATEK / Syncore 座舱）测试岗的 adb 图形化工具箱。**

它不提供"任意命令输入"，而是把测试岗高频的 30 多个动作**固化成按钮**，每个按钮背后是一到几条 adb 命令 + 一个固定产物目录。

### 1.2 目标设备（从实测返回值看）

| 属性 | 实测样例 |
|---|---|
| `ro.oem.product.name` | `3588_SYNCORE_t9m`、`8295_DESAY_AH8`、`8838_DESAYSV_T75` |
| 系统 | Android Automotive（`com.android.car.*`、`dumpsys car_service`） |
| 关键应用 | `com.gac.cloud.app`、`com.gxatek.cockpit.*`、`space.syncore.cockpit.*` |

### 1.3 技术栈【实测】

| 层 | 组件 |
|---|---|
| UI | PySide6（Qt 6），外置 `dark.qss` 深色主题 |
| 设备通信 | `adbutils 2.7.2` + 自封装 `tools.commons.adb` |
| 投屏 | 外部 `scrcpy.exe`（路径可配） |
| 弱网 | mitmproxy（`_brotli` / `cryptography` / `zstandard` / `certifi` 均在包内） |
| 图像 | opencv、PIL、numpy |
| 系统 | psutil、wmi（进程管理） |
| 文本 | lxml |
| 存储 | SQLite（`syntest.db`） |
| 打包 | PyInstaller onefile，`console=False`（无黑窗），UPX 压缩 |

### 1.4 运行结构

```
SynTestUtil/
├─ SynTestUtil.exe            主程序（43 MB）
├─ temp_mitmproxy_script.py   弱网脚本（运行时落地）
├─ _internal/
│  ├─ syntest.db              SQLite：路径配置 + 设备绑定
│  ├─ data/                   8 类产物目录
│  │  ├─ android_log/  log/  tcpdump/
│  │  ├─ screen/  video/  longtimeVideo/
│  │  └─ pref_data/
│  └─ temps/voice/            语音功能临时目录
└─ log/                       polaris-*.log（4 个级别）
```

---

## 2. 架构与模块

### 2.1 模块划分【实测，来自日志的 logger 名】

| 模块 | 调用次数 | 职责 |
|---|---:|---|
| `tools.commons.adb` | 15384 | adb 命令封装（统一 `cmd/out/err/执行完成` 四段式日志） |
| `tools.commons.decorators` | 11107 | 装饰器：设备校验、计时、进程回收 |
| `tools.network_utils` | 237 | 网络：代理、mitmproxy、弱网 |
| `tools.car_logs_utils` | 116 | 日志：logcat、tcpdump、时间比对 |
| `tools.car_mediax_utils` | 4 | 媒体：截图、录屏、投屏 |
| `tools.car_voice_utils` | 2 | 语音：按键注入 |
| `tools.car_system_utils` | 1 | 系统：环境、夜间模式、工程模式 |

### 2.2 统一装饰器语义【实测，从日志推断】

每个功能都被同一个装饰器包裹，日志固定出现三段：

```
start function 'xxx'
   （中间是 adb_cmd 的 cmd / out / err / 执行完成）
stop Function 'xxx' executed
```

装饰器负责三件事：

1. **连接校验**：先 `设备连接成功`，失败则整段跳过
2. **耗时统计**：start / stop 时间戳
3. **进程回收**：长任务再次启动前，先 `kill` 上一次的 PID

### 2.3 长任务单实例模型（重要）

采集类功能（`logcat` / `qrz_log` / `tcpdump` / `lzsp` / `luping` / `scrcpy`）不是走 `adb_cmd`，而是**起一个子进程并记录 PID**：

```
start function 'qrz_log'
  start function 'kill'
    kill process 29312          ← 先杀掉上次的
  stop Function 'qrz_log' executed
```

也就是说：**这些按钮是"开关"语义——再点一次是重启采集，不是叠加**。

> 需求启示：任何长时间运行的采集功能，必须实现「单实例 + 重入即重启」。
> 我方目前 `:sid`（logcat 过滤）是阻塞式的，没有单实例保护。

---

## 3. 配置与数据

### 3.1 `pz.json` —— 9 个输出路径【实测】

```json
{"logcat":"", "screenrecord":"", "screencap":"", "tcpdump":"", "maplog":"",
 "pushapk":"", "pullapk":"", "dbc_file":"", "scrcpy":""}
```

| 键 | 含义 | 用途 |
|---|---|---|
| `logcat` | 日志落盘目录 | logcat 输出 |
| `screenrecord` | 录屏输出目录 | screenrecord 产物 |
| `screencap` | 截图输出目录 | 截图存放 |
| `tcpdump` | 抓包输出目录 | .pcap 存放 |
| `maplog` | 地图日志目录 | 地图专项日志 |
| `pushapk` | APK 推送源目录 | 安装包来源 |
| `pullapk` | APK 拉取目标目录 | 从设备取包 |
| `dbc_file` | DBC 文件路径 | CAN 报文定义 |
| `scrcpy` | scrcpy.exe 路径 | 投屏可执行 |

**实测历史值泄露了另一台电脑的用户名**（`C:/Users/sunxi/...`、`C:/Users/EDY/...`），说明：

- 路径是**用户手工选择后落盘**的，不是自动定位
- 换机器后这些路径全部失效，属于已知缺陷

### 3.2 `syntest.db` —— 3 张表【实测，从文件字节还原 DDL】

```sql
CREATE TABLE path (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  path TEXT
);
CREATE TABLE computer_device (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid TEXT
);
CREATE TABLE sqlite_sequence (name, seq);
```

| 表 | 作用【推断】 |
|---|---|
| `path` | 功能名 → 路径（`pz.json` 的持久化后端） |
| `computer_device` | 记录"这台电脑连过哪些设备"，用于多机切换或授权 |

### 3.3 产物目录与命名规则【实测】

| 目录 | 内容 | 命名规则 |
|---|---|---|
| `data/screen/` | 截图 png | `YYYY-MM-DD-HH_MM_SS.png` |
| `data/video/` | 录屏 mp4 | `YYYYMMDDHH_MM_SS.mp4` |
| `data/longtimeVideo/` | 长时录屏 mp4 | `YYYYMMDDHH_MM_SS.mp4` |
| `data/tcpdump/` | 抓包 | 未见样本【未知】 |
| `data/android_log/` | 设备日志 | 未见样本【未知】 |
| `data/pref_data/` | **每包一份帧率统计** | `<包名>__framestats.txt` |
| `data/log/` | 运行日志 | 未见样本【未知】 |
| `temps/voice/` | 语音临时文件 | 【未知】 |

> `pref_data/*__framestats.txt` 的文件名后缀 `framestats` 指向 **按包采集帧率** 的能力
> （通常是 `dumpsys gfxinfo <pkg> framestats`）。**但 info 日志里查不到该命令**（0 次命中），
> 说明这条路径不在统一 adb 封装里，或来自旧版本 → 列入「第 10 章未确认项」。
> 实测样本包含：`android.ext.services`、`com.android.shell`、`com.bilibili.bilithings`、`com.iflytek.autofly.platformservice` 等。

### 3.4 日志分级【实测】

`log/` 下有 **5 个**文件：

| 文件 | 大小 | 说明 |
|---|---:|---|
| `polaris-critical.log` | 0 B | 从未使用 |
| `polaris-debug.log` | 3.5 MB | 与 info 内容几乎相同 |
| `polaris-info.log` | 3.5 MB | 主日志 |
| `polaris-error.log` | 417 KB | ← 与 warning **md5 完全相同** |
| `polaris-warning.log` | 417 KB | ← `c60a442d...`，同上 |

**error 与 warning 的 md5 一致**（`c60a442d2356f2048889a467f2a06310`），说明 warning 处理器
实际写入的是 error 的内容 —— 日志级别配置缺陷，warning 通道形同虚设。

---

## 4. 功能清单

> 编号规则：`F-<组><序号>`。频率为该功能在 15384 次调用日志中的出现次数，可作为优先级证据。

### A 组 · 环境切换与查询

#### F-A1 `env` —— 一键切环境并重启应用　【实测·307 次】

| 项 | 内容 |
|---|---|
| 前置 | 设备在线 |
| 命令序列 | `setprop persist.sys.autofly.web.deploy <test\|pre\|dev>`<br>`setprop persist.sys.autofly.web.https <url>`<br>`setprop persist.sys.autofly.web.domain <url>`<br>`am start -n com.gac.cloud.app/.app.MainActivity` |
| 目的 | 改完属性后**重启 App 使配置生效**（否则属性改了但进程还持有旧值） |
| 产物 | 无 |
| 实测返回 | `Starting: Intent { cmp=com.gac.cloud.app/.app.MainActivity }` |
| 失败模式 | 设备未连接 → `adb.exe: no devices/emulators found` |

**3 套环境取值【实测】**

| 环境 | deploy | https | domain |
|---|---|---|---|
| test | `test` | `api-test.syncore.space:20443` | `api-test.syncore.space:20443` |
| pre | `pre` | `api-pre.syncore.space:20443` | `api-pre.syncore.space:20443` |
| dev | `dev` | `api.syncore.space` | `api.syncore.space` |

#### F-A2 `cartest` —— 查当前环境　【实测·200 次】

| 项 | 内容 |
|---|---|
| 命令 | `getprop persist.sys.autofly.web.deploy` |
| 实测返回 | `test` / `pre` / `dev` |
| 用途 | 切完环境后回读确认（仅读 deploy 一个键，**不校验 https/domain 是否配套**） |

> 需求启示：只比对一个键不够。我方 `:env` 是三个键全比 + 全量回读校验，这点比它严谨。

#### F-A3 `settest` / `setpre` —— 只设属性不重启　【实测·71 / 82 次】

| 项 | 内容 |
|---|---|
| 命令 | `setprop persist.sys.autofly.web.deploy test`（或 `pre`） |
| 与 F-A1 的区别 | **不**执行 `am start`，App 需自行重启才生效 |

> 需求启示：切环境有两种语义——「只改配置」和「改完立刻生效」。这是一个值得保留的细分。

---

### B 组 · 车机信息采集

#### F-B1 `car_info` —— 车型识别　【实测·304 次】

| 项 | 内容 |
|---|---|
| 命令 | `getprop \| findstr ro.oem.product.name` |
| 实测返回 | `[ro.oem.product.name]: [3588_SYNCORE_t9m]`<br>`8295_DESAY_AH8`<br>`8838_DESAYSV_T75` |
| 用途 | 判断当前连接的是哪个平台的机器（T9M / AH8 / T75…），后续功能按平台分支【推断】 |

#### F-B2 `getprop` 信息面板 —— 12 个关键属性　【实测】

| 属性键 | 次数 | 含义【推断】 | 实测值样例 |
|---|---:|---|---|
| `persist.sys.autofly.web.https` | 349 | 环境 HTTPS 地址 | `api-pre.syncore.space:20443` |
| `persist.sys.autofly.web.domain` | 349 | 环境域名 | `api-pre.syncore.space:20443` |
| `persist.sys.autofly.web.deploy` | 349 | 环境标识 | `test` / `pre` / `dev` |
| `ro.oem.product.name` | 304 | 车型平台 | `8295_DESAY_AH8` |
| `ro.build.display.id` | 154 | 系统版本号 | 未采到样例 |
| `persist.sys.vehicle.vin` | 150 | 车架号 VIN | `HACAATA29T1S03086` / `J01NSG3071PA17000A5D` |
| `persist.sys.navi.did` | 150 | 导航 DID | `cebfbf76` |
| `persist.sys.navi.openid` | 150 | 导航 openid | `48e24a4c` / `6a29b54b` |
| `persist.sys.navi.uid` | 149 | 导航 UID | `55884556522455511445` |
| `persist.sys.navi.uuid` | 149 | 导航 UUID | `LMGKD1S8XS1S00073` |
| `sys.vehicle.mcu.version` | 149 | MCU 版本 | 未采到样例 |

> **这份键表就是"测试岗关心的设备标识"标准答案。**
> 与用户此前追加的 `uuid` / `did` / `openid` 三个 DIY 命令完全对应，可补上 `uid`、`vin`、`mcu.version`、`build.display.id`。

#### F-B3 `app_version` / `apk_version` / `apk_list` —— 应用版本　【实测·6 / 2 / 少】

| 项 | 内容 |
|---|---|
| 命令 | `dumpsys package <包名> \| findstr version` |
| 实测目标包 | `com.gxatek.cockpit.ispace`、`com.iflytek.autofly.mediax`、`com.iflytek.autofly.mediaxkid`、`space.syncore.cockpit.soundeffect`、`com.gxatek.cockpit.shortcut`、`com.gxatek.cockpit.gallery`、`space.syncore.cockpit.aigccreator`、`com.gxatek.cockpit.launcher` |
| 已知缺陷 | `apk_list` 在设备未连接时抛 `IndexError: list index out of range`（空列表未判空） |

> 需求启示：包清单是**项目数据**，应放配置而非代码。我方 `version_pkgs` 正是这个设计。

---

### C 组 · 日志与取证

#### F-C1 `logcat` —— 日志采集　【实测·长期使用】

| 项 | 内容 |
|---|---|
| 形态 | 长任务（起子进程），路径来自 `pz.json.logcat` |
| 单实例 | 再次启动前 kill 旧 PID【实测，由 kill 调用推断】 |
| 产物 | 指定目录下的日志文件，命名【未知】 |

#### F-C2 `qrz_log` —— 一键抓日志　【实测·57 次】

| 项 | 内容 |
|---|---|
| 序列 | `kill <旧PID>` → 起 logcat 子进程 → 时间比对 |
| 关联 | 每次 `qrz_log` 后几乎必跟 `compare_times`（见 F-C3） |
| 用途【推断】 | 抓日志并记录"设备时间 vs PC 时间"基准，便于事后对齐时间轴 |

#### F-C3 `compare_times` —— 设备时间与 PC 时间比对　【实测·29 次】

| 项 | 内容 |
|---|---|
| 命令 | `shell date` |
| 实测返回 | `Fri Apr 25 11:45:37 CST 2025`（PC 侧为 `11:45:38`，差 1 秒） |
| 用途 | 日志时间轴对齐；发现设备时钟漂移 |

> **这条需求我方完全没有**，但真实痛点：设备时间不准时，按时间找日志会全部错位。

#### F-C4 `check_log` —— 日志校验　【实测·29 次】

| 项 | 内容 |
|---|---|
| 行为【未知】 | 无 adb 命令记录，可能只做本地文件检查（大小/行数/是否为空） |

#### F-C5 `tcpdump` —— 设备端抓包　【实测·14 次】

| 项 | 内容 |
|---|---|
| 形态 | 长任务，起设备侧 tcpdump 子进程，产物落 `pz.json.tcpdump` / `data/tcpdump` |
| 前置 | 设备需 root（tcpdump 需要）【推断】 |
| 单实例 | 再次启动先 kill 旧进程【实测】 |

---

### D 组 · 媒体与投屏

#### F-D1 `scrcpyback` / `scrcpyfront` —— 投屏　【实测·860 / 542 次，**使用频率最高**】

| 项 | 内容 |
|---|---|
| 实现 | 调用外部 `scrcpy.exe`（路径 `pz.json.scrcpy`），起子进程 |
| 两种模式 | `scrcpyfront` = 前台显示；`scrcpyback` = 后台启动（不抢焦点，可能带 `--no-display` 或最小化）【推断】 |
| 单实例 | 切换前 kill 旧进程【实测】 |
| 需求启示 | **投屏是测试岗第一高频操作**，因为座舱测试要边看屏幕边操作 |

#### F-D2 `jt`（截图）　【实测·41 次】

| 项 | 内容 |
|---|---|
| 命令序列 | `mkdir /sdcard/screen/`<br>`screencap -p /sdcard/screen/<YYYY-MM-DD-HH_MM_SS>.png`<br>`pull` 到本地<br>`rm -rf /sdcard/screen`（清理） |
| 实测产物 | `2025-05-15-17_51_25.png` 等 |
| 细节 | 先建目录、截图、拉回、删设备侧残留 —— **四步完整闭环** |

#### F-D3 `luping` / `lzsp` / `longtimeVideo` —— 录屏　【实测·8 次 / 长时录屏目录存在】

| 项 | 内容 |
|---|---|
| 形态 | 长任务，`screenrecord` 子进程 |
| 产物 | `data/video/YYYYMMDDHH_MM_SS.mp4`；长时录屏落 `longtimeVideo/` |
| 已知问题 | 长时录屏需要"分段拼接"或调大 `--time-limit`【推断】 |
| 单实例 | 再次点击 kill 旧进程【实测】 |

---

### E 组 · 网络与弱网（我方完全缺失的一块）

#### F-E1 `get_local_ip` —— 取本机 IP　【实测·20 次】

| 项 | 内容 |
|---|---|
| 用途 | 为代理地址提供 PC 的局域网 IP（`10.41.152.100` / `192.168.135.177`） |

#### F-E2 `networkdaili` —— 设置/清除 HTTP 代理　【实测·38 次】

| 项 | 内容 |
|---|---|
| 设置 | `settings put global http_proxy <PC_IP>:8888` |
| 查询 | `settings get global http_proxy`（**56 次，是所有 settings 操作里最多的**） |
| 清除 | `settings delete global http_proxy`<br>`settings delete global global_http_proxy_host`<br>`settings delete global global_http_proxy_port` |
| 验证 | 再 `get global http_proxy` → 期望 `null` |

**注意**：清除时必须删三个键。只删 `http_proxy` 会留下 host/port 残值，导致"看起来清了实际还走代理"。

#### F-E3 `start_mitmproxy` / `stop_mitmproxy` —— 代理服务　【实测·18 / 17 次】

| 项 | 内容 |
|---|---|
| 实现 | 起 mitmproxy 进程（监听 8888），加载 `temp_mitmproxy_script.py` |
| 停止 | kill 进程 + 清代理设置（与 E2 联动） |

#### F-E4 `start_network_simulation` / `simulate_network_delay` —— 弱网模拟　【实测·18 次】

脚本参数（`temp_mitmproxy_script.py` 原文）：

```python
UPLOAD_RATE   = 15    # 上行限速 KB/s
DOWNLOAD_RATE = 15    # 下行限速 KB/s
UPLOAD_DELAY  = 0.5   # 上行延迟 s
DOWNLOAD_DELAY= 0.4   # 下行延迟 s
UPLOAD_LOSS   = 0.0   # 上行丢包率（0.1 = 10%）
DOWNLOAD_LOSS = 0.0   # 下行丢包率
```

实现要点：

- `limit_rate()` 按 1 秒一块 sleep 节流，**粗粒度限速**（实际速率 = `rate`，但只对单次请求生效）
- `should_drop_packet()` 用随机数模拟丢包，丢包时直接返回 **HTTP 502 空响应**
- 上行在 `request()` 里处理，下行在 `response()` 里处理

**局限【实测推断】**：

1. 只对 HTTP(S) 流量生效，**UDP / 原生 socket 不受影响**
2. 丢包是"整个请求丢弃并返回 502"，不是真的丢 TCP 包 —— 与真实弱网行为差异大
3. 限速粒度 1 秒，短请求几乎不减速

> 需求启示：若要覆盖真实弱网，需要用 `tc netem`（设备端，需 root）而不是应用层代理。

#### F-E5 `stop_agent` —— 收尾清理　【实测·18 次】

| 项 | 内容 |
|---|---|
| 行为【推断】 | 一次性还原：kill mitmproxy + 清代理 + 关脚本痕迹 |

---

### F 组 · 语音与按键注入（我方完全缺失）

全部通过 `dumpsys car_service inject-key <code>` 注入车机硬键，不依赖 UI 坐标。

| 功能 | 键码 | 次数 | 用途 |
|---|---:|---:|---|
| `yaj_voice` | **508** | 40 | 语音键（唤醒语音助手） |
| `yaj_up` | **506** | 33 | 上键 |
| `yaj_down` | **507** | 33 | 下键 |
| `yaj_ok` | **522** | 40 | 确认键 |
| `yaj_soundup` | **513** | 5 | 音量 + |
| `yaj_sounddown` | **514** | 5 | 音量 − |
| `yaj_call` | **503** | 3 | 接听/来电 |

实测返回统一是 `Succeeded`。

> **这是我方最值得补的一块**：座舱语音测试必须能模拟方向盘/中控硬键，而 `input keyevent` 的键值（如 87/88）走的是 Android 标准键，与车机自定义键（5xx）不是一回事。

---

### G 组 · 系统与配置

| 功能 | 实测命令 | 次数 | 说明 |
|---|---|---:|---|
| `night` | `shell "su 0 cmd uimode night yes"` | 22 | 夜间模式开，**需 root** |
| `daytime` | `shell "su 0 cmd uimode night no"` | 21 | 夜间模式关，需 root |
| `gcms` | `am start -n com.android.engmode/com.android.engmode.MainActivity` | 18 | 进工程模式主页 |
| `zhzs` | `am start -n com.android.engmode/.ui.AssistantActivity` | 3 | 工程模式-助手页 |
| `xxpz` | `am start -n com.android.engmode/.ui.OfflineConfigActivity` | 2 | 工程模式-离线配置页 |
| `reboot` | `reboot` | 1 | 重启设备 |
| `car_df` | `df`（推断） | 1 | 分区空间 |
| `catcarvin` | 读 VIN | 1 | 单独取 VIN |
| `app_help` | 无命令 | 1 | 帮助页【推断】 |
| `setdev` | 无 adb 命令 | 10 | 切换当前设备【推断】 |
| `xg` | 无 adb 命令 | — | 修改/配置项【未知】 |
| `run` | 无固定命令 | 159 | **通用"执行"入口**，可能是执行自定义命令【推断】 |
| `tab_changed` | 无命令 | 123 | UI 埋点（切换标签页） |
| `dbc_load` | 本地文件读取 | — | 加载 DBC 文件（CAN 报文定义） |
| `clear_Cache` | `pm clear <pkg>`【推断】 | — | 清应用数据 |
| `close_app` | `am force-stop <pkg>`【推断】 | — | 关闭应用 |
| `apk_list` / `pushapk` / `pullapk` | `pm list packages` / `adb push` / `adb pull` | — | APK 清单与推拉 |

---

## 5. 异常与边界（来自 417 KB error 日志的真实失败）

| 现象 | 次数 | 根因 | 应有处理 |
|---|---:|---|---|
| `psutil.NoSuchProcess` | **807** | kill 一个已经退出的进程 | kill 前先查存在性；把它当"已完成"而非异常 |
| `psutil.ProcessLookupError` | **433** | 同上（底层） | 同上 |
| `拒绝访问。` | 8 | Windows 侧文件/进程权限 | 提示"以管理员运行" |
| `adb.exe: no devices/emulators found` | — | 设备掉线 | 统一拦截并提示重连 |
| `/system/bin/sh: su: inaccessible or not found` | — | `night/daytime` 需要 root，设备没 root | 降级提示"该机型无 su" |
| `IndexError: list index out of range` | — | `apk_list` 空列表 | 判空 + 明确提示 |
| `ConnectTimeoutError www.wpbkj.com` | — | 启动时联网检查（1 秒超时） | 失败不应阻塞；可关掉 |

> **807 + 433 次"杀不存在的进程"** 说明进程管理没做幂等——每次点采集按钮都会先 kill，然后必然报一次异常。这不是偶发，是设计缺陷。

---

## 6. 非功能需求（从实现反推）

| 编号 | 需求 | 证据 |
|---|---|---|
| N-1 | 长任务必须单实例，重入即重启 | `kill` 被调用 439 次 |
| N-2 | 每个功能有独立的产物目录，路径可配 | `pz.json` 9 键 |
| N-3 | 产物文件名带时间戳，可排序 | `2025-05-15-17_51_25.png` |
| N-4 | 统一日志分级 + 功能级耗时 | `start/stop Function` 装饰器 |
| N-5 | 设备未连接时统一拦截，不逐条报错 | `装饰器 → 设备连接成功` |
| N-6 | 设备侧临时文件必须清理 | 截图后 `rm -rf /sdcard/screen` |
| N-7 | 所有 adb 命令需可在日志中回溯 | `adb_cmd: cmd/out/err` 四段式 |
| N-8 | 配置（路径/包名/属性键）与代码分离 | `pz.json`、`syntest.db` |

---

## 7. 对我方的需求条目（可直接勾选）

> 落点说明：**配** = `cmds.ini` 配置即可；**`:`** = 需要新的工具命令；**引擎** = 需要改核心能力；**不做** = 判断不值得。

### P0 —— 高频且我方完全缺失

| 编号 | 需求 | 来源 | 落点 | 验收标准 |
|---|---|---|---|---|
| R-01 | 一键切环境并重启 App（`setprop ×3` + `am start`） | F-A1 | 配 | `:env test` 后 `:env` 回读三键全绿 |
| R-02 | 只改属性不重启（可与 R-01 分开） | F-A3 | 配 | `:env test -norestart` 生效且不重启 |
| R-03 | 车机标识面板：`vin`/`mcu`/`build.id`/`navi.uid` 补齐 | F-B2 | 配 | `:id` 一次输出 8 项，缺失显示 `-` |
| R-04 | **硬键注入**：`car_service inject-key 508/506/507/522/513/514/503` | F | 配 | `:voice` `:up` `:down` `:ok` `:vol+` `:vol-` `:call` 均返回 `Succeeded` |
| R-05 | 设备时间与 PC 时间偏差 | F-C3 | `:` | `:time` 输出 `设备 11:45:37 / PC 11:45:38 / 偏差 -1s` |
| R-06 | 截图闭环（建目录→截图→拉回→清理） | F-D2 | 配 | `:shot` 产出 `screen/YYYY-MM-DD-HH_MM_SS.png`，设备侧无残留 |

### P1 —— 有价值但成本较高

| 编号 | 需求 | 来源 | 落点 | 验收标准 |
|---|---|---|---|---|
| R-07 | 投屏（scrcpy）前台/后台两种模式 | F-D1 | 引擎 | 可配置 scrcpy 路径；重复点不叠加进程 |
| R-08 | 录屏（含长时录屏） | F-D3 | 引擎 | 产物 mp4 可播放；再次点击重启采集 |
| R-09 | 抓包（tcpdump） | F-C5 | 配 | 产出 pcap；无 root 时明确报错 |
| R-10 | 代理设置/清除（三键一起删） | F-E2 | 配 | `:proxy off` 后 `get http_proxy` 为 `null` |
| R-11 | 弱网模拟 | F-E4 | 引擎 | 参数可配（上下行速率/延迟/丢包），能一键还原 |
| R-12 | 长任务单实例 + 重入即重启 | N-1 | 引擎 | 连续点两次，只有一个采集进程 |
| R-13 | 设备未连接统一拦截 | N-5 | 引擎 | 离线时点任何采集都提示重连，不逐条报 `no devices` |
| R-14 | 包版本 + 安装路径 | F-B3 | 已有 | `:pkg ver <包名>` 已实现，需补 verify |

### P2 —— 锦上添花

| 编号 | 需求 | 来源 | 落点 | 说明 |
|---|---|---|---|---|
| R-15 | 工程模式跳转（`engmode` 三个 Activity） | G | 配 | 换项目即失效，做成配置 |
| R-16 | APK 清单 / 推拉 | G | 已有 | `push`/`pull` 已覆盖 |
| R-17 | DBC 加载（CAN 报文解析） | G | 不做 | 属专业领域，独立工具更合适 |
| R-18 | 按包采帧率（`gfxinfo framestats`） | 3.3 | 不做 | 用 perfetto 更准 |

### 明确不做

| 项 | 理由 |
|---|---|
| 图形界面 | 我方定位是命令行编排器，GUI 会推翻现有交互模型 |
| 应用层弱网代理（mitmproxy 版） | 只影响 HTTP，丢包是假丢包，价值低于 `tc netem` |
| 启动联网检查 | 无必要，且引入 1 秒启动延迟 |
| 单文件 2300 行的大脚本 | 我方已按模块拆分，不回退 |

---

## 8. 能力对照矩阵

| 能力 | SynTestUtil | 我方 v7.5 | 差距 |
|---|---|---|---|
| 任意 adb / shell 输入 | ❌ 只能用按钮 | ✅ | 我方强 |
| 环境切换 | ✅ 一键 + 重启 | ✅ `:env` 三键校验 | 平；**缺"改完立刻重启 App"** |
| 车机标识 | ✅ 12 个属性 | 部分（uuid/did/openid） | **缺 vin / mcu / build.id / uid** |
| APK 版本 + 路径 | ✅ | ✅ `:pkg ver` | 平 |
| 日志采集 | ✅ 长任务 | ⚠️ `:sid` 可流式但无落盘 | **缺落盘 + 单实例** |
| 截图 | ✅ 四步闭环 | ✅ `:shot` | 平 |
| 录屏 | ✅ | ❌ | **缺** |
| 投屏 | ✅ | ❌ | **缺** |
| 抓包 | ✅ | ❌ | **缺** |
| 弱网 | ✅ | ❌ | **缺** |
| 硬键注入 | ✅ 7 个键 | ❌ | **缺** |
| 设备/PC 时间比对 | ✅ | ❌ | **缺** |
| 夜间模式 | ✅ | ✅ `:yes`/`:no` | 平 |
| DIY / 可扩展 | ❌ 改代码 | ✅ 改 ini | 我方强 |
| 离线可用 | ❌ | ✅ | 我方强 |

---

## 9. 关键设计判断（给人看的结论）

1. **它的价值不在 adb 命令，而在"把命令固化成按钮"。** 全部 7 组功能里，没有一条是我方做不到的命令，差别只在"要不要记、要不要打"。

2. **它覆盖了我方三个真实空白：硬键注入、投屏、弱网。** 其中硬键注入最值得补——三行配置就能覆盖，且座舱语音测试离不开。

3. **它的进程管理是反面教材。** error 日志里 **1240 次"杀不存在的进程"**（807 次 `NoSuchProcess` + 433 次 `ProcessLookupError`），说明"先 kill 再启动"没做幂等——每次操作都白报一次异常。我方若做长任务，必须"先查存在再 kill，并把'已退出'当作成功"。

4. **它的配置设计值得学一半。** `pz.json` 把 9 个路径外置是对的，但写死成绝对路径导致换机即失效；应改成"相对 exe 目录的默认值 + 可覆盖"。

5. **它的日志设计值得学。** 每条 adb 命令都有 `cmd / out / err / 执行完成` 四段，事后能完整复盘。我方日志偏少，长任务失败时证据不足。

---

## 10. 未确认项（需上机验证）

| # | 问题 | 验证方法 |
|---|---|---|
| 1 | `scrcpyback` 与 `scrcpyfront` 的具体参数差异 | 抓进程命令行 `wmic process where name='scrcpy.exe' get commandline` |
| 2 | `qrz_log` / `lzsp` 抓的到底是哪些日志（logcat? dumpsys?） | 看产物文件名与内容 |
| 3 | `check_log` 的判定规则 | 断网/空日志时点一次，看提示 |
| 4 | `run` 是不是"自定义命令"入口 | 输入一条命令试 |
| 5 | `xg` / `setdev` 的实际行为 | 点一次看界面变化 |
| 6 | 弱网是否也作用于 UDP | 用 UDP 打流验证 |
| 7 | 帧率采集的采样周期 | 看 `pref_data` 文件的 timestamp 间隔 |
| 8 | `pref_data/*__framestats.txt` 是由哪条命令产生的（日志无记录） | 点一次帧率采集，同时 `adb shell` 侧抓命令 |

---

## 附：本文件的使用方式

- 第 4 章的 `F-xx` 是**功能原始事实**，改需求时以此为准，不要凭印象
- 第 7 章的 `R-xx` 是**可直接排期的需求条目**，已给出落点与验收标准
- 第 9 章是**判断**，允许再讨论
- 第 10 章是需要上机确认的，未确认前不要写进规格
