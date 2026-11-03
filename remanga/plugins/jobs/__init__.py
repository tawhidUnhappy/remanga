"""The chapter jobs the queue runs unattended (workflow/queue.py) - the same
words as the chapter menu, so a queued job means what choosing it there means.

    run.py      what each one does"""

from remanga.plugins import Job, register

RUN = "remanga.plugins.jobs.run:"

for order, job in enumerate((
    Job("download", "Download", "fetch the pages (checks the ones already here)", RUN + "download",
        needs_pages=False),
    Job("pdf", "Make PDF", "the panels, to give to the LLM with the prompt", RUN + "pdf"),
    Job("video", "Make video", "narrates the whole chapter from narration.json, then makes the video",
        RUN + "video"),
    Job("remix", "Rebuild video", "keeps the narration - remakes the music, intro and video", RUN + "remix"),
    Job("reaudio", "Narrate again, no video", "replaces the narration and keeps only that", RUN + "reaudio"),
    Job("source", "Remake from source", "deletes all but the pages, panel marks and narration.json, "
                                        "then makes it all again", RUN + "source"),
)):
    register("job", Job(job.name, job.label, job.help, job.run, job.needs_pages, order=(order + 1) * 10))
