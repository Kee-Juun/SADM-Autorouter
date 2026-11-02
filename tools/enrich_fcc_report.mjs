import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const discoveryRoot = path.join(
  process.env.USERPROFILE || "C:\\Users\\libunak",
  "Downloads",
  "Case Law Auto-Routing Resources",
  "FCC Discovery",
);
const inputPath = process.env.FCC_REPORT_INPUT || path.join(discoveryRoot, "FDFCC000_inventory_discovery.xlsx");
const auditPath = process.env.FCC_AUDIT_JSON || path.join(projectRoot, "tmp", "fcc_pdf_audit.json");
const outputPath = process.env.FCC_REPORT_OUTPUT || path.join(discoveryRoot, "FDFCC000_inventory_discovery_enriched.xlsx");
const previewPath = path.join(projectRoot, "tmp", "fcc_report_enriched_preview.png");

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("FDFCC000 Results");

if (process.argv.includes("--inspect")) {
  const summary = await workbook.inspect({
    kind: "workbook,sheet,table,region",
    sheetId: sheet.sheetId,
    range: "A1:G12",
    maxChars: 6000,
    tableMaxRows: 12,
    tableMaxCols: 8,
  });
  console.log(summary.ndjson);
  const preview = await workbook.render({
    sheetName: sheet.name,
    range: "A1:G12",
    autoCrop: "all",
    scale: 1.5,
    format: "png",
  });
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  console.log(`Preview: ${previewPath}`);
  process.exit(0);
}

const auditRows = JSON.parse(await fs.readFile(auditPath, "utf8"));
const auditByLni = new Map(auditRows.map((row) => [String(row.lni), row]));
const used = sheet.getUsedRange();
const rowCount = used.rowCount;
if (rowCount < 2) throw new Error("FCC report does not contain data rows.");

const additions = [
  "Filename",
  "Docket Number",
  "Filename Pattern",
  "PDF Read Status",
  "PDF Page Count",
  "Content Title",
  "Docket Match",
  "Decision Date Match",
  "Source Detail Evidence",
  "Content Read Note",
];
const enrichment = [additions];
const lnis = sheet.getRange(`A2:A${rowCount}`).values;
for (const [lniValue] of lnis) {
  const record = auditByLni.get(String(lniValue || ""));
  if (!record) {
    enrichment.push(["", "", "", "No completed IRT HTML row", "", "", "Not assessed", "Not assessed", "Not assessed", "LNI absent from saved IRT HTML"]);
    continue;
  }
  enrichment.push([
    record.filename || "",
    record.docket_number || "",
    record.filename_pattern || "",
    record.local_pdf_status || "",
    record.pdf_page_count || "",
    record.content_title || "",
    record.docket_match || "",
    record.decision_date_match || "",
    record.source_detail_evidence || "",
    record.read_error || "",
  ]);
}

const endColumn = "Q";
sheet.getRange(`H1:${endColumn}${rowCount}`).values = enrichment;
sheet.getRange("H1:Q1").format = {
  fill: "#1F4E78",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#FFFFFF" },
};
sheet.getRange(`A1:${endColumn}${rowCount}`).format.font = { name: "Arial", size: 10 };
sheet.getRange(`H2:${endColumn}${rowCount}`).format.verticalAlignment = "center";
sheet.getRange(`H2:H${rowCount}`).format.columnWidth = 36;
sheet.getRange(`I2:I${rowCount}`).format.columnWidth = 24;
sheet.getRange(`J2:J${rowCount}`).format.columnWidth = 25;
sheet.getRange(`K2:K${rowCount}`).format.columnWidth = 18;
sheet.getRange(`L2:L${rowCount}`).format.columnWidth = 14;
sheet.getRange(`M2:M${rowCount}`).format.columnWidth = 58;
sheet.getRange(`N2:P${rowCount}`).format.columnWidth = 28;
sheet.getRange(`Q2:Q${rowCount}`).format.columnWidth = 36;
sheet.freezePanes.freezeRows(1);
workbook.recalculate();

const verification = await workbook.inspect({
  kind: "region",
  sheetId: sheet.sheetId,
  range: "A1:Q6",
  maxChars: 6000,
});
console.log(verification.ndjson);
const preview = await workbook.render({
  sheetName: sheet.name,
  range: "A1:Q12",
  autoCrop: "all",
  scale: 1.25,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(`Output: ${outputPath}`);
