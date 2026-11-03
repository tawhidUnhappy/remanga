"""The language a chapter's lettering is in, by name. A chapter can come in
another language than the narration's (downloader.fallback_languages), and
the PDF's text page then tells the LLM which, so it reads the bubbles in that
language and still narrates in English."""

from __future__ import annotations

from remanga.paths import read_manifest

# MangaDex's language codes (the ones a site uses for its uploads).
NAMES = {
    "ar": "Arabic", "az": "Azerbaijani", "bg": "Bulgarian", "bn": "Bengali", "ca": "Catalan", "cs": "Czech",
    "cv": "Chuvash", "da": "Danish", "de": "German", "el": "Greek", "en": "English", "eo": "Esperanto",
    "es": "Spanish", "es-la": "Latin American Spanish", "et": "Estonian", "fa": "Persian", "fi": "Finnish",
    "fr": "French", "ga": "Irish", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian",
    "id": "Indonesian", "it": "Italian", "ja": "Japanese", "ja-ro": "romanized Japanese", "jv": "Javanese",
    "ka": "Georgian", "kk": "Kazakh", "ko": "Korean", "ko-ro": "romanized Korean", "la": "Latin",
    "lt": "Lithuanian", "mn": "Mongolian", "ms": "Malay", "my": "Burmese", "ne": "Nepali", "nl": "Dutch",
    "no": "Norwegian", "pl": "Polish", "pt": "Portuguese", "pt-br": "Brazilian Portuguese", "ro": "Romanian",
    "ru": "Russian", "sk": "Slovak", "sl": "Slovenian", "sr": "Serbian", "sv": "Swedish", "ta": "Tamil",
    "te": "Telugu", "th": "Thai", "tl": "Filipino", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu",
    "uz": "Uzbek", "vi": "Vietnamese", "zh": "Simplified Chinese", "zh-hk": "Traditional Chinese",
    "zh-ro": "romanized Chinese",
}


def wanted_languages(config) -> list[str]:
    """A downloader config's languages in order of preference: its language,
    then each fallback ("*" = any)."""
    return list(dict.fromkeys([config.language, *config.fallback_languages]))


def language_rank(language: str, wanted: list[str]) -> int | None:
    """Where an upload in `language` stands among `wanted`: 0 = the first,
    None = not wanted at all. A code also covers its regional forms ("en"
    takes "en-us"), and an upload that names no language counts as the
    first - a site that does not say is taken at its word."""
    code = (language or "").lower()
    if not code:
        return 0
    for rank, want in enumerate(w.lower() for w in wanted):
        if want == "*" or code == want or code.startswith(want + "-"):
            return rank
    return None


def language_name(code: str) -> str:
    """"Indonesian (id)" - the code alone when it is not a known one."""
    name = NAMES.get(code.lower())
    return f"{name} ({code})" if name else code


def chapter_language(project: str, chapter: str) -> str:
    """The language code the chapter's pages were downloaded in, as the
    download recorded it; "" when it did not say (a source with no language,
    or a download from before this was recorded)."""
    pages = read_manifest(project).get("chapters", {}).get(str(chapter), {}).get("pages") or {}
    return str(pages.get("language") or "")


def lettering(project: str, chapter: str, narration_language: str) -> str:
    """What the PDF's text page says the lettering is in: "" when it is in the
    narration's own language (or nobody recorded it)."""
    code = chapter_language(project, chapter)
    return language_name(code) if code and code.lower() != narration_language.lower() else ""
