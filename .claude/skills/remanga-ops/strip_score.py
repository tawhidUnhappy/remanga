"""Score the webtoon panel proposal against the user's own Strip Marker marks (read only), and
try settings fast: every run is measured once (signals, gutters, borders, cached), then the
cheap decision steps (glue small pieces, drop blank ones, split tall ones) are replayed.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-ops/strip_score.py [--grid]

2026-10-27 baseline -> tuned (detect.py docstring): false cuts 47 -> 23, missed 23 -> 33.
Add a chapter to CHAPTERS once the user has marked it in the Strip Marker.

Scoring: a boundary is the gap between two panels; a proposed one matches a user one when they
are within TOL rows, or when only blank rows (one flat tone) lie between them."""
import itertools
import pickle
import sys
from pathlib import Path

import numpy as np

from remanga.plugins.long_strip import detect as D
from remanga.plugins.long_strip import quiet as Q
from remanga.plugins.long_strip.borders import borders
from remanga.plugins.long_strip.gutters import verified_gutters
from remanga.plugins.long_strip.layout import source_pages
from remanga.plugins.long_strip.marks import read_marks
from remanga.plugins.long_strip.runs import runs_of
from remanga.plugins.long_strip.signals import border_score, measure
from remanga.plugins.long_strip.tiles import StripView

CHAPTERS = [("ITheInvincibleVillainMasterWithMy", "1"), ("UrbanImmortalDoctorReturn", "1"),
            ("GhostStoryClubRemake", "1"), ("GhostStoryClubRemake", "2")]
TOL = 60
CACHE = Path(".cache/strip_score.pkl")   # delete it after a change to signals/gutters/borders


def measured():
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    data = []
    for project, chapter in CHAPTERS:
        sources = source_pages(project, chapter)
        user = [(m[0], m[1]) for m in read_marks(project, chapter, sources)]
        view = StripView(runs_of(sources))
        runs = []
        blank = []
        for i, run in enumerate(view.runs):
            arr = np.asarray(view.image(i).convert("RGB"))
            s = measure(arr)
            runs.append({"top": run.top, "height": arr.shape[0], "width": arr.shape[1], "signals": s,
                         "gutters": verified_gutters(arr), "borders": borders(s), "score": border_score(s)})
            blank.append(s.busy < 4)
        data.append({"name": f"{project[:14]} ch{chapter}", "user": user, "runs": runs,
                     "blank": np.concatenate(blank)})
    CACHE.write_bytes(pickle.dumps(data))
    return data


def propose(run, small=D.SMALL_SHARE, tall=Q.TALL, strong=D.STRONG_BORDER, calm=Q.CALM_SHARE, featureless=D.FEATURELESS):
    D.SMALL_SHARE, Q.TALL, Q.CALM_SHARE = small, tall, calm
    s, width, height = run["signals"], run["width"], run["height"]
    strong_borders = [(y, float(run["score"][y])) for y in run["borders"] if run["score"][y] >= strong]
    pieces = D.glue_small(D.between_gutters(height, run["gutters"]), width)
    pieces = [p for p in pieces if float(s.busy[p[0]:p[1]].max(initial=0)) > featureless]
    panels = [part for t, b in pieces for part in Q.split_tall(t, b, s.energy, width, strong_borders)]
    return [(run["top"] + t, run["top"] + b) for t, b in panels]


def gaps(marks):
    marks = sorted(marks)
    return [(min(a[1], b[0]), max(a[1], b[0])) for a, b in zip(marks, marks[1:])]


def same(g, h, blank):
    if g[0] - TOL <= h[1] and h[0] <= g[1] + TOL:
        return True
    lo, hi = sorted((int((g[0] + g[1]) / 2), int((h[0] + h[1]) / 2)))
    return hi - lo < 4000 and bool(blank[lo:hi].all())


def score(user, proposed, blank):
    uc, pc = gaps(user), gaps(proposed)
    hits = sum(1 for u in uc if any(same(u, p, blank) for p in pc))
    false = sum(1 for p in pc if not any(same(u, p, blank) for u in uc))
    return len(uc), hits, false


def evaluate(data, **params):
    total = [0, 0, 0]
    per = []
    for ch in data:
        proposed = [p for run in ch["runs"] for p in propose(run, **params)]
        n, hits, false = score(ch["user"], proposed, ch["blank"])
        total = [total[0] + n, total[1] + hits, total[2] + false]
        per.append(f"{ch['name']}: {hits}/{n} false {false}")
    n, hits, false = total
    return n, hits, false, per


if __name__ == "__main__":
    data = measured()
    base = evaluate(data)
    print(f"baseline: hits {base[1]}/{base[0]} missed {base[0] - base[1]} false {base[2]}")
    for line in base[3]:
        print("   ", line)
    if "--grid" in sys.argv:
        rows = []
        for small, tall, strong, calm in itertools.product((0.45, 0.6, 0.8), (1.8, 2.4, 3.0, 99.0), (0.6, 0.8),
                                                           (0.25, 0.15)):
            n, hits, false, _ = evaluate(data, small=small, tall=tall, strong=strong, calm=calm)
            rows.append((n - hits + false, n - hits, false, small, tall, strong, calm))
        for errors, missed, false, small, tall, strong, calm in sorted(rows)[:12]:
            print(f"errors {errors:3d} (missed {missed:2d}, false {false:2d})  small {small}  tall {tall}  "
                  f"strong {strong}  calm {calm}")
