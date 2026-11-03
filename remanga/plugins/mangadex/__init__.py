"""MangaDex: the source manga are looked up on and downloaded from.

    mangadex.py       MangaDexDownloader - the source plug-in's client
    resolve.py        URL/UUID parsing, title search, the manga's facts
    feed.py           the chapter feed
    chapter_list.py   the chapter list with each chapter's local status
    chapter_pages.py  one chapter's download steps
    pages.py          page files and their checksums
    hooks.py          `handles`: which links/IDs are MangaDex's"""

from remanga.plugins import Source, register

register("source", Source(
    "mangadex", "MangaDex",
    client="remanga.plugins.mangadex.mangadex:MangaDexDownloader",
    handles="remanga.plugins.mangadex.hooks:handles",
    order=10,
))
