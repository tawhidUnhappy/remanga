// The Strip Marker: a webtoon chapter as one strip, scrolled like reading it,
// each panel a band across it from a top row to a bottom row. Ported from
// mangaEasy's webtoon panel editor (assets/static/js/editor.js) - the same
// gestures: click a line, click again for the area; drag an edge; right-click
// deletes; S splits the panel under the mouse; N starts a line after the last
// panel; R re-runs the auto marks. Added here: Ctrl+Z, autosave, panel numbers,
// remanga's look.
//
// Every row number is a row of the WHOLE strip - the downloaded images stacked
// in order, each at its own natural size - the same rows strip_marks.json and
// remanga/longstrip/build.py use.

(() => {
  const MIN_PANEL = 20;           // rows; build.py's MIN_MARK_PX
  const EDGE_GRAB_PX = 10;        // how near an edge (on screen) grabs it
  const HISTORY_LIMIT = 100;

  const $ = (id) => document.getElementById(id);
  const reader = $("reader"), pagesEl = $("pages"), statusEl = $("status"), countEl = $("count");

  let pages = [];                 // [{name, width, height, top, img, overlay}]
  let panels = [];                // [{top, bottom}] in strip rows, sorted, not overlapping
  let totalHeight = 0;
  let pendingLine = null;         // first click of a new panel
  let hoverIndex = -1, hoverY = null;
  let dragging = null;            // {index, edge, startY, startTop, startBottom, before}
  let suppressClick = false;
  let finished = false;
  const history = [];

  const setStatus = (text) => { statusEl.textContent = text; };
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  // --- changes: normalize, remember for undo, autosave -------------------
  function normalize(list) {
    const cleaned = list
      .map(p => ({ top: clamp(Math.round(p.top), 0, totalHeight), bottom: clamp(Math.round(p.bottom), 0, totalHeight) }))
      .filter(p => p.bottom > p.top)
      .sort((a, b) => a.top - b.top);
    const out = [];
    for (const p of cleaned) {
      const top = out.length ? Math.max(p.top, out[out.length - 1].bottom) : p.top;
      if (p.bottom - top >= MIN_PANEL) out.push({ top, bottom: p.bottom });
    }
    return out;
  }

  // Every change goes through here: what the marks were goes on the undo
  // stack, the new ones are drawn and saved.
  function commit(next, before = JSON.stringify(panels)) {
    const normalized = normalize(next);
    if (JSON.stringify(normalized) === before) { panels = normalized; redrawAll(); return; }
    history.push(before);
    if (history.length > HISTORY_LIMIT) history.shift();
    panels = normalized;
    changed();
  }

  function undo() {
    if (!history.length) { setStatus("Nothing to undo."); return; }
    panels = JSON.parse(history.pop());
    pendingLine = null;
    changed();
    setStatus("Undone.");
  }

  let saveTimer = null;
  function changed() {
    countEl.textContent = panels.length;
    $("undoBtn").disabled = !history.length;
    redrawAll();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 500);
  }

  async function post(url, body) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                   body: JSON.stringify(body || {}) });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }

  async function save() {
    if (finished) return;
    try { await post("/api/marks", { panels: panels.map(p => [p.top, p.bottom]) }); }
    catch (e) { setStatus("Couldn't save the marks: " + e.message); }
  }

  // --- the strip ----------------------------------------------------------
  async function load() {
    setStatus("Finding the panels...");
    const data = await (await fetch("/api/strip")).json();
    $("where").textContent = `${data.title} · chapter ${data.chapter}`;
    document.title = `remanga - Strip Marker - chapter ${data.chapter}`;
    for (const image of data.images) addPage(image);
    totalHeight = data.images.reduce((sum, im) => sum + im.height, 0);
    panels = normalize(data.panels.map(([top, bottom]) => ({ top, bottom })));
    countEl.textContent = panels.length;
    $("undoBtn").disabled = true;
    requestAnimationFrame(() => { resizeAll(); redrawAll(); });
    setStatus(data.proposed ? "Marked by the gutter splitter - scroll through and fix what is wrong."
                            : "Your saved marks.");
  }

  function addPage(image) {
    const el = document.createElement("div");
    el.className = "page";
    const img = document.createElement("img");
    img.src = `/api/images/${encodeURIComponent(image.name)}`;
    img.width = image.width; img.height = image.height;   // the right height before it loads
    img.draggable = false;
    img.loading = "lazy";
    const overlay = document.createElement("canvas");
    el.append(img, overlay);
    pagesEl.appendChild(el);
    const page = { ...image, el, img, overlay };
    pages.push(page);
    visibility.observe(el);
    img.addEventListener("load", () => { resize(page); redraw(page); });
    attachEvents(page);
  }

  // Only pages on screen are drawn; one that scrolls in is drawn then.
  const visible = new Set();
  const visibility = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      const page = pages.find(p => p.el === entry.target);
      if (!page) continue;
      if (entry.isIntersecting) { visible.add(page); redraw(page); } else visible.delete(page);
    }
  }, { root: reader, rootMargin: "200px" });

  function resize(page) {
    const rect = page.img.getBoundingClientRect();
    if (!rect.width) return;
    page.overlay.width = rect.width; page.overlay.height = rect.height;
    page.overlay.style.width = rect.width + "px"; page.overlay.style.height = rect.height + "px";
  }
  const resizeAll = () => pages.forEach(resize);

  let frame = null;
  function redrawAll() {
    if (frame) return;
    frame = requestAnimationFrame(() => { frame = null; (visible.size ? visible : pages).forEach(redraw); });
  }

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  function redraw(page) {
    const ctx = page.overlay.getContext("2d");
    const w = page.overlay.width, h = page.overlay.height;
    ctx.clearRect(0, 0, w, h);
    if (!w) return;
    const scale = h / page.height;
    const pageTop = page.top, pageBottom = page.top + page.height;
    const accent = css("--accent") || "#fea62b", ok = css("--ok") || "#4ebf71";
    panels.forEach((p, i) => {
      const top = Math.max(p.top, pageTop), bottom = Math.min(p.bottom, pageBottom);
      if (bottom <= top) return;
      const y0 = (top - pageTop) * scale, y1 = (bottom - pageTop) * scale;
      const hovered = i === hoverIndex;
      ctx.fillStyle = hovered ? "rgba(254,166,43,0.16)" : "rgba(78,191,113,0.12)";
      ctx.fillRect(0, y0, w, y1 - y0);
      ctx.strokeStyle = hovered ? accent : ok;
      ctx.lineWidth = hovered ? 2.5 : 2;
      ctx.beginPath();
      ctx.moveTo(1, y0); ctx.lineTo(1, y1); ctx.moveTo(w - 1, y0); ctx.lineTo(w - 1, y1);
      const trueTop = p.top >= pageTop, trueBottom = p.bottom <= pageBottom;
      if (trueTop) { ctx.moveTo(0, y0 + 1); ctx.lineTo(w, y0 + 1); }
      if (trueBottom) { ctx.moveTo(0, y1 - 1); ctx.lineTo(w, y1 - 1); }
      ctx.stroke();
      ctx.fillStyle = hovered ? accent : ok;
      for (const [edge, y] of [[trueTop, y0 + 1], [trueBottom, y1 - 1]]) {
        if (!edge) continue;
        ctx.beginPath(); ctx.arc(10, y, 4, 0, Math.PI * 2); ctx.arc(w - 10, y, 4, 0, Math.PI * 2); ctx.fill();
      }
      if (trueTop) {   // the panel's number, where it starts
        const label = `Panel ${i + 1}`;
        ctx.font = "600 12px 'JetBrains Mono', monospace";
        const lw = ctx.measureText(label).width + 12;
        ctx.fillStyle = hovered ? accent : ok;
        ctx.fillRect(18, y0 + 4, lw, 18);
        ctx.fillStyle = "#101010";
        ctx.fillText(label, 24, y0 + 17);
      }
    });
    if (pendingLine !== null && pendingLine >= pageTop && pendingLine <= pageBottom) {
      const y = (pendingLine - pageTop) * scale;
      ctx.setLineDash([6, 4]); ctx.strokeStyle = accent; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); ctx.setLineDash([]);
    }
  }

  // --- the mouse ----------------------------------------------------------
  function stripY(page, evt) {
    const rect = page.overlay.getBoundingClientRect();
    return page.top + (evt.clientY - rect.top) * (page.height / rect.height);
  }
  const grab = (page) => EDGE_GRAB_PX * (page.height / page.overlay.getBoundingClientRect().height);
  const panelAt = (y) => panels.findIndex(p => y >= p.top && y <= p.bottom);
  const overlapsAny = (top, bottom, skip) => panels.some((p, i) => i !== skip && !(bottom <= p.top || top >= p.bottom));

  function edgeNear(y, tolerance) {
    for (let i = panels.length - 1; i >= 0; i--) {
      if (Math.abs(y - panels[i].top) <= tolerance) return { index: i, edge: "top" };
      if (Math.abs(y - panels[i].bottom) <= tolerance) return { index: i, edge: "bottom" };
    }
    return null;
  }

  function dragTo(y) {
    const d = dragging, dy = y - d.startY;
    const top = d.edge === "top" ? d.startTop + dy : d.startTop;
    const bottom = d.edge === "bottom" ? d.startBottom + dy : d.startBottom;
    if (bottom - top >= MIN_PANEL && top >= 0 && bottom <= totalHeight && !overlapsAny(top, bottom, d.index)) {
      panels[d.index] = { top, bottom };
      redrawAll();
    }
  }

  function attachEvents(page) {
    const canvas = page.overlay;
    canvas.addEventListener("mousemove", (evt) => {
      const y = stripY(page, evt);
      hoverY = y;
      if (dragging) { dragTo(y); return; }
      const before = hoverIndex;
      hoverIndex = panelAt(y);
      canvas.style.cursor = edgeNear(y, grab(page)) ? "ns-resize" : "crosshair";
      if (before !== hoverIndex) redrawAll();
    });
    canvas.addEventListener("mouseleave", () => {
      if (dragging) return;
      hoverIndex = -1; hoverY = null; redrawAll();
    });
    canvas.addEventListener("mousedown", (evt) => {
      if (evt.button !== 0) return;
      const near = edgeNear(stripY(page, evt), grab(page));
      if (!near) return;
      const p = panels[near.index];
      dragging = { ...near, startY: stripY(page, evt), startTop: p.top, startBottom: p.bottom,
                   before: JSON.stringify(panels) };
      suppressClick = true;
      evt.preventDefault();
    });
    canvas.addEventListener("click", (evt) => {
      if (suppressClick) { suppressClick = false; return; }
      const y = stripY(page, evt);
      if (panelAt(y) >= 0) return;
      if (pendingLine === null) {
        pendingLine = y;
        setStatus("Line set - click again to mark the panel down (or up) to there. Esc drops it.");
        redrawAll();
        return;
      }
      const top = Math.min(pendingLine, y), bottom = Math.max(pendingLine, y);
      pendingLine = null;
      if (bottom - top < MIN_PANEL) { setStatus("Too short for a panel."); redrawAll(); return; }
      if (overlapsAny(top, bottom)) { setStatus("That would cover another panel."); redrawAll(); return; }
      commit([...panels, { top, bottom }]);
      setStatus("Panel added.");
    });
    canvas.addEventListener("contextmenu", (evt) => {
      evt.preventDefault();
      const y = stripY(page, evt);
      if (pendingLine !== null && Math.abs(y - pendingLine) <= grab(page)) {
        pendingLine = null; setStatus("Line dropped."); redrawAll(); return;
      }
      const near = edgeNear(y, grab(page));
      const index = panelAt(y) >= 0 ? panelAt(y) : near ? near.index : -1;
      if (index < 0) return;
      commit(panels.filter((_, i) => i !== index));
      setStatus("Panel deleted.");
    });
  }

  // A drag that leaves the page it started on carries on over the others.
  window.addEventListener("mousemove", (evt) => {
    if (!dragging || pages.some(p => p.overlay === evt.target)) return;
    let best = null, bestDistance = Infinity;
    for (const page of pages) {
      const rect = page.overlay.getBoundingClientRect();
      const distance = Math.max(0, rect.top - evt.clientY, evt.clientY - rect.bottom);
      if (distance < bestDistance) { bestDistance = distance; best = page; }
    }
    if (best) dragTo(stripY(best, evt));
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    const before = dragging.before;
    dragging = null;
    commit(panels, before);
    // The click that follows this mouseup (if it lands on a page) is the end
    // of the drag, not a new line - and if none follows, the next real one isn't.
    setTimeout(() => { suppressClick = false; }, 0);
  });

  // --- the keys -----------------------------------------------------------
  function splitHovered() {
    const index = hoverIndex;
    if (index < 0 || hoverY === null) { setStatus("Point at a panel to split it there."); return; }
    const p = panels[index], y = Math.round(hoverY);
    if (y - p.top < MIN_PANEL || p.bottom - y < MIN_PANEL) { setStatus("Too close to the edge to split."); return; }
    commit([...panels.slice(0, index), { top: p.top, bottom: y }, { top: y, bottom: p.bottom },
            ...panels.slice(index + 1)]);
    setStatus("Panel split.");
  }

  function lineAfterLast() {
    if (!panels.length || pendingLine !== null) return;
    pendingLine = Math.min(panels[panels.length - 1].bottom + 1, totalHeight - 1);
    const page = pages.find(p => pendingLine >= p.top && pendingLine <= p.top + p.height);
    if (page) {
      const rect = page.img.getBoundingClientRect(), readerRect = reader.getBoundingClientRect();
      const y = rect.top - readerRect.top + reader.scrollTop + (pendingLine - page.top) * (rect.height / page.height);
      reader.scrollTo({ top: y - 120, behavior: "smooth" });
    }
    setStatus("Line started after the last panel - click to mark down to there.");
    redrawAll();
  }

  async function autoMarks() {
    setStatus("Finding the panels...");
    const before = JSON.stringify(panels);
    try {
      const data = await post("/api/auto");
      commit(data.panels.map(([top, bottom]) => ({ top, bottom })), before);
      setStatus(`Marked by the gutter splitter: ${panels.length} panels. Ctrl+Z takes it back.`);
    } catch (e) { setStatus("Auto marks failed: " + e.message); }
  }

  async function finish() {
    if (finished) return;
    clearTimeout(saveTimer);
    setStatus("Saving and cutting the strip...");
    $("finishBtn").disabled = true;
    try {
      const data = await post("/api/finish", { panels: panels.map(p => [p.top, p.bottom]) });
      finished = true;
      $("doneTitle").textContent = `Saved - ${data.panels} panels`;
      $("doneOverlay").classList.add("visible");
    } catch (e) {
      $("finishBtn").disabled = false;
      setStatus("Couldn't finish: " + e.message);
    }
  }

  $("undoBtn").addEventListener("click", undo);
  $("autoBtn").addEventListener("click", autoMarks);
  $("clearBtn").addEventListener("click", () => { commit([]); setStatus("Cleared - Ctrl+Z brings them back."); });
  $("finishBtn").addEventListener("click", finish);

  document.addEventListener("keydown", (evt) => {
    if (finished) return;
    const key = evt.key.toLowerCase(), mod = evt.ctrlKey || evt.metaKey;
    if (mod && key === "z") { evt.preventDefault(); undo(); return; }
    if (mod && key === "s") { evt.preventDefault(); finish(); return; }
    if (mod || evt.altKey) return;
    if (key === "s") splitHovered();
    else if (key === "n") lineAfterLast();
    else if (key === "r") autoMarks();
    else if (key === "c") { commit([]); setStatus("Cleared - Ctrl+Z brings them back."); }
    else if (key === "escape" && pendingLine !== null) { pendingLine = null; setStatus("Line dropped."); redrawAll(); }
  });

  window.addEventListener("resize", () => { resizeAll(); redrawAll(); });
  document.addEventListener("dragstart", e => e.preventDefault());

  load().catch(e => setStatus("Couldn't load the chapter: " + e.message));
})();
