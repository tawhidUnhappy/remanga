"""Which source plug-in a manga comes from (remanga/plugins/, kind "source"),
and its client. project.json records the source a project was made from;
a project made before sources were plug-ins is the default (MangaDex)."""

from __future__ import annotations

from typing import Any

from remanga import plugins
from remanga.paths import load_project_metadata


def source_for(reference: str) -> plugins.Source:
    """The source whose link or ID this is - the default one for anything no
    source claims (a title to search)."""
    every = plugins.items("source")
    for source in every:
        if plugins.call(source.handles, reference):
            return source
    return every[0]


def project_source(project: str) -> plugins.Source:
    return plugins.get("source", load_project_metadata(project).get("source"))


def client(source: plugins.Source, config) -> Any:
    """The source's client, built with the downloader settings."""
    return plugins.resolve(source.client)(config.downloader)


def project_client(project: str, config) -> Any:
    return client(project_source(project), config)
