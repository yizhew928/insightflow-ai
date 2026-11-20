"""Transparent, non-destructive data profiling."""
import pandas as pd
from .type_inference import _classify_column


def profile(df: pd.DataFrame) -> dict:
    rows = len(df)
    stats = []
    for name in df.columns:
        col = df[name]
        stats.append({'column': name, 'dtype': str(col.dtype), 'inferred_type': _classify_column(col, col.dropna()), 'missing': int(col.isna().sum()),
                      'missing_pct': round(100 * col.isna().sum() / rows, 2) if rows else 0.0,
                      'distinct': int(col.nunique(dropna=True))})
    return {'rows': rows, 'columns': len(df.columns), 'duplicate_rows': int(df.duplicated().sum()),
            'missing_cells': int(df.isna().sum().sum()),
            'column_stats': pd.DataFrame(stats, columns=['column', 'dtype', 'inferred_type', 'missing', 'missing_pct', 'distinct'])}
