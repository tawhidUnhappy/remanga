"""Which layout plug-in a chapter is (remanga/plugins/, kind "layout"): pages,
a long strip, or whatever else is installed - and the two things the rest of
remanga asks a layout for without caring which one it is.

project.json's `layout` decides when it names an installed layout (set from
the source when the project is made, or written by hand for a manga the
source tags wrong). Otherwise each layout, in order, is asked whether the
chapter's images look like its kind; the last one ("pages") says yes to
anything."""

from __future__ import annotations

from pathlib import Path

from remanga import plugins
from remanga.paths import load_project_metadata


def layout_for(project: str, chapter: str) -> plugins.Layout:
    named = plugins.find("layout", load_project_metadata(project).get("layout"))
    if named is not None:
        return named
    every = plugins.items("layout")
    for layout in every:
        if plugins.call(layout.matches, project, chapter):
            return layout
    return every[-1]


def pages_dir(project: str, chapter: str, build: bool = True) -> Path:
    """The images a chapter's panels are marked on and cut from - pages/ for
    a manga, strip/ for a long strip - brought up to date first unless
    `build` is False (for callers that only list names and must not spend
    seconds per chapter)."""
    return plugins.call(layout_for(project, chapter).pages_dir, project, chapter, build=build)
