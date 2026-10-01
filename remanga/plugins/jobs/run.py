"""What each built-in job does: (project, chapter, config) -> anything."""

from __future__ import annotations

from remanga import workflow


def download(project: str, chapter: str, config):
    return workflow.download(project, [chapter], config)


def pdf(project: str, chapter: str, config):
    return workflow.make_pdf(project, chapter, config)


def video(project: str, chapter: str, config):
    return workflow.make_video(project, chapter, config)


def remix(project: str, chapter: str, config):
    return workflow.remix_video(project, chapter, config)


def reaudio(project: str, chapter: str, config):
    return workflow.make_video(project, chapter, config, force=True, audio_only=True)


def source(project: str, chapter: str, config):
    return workflow.remake_from_source(project, chapter, config)
