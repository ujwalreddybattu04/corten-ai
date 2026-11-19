"""Validated, stateless yearly-to-monthly calculations. No LLM or external data."""
import csv
import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum
from functools import lru_cache
from importlib.metadata import version
from io import StringIO
from pathlib import Path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_YEARS = 100
MAX_COLUMNS = 20
MAX_MONTHLY_VALUES = 12_000
MAX_YEAR = 2**53 - 1
# Year labels: 2025, 1, "Year 1", "Year1", "Yr 1", "FY2025", "Y25".
YEAR_PREFIX = r"^(?:year|yr|fy|y)\s*"
YEAR_LABEL = re.compile(r"(?:(?:year|yr|fy|y)\s*)?[+-]?\d+", re.IGNORECASE)
MONTH_LABEL = re.compile(r"(?:month|mon|mo|m)\s*\d+", re.IGNORECASE)
THOUSANDS = re.compile(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?")


class Mode(str, Enum):
    average = "average"
    exit = "exit"


class Encoding(str, Enum):
    auto = "auto"
    utf8 = "utf-8-sig"
    utf16 = "utf-16"
    windows = "cp1252"
    chinese = "gb18030"


class InputLimitError(ValueError):
    pass


@dataclass(frozen=True)
class YearlyInput:
    columns: tuple[str, ...]
    units: tuple[str, ...]
    years: tuple[int, ...]
    values: tuple[tuple[float, ...], ...]
    input_digest: str
    encoding: str
    delimiter: str
    sorted_input: bool
    transposed: bool = False

    def preview(self):
        return {"columns": list(self.columns), "units": list(self.units),
                "yearly": [{"year": y, "values": list(v)} for y, v in zip(self.years, self.values)],
                "input_digest": self.input_digest, "encoding": self.encoding,
                "delimiter": self.delimiter, "sorted_input": self.sorted_input,
                "transposed": self.transposed}


def read_csv(content: bytes, encoding: Encoding = Encoding.auto) -> YearlyInput:
    if len(content) > MAX_UPLOAD_BYTES:
        raise InputLimitError("CSV files must be no larger than 10 MB.")
    if not content:
        raise ValueError("CSV is empty. Include a year column and at least one value column.")
    encoding = Encoding(encoding)
    codec = encoding.value
    if encoding == Encoding.auto:
        if content.startswith((b'\xff\xfe', b'\xfe\xff')):
            codec = "utf-16"
        else:
            try:
                content.decode("utf-8-sig")
                codec = "utf-8-sig"
            except UnicodeDecodeError:
                codec = "cp1252"
    try:
        text = content.decode(codec)
    except UnicodeError:
        raise ValueError("CSV encoding could not be read. Select the file's encoding or save as UTF-8 CSV.") from None
    if "\x00" in text:
        raise ValueError("CSV contains null characters. Choose UTF-16 for an Excel Unicode export or save as UTF-8.")
    text = text.lstrip("\ufeff")
    # Excel sometimes writes a delimiter declaration before the header.
    declaration = re.match(r"\Asep=([,;\t])(?:\r\n|\n|\r)", text, re.IGNORECASE)
    if declaration:
        delimiter = declaration[1]
        text = text[declaration.end():]
    else:
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t").delimiter
        except csv.Error:
            delimiter = ","
    # Sideways files carry years across the header, so either dimension may reach MAX_YEARS
    # while reading; the exact year and column limits are applied once the layout is known.
    max_fields = max(MAX_COLUMNS, MAX_YEARS) + 1
    try:
        records = []
        for record in csv.reader(StringIO(text, newline=""), delimiter=delimiter, strict=True):
            # Spreadsheet exports pad rows with trailing empty cells (",,,,") and append
            # empty rows. Neither carries data, so both are ignored.
            end = len(record)
            while end and not record[end - 1].strip():
                end -= 1
            if not end:
                continue
            if end > max_fields:
                raise InputLimitError(f"CSV supports at most {MAX_COLUMNS} value columns and {MAX_YEARS} years.")
            records.append(record[:end])
            if len(records) > max_fields:
                raise InputLimitError(f"CSV supports at most {MAX_YEARS} yearly rows.")
    except csv.Error:
        raise ValueError("CSV contains a malformed quoted field. Export a new CSV from your spreadsheet.") from None
    if len(records) < 2:
        raise ValueError("CSV must contain a header and at least one yearly data row.")
    # Rows trimmed of trailing padding are re-aligned; a short row then reports its empty cell.
    # Interior columns with no header and no values (blank spreadsheet columns) are dropped.
    full_width = max(len(record) for record in records)
    records = [record + [""] * (full_width - len(record)) for record in records]
    kept = [i for i in range(full_width) if any(record[i].strip() for record in records)]
    records = [[record[i] for i in kept] for record in records]
    header = [name.strip() for name in records[0]]
    # Years across the first row with one series per row (e.g. ",Y23,Y24" then "Erosion 1,5%,6%")
    # is transposed. Only a file that would otherwise be unreadable is detected this way.
    sideways = (len(header) >= 2 and all(YEAR_LABEL.fullmatch(name) for name in header[1:])
                and not all(YEAR_LABEL.fullmatch(record[0].strip()) for record in records[1:]))
    if sideways:
        for row_number, record in enumerate(records[1:], 2):
            if not record[0].strip():
                raise ValueError(f"Row {row_number}: add a series name in the first column.")
        records = [["year", *(record[0] for record in records[1:])],
                   *([records[0][j], *(record[j] for record in records[1:])] for j in range(1, len(header)))]
    if len(records[0]) > MAX_COLUMNS + 1:
        raise InputLimitError(f"CSV supports at most {MAX_COLUMNS} value columns.")
    if len(records) > MAX_YEARS + 1:
        raise InputLimitError(f"CSV supports at most {MAX_YEARS} years.")
    names = [name.strip() for name in records[0]]
    keys = [unicodedata.normalize("NFC", name).casefold() for name in names]
    for index, name in enumerate(names):
        if not name:
            row_number = next(n for n, record in enumerate(records[1:], 2) if record[index].strip())
            raise ValueError(f"Column {index + 1} has values (first in row {row_number}) but no name. "
                             "Add a column name or delete those values.")
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate column names are not allowed (case-insensitive).")
    if "year" not in keys and len(names) >= 2 and all(MONTH_LABEL.fullmatch(name) for name in names[1:]):
        raise ValueError(f"This file already has monthly columns ({names[1]}, {names[2] if len(names) > 2 else '…'} …). "
                         "Upload yearly values instead: one row per year, or years across the first row.")
    if "year" not in keys or len(names) < 2:
        raise ValueError("Include a 'year' column and at least one numeric value column, "
                         "or put the years across the first row (for example 2023, 2024 or Y23, Y24).")
    for name in names:
        if len(name) > 200 or any(unicodedata.category(ch) in {"Cc", "Cf"} for ch in name):
            raise ValueError("Column names must be at most 200 characters and contain no control or formatting characters.")
        if name.startswith(("=", "+", "-", "@")):
            raise ValueError("Rename formula-like headers beginning with =, +, - or @ before exporting to spreadsheets.")
    if "month" in keys:
        raise ValueError("Rename the value column 'month'; it is reserved for monthly output.")
    width = len(names)
    if (len(records) - 1) * 12 * (width - 1) > MAX_MONTHLY_VALUES:
        raise InputLimitError(f"Request exceeds {MAX_MONTHLY_VALUES:,} monthly values. Use fewer columns while retaining all years.")
    year_index = keys.index("year")
    indices = [i for i in range(width) if i != year_index]
    units = ["%" if "%" in names[i] else "" for i in indices]
    rows = []
    for row_number, record in enumerate(records[1:], 2):
        label = record[year_index].strip()
        # Errors name the year for sideways files, whose rows are now the original columns.
        place = f"Year '{label}'" if sideways else f"Row {row_number}"
        year_text = re.sub(YEAR_PREFIX, "", label, flags=re.IGNORECASE)
        try:
            number = Decimal(year_text)
            if not number.is_finite() or number != number.to_integral_value() or number.copy_abs() > MAX_YEAR:
                raise ValueError
            year = int(number)
        except (ValueError, InvalidOperation, OverflowError):
            raise ValueError(f"{place}: year must be a whole number such as 2025, 1, Year 1 or Y25.") from None
        values = []
        for position, index in enumerate(indices):
            raw = record[index].strip()
            if not raw:
                raise ValueError(f"{place}, '{names[index]}': value is empty. Enter a number; "
                                 "missing values are never filled automatically.")
            if raw.startswith("#"):
                raise ValueError(f"{place}, '{names[index]}': the spreadsheet shows the error {raw}. "
                                 "Fix that cell in Excel and export the CSV again.")
            if raw.endswith("%"):
                units[position] = "%"
                raw = raw[:-1].strip()
            # In comma-separated files a quoted "1,234" can only be a thousands separator.
            if delimiter == "," and THOUSANDS.fullmatch(raw):
                raw = raw.replace(",", "")
            try:
                # Decimal rejects bad fields before float conversion; floats must
                # remain finite and nonzero targets must not underflow to zero.
                if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", raw):
                    raise ValueError
                decimal = Decimal(raw)
                value = float(decimal)
                if not math.isfinite(value) or (decimal != 0 and value == 0):
                    raise ValueError
                if decimal:
                    with localcontext() as context:
                        context.prec = 800
                        if abs(Decimal.from_float(value) - decimal) / decimal.copy_abs() > Decimal("1e-12"):
                            raise ValueError
            except (ValueError, InvalidOperation, OverflowError):
                raise ValueError(f"{place}, '{names[index]}': enter a finite number, optionally ending in %. Value is invalid, overflowing or too small to represent.") from None
            values.append(value)
        rows.append((year, tuple(values)))
    years = [row[0] for row in rows]
    if len(set(years)) != len(years):
        raise ValueError("Duplicate years are not allowed.")
    ordered = sorted(rows)
    if any(right[0] - left[0] != 1 for left, right in zip(ordered, ordered[1:])):
        raise ValueError("Years must be consecutive. Include missing years explicitly; they are never filled automatically.")
    return YearlyInput(tuple(names[i] for i in indices), tuple(units),
                       tuple(row[0] for row in ordered), tuple(row[1] for row in ordered),
                       hashlib.sha256(content).hexdigest(), codec, delimiter, ordered != rows, sideways)


@lru_cache(maxsize=1)
def engine_metadata():
    versions = {name: version(name) for name in ("numpy", "scipy", "cvxpy", "osqp", "clarabel")}
    digest = hashlib.sha256()
    for name in ("interpolation.py", "interpolation_smoothing.py"):
        digest.update(Path(__file__).with_name(name).read_bytes())
    digest.update(json.dumps(versions, sort_keys=True).encode())
    return {"id": "sha256:" + digest.hexdigest(), "dependencies": versions,
            "method": "minimum-curvature", "range_penalty_weight": 0.1,
            "first_month_fraction": 0.01, "zero_series_first_month_floor": 1e-6,
            "relative_constraint_tolerance": 1e-6, "zero_target_absolute_tolerance": 1e-12,
            "display_decimals": 2}


def calculate(data: YearlyInput, mode: Mode) -> dict:
    import numpy as np
    from src.services.interpolation_smoothing import smooth_average, smooth_exit
    mode = Mode(mode)
    targets = np.asarray(data.values, dtype=float)
    output = (smooth_average if mode == Mode.average else smooth_exit)(targets, data.columns)
    if output.shape != (len(data.years) * 12, len(data.columns)) or not np.isfinite(output).all():
        raise ValueError("The calculation returned an invalid monthly series; no output has been released.")
    checks, series = [], []
    with localcontext() as context:
        context.prec = 800
        for col, name in enumerate(data.columns):
            first = float(output[0, col])
            if (mode == Mode.average and first <= 0) or (mode == Mode.exit and first < 0):
                raise ValueError(f"Column '{name}' failed its first-month constraint.")
            for index, year in enumerate(data.years):
                block = output[index * 12:(index + 1) * 12, col]
                target = Decimal(str(targets[index, col]))
                actual = sum((Decimal(str(v)) for v in block), Decimal(0)) / 12 if mode == Mode.average else Decimal(str(block[-1]))
                error = abs(actual - target)
                tolerance = abs(target) * Decimal("1e-6") if target else Decimal("1e-12")
                if error >= tolerance:
                    raise ValueError(f"Column '{name}', year {year}: yearly accuracy could not be verified.")
                checks.append({"column": col, "year": year, "target": float(target),
                               "actual": float(actual), "absolute_error": float(error), "passed": True})
            low, high = float(targets[:, col].min()), float(targets[:, col].max())
            scale = max(abs(low), abs(high), 1e-6)
            # Ignore equality roundoff when reporting visible range excursions.
            outside = int(np.count_nonzero((output[:, col] < low - scale * 1e-9) | (output[:, col] > high + scale * 1e-9)))
            series.append({"name": name, "unit": data.units[col], "input_min": low, "input_max": high,
                           "monthly_min": float(output[:, col].min()), "monthly_max": float(output[:, col].max()),
                           "first_month": first, "outside_range_months": outside})
    result = {**data.preview(), "mode": mode.value,
              "monthly": [{"year": year, "month": month, "values": output[index * 12 + month - 1].tolist()}
                          for index, year in enumerate(data.years) for month in range(1, 13)],
              "checks": checks, "series": series, "engine": engine_metadata(),
              "notes": ["Yearly constraints are verified on unrounded float64 values. Display rounding can change visible averages.",
                        "A percent sign is a unit marker: 25% and 25 both mean 25; no 0–1 conversion is applied.",
                        "Uploaded values are never replaced, clipped or automatically edited.",
                        "Only the first month has a sign constraint. Other months may be negative or exceed yearly extrema."]}
    result["calculation_id"] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return result


def monthly_csv(result: dict) -> bytes:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(["year", "month", *result["columns"]])
    for row in result["monthly"]:
        writer.writerow([row["year"], row["month"], *row["values"]])
    return stream.getvalue().encode("utf-8-sig")
