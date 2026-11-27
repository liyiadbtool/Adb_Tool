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
