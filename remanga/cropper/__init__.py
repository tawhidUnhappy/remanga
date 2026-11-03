"""Cutting a chapter's marked panels out of its pages.

The marks come from the Panel Marker web UI (remanga/webui/), which writes
crops.json; this turns them into panels/panel_*.png, which is what the LLM is
shown and what the video plays."""

from remanga.cropper.crop import CoordinateCropper, cropped_panels

__all__ = ["CoordinateCropper", "cropped_panels"]
