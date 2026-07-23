# v0.2 用户验收测试文档

本文档用于从“实际使用者”的角度验收 `heat_index_urop` v0.2。它回答四个问题：怎么运行、一个 case 一个 case 怎么看、输出在哪里、什么结果才算通过。

本轮必须完成的两项现场验收是：

1. 五个已选 pilot 必须在同一次请求中完整走过 A–E，并逐个检查结果。
2. HKUST 足球场素材必须作为 V/T 对不上的 case，先停在人工复核，再由人工拒绝对应关系并完整进入 Part C*。

## 1. 验收原则

- 在仓库根目录 `E:\Projects\heat_index_urop` 的 PowerShell 中执行全部命令。
- 原始 DJI 文件只读；不要移动、改名或覆盖 `data/raw/` 下的文件。
- 使用 `config/workflow_v0_2_acceptance.json`。所有持久工作流验收输出都进入被 Git 忽略的 `outputs/runs/v0_2_user_acceptance/`，不会写入正式 `data/processed/images/` 或正式结果索引。
- 五 pilot 的兼容路线会复用已经人工复核的 Part C mask 和已经成功提取的 Part D 温度矩阵。这验证的是 v0.2 支持入口的 A–E 串联和数值兼容性，不代表重新操作了一遍 GUI，也不代表重新调用了真实 DJI SDK。
- 足球场路线使用真实 V/T 图像、真实 TAT3 环境温度，但本测试文档生成的温度矩阵是**路线测试专用的合成矩阵**。它只能验收路由、尺寸、polygon、schema、extreme 和 Part E 接线，绝不能当作足球场科学温度结果。
- 自动 Part B 分数只是候选证据。只有最终人工接受且覆盖整个 thermal 的 Part B 才能进入普通 Part C。
- B0 的显式人工决定高于自动 triage candidate：`accepted` 只允许继续 full Part B，绝不直接接受 alignment；`rejected` 进入 C*；`cancelled` 停止。没有人工决定的新 mismatch candidate 仍直接进入 C*。
- `pytest` 的临时 case 在测试结束后会删除临时目录；其可保存证据是控制台日志和 JUnit XML。持久入口的 JSON、NPY、Parquet、CSV、PNG/PDF 则保留在验收目录。

## 2. 一次性准备

### UAT-00：确认代码、环境和测试隔离

```powershell
Set-Location E:\Projects\heat_index_urop
git branch --show-current
git status --short
Test-Path .\.venv\Scripts\python.exe
Test-Path config\workflow_v0_2_acceptance.json
Test-Path data\metadata\part_b_pilot_pairs.xlsx
```

预期：

- 分支为 `codex/heat-index-urop-0.2`。
- `commit_code_exports/` 可以显示为用户自有未跟踪目录；不要进入、修改、删除或提交它。
- Python、验收 config 和 pilot 表均返回 `True`。

设置本次 PowerShell 会话会反复使用的变量：

```powershell
$Py = ".\.venv\Scripts\python.exe"
$Runner = "scripts\run_analysis.py"
$Cfg = "config\workflow_v0_2_acceptance.json"
$UatRoot = "outputs\runs\v0_2_user_acceptance"
$PilotDir = "data\raw\HKUST\20260107_Thermal_HKUST\DCIM\DJI_202601071424_001"
$SoccerDir = "data\raw\HKUST\20260202_Thermal_HKUST\DCIM\DJI_202602020853_001"
$SoccerId = "DJI_20260202091128_0058"
$SoccerV = "$SoccerDir\DJI_20260202091127_0058_V.JPG"
$SoccerT = "$SoccerDir\DJI_20260202091128_0058_T.JPG"
```

如果尚未安装环境：

```powershell
C:\Users\Victo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m venv .venv
& $Py -m pip install --upgrade pip
& $Py -m pip install -r requirements.txt
$env:MPLCONFIGDIR = "$PWD\.matplotlib-cache"
```

### UAT-01：建立可保存的测试日志

```powershell
New-Item -ItemType Directory -Force "$UatRoot\test_logs" | Out-Null
& $Py -m pytest --collect-only -q 2>&1 |
    Tee-Object "$UatRoot\test_logs\pytest_collect.log"
```

本版本预期收集到 `48 tests`。收集清单保存在：

`outputs/runs/v0_2_user_acceptance/test_logs/pytest_collect.log`

### UAT-02：需要“第一次运行/cache miss”时重置验收沙箱

仅删除本文件指定的验收目录，不要删除 `outputs/runs/`、`outputs/` 或 `data/processed/`：

```powershell
if (Test-Path -LiteralPath $UatRoot) {
    (Resolve-Path -LiteralPath $UatRoot).Path
}
```

确认打印的绝对路径严格等于：

`E:\Projects\heat_index_urop\outputs\runs\v0_2_user_acceptance`

然后才执行：

```powershell
Remove-Item -Recurse -Force -LiteralPath $UatRoot
New-Item -ItemType Directory -Force "$UatRoot\test_logs" | Out-Null
```

## 3. 输出地图：先知道去哪里看

| 输出 | 路径 | 用途 |
|---|---|---|
| 每次请求总表 | `outputs/runs/v0_2_user_acceptance/workflow_runs/run_<UTC>/run_summary.json` | 每组 route、status、reason 和证据路径 |
| A/B0/B 临时证据 | 同一 run 下的 `groups/<image_id>/` | `part_a.json`、`part_b0/part_b0.json`、`part_b/part_b.json` 和 review 图 |
| 每图 canonical | `outputs/runs/v0_2_user_acceptance/canonical/images/<image_id>/` | manifest、温度、labels、known/target/shadow mask、pixels Parquet、extremes |
| 验收结果索引 | `outputs/runs/v0_2_user_acceptance/canonical/result_index.json` | cache 依赖和 canonical manifest 定位 |
| 多来源合并 | `outputs/runs/v0_2_user_acceptance/part_e/` | combined Parquet、source summary、dashboard |
| 正式 Part E | `outputs/runs/v0_2_user_acceptance/part_e/schema_0_2/` | sample、statistics、effect size、KDE、图、QA、报告 |
| pytest 日志 | `outputs/runs/v0_2_user_acceptance/test_logs/` | 全量/单 case 控制台日志和 JUnit XML |
| 临时 TAT3 | 本文指定的 `outputs/runs/v0_2_user_acceptance/tat3_soccer_ambient_only/` | temporary manifest 和解释；不进 canonical/index |

找最新一次 run：

```powershell
$LatestRun = Get-ChildItem "$UatRoot\workflow_runs" -Directory |
    Sort-Object LastWriteTime |
    Select-Object -Last 1
$LatestRun.FullName
Get-Content "$($LatestRun.FullName)\run_summary.json"
```

状态解释：

| status | 是否通过当前边界 | 解释 |
|---|---|---|
| `success` | 是 | 本组已创建 schema 0.2 canonical |
| `cache_hit` | 是 | 所有依赖和 artifact hash 兼容，复用了成功结果 |
| `awaiting_part_b0_review` | 是，等待人 | B0 模糊或 Part A 配对不确定，禁止静默向下走 |
| `awaiting_part_b_review` | 是，等待人 | 已有 full Part B 候选，但没有最终人工决定 |
| `awaiting_part_c_review` | 是，等待人 | superpixel review 未最终接受 |
| `cancelled` | 是，按用户操作停止 | 不得生成新的成功 canonical，不得进入 Part E |
| `failed` | 对负面 case 是预期 | fatal thermal 或 QA fail |
| `incomplete` | 需要按 reason 判断 | 缺温度、缺 polygon 上下文、尺寸冲突等输入未完成 |

## 4. 必测一：五个 pilot 完整 A–E 联跑

### PILOT-00：五个输入必须全部存在

```powershell
$PilotIds = @(
    "DJI_20260107143259_0005",
    "DJI_20260107143320_0007",
    "DJI_20260107143328_0008",
    "DJI_20260107143344_0009",
    "DJI_20260107143401_0011"
)

foreach ($Id in $PilotIds) {
    [pscustomobject]@{
        image_id = $Id
        visible = Test-Path "$PilotDir\${Id}_V.JPG"
        thermal = Test-Path "$PilotDir\${Id}_T.JPG"
    }
}
```

五行的 `visible` 和 `thermal` 都必须是 `True`。

### PILOT-01：同一次请求完整跑五组

先执行 UAT-02，确保这是 cache miss。然后运行：

```powershell
& $Py $Runner --config $Cfg `
    selected `
    --dataset-id HKUST_five_pilot_acceptance `
    --group "$PilotDir\DJI_20260107143259_0005_V.JPG" "$PilotDir\DJI_20260107143259_0005_T.JPG" `
    --group "$PilotDir\DJI_20260107143320_0007_V.JPG" "$PilotDir\DJI_20260107143320_0007_T.JPG" `
    --group "$PilotDir\DJI_20260107143328_0008_V.JPG" "$PilotDir\DJI_20260107143328_0008_T.JPG" `
    --group "$PilotDir\DJI_20260107143344_0009_V.JPG" "$PilotDir\DJI_20260107143344_0009_T.JPG" `
    --group "$PilotDir\DJI_20260107143401_0011_V.JPG" "$PilotDir\DJI_20260107143401_0011_T.JPG" `
    2>&1 | Tee-Object "$UatRoot\test_logs\five_pilot_first_run.log"
```

第一次运行预期：

- `Groups requested: 5`。
- 五组都是 `success via normal_visible_thermal - canonical_result_created`。
- 进程退出码为 0；可立即查看 `$LASTEXITCODE`。
- 五组都有 Part A、B0、full Part B 证据。
- normal Part C/Part D 使用已验证五 pilot adapter，写出 schema 0.2 canonical。
- 五个 manifest 都标记 `source_method = visible_review`、`measurement_type = full_thermal_pixel`、`scene_correspondence = accepted` 和 `coverage_class = thermal_fully_supported_by_visible`。
- Part E 收到五个成功 manifest，并生成正式输出。

本机 2026-07-17 的一次真实 cache-miss 实测约 528 秒（约 8.8 分钟），随后五图 cache-hit 复跑约 11 秒。它们是本机观察值，不是跨机器 SLA。入口只在所有阶段结束时打印最终 summary；中途只出现部分 canonical 目录不算通过，不要给真实五图设置两分钟硬超时。

当前五 pilot 的初始 B0 阈值可能给出 `content_mismatch_candidate`，这正体现了阈值尚未由五图一般化校准。pilot 的下游人工 reviewed mask 与成功 Part D grid 是已有的显式验证证据，因此 `part_b0.json` 应同时记录自动 triage 和 `manual_review_status = accepted`，再继续 full Part B；不得把自动候选字段改写成“自动通过”。新图没有这些验证证据时不会获得该兼容处理。

日志位置：

`outputs/runs/v0_2_user_acceptance/test_logs/five_pilot_first_run.log`

### PILOT-02：五个 pilot 一个一个检查

```powershell
foreach ($Id in $PilotIds) {
    $Dir = "$UatRoot\canonical\images\$Id"
    $Manifest = Get-Content "$Dir\manifest.json" -Raw | ConvertFrom-Json
    [pscustomobject]@{
        image_id = $Id
        schema = $Manifest.schema_version
        status = $Manifest.processing_status
        route = $Manifest.processing_route
        measurement = $Manifest.measurement_type
        source = $Manifest.source_method
        qa = $Manifest.qa_status
        dimensions = "$($Manifest.image_height)x$($Manifest.image_width)"
        known = $Manifest.known_pixel_count
        unknown = $Manifest.unknown_pixel_count
        pixels = Test-Path "$Dir\pixels.parquet"
        extremes_csv = Test-Path "$Dir\extreme_temperature_summary.csv"
        extremes_png = Test-Path "$Dir\extreme_temperature_locations.png"
    }
}
```

每一行必须满足：

- schema `0.2.0`；status `success`；route `normal_visible_thermal`；measurement `full_thermal_pixel`；source `visible_review`。
- dimensions `512x640`。
- `known + unknown = 327680`。
- `pixels`、`extremes_csv`、`extremes_png` 均为 `True`。
- QA 可以是 `pass` 或保留历史验证警告的 `warn`，但不能是 `fail`。

逐图打开重点证据：

1. `<image>/manifest.json`：看 Part A、Part B0、Part B、provenance、QA、artifact hash。
2. `<image>/extreme_temperature_summary.csv`：看 min/max/q01/median/q95/q99、delta 和计数。
3. `<image>/extreme_temperature_coordinates.csv`：看 deterministic min/max 坐标和所有 tie 坐标。
4. `<image>/extreme_temperature_locations.png`：看 min、max、q99 threshold/exceedance overlay。
5. `<image>/pixels.parquet`：canonical pixel rows；默认没有 full-pixel CSV/Excel。

### PILOT-03：核对冻结的数值基线

```powershell
& $Py -m pytest -vv `
    tests/test_v02_pilot_numeric_baseline.py `
    tests/test_pilot_regression.py `
    2>&1 | Tee-Object "$UatRoot\test_logs\five_pilot_numeric_regression.log"
```

重点通过标准：

- 五个 reviewed mask 的 SHA-256 与冻结值相同。
- 每图温度矩阵都是 `512 × 640 = 327680` 行；五图合计 `1638400` 像素。
- 温度 min/max/mean/q99 和环境温度在 `2e-6` 绝对容差内与冻结基线相同。
- Part E 每图 delta-T mean 与基线一致；roof 和 GIC/open-space 的关键统计量一致。
- 本地 legacy Part E Parquet 存在时，其行数必须是 `5 × 512 × 640`。

### PILOT-04：检查五图 Part E 输出

```powershell
Get-Item "$UatRoot\part_e\part_e_multi_source_pixels.parquet"
Import-Csv "$UatRoot\part_e\source_summary.csv" | Format-Table -AutoSize
Get-ChildItem "$UatRoot\part_e\schema_0_2\tables" -File
Get-ChildItem "$UatRoot\part_e\schema_0_2\figures\spectrum" -File
Get-ChildItem "$UatRoot\part_e\schema_0_2\qa" -File
```

必须至少存在：

- `part_e_pixel_sample_coverage.csv`
- `part_e_pixel_statistical_tests.csv`
- `part_e_pixel_effect_sizes.csv`
- `part_e_pixel_delta_t_spectrum_summary.csv`
- `part_e_inclusion_exclusion.csv`
- `part_e_sampling_reproducibility.csv`
- spectrum PNG/PDF 和正式报告

统计/图中必须保留 image/time、measurement type、temperature source、surface-cover provenance、LUHK provenance、target 和 QA 分层。默认不得出现把不同 source 当同类独立观测静默混池的主结论。

### PILOT-05：第二次原命令验证 cache

原样再次执行 PILOT-01 命令。预期五组都显示：

`cache_hit via cached_result - compatible_canonical_result`

然后检查新 `run_summary.json` 中五个 `cache_hit = true`。如果任何一组不是 cache hit，先看其 `reason`，再运行自动 cache case，不要直接判定为性能问题。

### PILOT-06：需要单独重跑某一个 pilot 时

下面以 0005 为例；替换 ID 即可逐个运行：

```powershell
$Id = "DJI_20260107143259_0005"
& $Py $Runner --config $Cfg --no-part-e `
    selected --dataset-id "single_$Id" `
    --group "$PilotDir\${Id}_V.JPG" "$PilotDir\${Id}_T.JPG"
```

这用于逐图排错，不替代 PILOT-01 的五图同批 Part E 验收。已有兼容结果时会命中 cache；若必须看 cache miss，请重置验收沙箱后再跑。

## 5. 必测二：足球场 V/T 对不上 case

真实素材：

- Visible：`DJI_20260202091127_0058_V.JPG`，4032 × 3024，画面是足球场中圈近景。
- Thermal：`DJI_20260202091128_0058_T.JPG`，640 × 512，画面是包含整个体育场和周边的广角热图。
- 二者 sample number 都是 `0058`，但时间戳相差 1 秒、空间覆盖明显不一致。因此这个 case 同时测试 Part A pairing uncertainty、B0 人工边界和拒绝后进入 C*。

### SOCCER-00：确认真实文件和画面尺寸

```powershell
@'
from pathlib import Path
from PIL import Image
for value in (
    r"data/raw/HKUST/20260202_Thermal_HKUST/DCIM/DJI_202602020853_001/DJI_20260202091127_0058_V.JPG",
    r"data/raw/HKUST/20260202_Thermal_HKUST/DCIM/DJI_202602020853_001/DJI_20260202091128_0058_T.JPG",
):
    path = Path(value)
    with Image.open(path) as image:
        print(path.name, image.size, image.mode)
'@ | & $Py -
```

预期分别为 `(4032, 3024)` 和 `(640, 512)`。先用普通图片查看器目视确认上述近景/广角差异。

### SOCCER-01：不提供决定，必须停在 B0 人工复核

```powershell
& $Py $Runner --config $Cfg --no-part-e `
    selected --dataset-id HKUST_soccer_mismatch_observation `
    --group $SoccerV $SoccerT `
    2>&1 | Tee-Object "$UatRoot\test_logs\soccer_awaiting_b0.log"
```

因为 V/T image ID/time 不完全一致且没有显式决定，预期：

- 控制台和 `run_summary.json` 为 `awaiting_part_b0_review`。
- 不生成该足球场图的成功 canonical manifest。
- `part_a.json` 保留 identifier/time pairing warning。
- `part_b0.json` 保留算法版本、candidate crop、各 feature score、overall score、threshold、confidence、triage state、reasons/warnings 和 diagnostic 路径。
- 无论自动分数看起来多好，都不能静默进入 normal Part C。

检查最新证据：

```powershell
$LatestRun = Get-ChildItem "$UatRoot\workflow_runs" -Directory |
    Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content "$($LatestRun.FullName)\groups\$SoccerId\part_a.json"
Get-Content "$($LatestRun.FullName)\groups\$SoccerId\part_b0\part_b0.json"
Test-Path "$UatRoot\canonical\images\$SoccerId\manifest.json"
```

最后一项在全新沙箱中必须为 `False`。

### SOCCER-02：生成仅用于路线验收的 512 × 640 合成温度矩阵

```powershell
$SoccerTestNpy = "$UatRoot\fixtures\soccer_route_only_temperature.npy"
New-Item -ItemType Directory -Force "$UatRoot\fixtures" | Out-Null
& $Py -c "from pathlib import Path; import numpy as np; p=Path(r'$SoccerTestNpy'); p.parent.mkdir(parents=True, exist_ok=True); np.save(p, np.linspace(18.0, 42.0, 512*640, dtype=np.float32).reshape(512, 640)); print(p, np.load(p).shape)"
```

预期打印 `(512, 640)`。再次强调：这不是 DJI radiometric temperature，不可用于科学比较。

### SOCCER-03：人工拒绝 V/T 对应，完整进入 Part C*

仓库提供三个小型验收输入：

- `config/acceptance/v0_2_soccer_b0_rejected.json`：人工拒绝 V/T content match。
- `config/acceptance/v0_2_soccer_polygon.json`：测试用足球场 polygon、target、cover、LUHK、provenance、confidence 和 notes。
- `config/acceptance/v0_2_soccer_ambient.json`：来自真实 TAT3 report 的 10.8°C ambient。

运行：

```powershell
& $Py $Runner --config $Cfg `
    --part-b0-review config\acceptance\v0_2_soccer_b0_rejected.json `
    --polygon-json config\acceptance\v0_2_soccer_polygon.json `
    --temperature-npy "$SoccerId=$SoccerTestNpy" `
    --ambient-json config\acceptance\v0_2_soccer_ambient.json `
    selected --dataset-id HKUST_soccer_mismatch_to_polygon `
    --group $SoccerV $SoccerT `
    2>&1 | Tee-Object "$UatRoot\test_logs\soccer_polygon_route.log"
```

预期：

- `success via thermal_polygon - canonical_result_created`。
- full Part B 和 normal Part C 均不得成为最终路线。
- canonical manifest 是 schema `0.2.0`、route `thermal_polygon`、measurement `polygon_selected_thermal_pixel`。
- `surface_cover_provenance = thermal_polygon_user_annotation`。
- `target_name = HKUST soccer field`、cover 为 `grass_low_vegetation`。
- LUHK 为 `GIC / open space`，provenance 必须是 `user_supplied_luhk`，不得伪装成 `official_luhk_lookup`。
- inside polygon：target、cover known、LUHK known、finite analysis eligible 都为 true。
- outside polygon：target false、cover/LUHK unknown、target analysis ineligible；完整温度矩阵仍保留。
- `target_mask.npy` 与两个 known mask 分开保存。
- 极值图画出 polygon boundary、min/max、q99 threshold 和 q99 exceedance region。

一键核对 manifest/mask：

```powershell
@'
from pathlib import Path
import json
import numpy as np

root = Path("outputs/runs/v0_2_user_acceptance/canonical/images/DJI_20260202091128_0058")
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
target = np.load(root / "target_mask.npy")
cover_known = np.load(root / "surface_cover_known_mask.npy")
luhk_known = np.load(root / "luhk_known_mask.npy")

print({key: manifest.get(key) for key in (
    "schema_version", "processing_status", "processing_route", "measurement_type",
    "source_method", "surface_cover_provenance", "luhk_provenance", "target_name",
    "known_pixel_count", "unknown_pixel_count", "qa_status",
)})
print("shape", target.shape)
print("target/cover/luhk known", int(target.sum()), int(cover_known.sum()), int(luhk_known.sum()))
print("outside unknown", int((~target).sum()))
assert target.shape == (512, 640)
assert np.array_equal(target, cover_known)
assert np.array_equal(target, luhk_known)
assert 0 < target.sum() < target.size
assert manifest["processing_route"] == "thermal_polygon"
assert manifest["measurement_type"] == "polygon_selected_thermal_pixel"
assert manifest["luhk_provenance"] == "user_supplied_luhk"
'@ | & $Py -
```

### SOCCER-04：人工画 polygon 的 GUI smoke test

配置中的 polygon 是可复现路线 fixture，confidence 故意是 low。真正操作验收时，先目视确认；若坐标不合适，应通过 GUI 重画，不能把 fixture 当研究标注。

要测试 GUI，先重置验收沙箱并重新执行 SOCCER-02，然后不传 `--polygon-json`：

```powershell
& $Py $Runner --config $Cfg `
    --part-b0-review config\acceptance\v0_2_soccer_b0_rejected.json `
    --surface-cover grass_low_vegetation `
    --target-name "HKUST soccer field" `
    --luhk "GIC / open space" `
    --luhk-provenance user_supplied_luhk `
    --reviewer-confidence high `
    --notes "Manually redrawn soccer field acceptance polygon" `
    --temperature-npy "$SoccerId=$SoccerTestNpy" `
    --ambient-json config\acceptance\v0_2_soccer_ambient.json `
    selected --dataset-id HKUST_soccer_manual_polygon `
    --group $SoccerV $SoccerT
```

在 GUI 中检查：Draw、Clear/Redraw、无有效 polygon 时 Accept 被阻止、Accept、Cancel。接受后重复 SOCCER-03 的 mask 检查。Cancel 必须在**全新验收沙箱**中检查，以免把上一次残留 manifest 误认为本次生成；取消后的本次 run summary 应为 `cancelled`，且没有本次成功结果进入 Part E。

### SOCCER-05：五个 normal pilot + 一个 polygon soccer 的多来源 Part E

完成 PILOT-01 和 SOCCER-03 后，用相同参数把六组放进同一次请求。它们通常会显示 cache hit，但 Part E 会收到全部六个兼容 manifest：

```powershell
& $Py $Runner --config $Cfg `
    --part-b0-review config\acceptance\v0_2_soccer_b0_rejected.json `
    --polygon-json config\acceptance\v0_2_soccer_polygon.json `
    --temperature-npy "$SoccerId=$SoccerTestNpy" `
    --ambient-json config\acceptance\v0_2_soccer_ambient.json `
    selected --dataset-id HKUST_multi_source_acceptance `
    --group "$PilotDir\DJI_20260107143259_0005_V.JPG" "$PilotDir\DJI_20260107143259_0005_T.JPG" `
    --group "$PilotDir\DJI_20260107143320_0007_V.JPG" "$PilotDir\DJI_20260107143320_0007_T.JPG" `
    --group "$PilotDir\DJI_20260107143328_0008_V.JPG" "$PilotDir\DJI_20260107143328_0008_T.JPG" `
    --group "$PilotDir\DJI_20260107143344_0009_V.JPG" "$PilotDir\DJI_20260107143344_0009_T.JPG" `
    --group "$PilotDir\DJI_20260107143401_0011_V.JPG" "$PilotDir\DJI_20260107143401_0011_T.JPG" `
    --group $SoccerV $SoccerT `
    2>&1 | Tee-Object "$UatRoot\test_logs\six_group_multi_source.log"
```

通过标准：source summary/dashboard 同时出现：

- `visible_review` + `full_thermal_pixel`；
- `thermal_polygon_user_annotation` + `polygon_selected_thermal_pixel`。

跨图汇总使用 equal-image 逻辑；不能因某图有更多像素而支配跨图平均。主结果分来源展示，不静默 pool。

## 6. Normal Part C superpixel GUI 人工验收

五 pilot adapter 不会让用户重新标完五张图。GUI 本身应按以下清单另测一次：

1. 使用一个 final Part B 已接受、覆盖为 `thermal_fully_supported_by_visible`、尚无 accepted Part C review 的 normal case，加 `--launch-part-c-gui` 运行。
2. 检查 visible ROI、superpixel boundary、thermal panel、颜色、legend 和明显的 unreviewed 区域。
3. 单击一段，Ctrl-click 多选，赋一个物理 cover，所有选中 segment 同时变化。
4. 标记 unknown/unclear；它必须保持 analysis-ineligible。
5. 单独切换 shadow；surface cover 不得随 shadow 改变。
6. 测 clear、undo、redo。
7. 填 notes、reviewer、confidence；保存 draft，关闭并 resume，状态必须完全一致。
8. 存在未审 segment 时 Accept 必须被阻止。
9. 全部完成后 Accept，生成 auditable review JSON 和 native-grid mask。
10. 另开一份 draft 后 Cancel；不得创建成功 canonical 或进入 Part E。

可先用下面的 headless controller case 验证全部状态逻辑，再做一次桌面 smoke test：

```powershell
& $Py -m pytest -vv -s tests/test_v02_part_c_controller.py `
    2>&1 | Tee-Object "$UatRoot\test_logs\part_c_controller.log"
```

普通入口还必须验证：裸 `--normal-labels-npy` 会被拒绝；兼容 override 必须同时有 accepted review manifest，且 image ID、shape、mapping、reviewer/source 和 artifact SHA-256 都匹配。

## 7. 真实足球场 TAT3 ambient-only report

本机实际包含足球场 thermal ID 的 report 是：

`data/local_external/tat3_reports/raw/combined_report__2026_07_17_18_12_48.docx`

它是 ambient/parameter report，不是 point/region measurement report。运行：

```powershell
$ProductionIndex = "data\metadata\canonical_result_index.json"
$IndexBefore = if (Test-Path $ProductionIndex) { (Get-FileHash $ProductionIndex -Algorithm SHA256).Hash } else { "ABSENT" }

& $Py scripts\run_tat3_manual_analysis.py `
    --report "data\local_external\tat3_reports\raw\combined_report__2026_07_17_18_12_48.docx" `
    --thermal-image $SoccerT `
    --target-name "HKUST soccer field" `
    --luhk "GIC / open space" `
    --luhk-provenance user_supplied_luhk `
    --surface-cover grass_low_vegetation `
    --output-dir "$UatRoot\tat3_soccer_ambient_only" `
    2>&1 | Tee-Object "$UatRoot\test_logs\tat3_soccer_ambient_only.log"

$IndexAfter = if (Test-Path $ProductionIndex) { (Get-FileHash $ProductionIndex -Algorithm SHA256).Hash } else { "ABSENT" }
$IndexBefore -eq $IndexAfter
```

本机预期：

- `TAT3 layout: ambient_metadata_only`
- `Measurement records: 0`
- `Persistence scope: temporary_session`
- image ID `DJI_20260202091128_0058`
- capture time `2026-02-02 09:11:28`
- ambient/reflected temperature `10.8°C`
- distance `5 m`、emissivity `0.95`、reported humidity `50%`
- 只生成 `temporary_manifest.json` 和 `temporary_analysis.md`；不制造点、坐标、region、Parquet measurement 或 location figure。
- 最后的 index hash 比较为 `True`；不得写入正式 canonical warehouse/main Part E。

三个已命名真实 local report 合计 185 entries 的回归 case：

```powershell
& $Py -m pytest -vv -s `
    tests/test_v02_tat3_manual.py::test_named_local_ambient_reports_have_185_entries_and_no_manual_measurements `
    2>&1 | Tee-Object "$UatRoot\test_logs\tat3_real_185_entries.log"
```

point、multiple points、region、mixed、缺坐标、缺 ambient、ID mismatch、invalid units、duplicate IDs 使用小型合成 parser fixtures 测试，不能从真实 ambient-only report 伪造。

## 8. 全量自动测试

### AUTO-ALL：一次跑完

```powershell
New-Item -ItemType Directory -Force "$UatRoot\test_logs" | Out-Null
& $Py -m pytest -vv `
    --junitxml "$UatRoot\test_logs\pytest_results.xml" `
    2>&1 | Tee-Object "$UatRoot\test_logs\pytest_full.log"
$LASTEXITCODE
```

本工作区完整通过标准：`48 passed`、退出码 0。证据：

- `outputs/runs/v0_2_user_acceptance/test_logs/pytest_full.log`
- `outputs/runs/v0_2_user_acceptance/test_logs/pytest_results.xml`

### 一个 case 一个 case 跑的方法

通用格式：

```powershell
$Case = "tests/test_file.py::TestClass::test_method"
& $Py -m pytest -vv -s $Case 2>&1 |
    Tee-Object "$UatRoot\test_logs\single_case.log"
```

以下是全部 48 个自动 case。每一项都可把 node ID 放进 `$Case` 单独运行。

#### Part A、B0、full Part B 和 routing（15）

| 自动 case | 主要验收点 |
|---|---|
| `tests/test_v02_part_a_b0_and_full_b.py::PartAAndB0Tests::test_part_a_metadata_and_native_shape_validation` | camera/altitude/GPS/shape；native matrix mismatch |
| `tests/test_v02_part_a_b0_and_full_b.py::PartAAndB0Tests::test_visible_only_failure_routes_to_polygon_and_identifier_mismatch_needs_review` | visible-only → C*；ID/time mismatch → review |
| `tests/test_v02_part_a_b0_and_full_b.py::PartAAndB0Tests::test_b0_match_mismatch_ambiguous_and_manual_routes` | B0 三状态；accept/reject/cancel |
| `tests/test_v02_part_a_b0_and_full_b.py::FullPartBAdapterTests::test_existing_candidate_evidence_is_retained_but_review_controls_route` | candidate/GCP/review evidence；人工决定控制 route |
| `tests/test_routing.py::RoutingTests::test_auto_candidate_never_implies_acceptance` | 自动候选不能自动接受 |
| `tests/test_routing.py::RoutingTests::test_cancelled_part_b_does_not_enter_polygon` | Part B cancel 不得偷转 C* |
| `tests/test_routing.py::RoutingTests::test_final_status_takes_precedence_over_candidate_quality` | final review 高于 candidate score |
| `tests/test_routing.py::RoutingTests::test_manual_full_coverage_acceptance_enters_normal_route` | 人工接受 + full coverage → normal Part C |
| `tests/test_routing.py::RoutingTests::test_missing_thermal_fails` | thermal missing fatal |
| `tests/test_routing.py::RoutingTests::test_unusable_visible_with_valid_thermal_enters_polygon` | thermal valid、visible unusable → C* |
| `tests/test_workflow_models_and_inputs.py::InputValidationTests::test_dataset_discovery_retains_thermal_only_fallback_groups` | dataset discovery 保留 thermal-only group |
| `tests/test_workflow_models_and_inputs.py::InputValidationTests::test_invalid_thermal_fails_clearly` | invalid thermal 明确失败 |
| `tests/test_workflow_models_and_inputs.py::InputValidationTests::test_missing_thermal_fails_clearly` | missing thermal 明确失败 |
| `tests/test_workflow_models_and_inputs.py::InputValidationTests::test_valid_vt_group_returns_structured_record` | valid V/T structured Part A record |
| `tests/test_v02_run_analysis_routes.py::RunAnalysisV02Routes::test_needs_part_b0_review_cannot_silently_enter_part_c` | awaiting B0 不生成 canonical |

#### 支持入口 integration（5）

| 自动 case | 主要验收点 |
|---|---|
| `tests/test_v02_run_analysis_routes.py::RunAnalysisV02Routes::test_verified_normal_route_runs_a_to_e_on_cache_miss_then_hits_cache` | normal A–E cache miss 后 cache hit |
| `tests/test_run_analysis_integration.py::RunAnalysisIntegrationTests::test_rejected_b0_uses_polygon_then_cache_and_part_e` | B0 reject → polygon → Part E → cache |
| `tests/test_run_analysis_integration.py::RunAnalysisIntegrationTests::test_cancelled_polygon_does_not_enter_part_e` | polygon cancel 不进 Part E |
| `tests/test_run_analysis_integration.py::RunAnalysisIntegrationTests::test_invalid_thermal_fails_without_annotation` | fatal thermal 不能被 annotation 绕过 |
| `tests/test_part_e_multi_source.py::PartEMultiSourceTests::test_normal_and_polygon_results_keep_separate_provenance` | normal/polygon 共存但 provenance 分开 |

#### Normal Part C、Part C* 和 canonical（8）

| 自动 case | 主要验收点 |
|---|---|
| `tests/test_v02_part_c_controller.py::PartCControllerTests::test_multi_assignment_unknown_shadow_undo_redo_and_masks` | 多选赋值、unknown、shadow 独立、undo/redo、mask |
| `tests/test_v02_part_c_controller.py::PartCControllerTests::test_draft_resume_cancel_and_bare_override_rejection` | draft/resume/cancel；裸 NPY 拒绝 |
| `tests/test_polygon_and_canonical.py::PolygonCanonicalTests::test_polygon_inside_known_outside_unknown` | polygon inside/outside 语义 |
| `tests/test_polygon_and_canonical.py::PolygonCanonicalTests::test_polygon_requires_luhk_dimension_match_and_preserves_provenance_kind` | LUHK required、dimension、provenance |
| `tests/test_polygon_and_canonical.py::PolygonCanonicalTests::test_cancelled_annotation_cannot_be_successful_canonical_result` | cancel 不可写 success |
| `tests/test_polygon_and_canonical.py::PolygonCanonicalTests::test_dynamic_dimensions_and_optional_shadow` | 动态尺寸和可选 shadow |
| `tests/test_polygon_and_canonical.py::PolygonCanonicalTests::test_unknown_storage_sentinel_is_enforced` | unknown sentinel 不是物理类别 |
| `tests/test_part_e_dynamic_sampling.py::DynamicSamplingTests::test_variable_native_shapes_are_sampled_deterministically` | 不同 native shapes 的 deterministic sampling |

#### Cache、schema、atomic、extremes（6）

| 自动 case | 主要验收点 |
|---|---|
| `tests/test_result_index.py::ResultIndexTests::test_compatible_cache_hit_and_hash_mismatch` | compatible hit 和 raw hash mismatch |
| `tests/test_v02_cache_schema_extremes.py::CacheAndSchemaTests::test_dependency_and_artifact_corruption_invalidate_cache` | Part C/LUHK/TAT3/SDK/polygon 依赖变化及 artifact corruption |
| `tests/test_v02_cache_schema_extremes.py::CacheAndSchemaTests::test_failed_qa_cannot_register_and_schema_01_is_read_only_compatible` | failed QA 不注册；0.1 只读兼容 |
| `tests/test_v02_cache_schema_extremes.py::CacheAndSchemaTests::test_missing_artifact_schema_mismatch_and_atomic_failure_are_not_reusable` | missing artifact、schema mismatch、atomic failure |
| `tests/test_v02_cache_schema_extremes.py::ExtremeTemperatureTests::test_deterministic_ties_q99_delta_and_polygon_figure` | min/max ties、q99 region、delta、polygon 图 |
| `tests/test_v02_cache_schema_extremes.py::ExtremeTemperatureTests::test_manual_measurement_without_coordinates_does_not_invent_location` | 手工 measurement 无坐标时不得造位置 |

#### Part D 和 TAT3（8）

| 自动 case | 主要验收点 |
|---|---|
| `tests/test_v02_temperature_extraction.py::TemperatureExtractionTests::test_shared_sdk_command_and_mocked_float32_extraction` | shared SDK command、mock float32、参数传播 |
| `tests/test_v02_temperature_extraction.py::TemperatureExtractionTests::test_override_missing_ambient_and_failed_qa_are_retained` | missing ambient、failed QA 保留且隔离 |
| `tests/test_v02_tat3_manual.py::TAT3ManualParserTests::test_point_multiple_points_region_and_mixed_fixtures` | point/multiple/region/mixed |
| `tests/test_v02_tat3_manual.py::TAT3ManualParserTests::test_missing_coordinates_are_reported_without_invented_locations` | missing coordinates 不造位置 |
| `tests/test_v02_tat3_manual.py::TAT3ManualParserTests::test_missing_ambient_mismatch_units_and_duplicate_ids` | missing ambient、ID mismatch、units、duplicates |
| `tests/test_v02_tat3_manual.py::TAT3ManualParserTests::test_temporary_bundle_does_not_touch_persistent_index` | temporary-only，不改 index |
| `tests/test_v02_tat3_manual.py::test_named_local_ambient_reports_have_185_entries_and_no_manual_measurements` | 三个真实 local reports 共 185 entries、0 measurements |
| `tests/test_v02_pilot_numeric_baseline.py::PilotNumericBaselineTests::test_part_d_temperature_numeric_baseline` | 五 pilot Part D 温度数值冻结 |

#### Part E 和 pilot regression（6）

| 自动 case | 主要验收点 |
|---|---|
| `tests/test_v02_part_e_formal.py::FormalPartEV02IntegrationTests::test_schema_02_sampling_statistics_kde_qa_report_and_resume` | schema 0.2 sample/stat/effect/KDE/plot/QA/report/resume/dry-run/inclusion |
| `tests/test_pilot_regression.py::PilotRegressionTests::test_five_pilot_artifact_contracts_remain_compatible` | 五 pilot pair/mask/temperature contract |
| `tests/test_pilot_regression.py::PilotRegressionTests::test_existing_part_e_row_count_when_local_parquet_is_available` | legacy Part E 五图精确行数 |
| `tests/test_pilot_regression.py::PilotRegressionTests::test_normal_part_c_pilot_adapter_builds_versioned_manifest` | pilot adapter 生成 versioned canonical |
| `tests/test_v02_pilot_numeric_baseline.py::PilotNumericBaselineTests::test_reviewed_part_c_mask_bytes_are_frozen` | 五个 mask byte hash |
| `tests/test_v02_pilot_numeric_baseline.py::PilotNumericBaselineTests::test_pilot_part_e_row_counts_and_selected_numeric_summaries` | exact rows、delta、cover、LUHK、sample counts |

总数：15 + 5 + 8 + 6 + 8 + 6 = 48。

## 9. 额外人工 case 矩阵

| ID | 操作 | 预期结果 | 主要证据 |
|---|---|---|---|
| MAN-A01 | 删除/改名 thermal 的副本后运行，不动 raw | exit 1，`fatal_part_a_thermal_validation` | run summary、part_a.json |
| MAN-A02 | thermal valid、visible 路径不存在 | route C*；缺上下文时 incomplete，不得 fatal thermal | part_a.json、run summary |
| MAN-A03 | 提供形状不是 512×640 的 temperature NPY | dimension mismatch；不写 success/index | part_a.json、run summary |
| MAN-B01 | B0 ambiguous 不给决定 | `awaiting_part_b0_review` | part_b0.json |
| MAN-B02 | B0 accept，但 full Part B 不给 final review | `awaiting_part_b_review` | part_b.json/review package |
| MAN-B03 | full Part B final accept，但 coverage 是 overlap-only | 不得 normal Part C | part_b.json、run summary |
| MAN-B04 | full Part B cancel | `cancelled`，不得自动进入 C* | run summary |
| MAN-C01 | GUI 留一个 segment unreviewed 后 Accept | GUI 阻止接受 | draft/review JSON |
| MAN-C02 | cover 已标后切换 shadow | cover 不变；shadow mask 独立 | review JSON、shadow_mask.npy |
| MAN-C03 | 只给 label NPY、不给 manifest | `normal_part_c_unreviewed_label_override_rejected` | run summary |
| MAN-CSTAR01 | 缺 target/cover/LUHK 任一项 | incomplete，不能成功 | run summary |
| MAN-CSTAR02 | polygon 少于 3 点、零面积或越界到完全无像素 | 明确 validation error | run summary |
| MAN-CSTAR03 | 点击 Cancel | cancelled，不写新 success/Part E | run summary |
| MAN-D01 | NPY 有温度但 ambient 缺失 | temperature 保留；delta unavailable；formal delta 排除 | manifest、inclusion report |
| MAN-D02 | QA fail 的一组与成功组同批 | fail 不进 index/Part E；成功组继续 | run summary、index、inclusion report |
| MAN-E01 | 同时输入 normal + polygon | source 分层；不默认 pool | source summary/dashboard |
| MAN-E02 | 重跑相同 formal Part E | resume 跳过兼容 stage | AUTO 的 Part E case 日志 |
| MAN-X01 | min/max 多个 ties | tie count 和全坐标表；代表点 row-major deterministic | extreme CSV/PNG |
| MAN-X02 | q99 | 显示 threshold 和 exceedance 区域，不谎称单个 q99 点 | extreme CSV/PNG |
| MAN-T01 | TAT3 report 无坐标 | location unavailable，不造坐标 | temporary analysis/manifest |
| MAN-T02 | TAT3 Cancel/parse fail | 保留明确诊断；不改 persistent index | log、index hash |

这些人工破坏型 case 优先使用对应 pytest 临时 fixture，不要修改 raw、pilot mask、正式 temperature matrix、正式 config 或正式 index。

## 10. Benchmark 和容量观察

```powershell
& $Py scripts\benchmark_v0_2.py 2>&1 |
    Tee-Object "$UatRoot\test_logs\benchmark_v0_2.log"
```

检查新生成的 ignored benchmark JSON。时间和内存是观察值，不设成跨机器硬门槛。验收口径：

- interactive 推荐每次 `X = 1`，因为每个 review boundary 要人工注意。
- unattended pre-reviewed 暂定 `X = 25`，只是调度建议。
- storage retention `Y = floor(0.8 × free_storage_bytes / measured_canonical_bytes_per_image)`。
- X 和 Y 不得混为同一个“最大组数”。
- 实际 DJI SDK 延迟和人工 review 时间必须单独说明；默认测试只使用 mocked SDK。

## 11. 存储、Git 和清洁度验收

```powershell
git check-ignore -v "$UatRoot\canonical\result_index.json"
git check-ignore -v "$UatRoot\tat3_soccer_ambient_only\temporary_manifest.json"
git status --short
```

通过标准：

- 验收 canonical/index/Part E、pytest logs、benchmark、temporary TAT3 都在 `outputs/runs/` 下并被忽略。
- 默认 persistent run 没有生成 full-pixel CSV 或 per-image Excel。
- raw DJI、`data/local_external/`、SDK binary/local SDK config、generated canonical、cache 和 temporary bundle 都没有被 Git 跟踪。
- `commit_code_exports/` 保持原样。

## 12. 最终签字清单

- [ ] 48 个自动 case 全部通过，保存 full log 和 JUnit XML。
- [ ] 五个指定 pilot 同批运行，五组均 success，逐个 manifest/mask/extreme 检查完成。
- [ ] 五 pilot frozen mask、temperature、row count 和 selected Part E 数值回归通过。
- [ ] 五 pilot 第二次运行全部 cache hit。
- [ ] 足球场真实 V/T 目视确认为近景/广角对不上。
- [ ] 足球场无决定时停在 `awaiting_part_b0_review`，无成功 canonical。
- [ ] 足球场人工 reject 后完整走 `thermal_polygon`，inside/outside、target、cover、LUHK/provenance 正确。
- [ ] 足球场 GUI polygon 至少 smoke test 一次；fixture polygon 未被误当成科学标注。
- [ ] 五 normal + 一 polygon 的 Part E 同时出现且 source 分层、不静默 pooling。
- [ ] 真实足球场 TAT3 report 输出 ambient-only、0 measurements、ambient 10.8°C，未制造位置。
- [ ] 临时 TAT3 前后正式 index hash 不变。
- [ ] Min/Max/ties/q99 table、coordinate table 和 location figure 正确。
- [ ] failed QA、cancelled、awaiting、unknown、missing ambient 都出现在 inclusion/exclusion 逻辑中。
- [ ] 默认没有大 full-pixel CSV/Excel。
- [ ] 所有生成/本地/临时资产被忽略，raw 和 `commit_code_exports/` 未改动。

只有以上项目都有证据，才将 v0.2 判为用户验收通过。
