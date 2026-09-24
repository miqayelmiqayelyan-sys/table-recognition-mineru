from table_recognition_mineru.divider_grid import (
    align_rows_to_lines,
    amount_column_dividers,
    build_grid,
    cell_data_from_dividers,
    cluster_words_into_lines,
    column_dividers_from_native,
    row_dividers_from_lines,
    split_single_column_into_label_and_amount,
    validate_grid,
)
from table_recognition_mineru.table_converter import ConvertedCell, ConvertedTable
from table_recognition_mineru.table_extractor import MinerUTableBlock

TABLE_PCT = {
    "left": 10.0,
    "top": 10.0,
    "right": 90.0,
    "bottom": 50.0,
    "width": 80.0,
    "height": 40.0,
}


def _word(text, left, top, right, bottom):
    return {"ocr_text": text, "left": left, "top": top, "right": right, "bottom": bottom}


def _three_row_words():
    """Label column near x=12, amount column near x=70, rows at y=12/20/28."""
    return [
        _word("Assets", 12.0, 12.0, 25.0, 13.0),
        _word("100", 70.0, 12.0, 75.0, 13.0),
        _word("Cash", 12.0, 20.0, 22.0, 21.0),
        _word("200", 70.0, 20.0, 75.0, 21.0),
        _word("Total", 12.0, 28.0, 21.0, 29.0),
        _word("300", 70.0, 28.0, 75.0, 29.0),
    ]


def _converted(num_rows=3, num_cols=2, cells=None):
    block = MinerUTableBlock(
        index=0,
        page_idx=0,
        bbox_norm=[100, 100, 900, 500],
        table_body_html="<table></table>",
    )
    if cells is None:
        values = [["Assets", "100"], ["Cash", "200"], ["Total", "300"]]
        cells = [
            ConvertedCell(row=r, col=c, value=values[r][c])
            for r in range(num_rows)
            for c in range(num_cols)
        ]
    return ConvertedTable(source=block, num_rows=num_rows, num_cols=num_cols, cells=cells)


def _native_cells():
    # Native jitter: every cell has a slightly different left/top.
    return {
        "1:1": {"left": 11.9, "top": 11.7, "width": 13.2, "height": 1.6, "colspan": 1, "rowspan": 1, "value": "Assets"},
        "2:1": {"left": 69.8, "top": 11.8, "width": 5.4, "height": 1.5, "colspan": 1, "rowspan": 1, "value": "100"},
        "1:2": {"left": 12.1, "top": 19.8, "width": 10.1, "height": 1.7, "colspan": 1, "rowspan": 1, "value": "Cash"},
        "2:2": {"left": 70.2, "top": 19.9, "width": 5.1, "height": 1.4, "colspan": 1, "rowspan": 1, "value": "200"},
        "1:3": {"left": 11.8, "top": 27.9, "width": 9.4, "height": 1.6, "colspan": 1, "rowspan": 1, "value": "Total"},
        "2:3": {"left": 70.1, "top": 28.1, "width": 5.2, "height": 1.3, "colspan": 1, "rowspan": 1, "value": "300"},
    }


def _single_column_divider(words, table_pct):
    """The one label/amount boundary a two-column split needs."""
    dividers = amount_column_dividers(words, table_pct, 2)
    return dividers[1] if dividers else None


def test_cluster_words_into_lines_groups_by_row():
    lines = cluster_words_into_lines(_three_row_words())
    assert [line.text for line in lines] == ["Assets 100", "Cash 200", "Total 300"]


def test_column_dividers_land_in_whitespace_between_columns():
    dividers = column_dividers_from_native(
        _native_cells(), _three_row_words(), TABLE_PCT, num_cols=2
    )
    assert dividers[0] == TABLE_PCT["left"]
    assert dividers[-1] == TABLE_PCT["right"]
    # The single internal divider must sit in the label/amount gap, never on ink.
    assert 25.0 <= dividers[1] <= 70.0


def test_align_rows_to_lines_is_monotonic_with_repeated_labels():
    lines = cluster_words_into_lines(
        [
            _word("Total", 12.0, 12.0, 21.0, 13.0),
            _word("Cash", 12.0, 20.0, 22.0, 21.0),
            _word("Total", 12.0, 28.0, 21.0, 29.0),
        ]
    )
    groups = align_rows_to_lines(["Total", "Cash", "Total"], lines)
    assert groups == [[0], [1], [2]]


def test_row_dividers_never_cross_text():
    words = _three_row_words()
    lines = cluster_words_into_lines(words)
    groups = align_rows_to_lines(["Assets 100", "Cash 200", "Total 300"], lines)
    dividers = row_dividers_from_lines(groups, lines, words, TABLE_PCT)

    assert len(dividers) == 4
    assert dividers == sorted(dividers)
    for divider in dividers:
        for word in words:
            assert not (word["top"] < divider < word["bottom"])


def test_grid_cells_tile_without_gaps_and_are_tabletag_safe():
    grid = build_grid(_converted(), _native_cells(), _three_row_words(), TABLE_PCT)
    validation = validate_grid(grid.cell_data)

    assert validation["valid"]
    assert validation["row_count"] == 3
    assert validation["col_count"] == 2
    assert grid.diagnostics["unique_lefts"] == 2
    assert grid.diagnostics["unique_tops"] == 3
    assert grid.diagnostics["rows_matched_to_ocr"] == 3

    # Adjacent cells share a boundary exactly: no gaps, no overlaps.
    assert grid.cell_data["1:1"]["top"] + grid.cell_data["1:1"]["height"] == grid.cell_data["1:2"]["top"]
    assert grid.cell_data["1:1"]["left"] + grid.cell_data["1:1"]["width"] == grid.cell_data["2:1"]["left"]


def test_grid_expands_colspan_so_vertical_lines_stay_continuous():
    cells = [
        ConvertedCell(row=0, col=0, value="Section", colspan=2),
        ConvertedCell(row=1, col=0, value="Cash"),
        ConvertedCell(row=1, col=1, value="200"),
        ConvertedCell(row=2, col=0, value="Total"),
        ConvertedCell(row=2, col=1, value="300"),
    ]
    converted = _converted(cells=cells)
    grid = build_grid(converted, _native_cells(), _three_row_words(), TABLE_PCT)

    # The spanning row becomes two cells, so every row has a boundary at the same x.
    assert len(grid.cell_data) == 6
    assert grid.cell_data["1:1"]["colspan"] == 1
    assert grid.cell_data["1:1"]["value"] == "Section"
    assert grid.cell_data["2:1"]["value"] == ""
    assert not any(cell["colspan"] > 1 for cell in grid.cell_data.values())
    assert len({round(cell["left"], 6) for cell in grid.cell_data.values()}) == 2


def test_rows_without_ocr_text_still_get_a_band():
    values = [["Assets", "100"], ["", ""], ["Total", "300"]]
    cells = [
        ConvertedCell(row=r, col=c, value=values[r][c])
        for r in range(3)
        for c in range(2)
    ]
    words = [
        _word("Assets", 12.0, 12.0, 25.0, 13.0),
        _word("100", 70.0, 12.0, 75.0, 13.0),
        _word("Total", 12.0, 28.0, 21.0, 29.0),
        _word("300", 70.0, 28.0, 75.0, 29.0),
    ]
    grid = build_grid(_converted(cells=cells), _native_cells(), words, TABLE_PCT)

    assert validate_grid(grid.cell_data)["valid"]
    assert all(cell["height"] > 0 for cell in grid.cell_data.values())
    assert grid.diagnostics["unique_tops"] == 3


def test_single_column_split_ignores_leading_account_numbers():
    """Rows starting with account numbers must not drag the divider onto the labels."""
    words = [
        _word("Total", 78.0, 11.0, 85.0, 12.0),
        _word("1010", 12.0, 20.0, 16.0, 21.0),
        _word("Citizens Bank", 17.0, 20.0, 35.0, 21.0),
        _word("196,137.31", 76.0, 20.0, 85.0, 21.0),
        _word("Total for Bank Accounts", 12.0, 28.0, 45.0, 29.0),
        _word("200,792.35", 76.0, 28.0, 85.0, 29.0),
        _word("1020", 12.0, 36.0, 16.0, 37.0),
        _word("Payroll", 17.0, 36.0, 28.0, 37.0),
        _word("4,655.04", 77.0, 36.0, 85.0, 37.0),
    ]
    cell_data = {
        "1:1": {"left": 10.0, "top": 10.5, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "Total"},
        "1:2": {"left": 10.0, "top": 19.0, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "1010 Citizens Bank 196,137.31"},
        "1:3": {"left": 10.0, "top": 27.0, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "Total for Bank Accounts 200,792.35"},
        "1:4": {"left": 10.0, "top": 35.0, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "1020 Payroll 4,655.04"},
    }
    split = split_single_column_into_label_and_amount(cell_data, words, TABLE_PCT)

    divider = split["2:2"]["left"]
    assert divider > 45.0, "divider must sit right of the longest label, not next to '1010'"
    for word in words:
        assert not (word["left"] < divider < word["right"])

    assert split["1:2"]["value"] == "1010 Citizens Bank"
    assert split["2:2"]["value"] == "196,137.31"
    # A row whose text is only in the amount column still emits an empty label cell.
    assert split["2:1"]["value"] == "Total"
    assert split["1:1"]["value"] == ""


def test_single_column_split_keeps_section_rows_two_celled():
    """Section headers must not merge, or the vertical line breaks at every header."""
    words = [
        _word("Assets", 12.0, 12.0, 25.0, 13.0),
        _word("Cash", 12.0, 20.0, 22.0, 21.0),
        _word("100.00", 78.0, 20.0, 85.0, 21.0),
        _word("Savings", 12.0, 28.0, 24.0, 29.0),
        _word("200.00", 78.0, 28.0, 85.0, 29.0),
        _word("Total", 12.0, 36.0, 21.0, 37.0),
        _word("300.00", 78.0, 36.0, 85.0, 37.0),
    ]
    cell_data = {
        "1:1": {"left": 10.0, "top": 11.0, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "Assets"},
        "1:2": {"left": 10.0, "top": 19.0, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "Cash 100.00"},
        "1:3": {"left": 10.0, "top": 27.0, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "Savings 200.00"},
        "1:4": {"left": 10.0, "top": 35.0, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "Total 300.00"},
    }
    split = split_single_column_into_label_and_amount(cell_data, words, TABLE_PCT)

    assert split["1:1"]["value"] == "Assets"
    assert split["2:1"]["value"] == ""
    assert not any(cell["colspan"] > 1 for cell in split.values())
    # Every row shares one divider x, so the line is unbroken top to bottom.
    assert len({round(cell["left"], 6) for cell in split.values()}) == 2


def test_amount_divider_is_stable_when_label_lengths_differ():
    """Same amount column, different longest label: the divider must not move."""
    amounts = [
        _word("196,137.31", 76.0, 20.0, 85.0, 21.0),
        _word("4,655.04", 78.0, 28.0, 85.0, 29.0),
        _word("200,792.35", 76.0, 36.0, 85.0, 37.0),
    ]
    short_labels = [_word("Cash", 12.0, 20.0, 22.0, 21.0)]
    long_labels = [_word("1400 Loan Receivable - J. Evans Acquisitions", 12.0, 20.0, 60.0, 21.0)]

    short = _single_column_divider(short_labels + amounts, TABLE_PCT)
    long = _single_column_divider(long_labels + amounts, TABLE_PCT)

    assert short is not None and long is not None
    assert abs(short - long) < 1e-6
    for word in short_labels + long_labels + amounts:
        assert not (word["left"] < short < word["right"])


def test_amount_divider_ignores_leading_account_number_cluster():
    """Account numbers look like amounts and cluster left; they must not win the anchor."""
    words = [
        _word("1010", 12.0, 20.0, 16.0, 21.0),
        _word("1020", 12.0, 28.0, 16.0, 29.0),
        _word("1100", 12.0, 36.0, 16.0, 37.0),
        _word("196,137.31", 76.0, 20.0, 85.0, 21.0),
        _word("4,655.04", 78.0, 28.0, 85.0, 29.0),
        _word("200,792.35", 76.0, 36.0, 85.0, 37.0),
    ]

    divider = _single_column_divider(words, TABLE_PCT)

    assert divider is not None
    assert divider > 16.0, "divider must be left of the amounts, not of the account numbers"
    assert divider < 76.0
    for word in words:
        assert not (word["left"] < divider < word["right"])


def test_amount_divider_clears_a_header_wider_than_its_figures():
    """'As of / Mar 2024' over '106,352': the line goes left of the header, not against it."""
    words = [
        _word("Prepaid expenses", 12.0, 20.0, 48.0, 21.0),
        _word("As of", 65.0, 11.0, 67.0, 12.0),
        _word("Mar", 66.9, 13.0, 68.45, 14.0),
        _word("106,352", 68.8, 20.0, 76.0, 21.0),
        _word("1,478", 71.0, 28.0, 76.0, 29.0),
        _word("115,947", 68.8, 36.0, 76.0, 37.0),
    ]

    divider = _single_column_divider(words, TABLE_PCT)

    assert divider is not None
    assert divider < 65.0, "divider must clear the header, not sit between it and the figures"
    assert divider > 48.0, "and must stay right of the label text"
    for word in words:
        assert abs(divider - word["left"]) > 0.1 and abs(divider - word["right"]) > 0.1


def test_amount_divider_yields_to_a_label_that_reaches_the_numbers():
    amounts = [
        _word("196,137.31", 76.0, 20.0, 85.0, 21.0),
        _word("4,655.04", 78.0, 28.0, 85.0, 29.0),
        _word("200,792.35", 76.0, 36.0, 85.0, 37.0),
    ]
    intruding = _word("A very long account description indeed", 12.0, 44.0, 75.9, 45.0)

    divider = _single_column_divider([intruding] + amounts, TABLE_PCT)

    assert divider is not None
    # Squeezed into the sliver between the label and the numbers rather than cutting either.
    assert intruding["right"] <= divider <= min(w["left"] for w in amounts)
    for word in [intruding] + amounts:
        assert not (word["left"] < divider < word["right"])


def test_single_column_stays_unsplit_without_an_amount_anchor():
    """Better one honest column than a whitespace guess that moves between pages."""
    words = [
        _word("Notes to the statements", 12.0, 20.0, 45.0, 21.0),
        _word("Prepared by management", 12.0, 28.0, 46.0, 29.0),
    ]
    cell_data = {
        "1:1": {"left": 10.0, "top": 19.0, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "Notes to the statements"},
        "1:2": {"left": 10.0, "top": 27.0, "width": 80.0, "height": 5.0, "colspan": 1, "rowspan": 1, "value": "Prepared by management"},
    }

    assert split_single_column_into_label_and_amount(cell_data, words, TABLE_PCT) == cell_data


def test_grid_reports_no_columns_rather_than_guessing():
    """With no column anchor the grid stands down so native geometry can take over."""
    converted = _converted(
        num_rows=1,
        num_cols=3,
        cells=[ConvertedCell(row=0, col=c, value=f"c{c}") for c in range(3)],
    )
    words = [_word("Narrative text only", 12.0, 20.0, 45.0, 21.0)]

    grid = build_grid(converted, {}, words, TABLE_PCT)

    assert grid.cell_data == {}
    assert grid.diagnostics["column_source"] == "none"
    assert not validate_grid(grid.cell_data)["valid"]


def test_cell_data_from_dividers_clamps_spans_to_grid():
    cells = [ConvertedCell(row=0, col=0, value="Wide", rowspan=9, colspan=9)]
    converted = _converted(num_rows=1, num_cols=1, cells=cells)
    cell_data = cell_data_from_dividers(converted, [10.0, 20.0], [10.0, 90.0])

    assert cell_data["1:1"]["rowspan"] == 1
    assert cell_data["1:1"]["colspan"] == 1
    assert cell_data["1:1"]["height"] == 10.0
