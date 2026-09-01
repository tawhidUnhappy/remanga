"""The full interactive settings walkthrough (voice, vision outputs -
what to generate/zip, language, BGM, resolution, background style, GPU) —
`remanga setup-config` / the wizard's 's' option."""

from __future__ import annotations

from pathlib import Path

from rich.prompt import Confirm, Prompt
from rich.table import Table

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.setup import (
    bundle_state_str, configure_vision_outputs, ensure_valid_voice_prompt, is_valid_file,
    read_reference_text, write_reference_text,
)


def run_setup_wizard(config: RemangaConfig) -> RemangaConfig:
    """Interactive step-by-step configuration wizard."""
    console.print(
        "[bold]remanga production settings[/]\n"
        "[dim]Configure vocal reference, vision outputs (what to generate/zip), BGM, video resolution, and canvas background style.[/]\n"
    )

    # 1. TTS Engine
    console.print("[bold]1. TTS Engine[/]")
    engine_table = Table(show_edge=False, show_header=True)
    engine_table.add_column("#", width=4)
    engine_table.add_column("Engine")
    engine_table.add_column("Notes", style="dim")
    engines = [
        ("1", "indextts-2.5", "Zero-shot cloning from a reference voice WAV alone"),
        ("2", "audio8-tts-0.1b", "Also wants a text transcript of the reference voice (see next step)"),
    ]
    for num, name, notes in engines:
        engine_table.add_row(num, name, notes)
    console.print(engine_table)
    curr_engine_num = next((num for num, name, _ in engines if name == config.tts.engine), "1")
    engine_choice = Prompt.ask("[bold]Select TTS engine[/]", choices=["1", "2"], default=curr_engine_num)
    config.tts.engine = next(name for num, name, _ in engines if num == engine_choice)
    console.print(f"[green]✓ Engine set to:[/] {config.tts.engine}")

    # 2. Reference Vocal Audio (Voice Cloning)
    console.print(f"\n[bold]2. Reference Speaker Voice Cloning ({config.tts.engine})[/]")
    console.print("[dim]Provide a clean 3-10 second WAV file of a neutral, steady voice.[/]")
    curr_voice = config.tts.spk_audio_prompt
    if is_valid_file(curr_voice):
        console.print(f"Current Voice: [green]{_esc(str(curr_voice))}[/]")
        if not Confirm.ask("Keep current reference voice?", default=True):
            ensure_valid_voice_prompt(config, interactive=True)
    else:
        ensure_valid_voice_prompt(config, interactive=True)

    if config.tts.engine == "audio8-tts-0.1b":
        console.print(
            "\n[dim]audio8-tts-0.1b also wants an accurate text transcript of that reference voice clip - "
            "cloning quality depends on it, unlike indextts-2.5's audio-only cloning.[/]"
        )
        ref_text_path = config.tts.audio8.reference_text_path
        curr_ref_text = read_reference_text(ref_text_path)
        if curr_ref_text:
            console.print(f"Current transcript ({_esc(ref_text_path)}): [green]{_esc(curr_ref_text)}[/]")
        else:
            console.print(f"[dim]No transcript yet - will be saved to: {_esc(ref_text_path)}[/]")
        new_text = Prompt.ask(
            "[bold]Transcript of the reference voice audio[/]", default=curr_ref_text
        ).strip()
        saved_path = write_reference_text(ref_text_path, new_text)
        console.print(f"[green]✓ Transcript saved to:[/] {_esc(str(saved_path))}")

    # 2. Vision Outputs: what to generate, what to zip/PDF for upload - see
    # remanga.setup.configure_vision_outputs, the same two-section checklist
    # the main interactive wizard can also reach on demand.
    console.print("\n[bold]3. Vision Outputs (What to Generate / Zip for Upload)[/]")
    configure_vision_outputs(config)
    package = config.cropper.package

    # 3. Voice Language Selection
    console.print("\n[bold]4. Voice Language[/]")
    lang_table = Table(show_edge=False, show_header=True)
    lang_table.add_column("#", width=4)
    lang_table.add_column("Language")
    lang_table.add_column("Code", style="dim")

    languages = [
        ("1", "English", "EN"),
        ("2", "Japanese", "JA"),
        ("3", "Chinese (Mandarin)", "ZH"),
        ("4", "Spanish", "ES"),
        ("5", "Arabic", "AR"),
    ]
    for num, name, code in languages:
        lang_table.add_row(num, name, code)
    console.print(lang_table)

    curr_lang = config.tts.lang.upper()
    default_lang_num = next((num for num, _, code in languages if code == curr_lang), "1")
    lang_choice = Prompt.ask("[bold]Select narration language[/]", default=default_lang_num).strip()
    matched_lang = next((code for num, _, code in languages if num == lang_choice or code.lower() == lang_choice.lower()), "EN")
    config.tts.lang = matched_lang
    console.print(f"[green]✓ Language set to:[/] {matched_lang}")

    # 4. Background Music (BGM)
    console.print("\n[bold]5. Background Music (BGM)[/]")
    enable_bgm = Confirm.ask("Enable background music track for recaps?", default=config.audio.bgm_enabled)
    config.audio.bgm_enabled = enable_bgm
    if enable_bgm:
        while True:
            curr_bgm = config.audio.bgm_path or ""
            bgm_input = Prompt.ask("[bold]Enter path to BGM audio file (MP3/WAV/AAC)[/]", default=curr_bgm).strip().strip("'\"")
            if bgm_input:
                valid = is_valid_file(bgm_input)
                if valid:
                    config.audio.bgm_path = str(valid.resolve())
                    console.print(f"[green]✓ BGM path saved:[/] {_esc(str(config.audio.bgm_path))}")
                    break
                else:
                    console.print(f"[red]File not found:[/] {Path(bgm_input).expanduser()}. Please enter a valid file path.")
            else:
                config.audio.bgm_enabled = False
                console.print("[yellow]No path entered. BGM disabled.[/]")
                break

        if config.audio.bgm_enabled:
            vol_str = Prompt.ask("[bold]BGM Volume Gain in dB (recommended -22 to -18 dB)[/]", default=str(config.audio.bgm_volume_db))
            try:
                config.audio.bgm_volume_db = float(vol_str)
            except ValueError:
                config.audio.bgm_volume_db = -22.0

    # 5. YouTube Quality / Video Resolution Presets
    console.print("\n[bold]6. Video Resolution Presets[/]")
    res_table = Table(title="Available Resolution Presets", show_edge=False)
    res_table.add_column("#", width=4)
    res_table.add_column("Preset Quality")
    res_table.add_column("Resolution", style="dim")
    res_table.add_column("Description", style="dim")

    resolutions = [
        ("1", "1080p Full HD", "1920x1080", "Standard YouTube 1080p broadcast [Recommended]", 1920, 1080),
        ("2", "1440p 2K QHD", "2560x1440", "High clarity & higher YouTube VP9/AV1 bitrate allocation", 2560, 1440),
        ("3", "2160p 4K UHD", "3840x2160", "Maximum ultra HD clarity & master render quality", 3840, 2160),
        ("4", "720p HD", "1280x720", "Ultra-fast rendering / lightweight preview quality", 1280, 720),
        ("5", "Custom", "Custom", "Specify custom width and height", 0, 0),
    ]

    for num, title, res, desc, _, _ in resolutions:
        res_table.add_row(num, title, res, desc)
    console.print(res_table)

    curr_res_str = f"{config.video.width}x{config.video.height}"
    default_res_num = next((num for num, _, res, _, _, _ in resolutions if res == curr_res_str), "1")

    res_choice = Prompt.ask("[bold]Choose video resolution preset[/]", default=default_res_num).strip()
    selected_preset = next((item for item in resolutions if item[0] == res_choice), resolutions[0])

    if selected_preset[0] == "5":
        w = int(Prompt.ask("Enter width in pixels", default="1920"))
        h = int(Prompt.ask("Enter height in pixels", default="1080"))
        config.video.width = w
        config.video.height = h
    else:
        _, _, _, _, w, h = selected_preset
        config.video.width = w
        config.video.height = h

    console.print(f"[green]✓ Resolution configured:[/] {config.video.width}x{config.video.height}")

    # 6. Canvas Background Style
    console.print("\n[bold]7. Canvas Background Style[/]")
    bg_table = Table(show_edge=False)
    bg_table.add_column("#", width=4)
    bg_table.add_column("Background Style")
    bg_table.add_column("Description", style="dim")

    bg_styles = [
        ("1", "Fast Bokeh Canvas Blur", "Dynamic blurred background of current panel (<1.5ms) [Recommended]"),
        ("2", "Solid Black Canvas", "Traditional solid black background (#000000)"),
    ]
    for num, title, desc in bg_styles:
        bg_table.add_row(num, title, desc)
    console.print(bg_table)

    default_bg_num = "1" if config.video.background_style == "blur" else "2"
    bg_choice = Prompt.ask("[bold]Choose background style[/]", default=default_bg_num).strip()
    if bg_choice == "2":
        config.video.background_style = "solid"
        console.print("[green]✓ Background set to:[/] Solid Black (#000000)")
    else:
        config.video.background_style = "blur"
        console.print("[green]✓ Background set to:[/] Fast Bokeh Canvas Blur")

    # 7. Hardware Acceleration
    console.print("\n[bold]8. Hardware Acceleration[/]")
    config.system.prefer_gpu = Confirm.ask("Prefer NVIDIA GPU Hardware Acceleration (NVENC)?", default=config.system.prefer_gpu)

    # Save Configuration
    config.save()

    summary_table = Table(title="Production settings saved (config.json)", show_edge=False)
    summary_table.add_column("Setting")
    summary_table.add_column("Value", style="dim")

    summary_table.add_row(
        "Generate",
        f"panels (always) + sheets {'on' if package.sheets else 'off'}",
    )
    summary_table.add_row(
        "Package (zip/PDF for upload)",
        f"panels_zip {bundle_state_str(package, package.panels_zip, package.panels_zip_splites)}, "
        f"pdf {bundle_state_str(package, package.pdf, package.pdf_split)}, "
        f"sheets_zip {'on' if package.sheets_zip else 'off'}",
    )
    summary_table.add_row("Resolution", f"{config.video.width}x{config.video.height} @ {config.video.fps}fps")
    summary_table.add_row("Background Style", f"{config.video.background_style.title()} Blur" if config.video.background_style == "blur" else "Solid Black")
    summary_table.add_row("TTS Engine", config.tts.engine)
    summary_table.add_row("Narration Language", config.tts.lang.upper())
    summary_table.add_row("Reference Voice", str(Path(config.tts.spk_audio_prompt).name) if config.tts.spk_audio_prompt else "[red]Not configured[/]")
    summary_table.add_row("Background Music (BGM)", f"Enabled ({Path(config.audio.bgm_path).name}, {config.audio.bgm_volume_db}dB)" if config.audio.bgm_enabled else "Disabled")
    summary_table.add_row("GPU Codec", f"{config.system.gpu_codec} (Fallback: {config.system.fallback_codec})")

    console.print(summary_table)
    console.print("[green]✓ Saved to config.json[/]\n")
    return config
