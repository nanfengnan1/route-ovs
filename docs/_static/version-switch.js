/* Offline-compatible release selector. The catalog lives outside each snapshot. */
(function () {
  "use strict";
  const htmlRoot = new URL("../", document.currentScript.src);
  const config = window.ROUTE_OVS_DOC_VERSION || {};
  const catalogURL = new URL((config.archiveBase || "../versions/") + "catalog.js", htmlRoot);
  let page = decodeURIComponent(window.location.pathname.slice(htmlRoot.pathname.length));
  if (!page || page.endsWith("/")) page += "index.html";

  function install() {
    const sidebar = document.querySelector(".wy-nav-side");
    if (!sidebar) return;
    const box = document.createElement("details");
    box.className = "route-ovs-version-switch";
    const summary = document.createElement("summary");
    summary.setAttribute("aria-label", "选择文档版本");
    const label = document.createElement("span");
    label.className = "route-ovs-version-label";
    label.textContent = "文档版本";
    const pageVersion = window.DOCUMENTATION_OPTIONS && window.DOCUMENTATION_OPTIONS.VERSION;
    const activeVersion = (config.archived ? config.version : pageVersion) || config.version || "当前版本";
    const value = document.createElement("span");
    value.className = "route-ovs-version-current";
    value.textContent = activeVersion;
    const arrow = document.createElement("span");
    arrow.className = "route-ovs-version-arrow";
    arrow.setAttribute("aria-hidden", "true");
    value.appendChild(arrow);
    summary.append(label, value);
    const panel = document.createElement("nav");
    panel.className = "route-ovs-version-panel";
    panel.setAttribute("aria-label", "可选文档版本");
    const heading = document.createElement("div");
    heading.className = "route-ovs-version-heading";
    heading.textContent = "版本";
    panel.appendChild(heading);
    function add(version, kind, destination, selected) {
      const link = document.createElement("a");
      link.href = destination;
      link.className = "route-ovs-version-option";
      if (selected) {
        link.classList.add("is-current");
        link.setAttribute("aria-current", "true");
      }
      const name = document.createElement("span");
      name.textContent = version;
      const badge = document.createElement("span");
      badge.className = "route-ovs-version-kind";
      badge.textContent = kind + (selected ? " ✓" : "");
      link.append(name, badge);
      panel.appendChild(link);
    }
    if (!config.archived) add(activeVersion, "当前构建", window.location.href, true);
    const records = window.ROUTE_OVS_DOC_VERSIONS || [];
    records.forEach(function (record) {
      const targetPage = record.pages.includes(page) ? page : "index.html";
      const target = new URL(encodeURIComponent(record.version) + "/html/" + targetPage, catalogURL);
      add(record.version, "归档", target.href, config.archived && record.version === activeVersion);
    });
    if (config.archived && !records.some(record => record.version === activeVersion)) {
      add(activeVersion, "归档", window.location.href, true);
    }
    box.append(summary, panel);
    document.addEventListener("click", function (event) {
      if (!box.contains(event.target)) box.open = false;
    });
    box.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        box.open = false;
        summary.focus();
      }
    });
    sidebar.classList.add("route-ovs-has-version-switch");
    sidebar.appendChild(box);
  }
  function load() {
    const script = document.createElement("script");
    const requestURL = new URL(catalogURL.href);
    requestURL.searchParams.set("t", String(Date.now()));
    script.src = requestURL.href;
    // A fresh project may not have an archive yet; still show the current version.
    script.onload = install;
    script.onerror = install;
    document.head.appendChild(script);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load);
  else load();
}());
