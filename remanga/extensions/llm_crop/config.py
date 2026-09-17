"""The LLM crop extension's settings - `config.extensions.llm_crop`: what
`crop-grid` builds for Gemini, and how its reply is imported. Whether the
crops' neighbours get painted out is the cropper's own `cropper.paint_out`.

The grid formats mirror PackageConfig's switches one for one - a folder of
images, a zip, a PDF, each single or split, sharing one size cap - and are
built by the same lossless zip and PDF builders, so a gridded chapter uploads
exactly the way a cropped one does. Their menu is generated from the Field
metadata below, like the packaging checklist's."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMCropConfig(BaseModel):
    # Validates on assignment, like every config section (remanga.config.base
    # - not imported here, so loading this model never re-enters the config
    # package that is building the schema around it).
    model_config = ConfigDict(validate_assignment=True)

    grid_pages: bool = Field(
        True, title="grid_pages",
        description="Every page on a square black canvas with the ruler grid, plus a 000_info "
                    "image - also what the zip and PDF formats are built from",
        json_schema_extra={"produces": "grid_pages/002_001.png, 002_002.png, ...", "group": "pages"},
    )
    grid_zip: bool = Field(
        False, title="grid_zip",
        description="Those grid images and chapter_info.json in one zip",
        json_schema_extra={"produces": "grid_zip/grid_1.zip", "group": "zip"},
    )
    grid_zip_splites: bool = Field(
        False, title="grid_zip_splites", description="That same zip, split into size-capped parts",
        json_schema_extra={"produces": "grid_zip/grid_1.zip, grid_2.zip, ...", "group": "zip"},
    )
    grid_pdf: bool = Field(
        False, title="grid_pdf", description="The grid images, one per PDF page, as a single file",
        json_schema_extra={"produces": "grid_pdf/grid_1.pdf", "group": "pdf"},
    )
    grid_pdf_splite: bool = Field(
        False, title="grid_pdf_splite",
        description="That same PDF split into size-capped raw .pdf files, not zipped",
        json_schema_extra={"produces": "grid_pdf/grid_1.pdf, grid_2.pdf, ...", "group": "pdf"},
    )
    grid_pdf_zip: bool = Field(
        False, title="grid_pdf_zip", description="The single grid PDF, wrapped in a zip",
        json_schema_extra={"produces": "grid_pdf/grid_1.zip", "group": "pdf"},
    )
    grid_pdf_zip_splite: bool = Field(
        False, title="grid_pdf_zip_splite", description="The grid PDF split into size-capped parts, each zipped",
        json_schema_extra={"produces": "grid_pdf/grid_1.zip, grid_2.zip, ...", "group": "pdf"},
    )
    max_mb: float = Field(
        50.0, gt=0, title="max_mb",
        description="Size cap per part for the split grid formats above, in MB",
        json_schema_extra={"group": "limits"},
    )

    # Side of every square grid image, in pixels. A page is scaled evenly to
    # fit it, anchored top-left, and the rest of the square is black. Big
    # enough that the 5-unit ticks below (10 px apart) still separate at the
    # ~2000 px a model looks at a page closely; shrunk to ~1000 px they blur,
    # and the 25-unit lines still carry the reading.
    grid_image_size: int = Field(2048, ge=512, le=4096)
    # Light lines every grid_line_step units and heavy labeled lines every
    # grid_label_step, on the 0-1000 scale Gemini's boxes use. 25 puts every
    # border within 12.5 units of a numbered line.
    grid_line_step: int = Field(25, ge=10, le=500)
    grid_label_step: int = Field(100, ge=10, le=500)
    # Ticks every grid_tick_step units, along the four edges and across every
    # labeled line - what turns an edge that falls between two lines into a
    # count rather than a guess. 0 draws none. See grid.py for why these are
    # ticks and not a mesh of lines that fine.
    grid_tick_step: int = Field(5, ge=0, le=100)
    # How readily Gemini shows several frames as one crop (prompts/llm_crop.md
    # <craft> 4). Written into chapter_info.json, so a change reaches Gemini
    # with the next crop-grid.
    grouping: Literal["none", "balanced", "generous"] = "balanced"
    # Draw every imported crop on its page, for checking by eye.
    preview: bool = True

    @property
    def zip_active(self) -> bool:
        return self.grid_zip or self.grid_zip_splites

    @property
    def pdf_active(self) -> bool:
        return self.grid_pdf or self.grid_pdf_splite or self.grid_pdf_zip or self.grid_pdf_zip_splite

    @property
    def pdf_split(self) -> bool:
        return self.grid_pdf_splite or self.grid_pdf_zip_splite

    @property
    def any_active(self) -> bool:
        return self.grid_pages or self.zip_active or self.pdf_active
