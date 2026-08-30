"""Chapter production-status computation and its rich-panel presentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from rich.panel import Panel

from remanga.config import RemangaConfig
from remanga.console import display_path, wrap_at_slashes
from remanga.json_io import has_real_json_content, read_json_or
from remanga.paths import get_chapter_dir, load_project_metadata


def get_chapter_status(project_name: str, chapter_num: str) -> Dict[str, Any]:
    config = RemangaConfig.load()
    chap_dir = get_chapter_dir(project_name, chapter_num)
    pages_dir = chap_dir / "pages"
    panels_dir = chap_dir / "panels"
    sheets_dir = chap_dir / "sheets"
    audio_dir = chap_dir / "audio"

    pages_count = len(list(pages_dir.glob("page_*.*"))) if pages_dir.exists() else 0
    pages_zip_exist = (chap_dir / "pages.zip").exists()
    crops_exist = has_real_json_content(chap_dir / "crops.json")

    panels_count = len(list(panels_dir.glob("panel_*.*"))) if panels_dir.exists() else 0
    sheets_count = len(list(sheets_dir.glob("sheet_*.*"))) if sheets_dir.exists() else 0
    sheets_zip_exist = (chap_dir / "sheets.zip").exists()
    panels_zip_exist = (chap_dir / "panels.zip").exists()

    narration_file = chap_dir / "narration.json"
    narration_exist = has_real_json_content(narration_file)
    total_narration_entries = 0
    if narration_exist:
        n_data = read_json_or(narration_file, {})
        total_narration_entries = len(n_data.get("narration", []))

    audio_clips_count = len(list(audio_dir.glob("panel_*.wav"))) if audio_dir.exists() else 0
    timing_exist = (chap_dir / "audio_timing.json").exists()
    master_audio_exist = (chap_dir / "master_audio.wav").exists()

    final_video_path = chap_dir / f"{project_name}_ch{chapter_num}_recap.mp4"
    video_exist = final_video_path.exists() and final_video_path.stat().st_size > 1000

    vision_ready = (config.cropper.primary_archive_format == "panels" and panels_zip_exist) or (config.cropper.primary_archive_format == "sheets" and sheets_zip_exist) or sheets_zip_exist or panels_zip_exist

    if video_exist:
        summary = "Recap Ready"
    elif master_audio_exist:
        summary = "Audio Ready (Pending Render)"
    elif total_narration_entries > 0 and audio_clips_count >= total_narration_entries:
        summary = "TTS Ready (Pending Mix)"
    elif total_narration_entries > 0 and audio_clips_count > 0:
        summary = f"TTS In-Progress ({audio_clips_count}/{total_narration_entries})"
    elif narration_exist:
        summary = "Narration Script Ready"
    elif vision_ready or panels_count > 0:
        summary = f"Cropped ({panels_count} panels)"
    elif crops_exist:
        summary = "Crops JSON Ready"
    elif pages_count > 0:
        summary = f"Pages Ready ({pages_count} pages)"
    else:
        summary = "Not Started"

    return {
        "project": project_name,
        "chapter": str(chapter_num),
        "chap_dir": chap_dir,
        "pages_count": pages_count,
        "pages_zip_exist": pages_zip_exist,
        "crops_exist": crops_exist,
        "panels_count": panels_count,
        "sheets_count": sheets_count,
        "sheets_zip_exist": sheets_zip_exist,
        "panels_zip_exist": panels_zip_exist,
        "narration_exist": narration_exist,
        "total_narration_entries": total_narration_entries,
        "audio_clips_count": audio_clips_count,
        "timing_exist": timing_exist,
        "master_audio_exist": master_audio_exist,
        "video_exist": video_exist,
        "video_path": final_video_path,
        "summary": summary,
    }


def render_status_panel(project: str, chapter: str) -> Panel:
    """Builds the rich Panel summarizing a chapter's production status for the CLI."""
    st = get_chapter_status(project, chapter)
    meta = load_project_metadata(project)
    saved_url = wrap_at_slashes(meta.get("manga_url") or meta.get("manga_id", "Not set"))

    config = RemangaConfig.load()
    voice_path = Path(config.tts.spk_audio_prompt).expanduser() if config.tts.spk_audio_prompt else None
    voice_status = f"[green]Configured ({display_path(voice_path)})[/]" if (voice_path and voice_path.exists()) else f"[yellow]Not set / Missing ({display_path(voice_path) if voice_path else 'n/a'})[/]"

    bgm_path = Path(config.audio.bgm_path).expanduser() if config.audio.bgm_path else None
    bgm_status = f"[green]Enabled ({display_path(bgm_path)})[/]" if (config.audio.bgm_enabled and bgm_path and bgm_path.exists()) else "[dim]Disabled / None[/]"

    res_str = f"{config.video.width}x{config.video.height} ({config.video.background_style.title()} Canvas)"
    asset_mode = config.cropper.primary_archive_format
    target_zip_name = config.cropper.expected_zip_name
    target_zip_ready = st['panels_zip_exist'] if asset_mode == "panels" else st['sheets_zip_exist']

    # Items 2-9 below name only the filename, not the full path - the
    # workspace directory they all live under is already stated once, in
    # "Workspace Directory" above. Repeating the full absolute path on every
    # line (the old behavior) made this panel wrap mid-directory-name on
    # anything narrower than a very wide terminal; a bare filename never
    # needs to wrap at all.
    status_str = f"""
[bold cyan]Project:[/] {project} | [bold cyan]Chapter:[/] {chapter}
[bold cyan]Saved Manga Source:[/] {saved_url}
[bold]Workspace Directory:[/] {display_path(st['chap_dir'])}
[bold]Video Resolution:[/] {res_str}
[bold]Vision Packaging Format:[/] {asset_mode.title()} ({target_zip_name})
[bold]Reference Voice Audio:[/] {voice_status}
[bold]Background Music:[/] {bgm_status}

  1. Pages Downloaded    : {'[green]✓ Yes (' + str(st['pages_count']) + ' pages)[/]' if st['pages_count'] > 0 else '[red]✗ Missing[/]'}
  2. Pages ZIP Archive   : {'[green]✓ Ready (pages.zip)[/]' if st['pages_zip_exist'] else '[dim yellow]✗ Not generated[/]'}
  3. Crop Instructions   : {'[green]✓ Present (crops.json)[/]' if st['crops_exist'] else '[yellow]✗ Missing/Empty placeholder[/]'}
  4. Panels Cropped      : {'[green]✓ Yes (' + str(st['panels_count']) + ' panels)[/]' if st['panels_count'] > 0 else '[red]✗ Missing[/]'}
  5. Panel Contact Sheets: {'[green]✓ Yes (' + str(st['sheets_count']) + ' sheets)[/]' if st['sheets_count'] > 0 else '[dim yellow]✗ Not generated (Mode: ' + asset_mode + ')[/]'}
  6. Vision ZIP Archive  : {'[green]✓ Ready (' + target_zip_name + ')[/]' if target_zip_ready else '[dim yellow]✗ Not generated[/]'}
  7. Narration Script    : {'[green]✓ Present (narration.json)[/]' if st['narration_exist'] else '[yellow]✗ Missing/Empty placeholder[/]'}
  8. Master Audio Track  : {'[green]✓ Generated (IndexTTS-2.5)[/]' if st['master_audio_exist'] else '[red]✗ Not built (' + str(st['audio_clips_count']) + '/' + str(st['total_narration_entries']) + ' clips)[/]'}
  9. Final Recap Video   : {'[green]✓ Ready (' + st['video_path'].name + ')[/]' if st['video_exist'] else '[red]✗ Not rendered[/]'}
"""
    return Panel(status_str.strip(), title="[bold white]remanga Chapter Production Status[/]", border_style="blue")
