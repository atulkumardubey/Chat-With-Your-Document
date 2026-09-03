import pandas as pd

Unit = tuple[str, dict]

ROWS_PER_MARKDOWN_CHUNK = 20


def _rows_as_text(df: pd.DataFrame, sheet: str, filename: str) -> list[Unit]:
    units: list[Unit] = []
    for idx, row in df.iterrows():
        row_num = idx + 2  # +1 for 0-index, +1 for header row
        text = " | ".join(f"{col}: {row[col]}" for col in df.columns)
        units.append(
            (text, {"source": filename, "sheet": sheet, "row": f"Row {row_num}", "format": "rows", "type": "excel"})
        )
    return units


def _markdown_table(df: pd.DataFrame, sheet: str, filename: str) -> list[Unit]:
    units: list[Unit] = []
    for start in range(0, len(df), ROWS_PER_MARKDOWN_CHUNK):
        chunk = df.iloc[start : start + ROWS_PER_MARKDOWN_CHUNK]
        first_row, last_row = start + 2, start + len(chunk) + 1
        text = chunk.to_markdown(index=False)
        units.append(
            (
                text,
                {
                    "source": filename,
                    "sheet": sheet,
                    "row": f"Rows {first_row}-{last_row}",
                    "format": "markdown",
                    "type": "excel",
                },
            )
        )
    return units


def _column_wise(df: pd.DataFrame, sheet: str, filename: str) -> list[Unit]:
    units: list[Unit] = []
    for col in df.columns:
        values = ", ".join(str(v) for v in df[col].tolist())
        text = f"Column '{col}' values: {values}"
        units.append(
            (text, {"source": filename, "sheet": sheet, "row": f"Column {col}", "format": "column", "type": "excel"})
        )
    return units


_FORMATTERS = {
    "rows": _rows_as_text,
    "markdown": _markdown_table,
    "column": _column_wise,
}


def parse_excel(file_path: str, filename: str, fmt: str) -> list[Unit]:
    """Serializes every sheet using a single format (rows-as-text / markdown / column-wise)."""
    if fmt not in _FORMATTERS:
        raise ValueError(f"Unknown excel format: {fmt}")
    sheets = pd.read_excel(file_path, sheet_name=None)
    units: list[Unit] = []
    for sheet_name, df in sheets.items():
        units.extend(_FORMATTERS[fmt](df, sheet_name, filename))
    return units


def parse_excel_all_formats(file_path: str, filename: str) -> dict[str, list[Unit]]:
    """Used by the evaluation bake-off to compare all 3 serialization formats side by side."""
    return {fmt: parse_excel(file_path, filename, fmt) for fmt in _FORMATTERS}


def get_sheet_count(file_path: str) -> int:
    sheets = pd.read_excel(file_path, sheet_name=None)
    return len(sheets)
