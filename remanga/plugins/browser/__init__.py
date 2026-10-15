"""Downloading through your own browser: for sites that only serve a real
person (Cloudflare checks and the like), remanga asks the remanga helper - a
small extension in your Firefox, in your own profile - to open each chapter
there. You solve any check the site shows; the helper keeps the images the
site's reader loaded, unchanged, and hands them to remanga.

    comix.py       ComixClient - the source plug-in's client (comix.to)
    session.py     one download's bridge: start it, wait for the helper, tidy up
    bridge.py      the 127.0.0.1 server the helper takes jobs from
    helper.py      the extension's file and how to load it into Firefox
    hooks.py       `handles`: which links are a browser site's
    settings_rows.py  its rows on the Settings screen (Firefox profile, pace, the helper)
    amo.py         having Mozilla sign the helper; commands.py `./run.sh helper`
    extension/     the helper itself (Firefox WebExtension)"""

from remanga.plugins import Source, register

register("source", Source(
    "comix", "comix.to (your Firefox)",
    client="remanga.plugins.browser.comix:ComixClient",
    handles="remanga.plugins.browser.hooks:handles",
    order=20,
    settings_rows="remanga.plugins.browser.settings_rows:rows",
    fresh_on_open=False,
))
