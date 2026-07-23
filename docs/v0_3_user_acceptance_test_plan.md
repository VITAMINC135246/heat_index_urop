# v0.3.2 普通用户验收流程

这份流程模拟“我就是最终用户”。它不要求你编写 JSON、选择 config、拼接长
PowerShell 参数或运行 pytest。程序员自动测试是另一套工作；本文件只回答：我有
真实输入时，怎样启动程序、怎样操作每个界面、怎样看到五张 pilot、足球场、
Part E、spatial 和 temporal 的实际结果。

## 当前真实证据快照（2026-07-22）

本文件既是复验步骤，也记录已经取得的真实证据；“已完成”和“仍在运行”必须
分开解释：

- normal Part C 桌面 GUI 已在真实 visible ROI/thermal 输入上实际操作。`Cancel`
  返回未接受（false/cancelled），没有创建本次成功 canonical；`Accept` 返回已接受
  （true/accepted）并继续创建 canonical。这一项验证 GUI 控制流和持久化边界，
  不等于自动证明某个人工 surface-cover 标签在科学上正确。
- 三时点足球场 temporal 已完成并通过输出验证。workflow run 是
  `outputs/runs/v0_3_user_acceptance/workflow_runs/run_20260722T053855Z/`，对应的
  run-scoped Part E 是
  `outputs/runs/v0_3_user_acceptance/part_e/schema_0_2/run_20260722T053855Z/`；详细
  数值和限制见第 6、7 节。
- 五张 pilot 加一张足球场的
  `outputs/runs/v0_3_user_acceptance/workflow_runs/run_20260722T055625Z/` 已完成六个
  image route（五个 normal Part C、一个 Part C*），均为 success。对应 Part E 位于
  `outputs/runs/v0_3_user_acceptance/part_e/schema_0_2/run_20260722T055625Z/`，最终
  validation 和 `USER_RESULTS.md` 均已生成。该 run 恰好包含六个 image ID，输出
  8 组 spectrum PNG/PDF 和 48 组 spatial PNG/PDF；五张 pilot 的 official LUHK
  known 均为 327,680 px，足球场 target/LUHK known 为 21,047 px。
  单时次 temporal 只输出描述统计并明确写成 no trend，没有生成空白趋势图。

每次运行的 Part E 都写入自己的 `<run_id>` 目录。persistent canonical image store
可以作为 cache/input 复用，但不能把共享旧目录或另一 run 的图表当成本次证据。

## 1. 启动程序

打开 PowerShell，进入仓库：

```powershell
Set-Location -LiteralPath "E:\Projects\heat_index_urop"
```

启动程序：

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

正常时首先看到：

```text
What do you want to explore this time?
  1) Five accepted pilot images
  2) Football field
  3) Five pilots + football field
  4) One visible/thermal group
  5) A dataset directory
  6) Several specific visible/thermal groups
```

这一个命令就是普通用户入口。后面输入的是菜单选择、路径和确认，不是新的程序
命令。默认写入隔离验收目录，结束后自动打开最新 run 文件夹。

如果 `python` 本身无法运行，先修复/激活本项目 `.venv`；不要因此改用一大串
底层 workflow 参数冒充普通用户流程。

## 2. 第一轮：五张真实 pilot

重新启动程序后，在 `Choose 1-6` 输入：

```text
1
```

这五张已经有接受过的人工标注和真实温度矩阵，正常情况不要求重新标五遍。观察
控制台逐张出现 Part A、Part B0/adapter、canonical 和 Part E 进度；每张最终应为
`success` 或可解释的 `cache_hit`，不能只出现一张极值图就结束。

当程序询问：

```text
Do you want to perform temporal analysis for repeated observations of the same location? [y/N]
```

直接按 Enter。本轮五张 pilot 没有被用户确认成同一物理 ROI，因此默认答案必须
是 No。随后应显示 temporal 未请求，但 spectrum、spatial 和其他 Part E 仍继续。

完成后 Explorer 会打开最新 run 文件夹。先打开：

```text
USER_RESULTS.md
```

按其中链接依次确认：

1. run summary 有五张图，均为 success/cache hit；
2. canonical image results 有五个 image 文件夹；
3. 每张都有温度、ΔT、surface cover、LUHK、target/eligibility 和 combined spatial
   图，缺失层必须写 `UNAVAILABLE` 及原因，不能用空白或假数据代替；
4. `figures/spectrum/` 有 overall、LUHK、surface cover、within-GIC、逐图等统计
   distribution/density spectrum，不是只看 min/max 极值图；
5. `tables/` 有逐图、LUHK、surface cover、sample coverage、统计检验和 effect size；
6. `temporal/temporal_run_summary.md` 明确写 temporal was not requested，不应生成
   一个暗示五图是时间序列的通用 temporal 图。

五张 pilot 的正式像素应各为完整 512×640。其 LUHK 来自官方只读 context；LUHK
类别不能因为你在 Part C 选择了某个 surface cover 而变化。

## 3. 第二轮：真实足球场 Part C*

重新运行同一个入口：

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

选择：

```text
2
```

程序依次显示 football-field visible JPG、thermal JPG、TAT3 DOCX、target name、
stable target ID、surface cover、LUHK 和 confidence 的默认值。若屏幕路径正是你要
测试的 09:11 capture，可以逐项按 Enter；若不是，就粘贴真实路径。你不需要把
这些内容写进 JSON。

随后程序会问是否重画已接受的 football-field polygon。第一次运行按 Enter；若要
复验或修订旧边界，输入 `y`，程序会只跳过这一张图的兼容 cache 并重新打开 Part
C*，不需要手动删除任何 cache 文件夹。

Part B0/Part B 显示真实 V/T 证据时，必须根据画面决定：

- `a`：只有 visible 与 thermal 确实是同一场景且完整覆盖时才接受 normal route；
- `r`：对应关系不可用但 thermal 有效时，拒绝并进入 Part C* polygon；
- `c`：取消本组，不得生成本次成功 canonical。

当前 09:11 足球场 visible 近景与 thermal 广角不宜作为可靠 normal 对应，验收
Part C* 时选择 `r`。程序提取真实温度后应打开 thermal polygon GUI。

在 polygon GUI 中：

1. 只沿足球场草地目标画边界；不要包含跑道、看台、建筑、树木、人员或设备；
2. 点击 `Clear / Redraw`，确认旧多边形清除且可重画；
3. 再画一个至少三点、覆盖合理的目标多边形；
4. 点击 `Accept`，窗口应关闭并继续 canonical、extremes、Part E；
5. 另开一次新 run 点击 `Cancel`，其 run 状态必须是 cancelled，不能新增成功
   canonical，也不能让取消的 capture 进入 Part E。

足球场的 LUHK 输入在当前 Part C* 中是目标范围内的
`user_supplied_luhk` context，不得伪装成官方逐像素 lookup。验收 canonical/spatial
时必须看到：

- polygon 内：`target_mask=true`，已接受的 cover/LUHK context 可为 known，有限
  温度才可 analysis eligible；
- polygon 外：`target_mask=false`，surface cover 和 LUHK 为 unknown，正式分析
  ineligible；
- 完整 thermal grid 仍保留用于审计，但场外像素不进入足球场正式 overall、逐图、
  spectrum 或 target statistics；
- spatial 图显示真实 thermal 底图和 polygon boundary，而不是黑白标签图。

在 `USER_RESULTS.md` 中查看足球场温度与 ΔT 摘要，再打开 canonical 的 min/max/q99
图。极值图只是一个功能，不等于 Part E 全部分析。

## 4. 第三轮：五张 pilot 加足球场的最终整批流程

重新启动：

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

选择：

```text
3
```

按第 3 节确认足球场路径、TAT3 参数和 polygon。五张 pilot 可命中 cache，足球场
可成功或命中其已接受 cache。temporal 问题仍按 Enter 选择默认 No，因为这六张
不是一个被确认的同地点同 ROI 时间组。

最终 `USER_RESULTS.md` 应同时列出六张图。验收重点：

- 五张 normal 的 source/measurement 是 visible-review/full-thermal；
- 足球场是 thermal-polygon/polygon-selected target；
- 两类 provenance 分层，不静默混成同一种测量；
- formal Part E、spectrum、spatial、统计表全部完成；
- 五张 normal 的总体行为不变；
- 足球场正式像素数只等于 polygon target 内像素数，场外不进入正式总体；
- LUHK official lookup 与 user-supplied target context 在表和图中可区分。

## 5. 单独验收 normal Part C GUI

2026-07-22 的真实桌面验收已经覆盖两个终止动作：`Cancel` 得到 false/cancelled，
没有写入本次成功 canonical；完整审核后的 `Accept` 得到 true/accepted，并继续
生成 canonical。下面仍保留为可重复执行的人工复验协议；不能用单元测试或自动
填充标签代替这项桌面操作。

五张已接受 pilot 会复用审核结果，所以要测试 GUI 本身，需要一组尚未有 accepted
Part C review、而且真实 V/T 对应可接受的输入。

启动：

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

选择：

```text
4
```

依次粘贴 visible JPG、thermal JPG；若已有对应 TAT3 report 就粘贴路径，否则按
提示仅在已存在兼容温度矩阵时留空。检查 Part B0 证据，只有确实同场景时才接受；
再检查 Part B contact sheet，确认 full thermal coverage 后接受。随后 normal Part C
GUI 应作为独立桌面进程打开。

GUI 必须显示：

- `Visible image + superpixel boundaries`：真实 visible 底图加边界；
- `Live review mask`：真实 visible 底图上的实时半透明标签；
- corresponding thermal panel；
- official LUHK context panel，或明确 unavailable 原因；
- LUHK 是 read-only 且与 surface cover 分开的提示。

按下列顺序手动验收：

1. 单击一个 superpixel，选区应变成黄色，状态栏列出 selected ID；
2. Ctrl+单击另一个 superpixel，两个区域应同时被选中；
3. 在右侧选一个 physical surface-cover 类别；
4. 点击 `Assign`，live overlay 立即变色，状态栏显示 `Assignment applied`；
5. 选择另一区域，点击 `Mark unknown`，它应显示灰色且 Unknown 计数增加；
6. 选择一区域点击 `Shadow`，overlay 变成 shadow 色，shadow 不得改掉 cover；
7. 点击 `No shadow`，只清除 shadow 状态；
8. 点击 `Undo`，刚才操作撤销；点击 `Redo`，操作恢复；
9. 点击 `Clear`，只清除当前选中区域的人工标签，不能清空整个图或 LUHK；
10. 点击 `Fill suggestions`，只把未审核区域填为机器建议；淡色 suggestion 变成正式
    overlay，但仍是一次可 Undo 的操作；
11. 在 Notes 输入备注，点击 `Save`，状态栏显示 draft saved；Save 不得生成成功
    canonical；
12. 若还有 unreviewed superpixel，点击 `Accept` 必须被阻止并显示剩余数量；
13. 完成或明确标为 unknown 后点击 `Accept`，窗口关闭并继续 canonical；
14. 对另一张从未成功处理的图点击 `Cancel`，该 run 必须 cancelled，不能创建本次
    successful canonical。

`Assign`、unknown、shadow、Undo/Redo 每一步都必须在 live overlay 和计数上有可见
反馈；不能要求用户靠猜测按钮是否生效。

## 6. 多时点 temporal 普通用户验收

只有在你有至少两张“同一物理地点、同一目标、每张都有独立接受且可比 ROI”的
真实 capture 时才做本节。对于足球场，09:11、14:08、17:04 可作为候选，但后两张
必须各自完成 Part C* polygon；不能复制 09:11 的图像坐标。

用“Several specific visible/thermal groups”把这些 capture 纳入同一次处理，避免把
同一航次目录里的无关图像也带入本次验收：

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

选择：

```text
6
```

逐组输入 09:11、14:08、17:04 的 visible/thermal 路径，空行结束；随后可输入以
分号分隔的多个真实 TAT3 DOCX。选择所有组使用 Part C*，为每张 capture 独立画并
接受足球场 ROI。共享 target 名称/ID 不等于共享图像坐标，任何旧 polygon 都不能
复制到另一姿态。只有 success/cache hit 且有合格 target/temperature 的图才会进入
后续候选列表。

当 temporal 问题出现时，先按 Enter 验证默认 No：应 clean skip，不影响普通
Part E。随后重跑同一输入，在该问题输入：

```text
y
```

程序会列出每张候选的 image ID、V/T 路径、capture time/source、GPS、target ID、
location ID、dataset、temperature source 和 measurement type。不要只凭时间接近或
同一文件夹分组。

对于一个已核实地点：

1. 输入 capture 编号，例如 `1,3-4`；
2. 输入 human-readable location/target name；
3. 输入稳定 `location_id`；
4. 输入每张 capture 已一致使用的稳定 `target_id`；
5. 输入唯一 `temporal_group_id`；
6. 在“same physical location”确认中，仅在证据充分时输入 `y`；
7. 在“accepted, comparable ROI”确认中，仅在每张都有独立接受的同目标 ROI 时
   输入 `y`；
8. 若出现 GPS/recorded-ID conflict，先人工检查；需要 override 时必须写具体原因；
9. pixel-level registration 默认输入 `n`；只有已做可靠配准且能说明 method 与稳定
   registration ID 时才输入 `y`；
10. 回答是否定义另一个 temporal group；可以建立多个互不重叠的地点组。

一个 capture 不能重复进入两个组。程序也不能自己把未选中的图塞进时间序列。

### 2026-07-22 已验证的三时点足球场实例

`run_20260722T053855Z` 的显式 group
`hkust-football-field-20260202` 使用三个独立接受的 Part C* polygon。EXIF local
times 是 09:11:28、14:08:15、17:04:53 `+08:00`；3/3 captures eligible，
`temporal_series_available=true`，状态为
`multi_capture_observed_series`。输出包括每张八类 spatial PNG（共 24 张）和八组
spectrum PNG/PDF pair。

已验证的 target-level 数值为：

- ROI mean 最大 38.792465 degC，最小 18.429496 degC，observed range
  20.362969 degC；
- ROI median range 20.549437 degC，q95 range 22.708586 degC；
- capture-level ROI max range 24.340452 degC；
- absolute observed pixels 从 4.0655761 到 44.443596 degC，range
  40.37802 degC；
- provisional TAT3 ambient 下的 ROI-mean delta-T range 为 24.36297 degC。

这三个 polygon 边界不同，所以 ROI status 是
`user_confirmed_varying_roi_target_level_only`。可以比较每个 capture 的目标总体摘要，
不能把相同 row/column 当成同一地面像素；pixelwise 状态必须为 unavailable，原因
`cross_capture_registration_not_confirmed`。采样只覆盖 09:11:28--17:04:53，状态
是 `partial_observation_window`，不是 full day。TAT3 exported ambient parameter
也只是 provisional，尚未独立验证为 meteorological air temperature。因此这些数值
不能证明 true daily extrema、same-pixel change，或精确复现历史口头“约 +26 degC”。

## 7. 怎样读 temporal 结果

先打开 run 的 `USER_RESULTS.md`，再进入：

```text
part_e/schema_0_2/<run_id>/temporal/temporal_run_summary.md
```

不要打开无 run ID 的旧共享目录或另一 run 的“最新”结果。每个显式组都有自己的
`<temporal_group_id>/temporal_summary.md`。这里应直接写出：

- eligible/submitted capture 数；
- hottest capture、时间和 image ID；
- coolest capture、时间和 image ID；
- primary ROI-mean observed peak-to-trough range；
- ROI median、q95、capture-level max 和 absolute-pixel range；
- ΔT range 是否因 ambient source/definition 不兼容而 unavailable；
- sampling window、间隔、最大 gap、day/night coverage 和排除原因；
- pixelwise analysis 是否可用及原因。

口径必须这样理解：

- ROI mean 是 primary target range；
- median 是较稳健的中心结果；
- q95 是较稳健的 hot-tail 结果，通常比单个 max 更适合讨论目标的高温尾部；
- absolute-pixel range 是所有 capture 中单个最热点减单个最冷点，最容易受噪声、
  小物体、emissivity 和错位影响；
- 未确认 registration 时，不得说两个极值坐标是同一地面像素；
- 09:00–17:00 只能叫 sampled daytime window，不能叫完整 daily range；
- 图中的 ROI quantile band 是单张图内的空间变化，不是 temporal confidence interval。

若只有一张兼容 capture，应明确 `single_capture_descriptive_no_trend`。若同地点或
ROI 没确认，应没有 trend。若温度定义可比但 ambient 定义不可比，可以有
temperature series，但 ΔT series 必须 unavailable。

## 8. 最终验收清单

- [ ] 只用 `.\.venv\Scripts\python.exe scripts\run_user_workflow.py` 即可开始普通用户流程。
- [ ] 用户无需编写 JSON/config，也无需复制长参数命令。
- [ ] 五张真实 pilot 均有 canonical、extremes、全部 spectrum、spatial、tables 和 QA。
- [ ] temporal 默认 No，No 不影响其他 Part E 功能，也不产生伪时间序列。
- [ ] 真实足球场可完成 Part C* polygon、温度提取、canonical、spatial 和 Part E。
- [ ] polygon 外 cover/LUHK unknown 且不进入正式 target/overall 统计。
- [ ] 五 pilot + 足球场同批运行时 source/provenance 分层清楚。
- [ ] normal Part C GUI 使用真实 visible+superpixel overlay，而不是孤立黑白标签图。
- [ ] Assign、unknown、shadow/no-shadow、Undo/Redo、Save、Accept、Cancel 都有可见反馈。
- [ ] Accept 只在 review 完整时成功；Cancel/Save/关窗不能创建本次成功 canonical。
- [ ] normal LUHK 是官方只读 context，与 surface cover 分离；unavailable 不伪造。
- [ ] temporal 只接收用户显式选择、同地点确认和可比 ROI 确认的 capture。
- [ ] 支持多个互不重叠 temporal group，不按文件夹/时间/GPS 自动分组。
- [ ] hottest、coolest、observed range、median/q95 与 absolute pixel 的含义写清楚。
- [ ] sampling gaps 和 sampled-window 限制清楚，不把 09–17 宣称为 full day。
- [ ] 未确认可靠 registration 时没有 pixelwise temporal maps。
- [ ] Part E、spatial、spectrum、temporal、tables 和 QA 都来自同一个 `<run_id>`，
      不混用共享旧目录或另一 run 的结果。
- [ ] `USER_RESULTS.md` 能让普通用户直接找到每个结果，不要求阅读 raw JSON。

以上每一项都能由用户亲眼看到，才算 v0.3.2 普通用户验收通过。
