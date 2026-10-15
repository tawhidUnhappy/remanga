// Runs inside the remanga tab's page (injected by background.js) and answers
// three questions: is this a check you must solve, what are the manga and its
// chapters, and which images are the chapter's pages, in reading order.
// Injected again after every navigation, so it defines itself once.

if (!window.__remangaReader) {
  window.__remangaReader = true;

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  // True once `test()` holds, false after `timeoutMs` - for pages that draw
  // themselves after loading ("Loading..." first, the list a moment later).
  async function waitFor(test, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (test()) return true;
      await sleep(400);
    }
    return test();
  }

  // Waits until `count()` has stopped changing for `quietMs`.
  async function settled(count, quietMs, timeoutMs = 20000) {
    const deadline = Date.now() + timeoutMs;
    let last = count();
    let since = Date.now();
    while (Date.now() < deadline && Date.now() - since < quietMs) {
      await sleep(300);
      const now = count();
      if (now !== last) { last = now; since = Date.now(); }
    }
  }

  // The innermost element holding at least 60% of `elements`: a list's own box.
  function container(elements) {
    if (!elements.length) return document.body;
    const counts = new Map();
    for (const el of elements) for (let a = el.parentElement; a; a = a.parentElement) counts.set(a, (counts.get(a) || 0) + 1);
    const need = Math.ceil(elements.length * 0.6);
    let best = document.body;
    let depth = -1;
    for (const [el, count] of counts) {
      if (count < need) continue;
      let d = 0;
      for (let a = el; a; a = a.parentElement) d++;
      if (d > depth) { depth = d; best = el; }
    }
    return best;
  }

  const trimmedHtml = (el, limit) => el ? el.outerHTML.replace(/\s+/g, " ").slice(0, limit) : "";
  const progress = text => browser.runtime.sendMessage({remangaProgress: text}).catch(() => {});

  // ---- checks

  const CHECK_TITLES = /just a moment|attention required|checking your browser|verify you are human|security check|ddos-guard/i;

  const shownOnPage = el => {
    const box = el.getBoundingClientRect();
    return box.width > 0 && box.height > 0 && getComputedStyle(el).visibility !== "hidden";
  };

  // A check to solve: Cloudflare's whole-page one, or one a site shows inside
  // the page when it wants to be sure mid-way (comix.to's "/@waf/challenge").
  function state() {
    const challenge = CHECK_TITLES.test(document.title)
      || !!document.querySelector("#challenge-form, #challenge-running, #challenge-stage, .cf-turnstile-wrapper")
      || [...document.querySelectorAll("iframe[src*='challenges.cloudflare.com'], iframe[src*='challenge'], "
                                       + ".g-recaptcha, .h-captcha")].some(shownOnPage)
      // A site's own firewall check (comix.to's "/@waf/challenge") counts while it is in the page at
      // all: in a background tab it may not be drawn - or run - until the tab comes to the front.
      || !!document.querySelector("iframe[src*='/@waf/']");
    return {challenge, title: document.title, url: location.href, ready: document.readyState};
  }

  // Waits while a check is showing - the remanga tab comes to the front for
  // you to solve it - then gives the page a moment. Ten minutes at most.
  async function clearChecks() {
    if (!state().challenge) return;
    browser.runtime.sendMessage({remangaCheck: true}).catch(() => {});
    const deadline = Date.now() + 10 * 60 * 1000;
    while (state().challenge && Date.now() < deadline) await sleep(1500);
    browser.runtime.sendMessage({remangaCheck: false}).catch(() => {});
    if (state().challenge) throw new Error("a check in the page wasn't solved in 10 minutes");
    await sleep(2500);
  }

  // ---- the page's own data (server-rendered JSON), searched generically

  function jsonBlobs() {
    const found = [];
    for (const script of document.querySelectorAll("script[type='application/json'], script#initial-data, "
                                                    + "script#__NEXT_DATA__, script[type='application/ld+json']")) {
      try { found.push(JSON.parse(script.textContent)); } catch (e) { /* not JSON */ }
    }
    return found;
  }

  function walk(value, visit, depth = 0, seen = new Set()) {
    if (!value || typeof value !== "object" || depth > 40 || seen.has(value)) return;
    seen.add(value);
    visit(value);
    for (const child of Object.values(value)) walk(child, visit, depth + 1, seen);
  }

  const IMAGE_URL = /\.(jpe?g|png|webp|avif|gif|jxl)(\?|#|$)/i;
  const absolute = (url, base) => { try { return new URL(url, base || location.href).href; } catch (e) { return ""; } };

  // The longest list of image URLs the page's data names: a chapter's pages,
  // as the site stores them (the originals, when the reader shows smaller ones).
  function dataPageUrls() {
    let best = [];
    for (const blob of jsonBlobs()) {
      walk(blob, node => {
        let list = null;
        let base = "";
        if (node.pages && Array.isArray(node.pages.items)) {
          list = node.pages.items;
          base = node.pages.baseUrl || node.pages.base_url || "";
        } else if (Array.isArray(node) && node.length >= 2) {
          list = node;
        }
        if (!list) return;
        const urls = list.map(item => typeof item === "string" ? item : item && (item.url || item.src || item.image))
                         .filter(url => typeof url === "string" && IMAGE_URL.test(url))
                         .map(url => absolute(url, base ? base.replace(/\/?$/, "/") : undefined));
        if (urls.length === list.length && urls.length > best.length) best = urls;
      });
    }
    return best;
  }

  // ---- manga facts and chapters

  const chapterAnchors = hid => {
    const pattern = new RegExp(`/title/${hid}[^/]*/(\\d+)-chapter-([\\d.]+)`, "i");
    return [...document.querySelectorAll("a[href]")].filter(link => pattern.test(link.href) && !excluded(link));
  };

  function chapterLinks(hid) {
    const pattern = new RegExp(`/title/${hid}[^/]*/(\\d+)-chapter-([\\d.]+)`, "i");
    const out = new Map();
    for (const link of chapterAnchors(hid)) {
      const match = link.href.match(pattern);
      if (!match || out.has(match[1])) continue;
      const row = (link.parentElement && link.parentElement.closest("li, tr, [class*='item']")) || link;
      const text = el => ((el || {}).textContent || "").trim();
      out.set(match[1], {
        id: match[1], number: match[2], url: link.href.split("#")[0], listed: true,
        name: text(row.querySelector("[class*='title'], [class*='name']")),
        group: text(row.querySelector("[class*='group'], [class*='scan'], [class*='team']")),
        votes: Number((text(row.querySelector("[class*='like'], [class*='vote']")).match(/\d+/) || [0])[0]),
        official: /\bofficial\b/i.test(row.className + " " + text(row.querySelector("[class*='group']"))),
      });
    }
    return [...out.values()];
  }

  function chapterData(hid) {
    const out = new Map();
    for (const blob of jsonBlobs()) {
      walk(blob, node => {
        if (Array.isArray(node) || node.number === undefined || node.number === null) return;
        const id = node.chapter_id || node.chapterId || node.id;
        if (!id || typeof node.number === "object") return;
        const group = node.group || node.scanlation_group || node.team || {};
        out.set(String(id), {
          id: String(id), number: String(node.number), url: node.url ? absolute(node.url) : "",
          name: typeof node.name === "string" ? node.name : (typeof node.title === "string" ? node.title : ""),
          group: typeof group === "string" ? group : (group.name || group.title || ""),
          official: !!(node.isOfficial || node.is_official || node.official),
          votes: Number(node.votes || node.likes || 0),
          pages: Number(node.pagesCount || node.pages_count || (typeof node.pages === "number" ? node.pages : 0)),
          language: node.language || node.lang || node.translatedLanguage || "",
        });
      });
    }
    return [...out.values()];
  }

  function mangaData(hid) {
    let best = null;
    for (const blob of jsonBlobs()) {
      walk(blob, node => {
        if (Array.isArray(node) || typeof node.title !== "string") return;
        const own = node.hid === hid || node.hash_id === hid || node.code === hid
                    || (typeof node.url === "string" && node.url.includes(`/title/${hid}`));
        if (own && (!best || Object.keys(node).length > Object.keys(best).length)) best = node;
      });
    }
    return best;
  }

  // "Showing 401 to 413 of 413 items": how many the list holds in all.
  function listTotal() {
    const match = document.body.innerText.match(/\bof\s+([\d,]+)\s+(items|chapters|results|entries)\b/i);
    return match ? Number(match[1].replace(/,/g, "")) : 0;
  }

  // Which stretch of the list is on show: {from, to} ("Showing 401 to 413 ...").
  function listShown() {
    const match = document.body.innerText.match(/\bshowing\s+([\d,]+)\s+to\s+([\d,]+)\s+of\b/i);
    return match ? {from: Number(match[1].replace(/,/g, "")), to: Number(match[2].replace(/,/g, ""))} : null;
  }

  // One page of the chapter list - the page the tab was opened on (its
  // address names it, ?page=N): the list is drawn after the page loads, so it
  // is waited for, through any check the site puts up first. The helper never
  // clicks the list's pager: a page opened by its address is what a person
  // following a link does, while scripted clicks are what the site's
  // firewall stops.
  async function listPage(hid) {
    await waitFor(() => chapterAnchors(hid).length > 0 || state().challenge, 45000);
    await clearChecks();
    await waitFor(() => chapterAnchors(hid).length > 0, 45000);
    await settled(() => chapterAnchors(hid).length, 2500);
    return {chapters: chapterLinks(hid), list_total: listTotal(), shown: listShown()};
  }

  // The manga's facts, and the chapters on the page as opened.
  async function title(hid) {
    const data = mangaData(hid) || {};
    const meta = name => (document.querySelector(`meta[property='${name}'], meta[name='${name}']`) || {}).content || "";
    const alt = Array.isArray(data.altTitles) ? data.altTitles : (Array.isArray(data.alt_titles) ? data.alt_titles : []);
    const first = await listPage(hid);
    const byId = new Map(first.chapters.map(c => [c.id, c]));
    for (const c of chapterData(hid)) {
      byId.set(c.id, Object.assign({}, byId.get(c.id) || {}, c, {url: c.url || (byId.get(c.id) || {}).url || ""}));
    }
    const list = container(chapterAnchors(hid));
    return {
      title: data.title || (document.querySelector("h1") || {}).textContent || meta("og:title") || document.title,
      alt_titles: alt.map(t => typeof t === "string" ? t : (t && (t.title || t.name || Object.values(t)[0])) || "").filter(Boolean),
      original_language: data.originalLanguage || data.original_language || "",
      type: data.type || "",
      formats: (Array.isArray(data.formats) ? data.formats : []).map(f => typeof f === "string" ? f : (f && f.title) || ""),
      chapters: [...byId.values()],
      list_total: first.list_total,
      shown: first.shown,
      discovery: Object.assign(discovery(), {
        chapter_list_html: trimmedHtml(list, 8000),
        around_list_html: trimmedHtml(list && list.parentElement && list.parentElement.parentElement, 12000),
      }),
    };
  }

  // ---- the chapter's pages

  function scroller() {
    const root = document.scrollingElement || document.documentElement;
    if (root.scrollHeight > innerHeight * 1.5) return root;
    let best = null;
    for (const el of document.querySelectorAll("body *")) {
      if (el.scrollHeight <= el.clientHeight * 1.5 || !/(auto|scroll)/.test(getComputedStyle(el).overflowY)) continue;
      if (!best || el.scrollHeight > best.scrollHeight) best = el;
    }
    return best || root;
  }

  // Down the chapter a screen at a time at a reading pace, so the reader loads
  // its pages the way it does for a person - one after another, not all at
  // once - noting each page as it goes by (`onScreen` after every step).
  // To the top of the chapter, and staying there: a reader that reopens a
  // chapter where you left off can jump back down a moment after it loads.
  async function toTop(el) {
    let still = 0;
    for (let n = 0; n < 60 && still < 4; n++) {
      if (el.scrollTop > 2) {
        el.scrollTop = 0;
        still = 0;
      } else {
        still++;
      }
      await sleep(500);
    }
  }

  async function scrollThrough(delay, onScreen) {
    const el = scroller();
    await toTop(el);
    await onScreen(el);
    let atBottom = 0;
    let lastHeight = -1;
    let target = 0;
    for (let step = 0; step < 6000 && atBottom < 3; step++) {
      target = el.scrollTop + Math.max(300, el.clientHeight * 0.85);
      el.scrollTop = target;
      await sleep(delay * 1000 * (0.7 + Math.random() * 0.6));
      // The reader moved the page itself (to where you left off): back to where reading was.
      if (Math.abs(el.scrollTop - target) > el.clientHeight && el.scrollTop + el.clientHeight < el.scrollHeight - 4) {
        el.scrollTop = Math.min(target, el.scrollHeight - el.clientHeight);
        await sleep(800);
      }
      await onScreen(el);
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 4) {
        atBottom = el.scrollHeight === lastHeight ? atBottom + 1 : 0;
        lastHeight = el.scrollHeight;
      }
      if (step % 5 === 0) progress(`reading ${Math.min(100, Math.round(100 * (el.scrollTop + el.clientHeight) / el.scrollHeight))}%`);
    }
  }

  const excluded = el => !!el.closest("header, nav, footer, aside, [role='navigation'], [class*='comment'], [class*='recommend']");

  // Every image big enough to be a page; then the element holding most of them
  // is the reader, and its pages are those inside it.
  function pageElements() {
    const big = [...document.querySelectorAll("img, canvas")].filter(el => {
      if (excluded(el)) return false;
      const w = el.naturalWidth || el.width || 0;
      const h = el.naturalHeight || el.height || 0;
      const shown = el.getBoundingClientRect().width;
      return (w >= 300 && h >= 200) || (el.tagName === "IMG" && !el.complete && shown >= 300);
    });
    if (!big.length) return [];
    const reader = container(big);
    return big.filter(el => reader.contains(el));
  }

  // Where an element sits in the whole scrolled page - stable even in a
  // reader that only keeps the pages near the screen (comix.to keeps ~4).
  function offsetIn(scrolling, el) {
    const root = scrolling === (document.scrollingElement || document.documentElement);
    const base = root ? 0 : scrolling.getBoundingClientRect().top;
    return Math.round(el.getBoundingClientRect().top - base + scrolling.scrollTop);
  }

  // The reader's page bar: one control per page ("Go to page 192") - its count.
  function readerBar() {
    let most = 0;
    for (const el of document.querySelectorAll("[aria-label], [title]")) {
      const match = (el.getAttribute("aria-label") || el.getAttribute("title") || "").match(/^(?:go to )?page (\d+)$/i);
      if (match) most = Math.max(most, Number(match[1]));
    }
    return most;
  }

  // The pages the reader numbers itself ("5 / 192" under each): its total.
  function readerTotal() {
    const counts = new Map();
    for (const match of (document.body.innerText.match(/\b\d+\s*\/\s*(\d+)\b/g) || [])) {
      const total = Number(match.split("/")[1]);
      counts.set(total, (counts.get(total) || 0) + 1);
    }
    let best = 0;
    let most = 2; // a total named at least 3 times - not some stray "1 / 82"
    for (const [total, n] of counts) if (n > most) { most = n; best = total; }
    return best;
  }

  // The largest image an <img> offers: its srcset's widest, else what it shows.
  function bestUrl(img) {
    let best = img.currentSrc || img.src || img.dataset.src || "";
    let widest = 0;
    for (const part of (img.srcset || img.dataset.srcset || "").split(",")) {
      const [url, size] = part.trim().split(/\s+/);
      const width = parseFloat(size) || 0;
      if (url && width > widest) { widest = width; best = absolute(url); }
    }
    return best;
  }

  async function pages(options) {
    // The reader draws itself after the page loads: wait for its first page.
    await waitFor(() => pageElements().length > 0, 45000);
    await sleep(1500);
    const seen = new Map(); // url -> {url, top, width, height, cls}
    const onScreen = async scrolling => {
      await clearChecks();
      // The pages on screen, once loaded (up to 15 s each - the reader's pace, not ours).
      const view = scrolling.getBoundingClientRect();
      const visible = pageElements().filter(img => {
        if (img.tagName !== "IMG") return false;
        const r = img.getBoundingClientRect();
        return r.bottom > Math.max(0, view.top) - 200 && r.top < Math.min(innerHeight, view.bottom) + 200;
      });
      const deadline = Date.now() + 15000;
      while (visible.some(img => !(img.complete && img.naturalWidth)) && Date.now() < deadline) await sleep(300);
      for (const img of pageElements()) {
        if (img.tagName !== "IMG" || !(img.complete && img.naturalWidth)) continue;
        const url = bestUrl(img);
        if (!url || seen.has(url)) continue;
        seen.set(url, {kind: "img", url, top: offsetIn(scrolling, img), width: img.naturalWidth,
                       height: img.naturalHeight, cls: String(img.className)});
      }
    };
    await scrollThrough(options.scrollDelay || 0.8, onScreen);
    // Only the reader's own kind of image (its class), top to bottom.
    const classes = new Map();
    for (const page of seen.values()) classes.set(page.cls, (classes.get(page.cls) || 0) + 1);
    const main = [...classes.entries()].sort((a, b) => b[1] - a[1])[0];
    let shown = [...seen.values()].filter(page => !main || page.cls === main[0]).sort((a, b) => a.top - b.top);
    const canvases = pageElements().filter(el => el.tagName === "CANVAS");
    if (canvases.length && canvases.length >= shown.length) {
      shown = canvases.map((c, index) => ({kind: "canvas", index, url: `canvas:${index}`, width: c.width, height: c.height}));
    }
    // The data's list is the site's own page list - used when it covers every
    // page the reader shows (it can name originals larger than the reader's).
    const data = dataPageUrls();
    const useData = data.length && data.length >= shown.length && !canvases.length;
    const expected = readerTotal();
    return {
      pages: useData ? data.map(url => ({kind: "img", url})) : shown,
      expected,
      bar: readerBar(),
      source: useData ? "page data" : "reader",
      discovery: Object.assign(discovery(), {
        shown: shown.slice(0, 400), data_urls: data, expected,
        reader_html: trimmedHtml(container(pageElements()), 6000),
      }),
    };
  }

  async function bytes(page) {
    try {
      if (page.kind === "canvas") {
        const canvas = pageElements().filter(el => el.tagName === "CANVAS")[page.index];
        if (!canvas) return {error: "the page's canvas is gone"};
        // A canvas holds pixels, not a file: PNG keeps every one of them.
        const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
        if (!blob) return {error: "the page's canvas could not be read"};
        return {type: "image/png", bytes: await blob.arrayBuffer()};
      }
      // Only the page's own in-memory images (blob:, data:) are read from here.
      if (!/^(blob|data):/.test(page.url)) return {error: "not a page-held image"};
      const response = await fetch(page.url);
      return {type: response.headers.get("content-type") || "", bytes: await response.arrayBuffer()};
    } catch (e) {
      return {error: String(e && e.message || e)};
    }
  }

  // What the page looked like, saved by remanga - for fixing the helper when a
  // site changes its reader.
  function discovery() {
    return {
      url: location.href,
      title: document.title,
      images: [...document.images].slice(0, 300).map(img => ({
        src: (img.currentSrc || img.src || "").slice(0, 300), w: img.naturalWidth, h: img.naturalHeight,
        shown: Math.round(img.getBoundingClientRect().width), srcset: (img.srcset || "").slice(0, 300),
        data: JSON.stringify(img.dataset).slice(0, 300), cls: String(img.className).slice(0, 80),
        excluded: excluded(img),
      })),
      canvases: [...document.querySelectorAll("canvas")].map(c => ({w: c.width, h: c.height, cls: String(c.className).slice(0, 80)})),
      json_scripts: [...document.querySelectorAll("script[type='application/json'], script#initial-data, script#__NEXT_DATA__")]
        .map(s => ({id: s.id, size: s.textContent.length, head: s.textContent.slice(0, 3000)})),
      scripts: [...document.scripts].map(s => s.src || `inline ${s.textContent.length}`).slice(0, 60),
      text: document.body ? document.body.innerText.slice(0, 3000) : "",
      scroll_height: document.documentElement.scrollHeight,
    };
  }

  browser.runtime.onMessage.addListener(message => {
    if (message.cmd === "state") return Promise.resolve(state());
    if (message.cmd === "title") return title(message.hid).catch(e => ({error: String(e && e.message || e)}));
    if (message.cmd === "listPage") return listPage(message.hid).catch(e => ({error: String(e && e.message || e)}));
    if (message.cmd === "pages") return pages(message).catch(e => ({error: String(e && e.message || e)}));
    if (message.cmd === "bytes") return bytes(message.page);
    return undefined;
  });
}
