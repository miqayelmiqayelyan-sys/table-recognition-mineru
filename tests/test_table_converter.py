from table_recognition_mineru.table_converter import convert_mineru_table
from table_recognition_mineru.table_extractor import MinerUTableBlock


def _convert(html: str):
    return convert_mineru_table(
        MinerUTableBlock(index=0, page_idx=0, bbox_norm=[0, 0, 1000, 1000], table_body_html=html)
    )


def _value(table, row: int, col: int) -> str:
    for cell in table.cells:
        if cell.row == row and cell.col == col:
            return cell.value
    return ""


def test_currency_marker_columns_merge_into_their_figure():
    """The page has one gap per real column, so "$" must not ask for a column of its own."""
    html = """
    <table>
      <tr><td>Net borrowings</td><td>$ (</td><td>973,468</td><td>$</td><td>3,813,655</td></tr>
      <tr><td>Distributions paid</td><td>(</td><td>58)</td><td></td><td>33,793)</td></tr>
    </table>
    """

    table = _convert(html)

    assert table.num_cols == 3
    assert _value(table, 0, 0) == "Net borrowings"
    assert _value(table, 0, 1) == "$ ( 973,468"
    assert _value(table, 0, 2) == "$ 3,813,655"
    assert _value(table, 1, 1) == "( 58)"


def test_trailing_empty_column_stays_on_an_ordinary_table():
    """An empty column with no "$" / "(" markers is left alone so values do not rewrite."""
    html = """
    <table>
      <tr><td>Cash</td><td>5,550</td><td></td></tr>
      <tr><td>Total</td><td>6,733</td><td></td></tr>
    </table>
    """

    table = _convert(html)

    assert table.num_cols == 3
    assert _value(table, 1, 1) == "6,733"


def test_empty_column_drops_when_currency_markers_are_present():
    html = """
    <table>
      <tr><td>Net borrowings</td><td>$ (</td><td>973,468</td><td>$</td><td>3,813,655</td><td></td></tr>
      <tr><td>Distributions</td><td>(</td><td>58)</td><td></td><td>33,793)</td><td></td></tr>
    </table>
    """

    table = _convert(html)

    assert table.num_cols == 3
    assert _value(table, 0, 1) == "$ ( 973,468"
    assert _value(table, 0, 2) == "$ 3,813,655"


def test_ordinary_table_is_left_alone():
    html = """
    <table>
      <tr><td></td><td>2025</td><td>2024</td></tr>
      <tr><td>Cash</td><td>$ 5,550</td><td>$ 40,920</td></tr>
    </table>
    """

    table = _convert(html)

    assert table.num_cols == 3
    assert _value(table, 0, 1) == "2025"
    assert _value(table, 1, 2) == "$ 40,920"


def test_label_column_survives_a_page_of_section_headers():
    """Column 0 stays even when every value in it looks like a marker."""
    html = """
    <table>
      <tr><td>-</td><td>Assets</td></tr>
      <tr><td></td><td>Liabilities</td></tr>
    </table>
    """

    table = _convert(html)

    assert table.num_cols == 2
    assert _value(table, 0, 1) == "Assets"
