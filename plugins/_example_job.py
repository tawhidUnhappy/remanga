"""An example drop-in plug-in: a queue job that prints where a chapter is.

Files starting with "_" are skipped - rename this to `example_job.py` to load
it, then `remanga plugins` lists it and a chapter's "Add to queue" offers it.
"""

from remanga.plugins import Job, register


def where_is_it(project: str, chapter: str, config) -> str:
    from remanga import workflow

    state = workflow.chapter_state(project, chapter)
    print(f"{project} chapter {chapter}: {state}")
    return state


# `run` may be the function itself - a reference string is only needed to keep
# a built-in's __init__ free of heavy imports.
register("job", Job("where", "Where is it", "prints the chapter's next step", where_is_it, order=500))
