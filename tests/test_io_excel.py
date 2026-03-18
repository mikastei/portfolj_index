from pathlib import Path
import sys

import pytest
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io_excel import _table_to_dataframe


def _write_transactions_workbook(path: Path, belopp_value) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "TransactionsSheet"
    ws.append(["Affärsdag", "ISIN", "Antal", "Kurs", "Valuta", "Transaktionstyp", "Belopp"])
    ws.append(["2024-01-02", "SE0001", 1, 100, "SEK", "KÖPT", belopp_value])

    table = Table(displayName="Transactions", ref="A1:G2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)
    wb.save(path)
    wb.close()


def test_table_to_dataframe_reads_cached_values_from_transactions_table(tmp_path: Path) -> None:
    workbook_path = tmp_path / "transactions.xlsx"
    _write_transactions_workbook(workbook_path, -100.0)

    df = _table_to_dataframe(workbook_path, "Transactions")

    assert list(df.columns) == ["Affärsdag", "ISIN", "Antal", "Kurs", "Valuta", "Transaktionstyp", "Belopp"]
    assert df.loc[0, "Belopp"] == -100.0


def test_table_to_dataframe_raises_clear_error_for_formula_without_cached_value(tmp_path: Path) -> None:
    workbook_path = tmp_path / "transactions_formula.xlsx"
    _write_transactions_workbook(workbook_path, "=[@Antal]*[@Kurs]*-1")

    with pytest.raises(ValueError, match="data_only=True"):
        _table_to_dataframe(workbook_path, "Transactions")
