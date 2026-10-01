# Your own plug-ins

Every `*.py` file or package (a folder with `__init__.py`) in this folder is
loaded when remanga starts. Names starting with `_` or `.` are skipped.
`remanga plugins` lists everything that loaded, and anything that failed (a
broken plug-in is reported and skipped, never fatal).

A plug-in registers itself on import:

```python
from remanga.plugins import register, Job
register("job", Job("name", "Label", "what it does", run_function))
```

The kinds, and what each one describes (full field list in
`remanga/plugins/_kinds.py`):

| kind     | object       | built-in examples                       |
|----------|--------------|-----------------------------------------|
| `tts`    | `TTSEngine`  | `remanga/plugins/kokoro/`, `qwen_tts/`  |
| `tool`   | `ToolSpec`   | each engine's / model's isolated venv   |
| `layout` | `Layout`     | `remanga/plugins/pages/`, `long_strip/` |
| `source` | `Source`     | `remanga/plugins/mangadex/`             |
| `job`    | `Job`        | `remanga/plugins/jobs/`                 |

A plug-in with the same kind and name as a built-in replaces it. A plug-in
shipped as its own Python package can register through an entry point in
the `remanga.plugins` group instead of living here.

`_example_job.py` is a complete example - rename it without the `_` to try it.

**A tool sets itself up.** A `tool` plug-in (anything that runs in its own
`.tools/venv-<name>`) brings a `setup.py` with `install(torch_backend, force)`
- build the environment, however it needs to - and `weights(config)` - fetch
what it runs on. remanga only decides when: on first use, from bootstrap.sh,
or `./run.sh setup --tool <name>`. `remanga/plugins/kokoro/setup.py` is the
pattern; `build_env` from `remanga.tool_envs` does the usual "these packages
into a fresh venv with uv" if that is all a tool needs. Each built-in one
also runs on its own: `.venv/bin/python -m remanga.plugins.kokoro.setup`.

A new narrator engine is the biggest one: copy `remanga/plugins/kokoro/` and
change its config block, synthesizer, worker script, settings rows and setup.py. Its
settings appear in config.json as `tts.<name>` and on the Settings screen by
themselves.
