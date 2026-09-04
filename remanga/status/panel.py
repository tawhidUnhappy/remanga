"""The `status` command's printed report: one chapter's production state,
plus the settings that will shape it when it's rendered."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import display_path, escape as _esc, wrap_at_slashes
from remanga.paths import load_project_metadata
from remanga.settings import package_summary
from remanga.status.compute import get_chapter_status


def render_status_panel(project: str, chapter: str) -> str:
    """Builds the plain-text chapter production status summary for the CLI."""
    st = get_chapter_status(project, chapter)
    meta = load_project_metadata(project)
    saved_url = wrap_at_slashes(meta.get("manga_url") or meta.get("manga_id", "Not set"))

    config = RemangaConfig.load()
    voice_path = Path(config.tts.spk_audio_prompt).expanduser() if config.tts.spk_audio_prompt else None
    voice_status = f"[green]Configured ({display_path(voice_path)})[/]" if (voice_path and voice_path.exists()) else f"[yellow]Not set / Missing ({display_path(voice_path) if voice_path else 'n/a'})[/]"

    bgm_path = Path(config.audio.bgm_path).expanduser() if config.audio.bgm_path else None
    bgm_status = f"[green]Enabled ({display_path(bgm_path)})[/]" if (config.audio.bgm_enabled and bgm_path and bgm_path.exists()) else "[dim]Disabled / None[/]"

    res_str = f"{config.video.width}x{config.video.height} ({config.video.background_style.title()} Canvas)"
    package = config.cropper.package
    # Same one-line rendering the settings screen uses, so "what does this
    # chapter get packaged into" reads identically wherever it's asked.
    package_str = package_summary(package)

    # Items 2-9 below name only the filename, not the full path - the
    # workspace directory they all live under is already stated once, in
    # "Workspace Directory" above. Repeating the full absolute path on every
    # line (the old behavior) made this panel wrap mid-directory-name on
    # anything narrower than a very wide terminal; a bare filename never
    # needs to wrap at all.
    status_str = f"""
[bold]Project:[/] {project} | [bold]Chapter:[/] {chapter}
[bold]Saved Manga Source:[/] {saved_url}
[bold]Workspace Directory:[/] {display_path(st['chap_dir'])}
[bold]Video Resolution:[/] {res_str}
[bold]Vision outputs:[/] {package_str}
[bold]Reference Voice Audio:[/] {voice_status}
[bold]Background Music:[/] {bgm_status}

   1. Pages Downloaded    : {'[green]✓ Yes (' + str(st['pages_count']) + ' pages)[/]' if st['pages_count'] > 0 else '[red]✗ Missing[/]'}
   2. Pages ZIP Archive   : {'[green]✓ Ready (pages.zip)[/]' if st['pages_zip_exist'] else '[dim yellow]✗ Not generated[/]'}
   3. Crop Instructions   : {'[green]✓ Present (crops.json)[/]' if st['crops_exist'] else '[yellow]✗ Missing/Empty placeholder[/]'}
   4. Panels Cropped      : {'[green]✓ Yes (' + str(st['panels_count']) + ' panels)[/]' if st['panels_count'] > 0 else '[red]✗ Missing[/]'}
   5. Panel Contact Sheets: {'[green]✓ Yes (' + str(st['sheets_count']) + ' sheets)[/]' if st['sheets_count'] > 0 else '[dim yellow]✗ Not generated[/]'}
   6. panels_zip          : {'[green]✓ Built[/]' if st['panels_zip_built'] else ('[dim yellow]✗ Not generated[/]' if package.panels_zip_active else '[dim]— off[/]')}
   7. pdf                 : {'[green]✓ Built[/]' if st['panels_pdf_built'] else ('[dim yellow]✗ Not generated[/]' if package.pdf_active else '[dim]— off[/]')}
   8. sheets_zip          : {'[green]✓ Built[/]' if st['sheets_zip_built'] else ('[dim yellow]✗ Not generated[/]' if package.sheets_zip_active else '[dim]— off[/]')}
   9. Narration Script    : {'[green]✓ Present (narration.json)[/]' if st['narration_exist'] else '[yellow]✗ Missing/Empty placeholder[/]'}
   9b. Narration Review   : {'[yellow]⚑ ' + str(st['review_flagged_count']) + ' flagged, awaiting LLM fix pass[/]' if st['review_pending'] else '[dim]— no pending review[/]'}
  10. Master Audio Track  : {'[green]✓ Generated (IndexTTS-2.5)[/]' if st['master_audio_exist'] else '[red]✗ Not built (' + str(st['audio_clips_count']) + '/' + str(st['total_narration_entries']) + ' clips)[/]'}
  11. Final Recap Video   : {'[green]✓ Ready (' + _esc(st['video_path'].name) + ')[/]' if st['video_exist'] else '[red]✗ Not rendered[/]'}
"""
    return status_str.strip()
