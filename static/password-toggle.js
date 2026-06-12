(function () {
  function enhancePasswordInput(input) {
    if (input.dataset.passwordToggle === "off" || input.closest(".password-field-wrap")) {
      return;
    }

    var wrap = document.createElement("span");
    wrap.className = "password-field-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "password-reveal-btn";
    btn.textContent = "Show password";
    btn.setAttribute("aria-pressed", "false");
    wrap.appendChild(btn);

    btn.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      btn.textContent = showing ? "Show password" : "Hide password";
      btn.setAttribute("aria-pressed", showing ? "false" : "true");
    });
  }

  function init() {
    document.querySelectorAll('input[type="password"]').forEach(enhancePasswordInput);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
