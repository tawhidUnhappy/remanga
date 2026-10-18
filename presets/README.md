# Narration presets

Each `.json` file here is one preset, picked in Settings as **Narration preset**
(the file name without `.json` is what config.json stores as `narration_preset`).
A preset fixes the settings it names; those rows are locked while it is picked.
Any key left out stays adjustable in Settings. Pick **No preset** to set every row yourself.

To make a new sound, copy a file, rename it and change the values. Nothing else
needs to change.

| Key | Values | Sets |
|---|---|---|
| `name` | text (required) | what Settings shows |
| `description` | text | the hint beside it |
| `engine` | `kokoro`, `qwen`, `index_tts`, ... | Narrator engine |
| `voice` | a voice of that engine, e.g. `af_heart` | Narrator voice |
| `speed` | e.g. `1.08` (1.0 = normal) | Speaking speed |
| `take_length` | minutes, `"whole_chapter"` or `"per_panel"` | Narration take length |
| `compressor` | `"off"`, `"gentle"`, `"medium"`, `"strong"` | Compressor |
| `bass_boost_db` | dB at 150 Hz, `0` = off | Bass boost |
| `limiter` | `true` / `false` | Limiter |
| `loudness_lufs` | e.g. `-14`, or `"off"` | Loudness |

A misspelt key makes the file be skipped, with a warning saying why.
