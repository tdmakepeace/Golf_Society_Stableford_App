(function () {
  var root = document.querySelector("[data-page-tabs]");
  if (!root) return;

  var tabs = root.querySelectorAll('[role="tab"]');
  var panels = root.querySelectorAll('[role="tabpanel"]');
  if (!tabs.length || !panels.length) return;

  function activate(panelId, focusTab) {
    tabs.forEach(function (tab) {
      var selected = tab.getAttribute("aria-controls") === panelId;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.tabIndex = selected ? 0 : -1;
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.id !== panelId;
    });
    var slug = panelId.replace(/^tab-/, "");
    if (history.replaceState) {
      history.replaceState(null, "", "#" + slug);
    }
    if (focusTab) {
      var tab = root.querySelector('[aria-controls="' + panelId + '"]');
      if (tab) tab.focus();
    }
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      activate(tab.getAttribute("aria-controls"), false);
    });
    tab.addEventListener("keydown", function (e) {
      var idx = Array.prototype.indexOf.call(tabs, tab);
      var next = -1;
      if (e.key === "ArrowRight") next = (idx + 1) % tabs.length;
      if (e.key === "ArrowLeft") next = (idx - 1 + tabs.length) % tabs.length;
      if (e.key === "Home") next = 0;
      if (e.key === "End") next = tabs.length - 1;
      if (next >= 0) {
        e.preventDefault();
        activate(tabs[next].getAttribute("aria-controls"), true);
      }
    });
  });

  var hash = (location.hash || "").replace(/^#/, "");
  var defaultSlug = root.getAttribute("data-default-tab") || "";
  var initial = hash ? "tab-" + hash : (defaultSlug ? "tab-" + defaultSlug : panels[0].id);
  if (!root.querySelector("#" + initial)) initial = panels[0].id;
  activate(initial, false);
})();
