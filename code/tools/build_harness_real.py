import os

D = os.environ.get("WORKDIR", ".")   # folder holding live/, vendor/, refimg/
js = open(os.path.join(D, "live", "index.js"), encoding="utf-8").read()
css = open(os.path.join(D, "live", "style.css"), encoding="utf-8").read()
react = open(os.path.join(D, "vendor", "react.js"), encoding="utf-8").read()
rdom = open(os.path.join(D, "vendor", "react-dom.js"), encoding="utf-8").read()

html = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>cc real harness</title>
<style>html,body{margin:0;background:#050b14;color:#eaf6ff;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}#root{min-height:100vh}</style>
<style>__CSS__</style>
<script>__REACT__</script>
<script>__REACTDOM__</script>
</head><body><div id="root"></div>
<script>
// Test page only: the SDK talks to REAL endpoints (no fixtures). No login here, this server exists only for the test.
if (location.search.indexOf("insecure") >= 0) { Object.defineProperty(window, "isSecureContext", { value: false, configurable: true }); }
window.__HERMES_PLUGIN_SDK__ = {
  React: React,
  hooks: { useState: React.useState, useEffect: React.useEffect, useCallback: React.useCallback, useRef: React.useRef, useMemo: React.useMemo },
  fetchJSON: function (url, opts) {
    return fetch(url, opts).then(function (r) { return r.text().then(function (t) { if (!r.ok) { throw new Error(r.status + " " + t.slice(0, 200)); } return t ? JSON.parse(t) : {}; }); });
  },
  buildWsUrl: function (path) { return Promise.resolve("ws://" + location.host + path); },
};
window.__HERMES_PLUGINS__ = { register: function (name, Comp) { ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(Comp)); } };
</script>
<script>__JS__</script>
</body></html>
"""
html = html.replace("__CSS__", css).replace("__REACT__", react).replace("__REACTDOM__", rdom).replace("__JS__", js.replace("</script>", "<\\/script>"))
out = os.path.join(D, "harness_cc_real.html")
open(out, "w", encoding="utf-8").write(html)
print("wrote", out, len(html) // 1024, "KB")
