param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [switch]$SkipPixelWorkbooks,
    [switch]$SkipPixelValidation
)

$ErrorActionPreference = 'Stop'
$config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
$excel = $null
$excelPid = $null
$results = New-Object System.Collections.Generic.List[object]
$progressPath = Join-Path $ProjectRoot 'outputs\part_e\qa\part_e_excel_progress.log'
[IO.File]::WriteAllText($progressPath, ("{0:o} start`r`n" -f [DateTime]::UtcNow))

function Write-ProgressLog([string]$Message) {
    [IO.File]::AppendAllText($progressPath, ("{0:o} {1}`r`n" -f [DateTime]::UtcNow,$Message))
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WindowProcess {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@

function Release-ComObject([object]$Object) {
    if ($null -ne $Object -and [Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}

function Import-CsvToSheet {
    param([object]$Workbook, [string]$SheetName, [string]$CsvPath, [string]$TableName)
    $sheet = $Workbook.Worksheets.Item($SheetName)
    while ($sheet.ListObjects.Count -gt 0) { $sheet.ListObjects.Item(1).Delete() }
    $sheet.Cells.Clear()
    $Workbook.Application.Workbooks.OpenText($CsvPath, 65001, 1, 1, 1, $false, $false, $false, $true, $false, $false)
    $csvWorkbook = $Workbook.Application.ActiveWorkbook
    $csvSheet = $csvWorkbook.Worksheets.Item(1)
    $csvRange = $csvSheet.UsedRange
    $rowCount = $csvRange.Rows.Count
    $columnCount = $csvRange.Columns.Count
    $destination = $sheet.Range($sheet.Cells.Item(1,1), $sheet.Cells.Item($rowCount,$columnCount))
    $destination.Value2 = $csvRange.Value2
    $csvWorkbook.Close($false)
    Release-ComObject $destination
    Release-ComObject $csvRange
    Release-ComObject $csvSheet
    Release-ComObject $csvWorkbook
    $used = $sheet.UsedRange
    $table = $sheet.ListObjects.Add(1, $used, $null, 1)
    $table.Name = $TableName
    $table.TableStyle = "TableStyleMedium2"
    $sheet.Rows.Item(1).RowHeight = 32
    $sheet.Rows.Item(1).Font.Bold = $true
    $sheet.Rows.Item(1).WrapText = $true
    $sheet.Cells.Font.Name = "Aptos"
    $sheet.Cells.Font.Size = 10
    $sheet.Activate()
    $Workbook.Application.ActiveWindow.FreezePanes = $false
    $sheet.Range("A2").Select()
    $Workbook.Application.ActiveWindow.FreezePanes = $true
    $headerMap = @{}
    for ($column = 1; $column -le $used.Columns.Count; $column++) {
        $name = [string]$sheet.Cells.Item(1, $column).Value2
        $headerMap[$name] = $column
        $sheet.Columns.Item($column).ColumnWidth = 16
    }
    foreach ($name in @('pixel_uid','image_id','flight_id','capture_datetime','luhk_cell_id','luhk_class_name','surface_cover_class','sampling_method','spatial_label_uncertainty')) {
        if ($headerMap.ContainsKey($name)) { $sheet.Columns.Item($headerMap[$name]).ColumnWidth = if ($name -eq 'spatial_label_uncertainty') { 45 } else { 24 } }
    }
    foreach ($name in @('temperature_c','ambient_temperature_c','delta_t_c','gps_latitude','gps_longitude','relative_altitude_m')) {
        if ($headerMap.ContainsKey($name)) { $sheet.Columns.Item($headerMap[$name]).NumberFormat = "0.000000" }
    }
    foreach ($name in @('thermal_row','thermal_col','pixel_x','pixel_y','luhk_grid_row','luhk_grid_col','luhk_class_code','surface_cover_class_id','shadow_flag','sampling_seed','tile_row','tile_col','source_population_count')) {
        if ($headerMap.ContainsKey($name)) { $sheet.Columns.Item($headerMap[$name]).NumberFormat = "0" }
    }
    $result = [pscustomobject]@{ Sheet = $sheet; Table = $table; Used = $used; Headers = $headerMap }
    return $result
}

function Set-ImageSummaryFormulas {
    param([object]$Workbook, [string]$TableName)
    $sheet = $Workbook.Worksheets.Item("Image_Summary")
    $formulaMap = @{
        'total pixel count' = "=ROWS($TableName[image_id])"
        'finite pixel count' = "=COUNT($TableName[temperature_c])"
        'accepted pixel count' = "=COUNTIF($TableName[pixel_accepted],TRUE)"
        'LUHK-labelled pixel count' = "=COUNTIF($TableName[luhk_label_valid],TRUE)"
        'cover-labelled pixel count' = "=COUNTIF($TableName[surface_cover_valid],TRUE)"
        'shadow-known pixel count' = "=COUNTIF($TableName[shadow_valid],TRUE)"
        'ambient_temperature_c' = "=MEDIAN($TableName[ambient_temperature_c])"
        'temperature mean (°C)' = "=AVERAGE($TableName[temperature_c])"
        'temperature median (°C)' = "=MEDIAN($TableName[temperature_c])"
        'temperature minimum (°C)' = "=MIN($TableName[temperature_c])"
        'temperature maximum (°C)' = "=MAX($TableName[temperature_c])"
        'ΔT mean (°C)' = "=AVERAGE($TableName[delta_t_c])"
        'ΔT median (°C)' = "=MEDIAN($TableName[delta_t_c])"
        'ΔT minimum (°C)' = "=MIN($TableName[delta_t_c])"
        'ΔT maximum (°C)' = "=MAX($TableName[delta_t_c])"
    }
    for ($row = 2; $row -le $sheet.UsedRange.Rows.Count; $row++) {
        $label = [string]$sheet.Cells.Item($row, 1).Value2
        if ($formulaMap.ContainsKey($label)) { $sheet.Cells.Item($row, 3).Formula = $formulaMap[$label] }
    }
    $sheet.Columns.Item(1).ColumnWidth = 34
    $sheet.Columns.Item(2).ColumnWidth = 24
    $sheet.Columns.Item(3).ColumnWidth = 24
    $sheet.Columns.Item(3).NumberFormat = "0.000000"
}

function Add-MainCrosscheckSheet {
    param([object]$Workbook)
    Write-ProgressLog 'crosscheck add worksheet'
    $sheet = $Workbook.Worksheets.Add()
    $sheet.Name = 'Excel_Crosscheck'
    Write-ProgressLog 'crosscheck write headers'
    $headers = @('surface_cover_class','Excel sampled n','Excel sampled mean ΔT','Python sampled n','Python sampled mean ΔT','n difference','mean difference')
    for ($column = 1; $column -le $headers.Count; $column++) { $sheet.Cells.Item(1,$column).Value2 = $headers[$column-1] }
    $coverSummary = $Workbook.Worksheets.Item('Full_Pixel_Cover_Summary')
    $sampleCover = $Workbook.Worksheets.Item('Sample_Cover')
    $sampleLast = $sampleCover.UsedRange.Rows.Count
    $last = $coverSummary.Cells.Item($coverSummary.Rows.Count,1).End(-4162).Row
    for ($row = 2; $row -le $last; $row++) {
        $targetRow = $row
        $sheet.Cells.Item($targetRow,1).Value2 = $coverSummary.Cells.Item($row,1).Value2
        $sheet.Cells.Item($targetRow,2).Formula = "=COUNTIF('Sample_Cover'!`$P`$2:`$P`$$sampleLast,A$targetRow)"
        $sheet.Cells.Item($targetRow,3).Formula = "=AVERAGEIF('Sample_Cover'!`$P`$2:`$P`$$sampleLast,A$targetRow,'Sample_Cover'!`$K`$2:`$K`$$sampleLast)"
        $sheet.Cells.Item($targetRow,4).Value2 = $coverSummary.Cells.Item($row,13).Value2
        $sheet.Cells.Item($targetRow,5).Value2 = $coverSummary.Cells.Item($row,14).Value2
        $sheet.Cells.Item($targetRow,6).Formula = '=B' + $targetRow + '-D' + $targetRow
        $sheet.Cells.Item($targetRow,7).Formula = '=C' + $targetRow + '-E' + $targetRow
    }
    Write-ProgressLog 'crosscheck add table'
    $range = $sheet.Range("A1:G$last")
    $table = $sheet.ListObjects.Add(1,$range,$null,1)
    $table.Name = 'tblExcelCrosscheck'
    $table.TableStyle = 'TableStyleMedium2'
    $sheet.Columns.Item(1).ColumnWidth = 24
    for ($column = 2; $column -le 7; $column++) { $sheet.Columns.Item($column).ColumnWidth = 20 }
    $sheet.Range("C2:G$last").NumberFormat = '0.000000'
    Release-ComObject $table
    Release-ComObject $range
    Release-ComObject $coverSummary
    Release-ComObject $sampleCover
    Write-ProgressLog 'crosscheck complete'
    return $sheet
}

function Create-PivotAnalysis {
    param([object]$Workbook)
    foreach ($sheet in @($Workbook.Worksheets)) {
        if ($sheet.Name -eq 'Pivot_Analysis') { $sheet.Delete(); break }
    }
    $pivotSheet = $Workbook.Worksheets.Add()
    $pivotSheet.Name = 'Pivot_Analysis'
    $pivotSheet.Range('A1').Value2 = 'Native Excel PivotTables built from sampled individual pixels'
    $pivotSheet.Range('A1:N1').Font.Bold = $true
    $pivotSheet.Range('A1:N1').Interior.Color = 14277081

    $coverSheet = $Workbook.Worksheets.Item('Sample_Cover')
    $coverRange = $coverSheet.ListObjects.Item('tblSampleCover').Range
    $cache = $Workbook.PivotCaches().Create(1, 'tblSampleCover', 6)
    $pivot = $cache.CreatePivotTable($pivotSheet.Range('A3'), 'pvtCoverDeltaT')
    [void]$cache.Refresh()
    [void]$pivot.RefreshTable()
    Write-ProgressLog 'pivot cover cache refreshed'
    $pivot.PivotFields('surface_cover_class').Orientation = 1
    $pivot.PivotFields('surface_cover_class').Position = 1
    $pivot.PivotFields('image_id').Orientation = 3
    [void]$pivot.AddDataField($pivot.PivotFields('delta_t_c'), 'Average ΔT (°C)', -4106)
    [void]$pivot.AddDataField($pivot.PivotFields('pixel_uid'), 'Sampled pixel count', -4112)
    $pivot.DataFields.Item(1).NumberFormat = '0.00'

    $imageSheet = $Workbook.Worksheets.Item('Sample_Image')
    $imageRange = $imageSheet.ListObjects.Item('tblSampleImage').Range
    $cache2 = $Workbook.PivotCaches().Create(1, 'tblSampleImage', 6)
    $pivot2 = $cache2.CreatePivotTable($pivotSheet.Range('J3'), 'pvtImageDeltaT')
    [void]$cache2.Refresh()
    [void]$pivot2.RefreshTable()
    Write-ProgressLog 'pivot image cache refreshed'
    $pivot2.PivotFields('image_id').Orientation = 1
    [void]$pivot2.AddDataField($pivot2.PivotFields('delta_t_c'), 'Average ΔT (°C)', -4106)
    [void]$pivot2.AddDataField($pivot2.PivotFields('pixel_uid'), 'Sampled pixel count', -4112)
    $pivot2.DataFields.Item(1).NumberFormat = '0.00'

    $shape = $pivotSheet.Shapes.AddChart2(201, 51, 10, 230, 720, 360)
    $shape.Chart.SetSourceData($pivot.TableRange1)
    $shape.Chart.HasTitle = $true
    $shape.Chart.ChartTitle.Text = 'Sampled-pixel ΔT by physical surface cover'
    $shape.Chart.HasLegend = $false
    $pivotSheet.Range('A:N').ColumnWidth = 16
    return $pivotSheet
}

function Export-NativeCharts {
    param([object]$Workbook, [string]$OutputDirectory)
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $index = 1
    for ($sheetIndex = 1; $sheetIndex -le $Workbook.Worksheets.Count; $sheetIndex++) {
        $sheet = $Workbook.Worksheets.Item($sheetIndex)
        $chartObjects = $sheet.ChartObjects()
        for ($chartIndex = 1; $chartIndex -le $chartObjects.Count; $chartIndex++) {
            $chartObject = $chartObjects.Item($chartIndex)
            $safeSheet = ($sheet.Name -replace '[^A-Za-z0-9_]+','_')
            $path = Join-Path $OutputDirectory ("excel_native_{0:D2}_{1}.png" -f $index,$safeSheet)
            [void]$chartObject.Chart.Export($path, 'PNG')
            $index++
            Release-ComObject $chartObject
        }
        Release-ComObject $chartObjects
        Release-ComObject $sheet
    }
    return ($index - 1)
}

function Validate-Workbook {
    param([object]$Excel, [string]$Path, [string]$ExpectedSheet, [int]$ExpectedRows)
    $workbook = $Excel.Workbooks.Open($Path, 0, $true)
    $sheet = $workbook.Worksheets.Item($ExpectedSheet)
    $rows = $sheet.UsedRange.Rows.Count
    $links = $workbook.LinkSources(1)
    $linkCount = if ($null -eq $links) { 0 } elseif ($links -is [Array]) { $links.Count } else { 1 }
    $formulaErrorCount = 0
    $formulaSheets = @('Image_Summary','Pixel_QA','Excel_Crosscheck')
    foreach ($name in $formulaSheets) {
        try {
            $item = $workbook.Worksheets.Item($name)
            $errors = $item.UsedRange.SpecialCells(-4123, 16)
            if ($null -ne $errors) { $formulaErrorCount += $errors.Cells.Count; Release-ComObject $errors }
            Release-ComObject $item
        } catch { }
    }
    $workbook.Close($false)
    Release-ComObject $sheet
    Release-ComObject $workbook
    return [pscustomobject]@{ rows = $rows; expected_rows = $ExpectedRows; links = $linkCount; formula_errors = $formulaErrorCount; status = if ($rows -eq $ExpectedRows -and $linkCount -eq 0 -and $formulaErrorCount -eq 0) {'PASS'} else {'FAIL'} }
}

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false
    [uint32]$pidValue = 0
    [void][WindowProcess]::GetWindowThreadProcessId([IntPtr]$excel.Hwnd, [ref]$pidValue)
    $excelPid = [int]$pidValue

    foreach ($imageId in $config.pilot_image_ids) {
        $workbookPath = Join-Path $ProjectRoot "outputs\part_e\excel\pixel_workbooks\${imageId}_pixel_delta_t.xlsx"
        $csvPath = Join-Path $ProjectRoot "data\processed\part_e\excel_source\${imageId}_pixel_data.csv"
        if ($SkipPixelWorkbooks) {
            if ($SkipPixelValidation) { continue }
            Write-ProgressLog "validate existing pixel workbook $imageId"
            $validation = Validate-Workbook -Excel $excel -Path $workbookPath -ExpectedSheet 'Pixel_Data' -ExpectedRows 327681
            $results.Add([pscustomobject]@{workbook=$workbookPath; excel_version=$excel.Version; automation='Microsoft Excel COM'; pivot_tables='not_applicable_per_image'; analysis_toolpak='installed_not_enabled'; used_rows=$validation.rows; expected_rows=$validation.expected_rows; external_links=$validation.links; formula_errors=$validation.formula_errors; status=$validation.status})
            continue
        }
        Write-ProgressLog "open pixel workbook $imageId"
        $workbook = $excel.Workbooks.Open($workbookPath, 0, $false)
        $excel.Calculation = -4135
        $tableName = 'tblPixelData_' + $imageId.Substring($imageId.Length - 4)
        $existingPixelSheet = $workbook.Worksheets.Item('Pixel_Data')
        if ($existingPixelSheet.UsedRange.Rows.Count -eq 327681 -and $existingPixelSheet.ListObjects.Count -gt 0) {
            $imported = [pscustomobject]@{ Sheet = $existingPixelSheet; Table = $existingPixelSheet.ListObjects.Item(1); Used = $existingPixelSheet.UsedRange; Headers = @{} }
        } else {
            Release-ComObject $existingPixelSheet
            $imported = Import-CsvToSheet -Workbook $workbook -SheetName 'Pixel_Data' -CsvPath $csvPath -TableName $tableName
        }
        Set-ImageSummaryFormulas -Workbook $workbook -TableName $tableName
        $excel.Calculation = -4105
        $excel.CalculateFullRebuild()
        $workbook.Save()
        $workbook.Close($true)
        Release-ComObject $imported.Table; Release-ComObject $imported.Used; Release-ComObject $imported.Sheet; Release-ComObject $workbook
        $validation = Validate-Workbook -Excel $excel -Path $workbookPath -ExpectedSheet 'Pixel_Data' -ExpectedRows 327681
        $results.Add([pscustomobject]@{workbook=$workbookPath; excel_version=$excel.Version; automation='Microsoft Excel COM'; pivot_tables='not_applicable_per_image'; analysis_toolpak='installed_not_enabled'; used_rows=$validation.rows; expected_rows=$validation.expected_rows; external_links=$validation.links; formula_errors=$validation.formula_errors; status=$validation.status})
        Write-ProgressLog "complete pixel workbook $imageId status=$($validation.status)"
        Write-Output "Finalized $imageId"
    }

    $mainPath = Join-Path $ProjectRoot 'outputs\part_e\excel\part_e_pixel_statistical_analysis.xlsx'
    Write-ProgressLog 'open main workbook'
    $main = $excel.Workbooks.Open($mainPath, 0, $false)
    $excel.Calculation = -4135
    $sampleImports = @(
        @('Sample_LUHK','part_e_sample_luhk.csv','tblSampleLUHK'),
        @('Sample_Cover','part_e_sample_surface_cover.csv','tblSampleCover'),
        @('Sample_LUHK_Cover','part_e_sample_luhk_surface_cover.csv','tblSampleLUHKCover'),
        @('Sample_Cover_Shadow','part_e_sample_surface_cover_shadow.csv','tblSampleCoverShadow'),
        @('Sample_Image','part_e_sample_image_comparison.csv','tblSampleImage')
    )
    foreach ($spec in $sampleImports) {
        $existingSheet = $main.Worksheets.Item($spec[0])
        if ($existingSheet.UsedRange.Rows.Count -gt 2 -and $existingSheet.UsedRange.Columns.Count -gt 1 -and $existingSheet.ListObjects.Count -gt 0 -and $existingSheet.ListObjects.Item(1).Name -eq $spec[2]) {
            Write-ProgressLog "reuse imported main sheet $($spec[0])"
            Release-ComObject $existingSheet
        } else {
            Release-ComObject $existingSheet
            Write-ProgressLog "import main sheet $($spec[0])"
            $csv = Join-Path $ProjectRoot ('data\processed\part_e\samples\' + $spec[1])
            $imported = Import-CsvToSheet -Workbook $main -SheetName $spec[0] -CsvPath $csv -TableName $spec[2]
            Release-ComObject $imported.Table; Release-ComObject $imported.Used; Release-ComObject $imported.Sheet
        }
    }
    Write-ProgressLog 'add Excel crosscheck sheet'
    try {
        $crosscheck = $main.Worksheets.Item('Excel_Crosscheck')
        Write-ProgressLog 'reuse Excel crosscheck sheet'
    } catch {
        $crosscheck = Add-MainCrosscheckSheet -Workbook $main
    }
    $main.Save()
    Write-ProgressLog 'saved main import checkpoint'
    Write-ProgressLog 'create pivot analysis'
    $pivotSheet = Create-PivotAnalysis -Workbook $main
    Write-ProgressLog 'recalculate main workbook'
    $excel.Calculation = -4105
    $excel.CalculateFullRebuild()
    $nativeCount = Export-NativeCharts -Workbook $main -OutputDirectory (Join-Path $ProjectRoot 'outputs\part_e\figures\excel')
    Write-ProgressLog "exported native charts count=$nativeCount"
    $main.Save()
    Write-ProgressLog 'saved main workbook'
    $main.Close($true)
    Release-ComObject $crosscheck; Release-ComObject $pivotSheet; Release-ComObject $main
    $mainValidation = Validate-Workbook -Excel $excel -Path $mainPath -ExpectedSheet 'Sample_Cover' -ExpectedRows 27075
    Write-ProgressLog "validated main workbook status=$($mainValidation.status)"
    $results.Add([pscustomobject]@{workbook=$mainPath; excel_version=$excel.Version; automation='@oai/artifact-tool + Microsoft Excel COM'; pivot_tables='2_native_pivottables_1_pivotchart'; analysis_toolpak='installed_not_enabled'; used_rows=$mainValidation.rows; expected_rows=$mainValidation.expected_rows; external_links=$mainValidation.links; formula_errors=$mainValidation.formula_errors; native_charts_exported=$nativeCount; status=$mainValidation.status})

    $statusPath = Join-Path $ProjectRoot 'outputs\part_e\qa\part_e_excel_com_validation.csv'
    $results | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath $statusPath
    Write-ProgressLog 'wrote Excel validation CSV'
}
finally {
    if ($null -ne $excel) {
        try { $excel.Calculation = -4105 } catch { }
        try { $excel.Quit() } catch { }
        Release-ComObject $excel
    }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers(); Start-Sleep -Seconds 2
    if ($null -ne $excelPid -and (Get-Process -Id $excelPid -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $excelPid -Force
    }
}
