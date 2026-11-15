/* HM-45: the copy icon of a Taskosaur key chip (web/tsrlinks.py) copies its key; the icon turns into a check mark for
   1.5 s. Optional: without it the chip's link still works. Off a secure origin (a LAN host over http) the async
   clipboard is missing, so a hidden textarea and execCommand do the copy. */
document.addEventListener("click", function (ev) {
  var b = ev.target.closest && ev.target.closest("button.tsr-copy");
  if (!b) return;
  var text = b.getAttribute("data-copy"), label = b.getAttribute("aria-label");
  function done() {
    b.setAttribute("data-copied", ""); b.setAttribute("aria-label", "Copied " + text); b.title = "Copied";
    setTimeout(function () { b.removeAttribute("data-copied"); b.setAttribute("aria-label", label); b.title = label; }, 1500);
  }
  function legacy() {
    var t = document.createElement("textarea");
    t.value = text; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
    document.body.appendChild(t); t.select();
    try { if (document.execCommand("copy")) done(); } catch (e) { /* copy refused: the icon stays as it was */ }
    document.body.removeChild(t);
  }
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, legacy); else legacy();
});
