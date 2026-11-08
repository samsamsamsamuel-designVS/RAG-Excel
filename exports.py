"""Create downloadable Excel workbooks in memory."""
from io import BytesIO

import pandas as pd


def results_to_excel(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    # Excel cannot store timezone-aware dates; preserve their offsets as text.
    export = frame.copy()
    for column in export.columns:
        if isinstance(export[column].dtype, pd.DatetimeTZDtype):
            export[column] = export[column].astype(str)
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        export.to_excel(writer, sheet_name='Results', index=False)
        sheet = writer.sheets['Results']
        # Keep source text beginning with '=' as text rather than executable formulas.
        for row in sheet.iter_rows():
            for cell in row:
                if cell.data_type == 'f':
                    cell.data_type = 's'
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
    return buffer.getvalue()
