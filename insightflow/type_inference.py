"""Type inference adapted from upstream app/core/data_profiler.py.
Copyright (c) 2026 Sayantan Chaklader. See ../LICENSE.
Source: Dark-Frost009/ai-data-analyst-agent at 094439308de57d99e0b89f0fbd0b42f043edf819.
"""
import warnings
from typing import Any
import numpy as np
import pandas as pd
ColumnType = str
_DATETIME_DETECTION_SAMPLE_SIZE = 100
_DATETIME_DETECTION_THRESHOLD = 0.9
def _classify_column(series: pd.Series, non_null: pd.Series) -> ColumnType:
    """Determine the semantic type of a column from its dtype and values."""
    if len(non_null) == 0:
        return "empty"

    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        if _looks_like_datetime(non_null):
            return "datetime"
        # A boolean column with missing values can't be held in a native
        # bool array (no NaN support), so pandas upcasts it to object —
        # detect that case explicitly rather than letting it fall to
        # "mixed".
        if all(isinstance(v, (bool, np.bool_)) for v in non_null):
            return "boolean"
        if all(isinstance(v, str) for v in non_null):
            return "string"
        return "mixed"

    # Any other/unusual dtype (category, timedelta, complex, ...) —
    # a safe, non-crashing fallback.
    return "mixed"


def _looks_like_datetime(non_null: pd.Series) -> bool:
    """Bounded, non-mutating heuristic: does this column look date-like?"""
    sample = non_null.head(_DATETIME_DETECTION_SAMPLE_SIZE)
    if len(sample) == 0:
        return False

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(sample, errors="coerce")
    except (TypeError, ValueError, OverflowError):
        # Genuinely mixed non-string types (e.g. int/str/float in the
        # same object column) can raise here rather than coercing
        # cleanly, depending on pandas version. Treat any such failure
        # as "not datetime-like" rather than letting it propagate.
        return False

    success_ratio = parsed.notna().sum() / len(sample)
    if success_ratio < _DATETIME_DETECTION_THRESHOLD:
        return False

    # A column of plain 4-digit numbers ("2020", "1999", ...) parses as
    # datetimes with a high success ratio, but almost always represents
    # a year number rather than an actual calendar date. Require that
    # most of the sample isn't bare year-like strings before trusting
    # the parse, so this stays specific to that one known ambiguity
    # instead of rejecting genuinely separated ("2020-01-01") or
    # unambiguous eight-digit ("20200115") date strings.
    year_like_ratio = sum(
        _is_bare_year_like_string(value) for value in sample
    ) / len(sample)
    if year_like_ratio >= _DATETIME_DETECTION_THRESHOLD:
        return False

    return True


def _is_bare_year_like_string(value: Any) -> bool:
    """True for a plain 4-digit numeric string, e.g. "2020" or "1999"."""
    text = str(value).strip()
    return len(text) == 4 and text.isdigit()


