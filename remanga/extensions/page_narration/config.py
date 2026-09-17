"""The page narration extension's settings - `config.extensions.page_narration`:
what `page-upload` builds for the LLM. The formats mirror the panels PDF
switches (PackageConfig) and are built by the same size-capped PDF builder,
remanga.cropper.llm_pdf."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PageNarrationConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    pages_pdf: bool = Field(
        True, title="pages_pdf", description="Every page of the chapter, one per PDF page, as a single file",
        json_schema_extra={"produces": "page_upload/pages_1.pdf", "group": "pdf"},
    )
    pages_pdf_splite: bool = Field(
        False, title="pages_pdf_splite",
        description="That same PDF split into size-capped raw .pdf files, not zipped",
        json_schema_extra={"produces": "page_upload/pages_1.pdf, pages_2.pdf, ...", "group": "pdf"},
    )
    pages_pdf_zip: bool = Field(
        False, title="pages_pdf_zip", description="The single pages PDF, wrapped in a zip",
        json_schema_extra={"produces": "page_upload/pages_1.zip", "group": "pdf"},
    )
    pages_pdf_zip_splite: bool = Field(
        False, title="pages_pdf_zip_splite", description="The pages PDF split into size-capped parts, each zipped",
        json_schema_extra={"produces": "page_upload/pages_1.zip, pages_2.zip, ...", "group": "pdf"},
    )
    max_mb: float = Field(
        50.0, gt=0, title="max_mb", description="Size cap in MB for every pages PDF file",
        json_schema_extra={"group": "limits"},
    )

    @property
    def any_active(self) -> bool:
        return self.pages_pdf or self.pages_pdf_splite or self.pages_pdf_zip or self.pages_pdf_zip_splite
