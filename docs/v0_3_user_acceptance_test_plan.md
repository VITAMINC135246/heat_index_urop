# v0.3 中文用户验收测试计划

本文从打开 PowerShell 开始，覆盖自动测试、五 pilot、路由、Part C/Part C*、
canonical/extreme/spatial/Part E/temporal、真实足球场后续手工复现、TAT3、
cache/resume/dry-run、存储和 Git。除明确标注“真实科学复现”的小节外，所有
合成矩阵都只是 **non-scientific route fixture**，不得用于 +26°C 结论。

## 0. 打开 PowerShell、进入仓库并设置变量

```powershell
Set-Location -LiteralPath "E:\Projects\heat_index_urop"
$Py = ".\.venv\Scripts\python.exe"
$Runner = "scripts\run_analysis.py"
$Cfg = "config\workflow_v0_3_acceptance.json"
$UatRoot = "outputs\runs\v0_3_user_acceptance"
$PilotDir = "data\raw\HKUST\20260107_Thermal_HKUST\DCIM\DJI_202601071424_001"
$SoccerDir = "data\raw\HKUST\20260202_Thermal_HKUST\DCIM\DJI_202602020853_001"
$SoccerId = "DJI_20260202091128_0058"
$SoccerV = "$SoccerDir\DJI_20260202091127_0058_V.JPG"
$SoccerT = "$SoccerDir\DJI_20260202091128_0058_T.JPG"
$env:MPLCONFIGDIR = "$PWD\.matplotlib-cache"
git status --short --branch
& $Py --version
```

为什么：锁定仓库、解释器、隔离配置和真实素材位置。输入是本仓库与本地 raw；
无交互。预期分支 `codex/heat-index-urop-0.3`，Python 可运行，只有允许的用户
自有 `commit_code_exports/` 可未跟踪。失败：分支/路径错误、出现其他未知改动。

尚未建立环境时：

```powershell
C:\Users\Victo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m venv .venv
& $Py -m pip install --upgrade pip
& $Py -m pip install -r requirements.txt
```

为什么：安装 `requirements.txt` 的 NumPy/Pandas/PyArrow/Matplotlib/scientific
依赖；需联网下载时有等待，无 GUI。预期退出码 0。输出在 `.venv/`；下一步
运行 collection。失败：安装异常或 import 错误。

## 1. 干净的隔离验收输出

先只解析目标，确认不是宽目录：

```powershell
if (Test-Path -LiteralPath $UatRoot) { (Resolve-Path -LiteralPath $UatRoot).Path }
```

预期只打印
`E:\Projects\heat_index_urop\outputs\runs\v0_3_user_acceptance`。确认后：

```powershell
if (Test-Path -LiteralPath $UatRoot) { Remove-Item -Recurse -Force -LiteralPath $UatRoot }
New-Item -ItemType Directory -Force "$UatRoot\test_logs" | Out-Null
```

为什么：制造 cache-miss，且只清理隔离 acceptance；无交互。输出是空的
`$UatRoot/test_logs`。失败：解析路径不严格相等时禁止删除；不得清理
`outputs/`、`outputs/runs/` 或 `data/processed/`。

## 2. 测试收集

```powershell
& $Py -m pytest --collect-only -q 2>&1 |
    Tee-Object "$UatRoot\test_logs\pytest_collect.log"
$LASTEXITCODE
```

为什么：验证所有 node 可导入，不执行测试；无交互。当前预期 60 tests、退出
码 0。输出 `pytest_collect.log`。下一步完整自动测试。失败：collection error、
数量不是 60 或退出码非 0。

## 3. 完整自动测试

```powershell
& $Py -m pytest -vv --junitxml "$UatRoot\test_logs\pytest_results.xml" 2>&1 |
    Tee-Object "$UatRoot\test_logs\pytest_full.log"
$LASTEXITCODE
```

为什么：运行默认 mocked SDK 的 unit/integration/regression/UAT；无 GUI。当前
预期 `60 passed`、退出码 0。输出 full log 与 JUnit XML。下一步先看失败 node；
任何 failed/error 都是不通过。

主要路由可逐组重跑：

```powershell
& $Py -m pytest -vv -s tests\test_v02_part_a_b0_and_full_b.py
& $Py -m pytest -vv -s tests\test_v02_run_analysis_routes.py tests\test_run_analysis_integration.py
& $Py -m pytest -vv -s tests\test_v02_part_c_controller.py tests\test_polygon_and_canonical.py
& $Py -m pytest -vv -s tests\test_v03_spatial_figures.py tests\test_v03_temporal_analysis.py
```

这些命令分别覆盖：exact/uncertain V/T、missing/invalid thermal、B0
match/mismatch/ambiguous 与 accept/reject/cancel、full Part B
accept/reject/overlap-only/indeterminate/cancel、normal Part C assignment/
multi-select/unknown/shadow/undo/redo/draft/resume/accept/cancel、bare NPY
拒绝、polygon accepted/missing context/dimension mismatch/cancel/inside-outside、
spatial/temporal。输入是小型临时 fixture；无桌面交互；输出在 pytest temp，
证据是控制台。所有 node passed 才通过。

## 4. 五 pilot cache-miss 同批运行

```powershell
$PilotIds = @(
  "DJI_20260107143259_0005",
  "DJI_20260107143320_0007",
  "DJI_20260107143328_0008",
  "DJI_20260107143344_0009",
  "DJI_20260107143401_0011"
)
& $Py $Runner --config $Cfg selected --dataset-id HKUST_five_pilot_v03_acceptance `
  --group "$PilotDir\DJI_20260107143259_0005_V.JPG" "$PilotDir\DJI_20260107143259_0005_T.JPG" `
  --group "$PilotDir\DJI_20260107143320_0007_V.JPG" "$PilotDir\DJI_20260107143320_0007_T.JPG" `
  --group "$PilotDir\DJI_20260107143328_0008_V.JPG" "$PilotDir\DJI_20260107143328_0008_T.JPG" `
  --group "$PilotDir\DJI_20260107143344_0009_V.JPG" "$PilotDir\DJI_20260107143344_0009_T.JPG" `
  --group "$PilotDir\DJI_20260107143401_0011_V.JPG" "$PilotDir\DJI_20260107143401_0011_T.JPG" `
  2>&1 | Tee-Object "$UatRoot\test_logs\five_pilot_cache_miss.log"
$LASTEXITCODE
```

为什么：用 v0.2 已验收五个 numeric pilot 回归 v0.3 A–E；输入是五组真实
pilot、冻结 reviewed masks 和本地已验证矩阵；无 GUI。预期五个
`success via normal_visible_thermal`、退出码 0。精确输出：

- `$UatRoot/workflow_runs/run_<UTC>/run_summary.json`；
- `$UatRoot/canonical/images/<image_id>/`；
- `$UatRoot/part_e/part_e_multi_source_pixels.parquet`；
- `$UatRoot/part_e/schema_0_2/figures/spatial/`；
- `$UatRoot/part_e/schema_0_2/temporal/`。

下一步逐图和 Part E 检查。失败：任一 failed/incomplete、canonical 缺失或
formal runner 报 spatial/temporal incomplete。

## 5. 五 pilot 逐图与 numeric 回归

```powershell
foreach ($Id in $PilotIds) {
  $Dir = "$UatRoot\canonical\images\$Id"
  $M = Get-Content "$Dir\manifest.json" -Raw | ConvertFrom-Json
  [pscustomobject]@{
    image_id=$Id; schema=$M.schema_version; processing=$M.processing_version
    route=$M.processing_route; measurement=$M.measurement_type; source=$M.source_method
    dimensions="$($M.image_height)x$($M.image_width)"
    count=($M.known_pixel_count + $M.unknown_pixel_count)
    pixels=(Test-Path "$Dir\pixels.parquet")
    extremes=(Test-Path "$Dir\extreme_temperature_summary.csv")
    locations=(Test-Path "$Dir\extreme_temperature_locations.png")
  }
}
```

为什么：逐图检查 manifest、schema、native dimension、canonical/extreme；无
交互。预期 schema `0.2.0`、processing `heat-index-urop-0.3`、normal/full
pixel/visible_review、`512x640`、count 327680、三个布尔均 True。下一步 numeric。

```powershell
& $Py -m pytest -vv tests\test_v02_pilot_numeric_baseline.py tests\test_pilot_regression.py 2>&1 |
  Tee-Object "$UatRoot\test_logs\five_pilot_numeric_regression.log"
```

为什么：核对五 pilot ID 仍为数字字符串、mask/hash、温度 min/max/mean/q99、
ambient、delta 和 1,638,400 行；无交互。预期全部 passed。输出 log。失败：
任一冻结数值/哈希漂移。

## 6. 五 pilot cache-hit 与单图调试

原样重跑第 4 节命令。预期五组均
`cache_hit via cached_result - compatible_canonical_result`，正式 runner 显示
`SKIP sample`、`SKIP spectrum`、`SKIP spatial-figures`，temporal status 为
`cache_hit`。新 run summary 五行 `cache_hit=true` 才通过。

单图调试：

```powershell
$Id = "DJI_20260107143259_0005"
& $Py $Runner --config $Cfg --no-part-e selected --dataset-id "debug_$Id" `
  --group "$PilotDir\${Id}_V.JPG" "$PilotDir\${Id}_T.JPG"
```

为什么：定位 A/B/C/D 单图问题，不重跑 Part E；无 GUI（pilot adapter）。预期
cache hit 或单图 success。输出最新 workflow run。它不替代五图同批验收。

## 7. exact、uncertain、mismatch、B0 与 full Part B

```powershell
& $Py -m pytest -vv -s `
  tests\test_v02_part_a_b0_and_full_b.py `
  tests\test_v02_run_analysis_routes.py `
  2>&1 | Tee-Object "$UatRoot\test_logs\routing_a_b.log"
```

为什么：用受控图像验证 exact valid pair、filename/timestamp uncertainty、clear
B0 match、clear mismatch、ambiguous、B0 accept/reject/cancel、full Part B
accepted full coverage/rejected/overlap-only/indeterminate/cancel，以及 valid
thermal with bad visible、missing/invalid thermal、matrix dimension mismatch；无
交互。预期全部 passed。临时输出自动清理，日志保留。任何自动 candidate 直接
接受 alignment、cancel 产生 canonical、invalid thermal 继续下游都失败。

真实 mismatch 观察：

```powershell
& $Py $Runner --config $Cfg --no-part-e selected --dataset-id soccer_mismatch_observation `
  --group $SoccerV $SoccerT 2>&1 |
  Tee-Object "$UatRoot\test_logs\soccer_awaiting_b0.log"
```

输入是 09:11:27 visible 近景与 09:11:28 thermal 广角；无 GUI。预期
`awaiting_part_b0_review`、有 Part A/B0 evidence、没有成功 soccer manifest。

## 8. Normal Part C GUI

先验证 controller：

```powershell
& $Py -m pytest -vv -s tests\test_v02_part_c_controller.py 2>&1 |
  Tee-Object "$UatRoot\test_logs\part_c_controller.log"
```

为什么：无 GUI 地验证 assignment、多选、unknown、shadow、undo/redo、draft/
resume、accept/cancel；预期全部 passed。桌面 smoke test 使用一个 final Part B
accepted/full-coverage 且没有 accepted review 的 V/T：

```powershell
& $Py $Runner --config $Cfg --launch-part-c-gui `
  --part-b-review "PATH_TO_ACCEPTED_FULL_PART_B_JSON" `
  selected --dataset-id normal_part_c_gui `
  --group "PATH_TO_VISIBLE.JPG" "PATH_TO_THERMAL.JPG"
```

此命令会交互。检查 visible ROI、superpixels、thermal panel、single/Ctrl
multi-select、physical cover、unknown、独立 shadow、undo/redo、notes/reviewer/
confidence、draft/resume、未完成时阻止 accept、accept 和另一次 cancel。输出在
最新 run group 与 canonical。通过：accepted 才 canonical；cancel/draft 不进入
Part E。裸 `--normal-labels-npy` 必须由自动测试拒绝。

## 9. Part C* polygon GUI 与缺失输入

创建只用于路线的 non-scientific 温度 fixture：

```powershell
$SoccerTestNpy = "$UatRoot\fixtures\soccer_route_only_temperature.npy"
New-Item -ItemType Directory -Force "$UatRoot\fixtures" | Out-Null
& $Py -c "from pathlib import Path; import numpy as np; p=Path(r'$SoccerTestNpy'); np.save(p,np.linspace(18,42,512*640,dtype=np.float32).reshape(512,640)); print(np.load(p).shape)"
```

预期 `(512, 640)`；它不是 radiometric scientific result。手动画 polygon：

```powershell
& $Py $Runner --config $Cfg `
  --part-b0-review config\acceptance\v0_2_soccer_b0_rejected.json `
  --target-id hkust-soccer-field-route-fixture `
  --target-name "HKUST soccer field" `
  --surface-cover grass_low_vegetation `
  --luhk "GIC / open space" --luhk-provenance user_supplied_luhk `
  --reviewer-confidence low --notes "NON-SCIENTIFIC route-only polygon" `
  --temperature-npy "$SoccerId=$SoccerTestNpy" `
  selected --dataset-id soccer_polygon_gui --group $SoccerV $SoccerT
```

会弹 GUI。Draw/Redraw 后 accept；另一次测试 cancel。因为未提供 ambient，预期
temperature canonical/extremes/spatial 存在，ΔT panel 明确 unavailable，temporal
temperature 描述存在，ΔT 排除。输出在 soccer canonical 与 formal spatial/
temporal。通过：inside target/cover/LUHK known，outside unknown/ineligible，
boundary 正确；cancel 无成功 canonical。缺 target/cover/LUHK、official vs user
provenance、polygon mismatch/cancel 的无 GUI回归：

```powershell
& $Py -m pytest -vv -s tests\test_polygon_and_canonical.py tests\test_run_analysis_integration.py
```

## 10. 温度提取、ambient、canonical、Min/Max/q99

```powershell
& $Py -m pytest -vv -s tests\test_v02_part_d_shared.py tests\test_v02_cache_schema_extremes.py
```

为什么：默认 mocked SDK，验证真实入口共享实现、parameter/shape/QA、missing
ambient、failed QA isolation、Min/Max ties、q99 threshold/region/location、atomic
cache；无交互。预期全部 passed。输出临时；检查 log。失败：默认测试要求真实
SDK、failed QA 进入 index/Part E、缺 ambient 被填值或 extreme 不确定。

真实 SDK 是可选本地集成，只有在合法 SDK 配置存在时运行：

```powershell
& $Py $Runner --config $Cfg --tat3-params-csv "PATH_TO_REAL_TAT3_PARAMETER_CSV" `
  --sdk-config config\part_d_sdk.local.json `
  selected --dataset-id optional_real_sdk `
  --group "PATH_TO_VISIBLE.JPG" "PATH_TO_THERMAL.JPG"
```

它使用 real TAT3 params/SDK，有较长等待，无 GUI（除 review boundary）。通过：
native shape、parameter audit、QA 和 source definition 完整。不要提交 matrix、raw
SDK output、binary 或 local config。

## 11. Spatial：normal、polygon、动态尺寸与完整性

```powershell
& $Py -m pytest -vv -s tests\test_v03_spatial_figures.py 2>&1 |
  Tee-Object "$UatRoot\test_logs\spatial_v03.log"
```

输入是明确标记的 non-scientific normal/polygon canonical fixtures；无交互。
预期 normal/polygon、dynamic dimensions、missing LUHK/shadow/ambient、outside
unknown、ineligible pixels、source labels、boundary、non-pixel exclusion、缺文件
validation 全 passed。

正式五图/多来源运行后检查：

```powershell
$Spatial = "$UatRoot\part_e\schema_0_2\figures\spatial"
Get-Content "$Spatial\spatial_figure_validation.json" -Raw | ConvertFrom-Json
Import-Csv "$Spatial\spatial_figure_manifest.csv" | Format-Table -AutoSize
Get-ChildItem $Spatial -File | Sort-Object Name
```

每个 eligible unit 必须有 temperature、delta、cover、LUHK、target、shadow、
eligibility、combined 各 PNG/PDF；缺层是 unavailable panel。validation canonical
hash 正确、expected files 全存在。目录空、少一张图仍显示 complete 即失败。

## 12. Normal + polygon source-stratified Part E

完成五 pilot 和一个 route-only polygon 后，从其 manifest 建列表运行正式集成，
或直接运行自动 case：

```powershell
& $Py -m pytest -vv -s tests\test_v02_part_e_formal.py tests\test_part_e_multi_source.py 2>&1 |
  Tee-Object "$UatRoot\test_logs\normal_polygon_part_e.log"
```

为什么：验证 combined canonical、spatial thinning、statistics/effects/KDE、normal
+ polygon、missing ambient、spatial、temporal、inclusion、resume/dry-run；无交互。
预期全 passed。source summary/figures 同时保留 `visible_review/full_thermal_pixel`
与 `thermal_polygon_user_annotation/polygon_selected_thermal_pixel`，不静默 pool。

## 13. Synthetic 多时点 temporal

```powershell
& $Py -m pytest -vv -s tests\test_v03_temporal_analysis.py 2>&1 |
  Tee-Object "$UatRoot\test_logs\temporal_v03.log"
```

为什么：运行 zero/one/multiple、timezone/order、duplicate/invalid、irregular、
equal-image、missing ambient、incompatible source/measurement、target linkage/
mismatch、deterministic tables/figures、resume/cache invalidation、no fabricated
26；无交互。预期全部 passed。

对现有 compatible Parquet 运行 CLI：

```powershell
& $Py scripts\run_temporal_analysis.py `
  --canonical-parquet "$UatRoot\part_e\part_e_multi_source_pixels.parquet" `
  --output-root "$UatRoot\temporal_cli" `
  --timezone Asia/Hong_Kong --resume
```

预期打印 complete/cache_hit。输出 `tables/temporal_capture_summary.csv`、
`temporal_stratum_summary.csv`、inclusion，三个 PNG/PDF family、QA/report/
validation。五 pilot 若无 explicit target ID，只能描述或 unlinked，不得宣称 target
trend。

## 14. 后续真实足球场手工科学复现（不要在路线测试中完成）

本节与 synthetic route-only 严格分开。历史对话只确认：2026-02-02 全天、约
09:00–17:00、HKUST soccer field、教授称 natural turf、ad-hoc ΔT 在中午 up to
约 +26°C；具体 statistic、ambient source/definition、截图与 TAT3 params 未在可
访问文字中锁定。

复制模板并逐 capture 填写，模板本身 draft/空 coordinates，不能成功：

```powershell
Copy-Item config\acceptance\v0_3_soccer_polygon_template.json "$UatRoot\real_soccer_polygons.json"
Copy-Item config\acceptance\v0_3_soccer_ambient_template.json "$UatRoot\real_soccer_ambient.json"
notepad "$UatRoot\real_soccer_polygons.json"
notepad "$UatRoot\real_soccer_ambient.json"
```

为什么：为每张 capture 记录独立 accepted polygon、同一 stable target ID、cover/
LUHK provenance/confidence/notes、真实 ambient value/source/definition/timezone；
有人工编辑。温度矩阵必须由 real DJI/TAT3 params 提取。每张图执行：

```powershell
& $Py $Runner --config $Cfg `
  --part-b0-review "PATH_TO_PER_CAPTURE_B0_DECISIONS.json" `
  --polygon-json "$UatRoot\real_soccer_polygons.json" `
  --tat3-params-csv "PATH_TO_REAL_TAT3_PARAMS.csv" `
  --sdk-config config\part_d_sdk.local.json `
  --ambient-json "$UatRoot\real_soccer_ambient.json" `
  selected --dataset-id HKUST_20260202_soccer_real `
  --group "PATH_TO_CAPTURE_VISIBLE.JPG" "PATH_TO_CAPTURE_THERMAL.JPG"
```

逐图有 review/GUI；预期 accepted 才 success。完成所有 capture 后，把 run summary
或 combined Parquet交给 temporal CLI。检查：

```powershell
Import-Csv "$UatRoot\part_e\schema_0_2\temporal\tables\temporal_capture_summary.csv" |
  Select-Object image_id,capture_time_local,temperature_mean_c,temperature_median_c,temperature_q95_c,temperature_q99_c,temperature_max_c,delta_t_mean_c,delta_t_median_c,delta_t_q95_c,delta_t_q99_c,delta_t_max_c |
  Format-Table -AutoSize
```

下一步与教授确认原 ad-hoc +26°C 对应哪一列/点/region。通过：定义、来源、
polygon、timestamp、QA 可审计，结果可复跑；不要求硬等于 26.0。失败：复用 v0.2
synthetic matrix、缺 ambient definition、复用 polygon 坐标无 registration、把
maximum 冒充 mean、或宣称本软件已经复现 26°C。

## 15. Temporary TAT3 与 persistent index 不变

```powershell
$ProductionIndex = "data\metadata\canonical_result_index_v0_3.json"
$Before = if (Test-Path $ProductionIndex) { (Get-FileHash $ProductionIndex -Algorithm SHA256).Hash } else { "ABSENT" }
& $Py scripts\run_tat3_manual_analysis.py `
  --report "data\local_external\tat3_reports\raw\combined_report__2026_07_17_18_12_48.docx" `
  --thermal-image $SoccerT --target-name "HKUST soccer field" `
  --luhk "GIC / open space" --luhk-provenance user_supplied_luhk `
  --surface-cover grass_low_vegetation `
  --output-dir "$UatRoot\tat3_soccer_ambient_only"
$After = if (Test-Path $ProductionIndex) { (Get-FileHash $ProductionIndex -Algorithm SHA256).Hash } else { "ABSENT" }
$Before -eq $After
```

有真实 local report 解析，无 GUI。预期 ambient-only、0 measurements、10.8°C、
distance 5 m、emissivity .95、humidity 50%，只写 temporary manifest/analysis，
hash 比较 True；不得制造点/region/坐标或修改 persistent index。

```powershell
& $Py -m pytest -vv -s tests\test_v02_tat3_manual.py
```

补测 point/region/ambient-only/missing/duplicate/unit/无坐标和 no persistent-index
mutation。全部 passed 才通过。

## 16. Cache invalidation、resume 与 dry-run

```powershell
& $Py -m pytest -vv -s tests\test_result_index.py tests\test_v02_cache_schema_extremes.py tests\test_v03_temporal_analysis.py
```

为什么：自动改 raw hash、config/review/LUHK/TAT3/SDK/polygon dependency、artifact、
canonical、timezone 并验证 miss；无交互。预期全部 passed。

正式 Part E resume：

```powershell
$FormalCfg = "$UatRoot\part_e\schema_0_2\part_e_schema_0_2_config.json"
& $Py scripts\part_e\run_part_e_pipeline.py --config $FormalCfg `
  --from-stage sample --to-stage spatial-figures --skip-supporting-figures --skip-excel --resume
```

预期 `SKIP sample/analyse/spectrum/spatial-figures`；若删任一 spatial file，必须
重跑 spatial，而不是 skip。

dry-run：

```powershell
& $Py scripts\part_e\run_part_e_pipeline.py --config $FormalCfg `
  --from-stage sample --to-stage spatial-figures --skip-supporting-figures --skip-excel --dry-run
& $Py scripts\run_temporal_analysis.py `
  --canonical-parquet "$UatRoot\part_e\part_e_multi_source_pixels.parquet" `
  --output-root "$UatRoot\temporal_dry_run" --timezone Asia/Hong_Kong --dry-run
```

预期只打印 DRY-RUN/planned，不把 stage state 写成 complete。

## 17. Benchmark

```powershell
& $Py scripts\benchmark_v0_3.py 2>&1 |
  Tee-Object "$UatRoot\test_logs\benchmark_v0_3.log"
```

为什么：用 non-scientific synthetic canonical 记录 spatial、temporal、resume 的
墙钟时间与输出大小；无交互。输出 ignored JSON 与 log。通过：脚本成功、明确
fixture 非科学、spatial/temporal validation complete；观察值不是跨机器 SLA。

## 18. 存储与 Git-ignore

```powershell
git check-ignore -v "$UatRoot\canonical\result_index.json"
git check-ignore -v "$UatRoot\part_e\part_e_multi_source_pixels.parquet"
git check-ignore -v "$UatRoot\tat3_soccer_ambient_only\temporary_manifest.json"
git status --short
```

为什么：确认 generated canonical/Part E/temp logs 不入 Git；无交互。预期三项
被 `.gitignore` 命中；status 只有开发文件与用户自有 `commit_code_exports/`。
失败：raw DJI、`data/local_external/`、generated canonical/Part E、temporary TAT3、
SDK binary/local config、cache、test logs、大 CSV/Excel 被跟踪。

## 19. 最终 checkbox

- [ ] collection 至少 57 tests，完整 suite 全 passed，保存 log/JUnit。
- [ ] 五 numeric pilot 同批 cache-miss 成功，ID、512×640、hash、温度与 Part E 回归通过。
- [ ] 五 pilot 第二次全部 cache hit；单图调试可用。
- [ ] exact/uncertain/mismatch、B0 accept/reject/cancel、full Part B 全路由通过。
- [ ] normal Part C GUI/controller 的 assignment、unknown、shadow、undo/redo、draft/resume、accept/cancel 通过。
- [ ] Part C* accepted/missing context/provenance/dimension/cancel/inside-outside 通过。
- [ ] matrix shape、missing ambient、failed QA、failure isolation、Min/Max/ties/q99 通过。
- [ ] normal 与 polygon spatial 各八类 PNG/PDF；missing layers 明确 unavailable；boundary/unknown 正确。
- [ ] spatial validation 与 resume 能发现缺文件；没有 legacy five-pilot table 依赖。
- [ ] normal + polygon Part E source-stratified，不静默 pooling。
- [ ] temporal zero/one/multiple、timezone、duplicates、irregular、equal-image、missing ambient、sources/types/targets、cache 通过。
- [ ] q bands 标注为 within-image descriptive，非 CI；single capture 非 trend；no interpolation。
- [ ] 真实 soccer workflow 只准备；每 capture 需手动画/accept polygon、real TAT3 matrix 与 real ambient。
- [ ] 没有硬编码、伪造或声称已复现约 +26°C。
- [ ] temporary TAT3 不改 persistent index，不制造坐标。
- [ ] acceptance/generated/raw/local/SDK/cache/log/large export 的 Git 边界正确。
- [ ] `commit_code_exports/` 从未被检查内容、修改、删除、暂存或提交。

全部有证据后，才把 v0.3 判为用户验收通过。
