// remanga helper: asks remanga (on 127.0.0.1 only) what to open, opens it in
// one tab of its own - in the background of your Firefox window, reused from
// chapter to chapter - waits while you solve any check, and hands back the
// images the site's reader loaded - the bytes the server sent, not a
// screenshot. One job at a time.
//
// Between jobs it does nothing but ask remanga, every few seconds, whether
// there is one. It never touches another tab: its request listeners exist
// only during a job and only for the remanga tab, and its page script runs
// only there.

const BRIDGE = "http://127.0.0.1:47615/remanga";
const VERSION = browser.runtime.getManifest().version;

let windowId = null; // the window the remanga tab is in (yours)
let tabId = null;
let capturing = false; // keeping image bytes (chapter jobs)
let watching = false; // noting the tab's requests for the discovery file (every job)
// url -> {type, bytes} for every image the remanga tab received this job.
const captured = new Map();
const contentTypes = new Map(); // requestId -> content-type of a 200 response ("" for any other)
const refererFor = new Map(); // url -> Referer for the helper's own fallback fetches
const seenRequests = []; // "type status url" of the tab's requests this job, for the discovery file

class Cancelled extends Error {}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const jitter = seconds => seconds * 1000 * (0.7 + Math.random() * 0.6);

// "development" when loaded from about:debugging (remanga can reload it),
// "normal" when installed from a signed file (an update is a new signed file).
let installType = "";
browser.management.getSelf().then(self => { installType = self.installType; }, () => {});

// ---- talking to remanga: both sides prove they share this copy's key
// (pairing.js) - an HMAC over a fresh nonce on every request, and over the
// answer for every job. Another program on this computer, or a web page,
// can neither give the helper work nor pose as it.

const encoder = new TextEncoder();
let hmacKey = null;

const hex = buffer => [...new Uint8Array(buffer)].map(b => b.toString(16).padStart(2, "0")).join("");

async function proof(...parts) {
  if (!hmacKey) {
    hmacKey = await crypto.subtle.importKey("raw", encoder.encode(REMANGA_PAIRING_KEY), {name: "HMAC", hash: "SHA-256"},
                                            false, ["sign"]);
  }
  return hex(await crypto.subtle.sign("HMAC", hmacKey, encoder.encode(parts.join("\n"))));
}

// Headers for one request to remanga: who we are, and the proof for `method path`.
async function signed(method, path, extra = {}) {
  const nonce = hex(crypto.getRandomValues(new Uint8Array(16)));
  const headers = Object.assign({"X-Remanga-Helper": VERSION, "X-Remanga-Install": installType}, extra);
  if (REMANGA_PAIRING_KEY) {
    headers["X-Remanga-Nonce"] = nonce;
    headers["X-Remanga-Proof"] = await proof("helper", nonce, method, path);
  }
  return {nonce, headers};
}

async function bridge(path, init = {}) {
  const method = init.method || "GET";
  const {nonce, headers} = await signed(method, "/remanga" + path, init.headers || {});
  const response = await fetch(BRIDGE + path, Object.assign({}, init, {headers, cache: "no-store"}));
  if (!response.ok) throw new Error(`remanga answered ${response.status} to ${path}`);
  const text = await response.text();
  if (path === "/job") {
    // Work is taken only from the remanga that holds this key.
    const said = response.headers.get("X-Remanga-Proof") || "";
    if (!REMANGA_PAIRING_KEY || said !== await proof("bridge", nonce, text)) {
      const answer = JSON.parse(text);
      // Unproven: nothing but a reload (Firefox reads the helper's own file again).
      return {job: answer.job && answer.job.kind === "reload" ? {id: answer.job.id, kind: "reload"} : null};
    }
  }
  return JSON.parse(text);
}

function post(path, body) {
  return bridge(path, {method: "POST", body: JSON.stringify(body), headers: {"Content-Type": "application/json"}});
}

// ---- capture: keep each image response's bytes while passing them through untouched.
// A response's body can finish before its headers' event arrives, so each
// request is kept once both are in, whichever comes second.

const bodies = new Map(); // requestId -> {url, bytes}

function commit(requestId) {
  const body = bodies.get(requestId);
  const type = contentTypes.get(requestId);
  if (!body || type === undefined) return;
  bodies.delete(requestId);
  contentTypes.delete(requestId);
  if (capturing && type.startsWith("image/")) {
    captured.set(body.url, {type, bytes: body.bytes});
    try { imageHosts.add(new URL(body.url).host); } catch (e) { /* not a URL */ }
  }
}

function onHeaders(details) {
  if (watching && details.tabId === tabId && seenRequests.length < 400) {
    seenRequests.push(`${details.type} ${details.statusCode} ${details.fromCache ? "cache " : ""}${details.url.slice(0, 200)}`);
  }
  if (!capturing || details.tabId !== tabId) return;
  const header = details.responseHeaders.find(h => h.name.toLowerCase() === "content-type");
  const type = details.statusCode === 200 && header ? header.value.split(";")[0].trim() : "";
  contentTypes.set(details.requestId, type);
  commit(details.requestId);
}

function onRequest(details) {
  if (!capturing || details.tabId !== tabId) return;
  const filter = browser.webRequest.filterResponseData(details.requestId);
  const chunks = [];
  filter.ondata = event => {
    chunks.push(event.data);
    filter.write(event.data);
  };
  filter.onstop = () => {
    filter.close();
    bodies.set(details.requestId, {url: details.url, bytes: new Blob(chunks)});
    commit(details.requestId);
  };
  filter.onerror = () => contentTypes.delete(details.requestId);
}

// A request that never got an answer - a content blocker's doing shows here.
function onFailed(details) {
  if (watching && details.tabId === tabId && seenRequests.length < 400) {
    seenRequests.push(`FAILED ${details.type} ${details.error} ${details.url.slice(0, 200)}`);
  }
}

// The helper's own fetch of a page the reader didn't load (rare) goes out with
// the chapter as its Referer, as the reader's own request would.
function onSending(details) {
  const referer = refererFor.get(details.url);
  if (details.tabId !== -1 || !referer) return;
  const requestHeaders = details.requestHeaders.filter(h => h.name.toLowerCase() !== "referer");
  requestHeaders.push({name: "Referer", value: referer});
  return {requestHeaders};
}

// Listening starts with a job, for the remanga tab only, and stops with it.
function listen(tab) {
  const mine = {urls: ["<all_urls>"], tabId: tab};
  browser.webRequest.onHeadersReceived.addListener(onHeaders, mine, ["responseHeaders"]);
  browser.webRequest.onBeforeRequest.addListener(onRequest, Object.assign({types: ["image", "imageset", "xmlhttprequest"]}, mine),
                                                 ["blocking"]);
  browser.webRequest.onErrorOccurred.addListener(onFailed, mine);
  // The helper's own requests belong to no window (tabId -1); only those it
  // marked in refererFor are changed.
  browser.webRequest.onBeforeSendHeaders.addListener(onSending, {urls: ["<all_urls>"], tabId: -1}, ["blocking", "requestHeaders"]);
}

function unlisten() {
  browser.webRequest.onHeadersReceived.removeListener(onHeaders);
  browser.webRequest.onBeforeRequest.removeListener(onRequest);
  browser.webRequest.onErrorOccurred.removeListener(onFailed);
  browser.webRequest.onBeforeSendHeaders.removeListener(onSending);
}

// ---- the toolbar button: what the helper is doing

function show(state, title) {
  const badge = {idle: "", working: "…", check: "!"}[state];
  browser.browserAction.setBadgeText({text: badge}).catch(() => {});
  browser.browserAction.setBadgeBackgroundColor({color: state === "check" ? "#d33" : "#557"}).catch(() => {});
  browser.browserAction.setTitle({title: `remanga helper ${VERSION} - ${title}`}).catch(() => {});
}

// ---- the remanga tab

async function closeTab() {
  if (tabId !== null) await browser.tabs.remove(tabId).catch(() => {});
  windowId = tabId = null;
}

browser.tabs.onRemoved.addListener(id => {
  if (id === tabId) windowId = tabId = null;
});

browser.tabs.onAttached.addListener((id, info) => {
  if (id === tabId) windowId = info.newWindowId; // dragged to another window
});

// Resolves when the tab has loaded `url` - a "complete" that arrives after the
// navigation began, never the previous page's (a tab still showing the last
// chapter is not done loading the next).
function waitForLoad(id, url, timeoutMs = 90000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => done(new Error("the page took over 90 s to load")), timeoutMs);
    let began = false;
    function done(error) {
      clearTimeout(timer);
      browser.tabs.onUpdated.removeListener(listener);
      error ? reject(error) : resolve();
    }
    function listener(updated, change, tab) {
      if (updated !== id) return;
      if (change.status === "loading" || change.url) began = true;
      if (change.status === "complete" && (began || tab.url === url)) done();
    }
    browser.tabs.onUpdated.addListener(listener);
    browser.tabs.get(id).catch(() => done(new Error("the remanga tab was closed")));
  });
}

// The remanga tab: a background tab in your Firefox window (a window of its
// own only when none is open), made on an empty page so listening can begin
// before the first request of the job's page. Reused from job to job.
async function ensureTab() {
  if (tabId !== null) {
    try {
      const tab = await browser.tabs.get(tabId);
      windowId = tab.windowId;
      return;
    } catch (e) {
      windowId = tabId = null;
    }
  }
  const windows = await browser.windows.getAll({windowTypes: ["normal"]});
  const yours = windows.filter(w => !w.incognito).sort((a, b) => (b.focused ? 1 : 0) - (a.focused ? 1 : 0))[0];
  if (yours) {
    const tab = await browser.tabs.create({url: "about:blank", active: false, windowId: yours.id});
    windowId = tab.windowId;
    tabId = tab.id;
  } else {
    const win = await browser.windows.create({url: "about:blank", focused: false});
    windowId = win.id;
    tabId = win.tabs[0].id;
  }
}

async function open(url) {
  const loaded = waitForLoad(tabId, url);
  await browser.tabs.update(tabId, {url});
  await loaded;
}

// The page script runs only while the remanga tab is on a site the helper
// knows: a page that sent it elsewhere (a redirect, a login) is not read.
async function inPage(message) {
  let tab = await browser.tabs.get(tabId);
  // Mid-navigation a tab can show a passing address (about:blank): judged
  // only once it has settled.
  for (let n = 0; n < 30 && !remangaAllowed(tab.url) && (tab.status === "loading" || tab.url === "about:blank"); n++) {
    await sleep(500);
    tab = await browser.tabs.get(tabId);
  }
  if (!remangaAllowed(tab.url)) {
    let where = "another page";
    try { where = new URL(tab.url).hostname || where; } catch (e) { /* about: and the like */ }
    throw new Error(`the remanga tab left the site (it is on ${where}) - stopped there`);
  }
  await browser.tabs.executeScript(tabId, {file: "reader.js"});
  return browser.tabs.sendMessage(tabId, message);
}

// A check (Cloudflare's "Just a moment...", a captcha) is yours to solve: the
// tab comes to the front and the helper waits for as long as it takes.
async function passChecks(job, status) {
  let asked = false;
  for (;;) {
    let state;
    try {
      state = await inPage({cmd: "state"});
    } catch (e) {
      // Off the site (a redirect elsewhere): stop - never wait on a page the helper won't read.
      if (String(e && e.message || e).includes("left the site")) throw e;
      // The check navigated away mid-question; ask the new page.
      await sleep(1500);
      continue;
    }
    if (!state.challenge) {
      if (asked) {
        show("working", "working for remanga");
        await status("loading", "Check passed - loading the page.");
      }
      return state;
    }
    if (!asked) {
      asked = true;
      await browser.windows.update(windowId, {focused: true, drawAttention: true}).catch(() => {});
      await browser.tabs.update(tabId, {active: true}).catch(() => {});
      show("check", "waiting for you to solve the check in the remanga tab");
    }
    await status("challenge", state.title || "a check");
    await sleep(2000);
  }
}

// ---- jobs

// Hosts that served images to the remanga tab this job.
const imageHosts = new Set();

const PRIVATE_HOST = /^(localhost|0\.|127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|\[|.*\.(local|internal|lan|home|localdomain)$)/i;

// What the helper may fetch on its own (a page the reader didn't load): a
// plain http(s) image from a host this chapter's reader already got images
// from, or the site itself - never this computer, the local network, or a
// site the page merely names (a hostile page could name your bank).
function fetchable(url) {
  let parsed;
  try { parsed = new URL(url); } catch (e) { return false; }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return false;
  if (remangaAllowed(url)) return true;
  return imageHosts.has(parsed.host) && !PRIVATE_HOST.test(parsed.hostname);
}

async function pageBytes(job, page, index) {
  if (page.kind === "canvas" || page.url.startsWith("blob:") || page.url.startsWith("data:")) {
    const got = await inPage({cmd: "bytes", page});
    if (got.error) throw new Error(`page ${index + 1}: ${got.error}`);
    return {type: got.type, bytes: new Blob([got.bytes]), how: "page"};
  }
  const hit = captured.get(page.url);
  if (hit) return Object.assign({how: "reader"}, hit);
  if (!fetchable(page.url)) throw new Error(`page ${index + 1}: not fetching ${page.url.slice(0, 120)} - not an image host this chapter used`);
  // Not loaded by the reader (a larger original than it showed, or it was
  // lazy): fetched once, from the browser's cache when it is there.
  refererFor.set(page.url, job.url);
  try {
    await sleep(jitter(job.request_delay));
    // The site's own cookies go only to the site; an image host gets none.
    const response = await fetch(page.url, {cache: "force-cache", credentials: remangaAllowed(page.url) ? "include" : "omit",
                                            redirect: "error"});
    if (!response.ok) throw new Error(`page ${index + 1}: the server answered ${response.status}`);
    const type = (response.headers.get("content-type") || "").split(";")[0].trim();
    return {type, bytes: await response.blob(), how: "fetched"};
  } finally {
    refererFor.delete(page.url);
  }
}

async function chapterJob(job, status) {
  const found = await inPage({cmd: "pages", scrollDelay: job.scroll_delay, hid: job.hid});
  if (found.error) throw new Error(found.error);
  if (!found.pages.length) throw new Error("found no chapter pages on this page");
  if (found.expected && found.pages.length !== found.expected) {
    throw new Error(`the reader numbers ${found.expected} pages but ${found.pages.length} were found - `
                    + "see .cache/browser/last-chapter.json");
  }
  const counts = {reader: 0, fetched: 0, page: 0};
  for (let i = 0; i < found.pages.length; i++) {
    const got = await pageBytes(job, found.pages[i], i);
    counts[got.how] += 1;
    const query = new URLSearchParams({job: job.id, index: String(i + 1), total: String(found.pages.length),
                                       type: got.type || "", url: found.pages[i].url.slice(0, 2000)});
    const {headers} = await signed("POST", `/remanga/page?${query}`, {"Content-Type": "application/octet-stream"});
    const response = await fetch(`${BRIDGE}/page?${query}`, {method: "POST", body: got.bytes, cache: "no-store", headers});
    const answer = await response.json();
    if (answer.cancel) throw new Cancelled();
    if (!response.ok) throw new Error(answer.error || `remanga refused page ${i + 1}`);
  }
  found.discovery.captured = [...captured.keys()];
  return {pages: found.pages.length, expected: found.expected, counts, source: found.source, discovery: found.discovery};
}

// The manga's page, then - for the whole list - each other page of its chapter
// list opened by its own address (?page=N), never by clicking the pager, one
// at a time at a person's pace: oldest first (chapter 1 is known early), and
// only until every upload the list says it holds is known. Uploads read on an
// earlier run (job.known) count: when the list hasn't grown, page 1 is enough.
async function titleJob(job, status) {
  const first = await inPage({cmd: "title", hid: job.hid});
  if (first.error || job.whole === false || !first.list_total) return first;
  const byId = new Map((job.known || []).map(c => [String(c.id), c]));
  for (const c of first.chapters) byId.set(c.id, Object.assign({}, byId.get(c.id) || {}, c));
  const total = first.list_total;
  const shown = first.shown || {from: 1, to: first.chapters.length};
  const perPage = Math.max(1, shown.to - shown.from + 1);
  const pages = Math.ceil(total / perPage);
  const opened = Math.floor((shown.from - 1) / perPage) + 1;
  const pageUrl = number => {
    const url = new URL(job.url);
    url.searchParams.set("page", String(number));
    return url.href;
  };
  // Page 1 holds the newest chapters - the only page a re-read needs when
  // nothing older changed; then from the last page (chapter 1) back.
  const order = [1, ...Array.from({length: pages}, (_, i) => pages - i).filter(n => n !== 1)].filter(n => n !== opened);
  const visited = [opened];
  // Only rows seen in the list itself count toward its total - not chapters
  // the page's data merely mentions.
  const listed = () => [...byId.values()].filter(c => c.listed).length;
  for (const number of order) {
    if (listed() >= total) break;
    await sleep(jitter(job.list_pause || 8));
    await status("reading", `chapter list: ${listed()} of ${total} - page ${number} of ${pages}`);
    await open(pageUrl(number));
    await passChecks(job, status);
    const page = await inPage({cmd: "listPage", hid: job.hid});
    if (page.error) throw new Error(`chapter list page ${number}: ${page.error}`);
    for (const c of page.chapters) byId.set(c.id, Object.assign({}, byId.get(c.id) || {}, c));
    visited.push(number);
  }
  return Object.assign(first, {
    chapters: [...byId.values()], list_total: total,
    discovery: Object.assign(first.discovery || {}, {list_pages: pages, pages_opened: visited, uploads_known: listed()}),
  });
}

async function runJob(job) {
  const status = async (state, message, extra = {}) => {
    let answer;
    try {
      answer = await post("/status", Object.assign({job: job.id, state, message}, extra));
    } catch (e) {
      throw new Cancelled(); // remanga stopped
    }
    if (answer.cancel) throw new Cancelled();
  };
  try {
    if (job.kind === "finish") {
      await closeTab();
      await post("/result", {job: job.id, ok: true, data: {}});
      return;
    }
    if (job.kind === "reload") {
      // remanga has a newer helper: Firefox reads it again from the file it was loaded from.
      await closeTab();
      await post("/result", {job: job.id, ok: true, data: {}});
      browser.runtime.reload();
      return;
    }
    if (!remangaAllowed(job.url)) throw new Error(`the helper only opens ${REMANGA_SITES.join(", ")} - not ${job.url}`);
    captured.clear();
    bodies.clear();
    contentTypes.clear();
    imageHosts.clear();
    seenRequests.length = 0;
    show("working", "working for remanga");
    await ensureTab();
    listen(tabId);
    watching = true;
    capturing = job.kind === "chapter";
    await status("opening", job.url);
    await open(job.url);
    await passChecks(job, status);
    const progress = message => {
      if (!message) return;
      if (message.remangaProgress) status("reading", message.remangaProgress).catch(() => {});
      if (message.remangaCheck === true) {
        // A check inside the page, mid-job: the tab comes to the front for you.
        browser.windows.update(windowId, {focused: true, drawAttention: true}).catch(() => {});
        browser.tabs.update(tabId, {active: true}).catch(() => {});
        show("check", "waiting for you to solve the check in the remanga tab");
        status("challenge", "a check inside the page").catch(() => {});
      } else if (message.remangaCheck === false) {
        show("working", "working for remanga");
        status("loading", "Check passed.").catch(() => {});
      }
    };
    browser.runtime.onMessage.addListener(progress);
    let data;
    try {
      data = job.kind === "chapter" ? await chapterJob(job, status) : await titleJob(job, status);
    } finally {
      browser.runtime.onMessage.removeListener(progress);
    }
    if (data && data.discovery) data.discovery.requests = seenRequests.slice();
    if (data && data.error) throw new Error(data.error);
    await post("/result", {job: job.id, ok: true, data});
  } catch (e) {
    if (!(e instanceof Cancelled)) {
      await post("/result", {job: job.id, ok: false, error: String(e && e.message || e)}).catch(() => {});
    }
  } finally {
    unlisten();
    show("idle", "idle - remanga gives it work when it downloads");
    capturing = false;
    watching = false;
    captured.clear();
    bodies.clear();
    contentTypes.clear();
  }
}

async function poll() {
  let wait = 5000;
  try {
    const answer = await bridge("/job");
    wait = 1500;
    if (answer.job) {
      await runJob(answer.job);
      wait = 200;
    }
  } catch (e) {
    // remanga isn't downloading right now.
  }
  setTimeout(poll, wait);
}

show("idle", "idle - remanga gives it work when it downloads");
poll();
// While a job runs the helper doesn't poll; this tells remanga Firefox is still there.
setInterval(() => { if (capturing || tabId !== null) bridge("/alive").catch(() => {}); }, 4000);
