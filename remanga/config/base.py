"""The base every config model shares.

One reason to exist: `validate_assignment`. Pydantic validates when a model
is BUILT but, by default, not when a field is later assigned - so
`config.audio.sample_rate = "not-a-number"` used to succeed silently and the
bad value travelled until something far away tried to use it as a number.
That was survivable while config.json was the only realistic way to change a
setting, because loading it goes through full validation. It stopped being
survivable when settings/browser.py made all 89 fields editable from a menu:
a generic editor that cannot be told "no" is a generic way to corrupt a
config.

Turning it on here rather than on each of the thirteen models is the point of
having a base at all - a model added later gets the behaviour by inheriting,
instead of by somebody remembering."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ConfigModel(BaseModel):
    """A config section. Validates on assignment as well as on load."""

    model_config = ConfigDict(validate_assignment=True)
