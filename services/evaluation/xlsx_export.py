"""One-way M10-D XLSX audit writer for the approved local research dependency."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence
import zipfile

from services.contracts.validation import ContractError

from .export import (
    AuditDataset,
    _artifact_metadata,
    _file_evidence,
    _fsync_directory,
    encode_audit_cell,
    partition_dataset,
)


XLSXWRITER_VERSION = "3.2.9"
XLSX_WORKBOOK_PATH = "xlsx/sage-vista-m10-audit.xlsx"
XLSX_DATASET_ORDER = (
    "RunSummary",
    "ForwardOutcomes",
    "TradeOutcomes",
    "ResearchAggregates",
    "PortfolioStatus",
    "BiasMissingData",
    "VersionEvidence",
    "HumanReview",
)
XLSX_SHEET_NAMES = {
    "RunSummary": "Run Summary",
    "ForwardOutcomes": "Forward Outcomes",
    "TradeOutcomes": "Trade Outcomes",
    "ResearchAggregates": "Research Aggregates",
    "PortfolioStatus": "Portfolio Status",
    "BiasMissingData": "Bias & Missing Data",
    "VersionEvidence": "Version Evidence",
    "HumanReview": "Human Review",
}
XLSX_PART_NAMES = {
    "RunSummary": "Run Summary",
    "ForwardOutcomes": "Forward",
    "TradeOutcomes": "Trade",
    "ResearchAggregates": "Research",
    "PortfolioStatus": "Portfolio",
    "BiasMissingData": "Bias Missing",
    "VersionEvidence": "Version",
    "HumanReview": "Human Review",
}


def _expected_worksheet_name(
    dataset_name: str, part_number: int, part_count: int
) -> str:
    if dataset_name not in XLSX_DATASET_ORDER:
        raise ContractError("M10-D dataset is not approved for XLSX")
    return (
        XLSX_SHEET_NAMES[dataset_name]
        if part_count == 1
        else f"{XLSX_PART_NAMES[dataset_name]} {part_number:03d}"
    )


def _xlsx_artifact_sort_key(item: Mapping[str, Any]) -> tuple[int, int]:
    try:
        dataset_order = XLSX_DATASET_ORDER.index(str(item["dataset"]))
    except ValueError as exc:
        raise ContractError("M10-D dataset is not approved for XLSX") from exc
    return dataset_order, int(item["part_number"])


@dataclass(frozen=True)
class XlsxPart:
    dataset: AuditDataset
    rows: tuple[Mapping[str, Any], ...]
    part_number: int
    part_count: int
    worksheet_name: str


def plan_xlsx_parts(
    datasets: Mapping[str, AuditDataset], max_data_rows: int
) -> tuple[XlsxPart, ...]:
    parts: list[XlsxPart] = []
    for name in XLSX_DATASET_ORDER:
        dataset = datasets[name]
        row_parts = partition_dataset(dataset, max_data_rows)
        if not row_parts:
            continue
        count = len(row_parts)
        for number, rows in enumerate(row_parts, 1):
            worksheet_name = _expected_worksheet_name(name, number, count)
            if len(worksheet_name) > 31:
                raise ContractError("M10-D worksheet name exceeds the XLSX limit")
            parts.append(XlsxPart(dataset, rows, number, count, worksheet_name))
    names = [part.worksheet_name for part in parts]
    if len(names) != len(set(names)):
        raise ContractError("M10-D worksheet names are not unique")
    return tuple(parts)


def _require_xlsxwriter():
    try:
        import xlsxwriter
    except ImportError as exc:
        raise ContractError(
            "M10-D XLSX export requires the isolated XlsxWriter 3.2.9 dependency"
        ) from exc
    if getattr(xlsxwriter, "__version__", None) != XLSXWRITER_VERSION:
        raise ContractError("M10-D XLSX dependency version is not approved")
    return xlsxwriter


def _check_write(code: Any) -> None:
    if code not in {0, None}:
        raise ContractError("M10-D XLSX cell could not be represented without loss")


def _write_cell(worksheet, row: int, column: int, spec, value, formats) -> None:
    if value is None:
        _check_write(worksheet.write_string(row, column, r"\N", formats["text"]))
        return
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ContractError("M10-D XLSX boolean cell has the wrong type")
        _check_write(worksheet.write_boolean(row, column, value, formats["boolean"]))
        return
    if spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractError("M10-D XLSX integer cell has the wrong type")
        _check_write(worksheet.write_number(row, column, value, formats["integer"]))
        return
    if spec.kind == "decimal":
        if not isinstance(value, Decimal):
            raise ContractError("M10-D XLSX Decimal display cell has the wrong type")
        _check_write(worksheet.write_number(row, column, float(value), formats["decimal"]))
        return
    encoded = encode_audit_cell(value, spec.kind)
    _check_write(worksheet.write_string(row, column, encoded, formats["text"]))


def _normalize_xlsx_zip(path: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".normalized", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(path, "r") as source:
            names = source.namelist()
            if len(names) != len(set(names)):
                raise ContractError("generated XLSX contains duplicate ZIP members")
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as target:
                for name in sorted(names):
                    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = 0o600 << 16
                    with source.open(name, "r") as source_member:
                        with target.open(info, "w", force_zip64=True) as target_member:
                            shutil.copyfileobj(source_member, target_member, 1024 * 1024)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_xlsx_artifact(
    root: Path,
    datasets: Mapping[str, AuditDataset],
    *,
    max_data_rows: int,
) -> list[dict[str, Any]]:
    """Write one deterministic multi-sheet workbook and return per-sheet evidence."""

    xlsxwriter = _require_xlsxwriter()
    parts = plan_xlsx_parts(datasets, max_data_rows)
    if not parts:
        raise ContractError("M10-D XLSX export has no source-backed worksheet")
    path = root / XLSX_WORKBOOK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        workbook = xlsxwriter.Workbook(str(temporary), {
            "constant_memory": True,
            "strings_to_formulas": False,
            "strings_to_urls": False,
            "strings_to_numbers": False,
        })
        try:
            workbook.set_properties({
                "title": "Sage Vista M10 audit copy",
                "subject": "Non-authoritative M10-D review export",
                "author": "Sage Vista",
                "comments": "Generated values only; no formulas and no import path.",
                "created": datetime(2000, 1, 1, 0, 0, 0),
            })
            workbook.read_only_recommended()
            formats = {
                "header": workbook.add_format({"bold": True, "bg_color": "#D9EAF7"}),
                "text": workbook.add_format({"num_format": "@"}),
                "boolean": workbook.add_format({"num_format": "General"}),
                "integer": workbook.add_format({"num_format": "0"}),
                "decimal": workbook.add_format({"num_format": "0.0000000000"}),
            }
            for part in parts:
                worksheet = workbook.add_worksheet(part.worksheet_name)
                worksheet.freeze_panes(1, 0)
                worksheet.autofilter(
                    0, 0, len(part.rows), len(part.dataset.columns) - 1
                )
                worksheet.set_column(0, len(part.dataset.columns) - 1, 18)
                for column, spec in enumerate(part.dataset.columns):
                    _check_write(
                        worksheet.write_string(0, column, spec.name, formats["header"])
                    )
                for row_number, values in enumerate(part.rows, 1):
                    for column, spec in enumerate(part.dataset.columns):
                        _write_cell(
                            worksheet, row_number, column, spec,
                            values[spec.name], formats,
                        )
        finally:
            workbook.close()
        _normalize_xlsx_zip(temporary)
        os.replace(temporary, path)
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        if path.exists():
            path.unlink()
        raise

    file_evidence = _file_evidence(path)
    return [
        _artifact_metadata(
            path,
            relative_path=XLSX_WORKBOOK_PATH,
            artifact_format="xlsx",
            dataset=part.dataset,
            rows=part.rows,
            part_number=part.part_number,
            part_count=part.part_count,
            worksheet_row_count=len(part.rows) + 1,
            worksheet_name=part.worksheet_name,
            file_evidence=file_evidence,
        )
        for part in parts
    ]


__all__ = [
    "XLSXWRITER_VERSION", "XLSX_DATASET_ORDER", "XLSX_SHEET_NAMES",
    "XLSX_WORKBOOK_PATH", "XlsxPart", "plan_xlsx_parts",
]
