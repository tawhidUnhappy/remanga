"""Long-strip manga (webtoons): chapters that arrive as a few very tall images
and are read by scrolling down. MAGI (trained on printed pages) is no use on
them, so:

    layout.py   is this chapter a long strip
    runs.py     the downloaded images as strips of one width, in chapter rows
    gutters.py  which rows are gutters - each colour verified before it may cut
    signals.py  per-row measurements the border vote uses
    borders.py  panel borders with no gutter, from those signals
    quiet.py    splitting a too-tall panel in a calm stretch
    detect.py   proposed panels: the art between gutters and borders
    marks.py    the Strip Marker's marks (overlap allowed, optional sides)
    pages.py    marks packed into strip/ pages, never splitting touching ones
    crops.py    crops.json from those pages, cut exactly as marked
    tiles.py    the strip as small tiles for the browser tab
    build.py    keeps strip/ and crops.json in step with images and marks
    hooks.py    what the "long_strip" layout plug-in does, for the pipeline
    web/        the Strip Marker (Flask routes, session, static page)"""

from remanga.plugins import Layout, register

HOOKS = "remanga.plugins.long_strip.hooks:"

register("layout", Layout(
    "long_strip", "Long strip (webtoon)",
    "the whole chapter as one strip, scrolled like reading it - cut between its panels",
    matches=HOOKS + "matches",
    mark=HOOKS + "mark",
    pages_dir=HOOKS + "pages_dir",
    detect=HOOKS + "detect",
    prepare_cut=HOOKS + "prepare_cut",
    order=50,
))
