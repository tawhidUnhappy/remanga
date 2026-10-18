# Narration presets

Each `.json` file here is one preset, picked in Settings as **Narration preset**
(the file name without `.json` is what config.json stores as `narration_preset`).
A preset fixes the settings it names; those rows are locked while it is picked.
Any key left out stays adjustable in Settings. Pick **No preset** to set every row yourself.

These are the presets that ship with remanga (tracked by git). Your own go in
`global/presets/`, which git never tracks: use **Save as preset** in Settings to
save the settings in use now, or put a file there by hand. A name used here can't
be reused there.

| Key | Values | Sets |
|---|---|---|
| `name` | text (required) | what Settings shows |
| `description` | text | the hint beside it |
| `engine` | `kokoro`, `qwen`, `index_tts`, ... | Narrator engine |
| `voice` | a voice of that engine, e.g. `af_heart` | Narrator voice |
| `speed` | e.g. `1.08` (1.0 = normal) | Speaking speed |
| `take_length` | minutes, `"whole_chapter"` or `"per_panel"` | Narration take length |
| `compressor` | `"off"`, `"gentle"`, `"medium"`, `"strong"` | Compressor |
| `bass_boost_db` | dB at 180 Hz, `0` = off | Bass boost |
| `presence_db` | dB at 4 kHz, `0` = off | Presence |
| `limiter` | `true` / `false` | Limiter |
| `loudness_lufs` | e.g. `-14`, or `"off"` | Loudness |

A misspelt key makes the file be skipped, with a warning saying why.
