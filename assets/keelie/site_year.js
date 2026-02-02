// File: assets/site_year.js
// Small helper so we don't need inline scripts (CSP-friendly).
(function () {
  "use strict";
  const el = document.getElementById("year");
  if (el) el.textContent = String(new Date().getFullYear());
})();
