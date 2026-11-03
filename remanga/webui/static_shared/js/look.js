// The look of remanga's pages: "android" (Material 3 Expressive, the default) or "terminal" (the
// menus' dark colours, theme.css). Loaded in <head> so the page never flashes the other look; the
// Look button it puts in the top bar switches and remembers the choice in this browser.
(function () {
  var KEY = 'remanga:look';
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { /* storage off: the default look */ }
  var look = saved === 'terminal' ? 'terminal' : 'android';
  root.dataset.style = look;

  function label(button) {
    button.textContent = root.dataset.style === 'android' ? 'Look: Android' : 'Look: Terminal';
    button.title = 'Switch between the Android look and the terminal look';
  }

  document.addEventListener('DOMContentLoaded', function () {
    var bar = document.querySelector('.topbar') || document.querySelector('header');
    if (!bar) return;
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'look-btn';
    label(button);
    button.addEventListener('click', function () {
      root.dataset.style = root.dataset.style === 'android' ? 'terminal' : 'android';
      try { localStorage.setItem(KEY, root.dataset.style); } catch (e) { /* not remembered */ }
      label(button);
    });
    bar.appendChild(button);
  });
}());
