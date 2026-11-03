// The only sites the helper will open a page on, whatever remanga asks for.
// remanga/plugins/browser/sites.py names the same hosts.
const REMANGA_SITES = ["comix.to", "comix.ws"];

function remangaAllowed(url) {
  try {
    const host = new URL(url).hostname;
    return REMANGA_SITES.some(site => host === site || host.endsWith("." + site));
  } catch (e) {
    return false;
  }
}
