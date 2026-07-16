#!/usr/bin/env node
// Author formal Part E workbooks with the supported @oai/artifact-tool runtime.

import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const payloadPath = process.argv[2];
if (!payloadPath) throw new Error("Usage: node build_part_e_workbooks.mjs <payload.json>");
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));

const headerFormat = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF", size: 11 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
const titleFormat = {
  fill: "#D9EAF7",
  font: { bold: true, color: "#17365D", size: 14 },
  verticalAlignment: "center",
};

function columnName(number) {
  let value = number;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

function typedValue(value) {
  if (value === "") return null;
  if (/^(true|false)$/i.test(value)) return value.toLowerCase() === "true";
  if (/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) return Number(value);
  return value;
}

function parseCsv(text) {
  const input = text.replace(/^\uFEFF/, "");
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    if (quoted) {
      if (char === '"' && input[index + 1] === '"') { field += '"'; index += 1; }
      else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === ',') { row.push(typedValue(field)); field = ""; }
    else if (char === '\n') {
      row.push(typedValue(field)); field = "";
      if (row.length > 1 || row[0] !== null) rows.push(row);
      row = [];
    } else if (char !== '\r') field += char;
  }
  if (field !== "" || row.length) { row.push(typedValue(field)); rows.push(row); }
  const columns = Math.max(...rows.map((item) => item.length));
  for (const item of rows) while (item.length < columns) item.push(null);
  return { values: rows, rows: rows.length, columns };
}

function styleDataSheet(sheet, rows, columns) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  sheet.getRangeByIndexes(0, 0, 1, columns).format = headerFormat;
  sheet.getRangeByIndexes(0, 0, Math.min(rows, 200), columns).format.verticalAlignment = "center";
  for (let col = 0; col < columns; col += 1) {
    sheet.getRangeByIndexes(0, col, Math.min(rows, 200), 1).format.columnWidth = col < 8 ? 18 : 16;
  }
  sheet.getRangeByIndexes(0, 0, 1, columns).format.rowHeight = 34;
}

async function importCsvSheet(workbook, spec) {
  const csvText = await fs.readFile(spec.path, "utf8");
  const parsed = parseCsv(csvText);
  const dims = { rows: parsed.rows, columns: parsed.columns };
  const sheet = workbook.worksheets.add(spec.name);
  const chunkSize = 5000;
  for (let start = 0; start < parsed.rows; start += chunkSize) {
    const chunk = parsed.values.slice(start, start + chunkSize);
    sheet.getRangeByIndexes(start, 0, chunk.length, parsed.columns).values = chunk;
  }
  styleDataSheet(sheet, dims.rows, dims.columns);
  if (spec.tableName && dims.rows >= 2) {
    const table = sheet.tables.add(`A1:${columnName(dims.columns)}${dims.rows}`, true, spec.tableName);
    table.style = "TableStyleMedium2";
    table.showFilterButton = true;
  }
  if (spec.numberFormats) {
    for (const item of spec.numberFormats) {
      sheet.getRange(item.range).format.numberFormat = item.format;
    }
  }
  return { sheet, ...dims };
}

function addPixelQaSheet(workbook, rows) {
  const sheet = workbook.worksheets.add("Pixel_QA");
  const headers = ["source_excel_row", "pixel_uid", "thermal_row", "thermal_col", "temperature_c", "ambient_temperature_c", "delta_t_c", "Excel residual: temperature - ambient - delta_t"];
  sheet.getRangeByIndexes(0, 0, 1, headers.length).values = [headers];
  if (rows.length) {
    sheet.getRangeByIndexes(1, 0, rows.length, 7).values = rows.map((row) => [row.source_excel_row, row.pixel_uid, row.thermal_row, row.thermal_col, row.temperature_c, row.ambient_temperature_c, row.delta_t_c]);
    sheet.getRange("H2").formulas = [[`='Pixel_Data'!I${rows[0].source_excel_row}-'Pixel_Data'!J${rows[0].source_excel_row}-'Pixel_Data'!K${rows[0].source_excel_row}`]];
    for (let index = 1; index < rows.length; index += 1) {
      const excelRow = rows[index].source_excel_row;
      sheet.getRange(`H${index + 2}`).formulas = [[`='Pixel_Data'!I${excelRow}-'Pixel_Data'!J${excelRow}-'Pixel_Data'!K${excelRow}`]];
    }
    sheet.getRange(`E2:H${rows.length + 1}`).format.numberFormat = "0.000000";
    sheet.getRange(`H2:H${rows.length + 1}`).conditionalFormats.add("cellIs", {
      operator: "notEqual", formula: 0, format: { fill: "#F4CCCC", font: { color: "#9C0006" } },
    });
  }
  styleDataSheet(sheet, rows.length + 1, headers.length);
  return sheet;
}

async function renderWorkbook(workbook, names, previewDir, prefix) {
  await fs.mkdir(previewDir, { recursive: true });
  for (const name of names) {
    const preview = await workbook.render({ sheetName: name, range: "A1:H24", scale: 1, format: "png" });
    await fs.writeFile(path.join(previewDir, `${prefix}_${name}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}

async function buildPixelWorkbook() {
  const workbook = Workbook.create();
  const readme = workbook.worksheets.add("README");
  readme.getRange("A1:B1").values = [["Part E complete thermal-pixel workbook", payload.image_id]];
  readme.getRange("A1:B1").format = titleFormat;
  readme.getRange("A3:B11").values = [
    ["Observation unit", "One original thermal pixel"],
    ["Delta-T formula", "delta_t_c = temperature_c - ambient_temperature_c"],
    ["Temperature unit", "°C"], ["Delta-T unit", "°C"],
    ["Pixel policy", "all_finite_pixels"], ["Ambient source", "TAT3"],
    ["Ambient validation", "provisional; not independently validated meteorological air temperature"],
    ["LUHK cell use", "Provenance and alignment QA only; never averaged"],
    ["Spatial dependence", "Neighbouring pixels are correlated; inferential p-values are exploratory"],
  ];
  readme.getRange("A3:A11").format.font = { bold: true, color: "#17365D" };
  readme.getRange("A1:B12").format.wrapText = true;
  readme.getRange("A1:A12").format.columnWidth = 28; readme.getRange("B1:B12").format.columnWidth = 75;
  readme.showGridLines = false;

  const pixel = workbook.worksheets.add("Pixel_Data");
  pixel.getRange("A1:B2").values = [["Pixel_Data is populated by the Excel COM import stage", ""], ["All 327,680 rows are inserted as an Excel Table before final validation", ""]];
  pixel.getRange("A1:B1").format = headerFormat; pixel.getRange("A1:B2").format.columnWidth = 45; pixel.showGridLines = false;

  const summary = workbook.worksheets.add("Image_Summary");
  summary.getRange("A1:C1").values = [["Metric", "Python full-pixel value", "Excel formula cross-check"]];
  summary.getRangeByIndexes(1, 0, payload.summary_rows.length, 2).values = payload.summary_rows;
  styleDataSheet(summary, payload.summary_rows.length + 1, 3);
  summary.getRange(`B2:C${payload.summary_rows.length + 1}`).format.numberFormat = "0.000000";

  addPixelQaSheet(workbook, payload.qa_rows);
  await importCsvSheet(workbook, { name: "Analysis_Sample", path: payload.analysis_sample_csv, tableName: "tblAnalysisSample" });

  const charts = workbook.worksheets.add("Charts");
  charts.getRange("A1:B4").values = [["Metric", "Value"], ["Mean temperature (°C)", payload.chart_data.temperature_mean_c], ["Ambient temperature (°C)", payload.chart_data.ambient_temperature_c], ["Mean ΔT (°C)", payload.chart_data.delta_t_mean_c]];
  charts.getRange("A1:B1").format = headerFormat; charts.getRange("B2:B4").format.numberFormat = "0.00"; charts.getRange("A1:B4").format.columnWidth = 28;
  const chart = charts.charts.add("bar", charts.getRange("A1:B4"));
  chart.title = "Image-level temperature and ΔT summary (°C)"; chart.hasLegend = false; chart.yAxis = { numberFormatCode: "0.0" }; chart.setPosition("D2", "L20");
  charts.showGridLines = false;

  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "pixel skeleton formula scan" });
  if (errors.ndjson.includes("#REF!") || errors.ndjson.includes("#VALUE!")) throw new Error(errors.ndjson);
  await renderWorkbook(workbook, ["README", "Pixel_Data", "Image_Summary", "Pixel_QA", "Analysis_Sample", "Charts"], payload.preview_dir, payload.image_id);
  await fs.mkdir(path.dirname(payload.output), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook); await output.save(payload.output);
}

async function buildMainWorkbook() {
  const workbook = Workbook.create();
  for (const spec of payload.sheets) await importCsvSheet(workbook, spec);
  const charts = workbook.worksheets.add("Charts");
  charts.getRange("A1").values = [["Native Excel charts; external publication figures are exported separately."]];
  charts.getRange("A1:H1").format = titleFormat; charts.showGridLines = false;
  const figureData = workbook.worksheets.getItem("Figure_Data");
  const coverChart = charts.charts.add("bar", figureData.getRange(payload.cover_chart_range));
  coverChart.title = "Full-pixel mean and median ΔT by cover (°C)"; coverChart.hasLegend = true; coverChart.yAxis = { numberFormatCode: "0.0" }; coverChart.setPosition("A3", "J20");
  const coverageChart = charts.charts.add("bar", figureData.getRange(payload.coverage_chart_range));
  coverageChart.title = "Sampled pixel count by analysis family"; coverageChart.hasLegend = false; coverageChart.yAxis = { numberFormatCode: "#,##0" }; coverageChart.setPosition("K3", "T20");

  const testsSheet = workbook.worksheets.getItem("Statistical_Tests");
  const testsUsed = testsSheet.getUsedRange();
  testsUsed.conditionalFormats.add("containsText", { text: "skipped", format: { fill: "#FFF2CC", font: { color: "#7F6000" } } });
  const sampleNames = ["Sample_LUHK", "Sample_Cover", "Sample_LUHK_Cover", "Sample_Cover_Shadow", "Sample_Image"];
  for (const name of sampleNames) workbook.worksheets.getItem(name).freezePanes.freezeRows(1);

  const names = payload.sheets.map((item) => item.name).concat(["Charts"]);
  const key = await workbook.inspect({ kind: "table", range: "Full_Pixel_Image_Summary!A1:H10", include: "values,formulas", tableMaxRows: 10, tableMaxCols: 8 });
  if (!key.ndjson.includes("image_id")) throw new Error("Main workbook key-range inspection failed.");
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "main workbook formula scan" });
  if (errors.ndjson.includes("#REF!") || errors.ndjson.includes("#VALUE!")) throw new Error(errors.ndjson);
  await renderWorkbook(workbook, names, payload.preview_dir, "main");
  await fs.mkdir(path.dirname(payload.output), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook); await output.save(payload.output);
}

if (payload.mode === "pixel") await buildPixelWorkbook();
else if (payload.mode === "main") await buildMainWorkbook();
else throw new Error(`Unknown workbook mode: ${payload.mode}`);
