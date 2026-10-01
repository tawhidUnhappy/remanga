// The two full-page screens every remanga browser tab shares: loading (while
// the tab waits for the server - a spinner, what it is doing and for how long,
// never an empty page) and done (when the session ends: what was saved, what
// to do next, and the tab closing itself - or saying plainly that it is safe
// to close). Styles in /shared/css/screens.css.

const html = (s) => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function layer(id) {
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement("div");
    el.id = id;
    el.className = "rm-screen";
    document.body.appendChild(el);
  }
  return el;
}

let timer = null;

// Shows (or updates) the loading screen. `detail` is a second, quieter line.
export function showLoading(text, detail = "") {
  const el = layer("rm-loading");
  const started = el.dataset.started ? Number(el.dataset.started) : Date.now();
  el.dataset.started = String(started);
  el.innerHTML = `<div class="rm-card"><div class="rm-spinner"></div>
    <h2>${html(text)}</h2>${detail ? `<p>${html(detail)}</p>` : ""}<p class="rm-elapsed mono">0 s</p></div>`;
  el.classList.add("visible");
  clearInterval(timer);
  const tick = () => {
    const out = el.querySelector(".rm-elapsed");
    if (out) out.textContent = `${Math.round((Date.now() - started) / 1000)} s`;
  };
  tick();
  timer = setInterval(tick, 500);
}

export function hideLoading() {
  clearInterval(timer);
  const el = document.getElementById("rm-loading");
  if (el) { el.classList.remove("visible"); delete el.dataset.started; }
}

// The end of a session. `facts` are [label, value] rows; `next` says what to
// do in the terminal now. The tab tries to close itself after `closeIn`
// seconds; browsers only allow that for tabs a script opened, so if it is
// still here after that it says so instead of counting forever.
export function showDone({ title, facts = [], next = "", closeIn = 10 }) {
  hideLoading();
  const el = layer("rm-done");
  el.classList.add("done");
  el.innerHTML = `<div class="rm-card wide">
    <div class="rm-check">✓</div>
    <h2>${html(title)}</h2>
    ${facts.length ? `<dl>${facts.map(([k, v]) => `<dt>${html(k)}</dt><dd>${html(v)}</dd>`).join("")}</dl>` : ""}
    ${next ? `<p class="rm-next"><b>Next:</b> ${html(next)}</p>` : ""}
    <p class="rm-terminal">The terminal has carried on - nothing else is needed here.</p>
    <p class="rm-close mono"></p>
    <button class="rm-close-btn" type="button">Close this tab</button></div>`;
  el.classList.add("visible");
  const note = el.querySelector(".rm-close");
  const close = () => {
    try { window.close(); } catch {}
    setTimeout(() => { note.textContent = "You can close this tab now."; }, 300);
  };
  el.querySelector(".rm-close-btn").addEventListener("click", close);
  let left = closeIn;
  note.textContent = `This tab closes in ${left} s`;
  const countdown = setInterval(() => {
    left -= 1;
    if (left > 0) { note.textContent = `This tab closes in ${left} s`; return; }
    clearInterval(countdown);
    close();
  }, 1000);
}
