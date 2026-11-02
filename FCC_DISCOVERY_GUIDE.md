# FCC discovery collector

This is the preparatory, read-only stage for an FCC Autorouter.  It does not
open a document for routing or click any IRT form action.  It only:

- searches IRT inventory for court `FDFCC000`;
- uses a received-date range;
- records **LNI, Decision Date, Date Received, Route, and Source Detail** from
  each result row; and
- optionally downloads the linked PDFs for document-pattern analysis.

In the IRT result table, downloads are taken only from the link in the
**File name** column. Other row links are intentionally ignored.

Its default range is `01-01-2026` through `10-01-2026`. IRT requires dates in
that hyphenated `mm-dd-yyyy` format; the collector also accepts slash-formatted
dates and normalizes them automatically.

## First run: identify the search controls

Run from the project folder while connected to the corporate network:

```powershell
python tools/fcc_inventory_discovery.py --inspect-ui
```

It opens a visible browser and saves a non-sensitive inventory of field labels,
IDs, and names under:

`%USERPROFILE%\Downloads\Case Law Auto-Routing Resources\FCC Discovery\fcc_search_ui_inventory.json`

If the automatic field detection cannot find all four search controls, create
`fcc_search_selectors.json` beside that output with the observed CSS selectors:

```json
{
  "court": "#courtCode",
  "received_from": "#receivedDateFrom",
  "received_to": "#receivedDateTo",
  "search": "#search"
}
```

The IDs above are examples only; use the actual IDs from your IRT page.

## Collection run

After validating the controls, collect the historical FCC sample and PDFs:

```powershell
python tools/fcc_inventory_discovery.py --collect --download-pdfs --date-from 01-01-2026 --date-to 10-01-2026
```

The collector waits for the result table to stop changing before reading it.
IRT renders this search as one unpaginated result set, so it collects that
single set and checkpoints the Excel report once. Re-running it reuses rows
whose LNI already downloaded.

Outputs:

- `%USERPROFILE%\Downloads\Case Law Auto-Routing Resources\FCC Discovery\FDFCC000_inventory_discovery.xlsx`
- `%USERPROFILE%\Downloads\Case Law Auto-Routing Resources\FCC Discovery\FCC PDF Downloads\`

Do not set `--headless` for the first run: the visible session makes SSO or an
IRT access prompt apparent.  Once the historical PDFs and report are reviewed,
we can design FCC extraction and routing rules from actual evidence.
