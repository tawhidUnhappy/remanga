// remanga helper: asks remanga (on 127.0.0.1 only) what to open, opens it in
// one window of its own, waits while you solve any check, and hands back the
// images the site's reader loaded - the bytes the server sent, not a
// screenshot. One job at a time.
//
// Between jobs it does nothing but ask remanga, every few seconds, whether
// there is one. It never touches another window: its request listeners exist
// only during a job and only for the remanga window, and its page script runs
// only in that window's tab.

const BRIDGE = "http://127.0.0.1:47615/remanga";
const VERSION = browser.runtime.getManifest().version;

let windowId = null;
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

async function bridge(path, init = {}) {
  const headers = Object.assign({"X-Remanga-Helper": VERSION, "X-Remanga-Install": installType}, init.headers || {});
  const response = await fetch(BRIDGE + path, Object.assign({}, init, {headers, cache: "no-store"}));
  if (!response.ok) throw new Error(`remanga answered ${response.status} to ${path}`);
  return response.json();
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
  if (capturing && type.startsWith("image/")) captured.set(body.url, {type, bytes: body.bytes});
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

// Listening starts with a job, for the remanga window only, and stops with it.
function listen(win) {
  const mine = {urls: ["<all_urls>"], windowId: win};
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

// ---- the remanga window

async function closeWindow() {
  if (windowId !== null) await browser.windows.remove(windowId).catch(() => {});
  windowId = tabId = null;
}

browser.windows.onRemoved.addListener(id => {
  if (id === windowId) windowId = tabId = null;
});

function waitForLoad(id, timeoutMs = 90000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => done(new Error("the page took over 90 s to load")), timeoutMs);
    function done(error) {
      clearTimeout(timer);
      browser.tabs.onUpdated.removeListener(listener);
      error ? reject(error) : resolve();
    }
    function listener(updated, change) {
      if (updated === id && change.status === "complete") done();
    }
    browser.tabs.onUpdated.addListener(listener);
    browser.tabs.get(id).then(tab => { if (tab.status === "complete" && tab.url !== "about:blank") done(); },
                              () => done(new Error("the remanga tab was closed")));
  });
}

// The remanga window, made on an empty page so listening can begin before the
// first request of the job's page.
async function ensureWindow() {
  if (tabId !== null) {
    try {
      await browser.tabs.get(tabId);
      return;
    } catch (e) {
      windowId = tabId = null;
    }
  }
  const win = await browser.windows.create({url: "about:blank", focused: false, width: 1280, height: 1000});
  windowId = win.id;
  tabId = win.tabs[0].id;
}

async function open(url) {
  await browser.tabs.update(tabId, {url});
  await waitForLoad(tabId);
}

async function inPage(message) {
  await browser.tabs.executeScript(tabId, {file: "reader.js"});
  return browser.tabs.sendMessage(tabId, message);
}

// A check (Cloudflare's "Just a moment...", a captcha) is yours to solve: the
// window comes forward and the helper waits for as long as it takes.
async function passChecks(job, status) {
  let asked = false;
  for (;;) {
    let state;
    try {
      state = await inPage({cmd: "state"});
    } catch (e) {
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
      show("check", "waiting for you to solve the check in the remanga window");
    }
    await status("challenge", state.title || "a check");
    await sleep(2000);
  }
}

// ---- jobs

async function pageBytes(job, page, index) {
  if (page.kind === "canvas" || page.url.startsWith("blob:") || page.url.startsWith("data:")) {
    const got = await inPage({cmd: "bytes", page});
    if (got.error) throw new Error(`page ${index + 1}: ${got.error}`);
    return {type: got.type, bytes: new Blob([got.bytes]), how: "page"};
  }
  const hit = captured.get(page.url);
  if (hit) return Object.assign({how: "reader"}, hit);
  // Not loaded by the reader (a larger original than it showed, or it was
  // lazy): fetched once, from the browser's cache when it is there.
  refererFor.set(page.url, job.url);
  try {
    await sleep(jitter(job.request_delay));
    const response = await fetch(page.url, {cache: "force-cache", credentials: "include"});
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
    const response = await fetch(`${BRIDGE}/page?${query}`, {
      method: "POST", body: got.bytes, cache: "no-store",
      headers: {"X-Remanga-Helper": VERSION, "Content-Type": "application/octet-stream"},
    });
    const answer = await response.json();
    if (answer.cancel) throw new Cancelled();
    if (!response.ok) throw new Error(answer.error || `remanga refused page ${i + 1}`);
  }
  found.discovery.captured = [...captured.keys()];
  return {pages: found.pages.length, expected: found.expected, counts, source: found.source, discovery: found.discovery};
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
      await closeWindow();
      await post("/result", {job: job.id, ok: true, data: {}});
      return;
    }
    if (job.kind === "reload") {
      // remanga has a newer helper: Firefox reads it again from the file it was loaded from.
      await closeWindow();
      await post("/result", {job: job.id, ok: true, data: {}});
      browser.runtime.reload();
      return;
    }
    if (!remangaAllowed(job.url)) throw new Error(`the helper only opens ${REMANGA_SITES.join(", ")} - not ${job.url}`);
    captured.clear();
    bodies.clear();
    contentTypes.clear();
    seenRequests.length = 0;
    show("working", "working for remanga");
    await ensureWindow();
    listen(windowId);
    watching = true;
    capturing = job.kind === "chapter";
    await status("opening", job.url);
    await open(job.url);
    await passChecks(job, status);
    const progress = message => {
      if (message && message.remangaProgress) status("reading", message.remangaProgress).catch(() => {});
    };
    browser.runtime.onMessage.addListener(progress);
    let data;
    try {
      data = job.kind === "chapter" ? await chapterJob(job, status) : await inPage({cmd: "title", hid: job.hid});
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
