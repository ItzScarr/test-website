// File: assets/keelie/keelie_stock_loader.js
// ------------------------------------------------------------
// Loads stock_codes.xlsx in the browser (via SheetJS) and exposes:
//   - window.keelieStockRows: [{ product_name, stock_code }, ...]
//   - window.keelieStockReady: Promise that resolves when done
//
// The Excel URL is passed from HTML as a data attribute:
//   data-keelie-excel-url="/test-website/assets/keelie/stock_codes.xlsx"
// ------------------------------------------------------------

(function () {
  "use strict";

  const scriptEl = document.currentScript;
  const excelUrl = (scriptEl && scriptEl.getAttribute("data-keelie-excel-url"))
    ? scriptEl.getAttribute("data-keelie-excel-url")
    : "assets/keelie/stock_codes.xlsx";

  // Ensure globals exist
  window.keelieStockRows = Array.isArray(window.keelieStockRows) ? window.keelieStockRows : [];

  function normKey(k) {
    return String(k || "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "_");
  }

  async function loadStockFromExcel() {
    try {
      if (!window.XLSX) {
        console.warn("Keelie: SheetJS (XLSX) not found. Stock codes will be unavailable.");
        window.keelieStockRows = [];
        return;
      }

      const res = await fetch(excelUrl, { cache: "no-store" });
      if (!res.ok) {
        console.warn("Keelie: stock_codes.xlsx not found:", res.status);
        window.keelieStockRows = [];
        return;
      }

      const buf = await res.arrayBuffer();
      const wb = window.XLSX.read(buf, { type: "array" });

      const sheetName = wb.SheetNames[0];
      const ws = wb.Sheets[sheetName];
      const rawRows = window.XLSX.utils.sheet_to_json(ws, { defval: "" });

      const rows = rawRows
        .map((r) => {
          const obj = {};
          for (const [k, v] of Object.entries(r)) obj[normKey(k)] = String(v).trim();
          return {
            product_name: obj.product_name || obj.product || obj.name || "",
            stock_code: obj.stock_code || obj.sku || obj.code || "",
          };
        })
        .filter((r) => r.product_name && r.stock_code);

      window.keelieStockRows = rows;
      console.log(`Keelie: Loaded ${rows.length} stock rows from Excel.`);

      // Light sanity warning (helps catch wrong path / empty file)
      if (rows.length > 0 && rows.length < 10) {
        console.warn(
          "Keelie: Loaded a very small number of stock rows. Check the Excel URL/contents:",
          excelUrl
        );
      }
    } catch (e) {
      console.error("Keelie: failed to load/parse Excel", e);
      window.keelieStockRows = [];
    }
  }

  // Python will await this promise
  window.keelieStockReady = loadStockFromExcel();
})();
