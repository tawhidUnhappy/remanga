"""Printed manga pages: marked page by page in the Panel Marker
(remanga/webui/), with MAGI v3 (plugins/magi/) finding the panels when asked.
The fallback layout - a chapter no other layout claims is pages.

    hooks.py    what the "pages" layout plug-in does, for the pipeline"""

from remanga.plugins import Layout, register

HOOKS = "remanga.plugins.pages.hooks:"

register("layout", Layout(
    "pages", "Pages",
    "page by page in the Panel Marker, MAGI v3 finding the panels",
    matches=HOOKS + "matches",
    mark=HOOKS + "mark",
    pages_dir=HOOKS + "pages_dir",
    detect=HOOKS + "detect",
    order=1000,
))
