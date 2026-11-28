# 网络模拟"配置后不生效"实测排查

> 2026-11-28 15:35 · 设备 b09acfa2（USB）实测 · **仅记录，未改代码**

## 结论

**主因是网络不可达**：工具把车机代理指向了 PC 的 `10.41.153.21:8888`，
而车机在 `172.16.x` / `192.168.8.x` 网段，**ping 不通 PC**。
设备发往代理的每个请求都超时 → 表现为"配置了但没效果"（实际是根本连不上）。

修法不是改参数，而是换通路：USB 连接时应走 `adb reverse` + `127.0.0.1`。

---

## 一、实测数据

```
# PC 侧
PC IPv4                  10.41.153.21

# 车机侧（adb shell ip -4 addr）
eth0     172.16.0.43/20
eth1     192.168.8.2/24
vlan4    172.16.64.43/20

# 车机 → PC
ping -c 1 -W 2 10.41.153.21
1 packets transmitted, 0 received, 100% packet loss
```

**不同网段 + 无路由 → 代理地址不可达**，这是决定性的。

```
# 当前设备代理三键
settings get global http_proxy               → null
settings get global global_http_proxy_host   → null
settings get global global_http_proxy_port   → null
```

（说明此刻没在跑；也说明"停止"是清干净的——这部分没问题。）

---

## 二、为什么工具会选到 10.41.153.21

`NetSim.LocalIp()` 的逻辑：遍历网卡，**优先返回"有网关"的那块**。
USB 连接时，PC 与车机之间并没有一条 IP 通路（adb 是应用层隧道），
于是它返回了公司网口的 `10.41.153.21`——这个地址车机永远到不了。

对比参考工具（SynTestUtil）：它要求**车机与 PC 在同一局域网**（车机连 PC 热点，或 PC 连车机 WiFi 192.168.8.x），
那样 LocalIp() 才是有意义的。本工具沿用了这套假设，但没有校验"车机能不能到"。

---

## 三、验证过的正确通路：adb reverse

```
$ adb reverse tcp:18888 tcp:18888
18888                                  ← 建立成功

$ adb shell "ss -ltn | grep 18888"
LISTEN 0 4 *:18888 *:*                 ← 设备侧确实出现了监听（adbd 在转发）
```

结论：**USB 连接时，设备访问 `127.0.0.1:<port>` 就能打到 PC 的同端口**，
不需要 PC 与车机在同一网段。

（设备上没有 nc/curl/wget，无法再做一次端到端 HTTP 抓包，但监听已证明通路存在。）

---

## 四、还有两个次要因素

### ① 只影响走系统代理的流量

即使通路打通，也只有"读系统代理的 HTTP(S) 请求"受影响：

```
受影响：遵循 ProxySelector 的 App / WebView / OkHttp(默认)
不受影响：原生 socket、UDP、忽略代理的 App、证书固定(SSL Pinning)
```

车机上后者不在少数，所以"配了没变化"有时是 App 根本不看代理。

### ② 改代理对"已在运行的 App"无效

`settings put global http_proxy` 只影响之后新建的连接；
已建立的长连接、已缓存的 DNS 都不会重走代理。
用户"配置完立刻看"往往看不到变化，需要重启目标 App。

---

## 五、建议修法（按优先级）

### 方案 A：USB 用 adb reverse（推荐，改动小）

```
① 启动时：adb reverse tcp:<port> tcp:<port>
② 代理地址写 127.0.0.1:<port>（不要写 LocalIp）
③ 停止时：adb reverse --remove tcp:<port> + 清三个 proxy 键
④ 启动前自检：reverse 列表里没有该端口就尝试建立，失败要明确报错
```

优点：不依赖网络环境，USB 一插就能用。
局限：只对 USB/adb 连接有效（无线 adb 也行，因为走 adb 通道）。

### 方案 B：先探测可达性，不可达就明确提示

```
启动前：adb shell ping -c1 -W1 <pcIp>
不通 → 不写代理，直接提示
      "车机无法访问本机 10.41.153.21，请改用 USB 反向代理或让车机连同一 WiFi"
```

这条即使不做 A 也应该做——**至少不要静默写一个不可达的代理**，
那样用户会以为"弱网模拟不生效"，实际是"网络被你配断了"。

### 方案 C：要求同网段（参考工具的做法）

车机连 PC 热点 / PC 连车机 WiFi，然后 LocalIp 才有意义。
问题是操作成本高，且很多车机不允许改 WiFi。

---

## 六、验收标准（修完后）

```
□ USB 连接：启动后 adb reverse 列表里有该端口
□ 设备侧 ss -ltn 能看到该端口监听
□ settings get global http_proxy = 127.0.0.1:<port>
□ 车机浏览器/WebView 打开 http 页面，能在 PC 侧看到连接计数上涨
□ 停止后：三键清空 + reverse 移除，车机网络恢复正常
□ 非 USB（无线 adb）：走 reverse 同样可用
□ 完全不可达场景：给出明确提示，而不是静默失败
```
