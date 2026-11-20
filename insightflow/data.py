"""Bounded CSV and workbook loading for local analysis."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import pandas as pd

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 200


def load_tables(file_bytes: bytes, filename: str) -> dict[str, pd.DataFrame]:
    if not file_bytes or len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError('File is empty or exceeds the 20 MB upload limit.')
    suffix = Path(filename).suffix.lower()
    if suffix == '.csv':
        tables = {'data': pd.read_csv(BytesIO(file_bytes), nrows=MAX_ROWS + 1)}
    elif suffix == '.xlsx':
        try:
            with ZipFile(BytesIO(file_bytes)) as archive:
                if sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_BYTES:
                    raise ValueError('Workbook exceeds the 100 MB expanded size limit.')
            workbook = pd.ExcelFile(BytesIO(file_bytes), engine='openpyxl')
            if len(workbook.sheet_names) > 20:
                raise ValueError('Workbook has more than 20 sheets.')
            tables = {name: pd.read_excel(workbook, sheet_name=name, nrows=MAX_ROWS + 1) for name in workbook.sheet_names}
        except BadZipFile as exc:
            raise ValueError('Invalid XLSX workbook.') from exc
    else:
        raise ValueError('Use a CSV or XLSX file.')
    for name, frame in tables.items():
        if len(frame) > MAX_ROWS or len(frame.columns) > MAX_COLUMNS:
            raise ValueError(f'{name}: limit is 100,000 rows and 200 columns.')
        frame.columns = [str(c) for c in frame.columns]
    return tables
