from table_recognition_mineru.geometry_diagnostics import verify_grid_against_page_ocr


def _word(text, left, top, right, bottom):
    return {"ocr_text": text, "left": left, "top": top, "right": right, "bottom": bottom}


def _two_row_grid():
    """Rows spanning y 10-20 and 20-30, split into two columns at x=50."""
    return {
        "0": {"left": 10.0, "top": 10.0, "width": 40.0, "height": 10.0, "row": 0, "col": 0},
        "1": {"left": 50.0, "top": 10.0, "width": 40.0, "height": 10.0, "row": 0, "col": 1},
        "2": {"left": 10.0, "top": 20.0, "width": 40.0, "height": 10.0, "row": 1, "col": 0},
        "3": {"left": 50.0, "top": 20.0, "width": 40.0, "height": 10.0, "row": 1, "col": 1},
    }


def test_clean_grid_reports_clean():
    words = [
        _word("Cash", 12.0, 13.0, 25.0, 17.0),
        _word("Total", 12.0, 23.0, 25.0, 27.0),
    ]
    report = verify_grid_against_page_ocr(_two_row_grid(), words)
    assert report["clean"]
    assert report["horizontal_cuts"] == []
    assert report["vertical_cuts"] == []


def test_horizontal_edge_through_text_is_reported():
    words = [_word("Cash", 12.0, 18.0, 25.0, 22.0)]  # straddles the y=20 divider
    report = verify_grid_against_page_ocr(_two_row_grid(), words)
    assert not report["clean"]
    assert [cut["position"] for cut in report["horizontal_cuts"]] == [20.0]
    assert report["horizontal_cuts"][0]["words"] == ["Cash"]


def test_vertical_edge_through_text_is_reported():
    words = [_word("Description", 45.0, 13.0, 55.0, 17.0)]  # straddles the x=50 divider
    report = verify_grid_against_page_ocr(_two_row_grid(), words)
    assert not report["clean"]
    assert [cut["position"] for cut in report["vertical_cuts"]] == [50.0]


def test_word_outside_edge_span_is_not_counted():
    """A word level with a divider but horizontally clear of it is not a crossing."""
    words = [_word("Footnote", 92.0, 18.0, 99.0, 22.0)]
    report = verify_grid_against_page_ocr(_two_row_grid(), words)
    assert report["clean"]


def test_edge_against_box_padding_is_a_graze_not_a_cut():
    """OCR boxes are padded well past the glyphs, so touching one is not cutting text."""
    words = [_word("Cash", 12.0, 13.0, 25.0, 19.995)]
    report = verify_grid_against_page_ocr(_two_row_grid(), words)
    assert report["clean"]
    assert report["horizontal_cuts"] == []
    assert [graze["position"] for graze in report["horizontal_grazes"]] == [20.0]


def test_edge_well_inside_a_box_still_cuts():
    """Padding tolerance must not excuse a line through the middle of the word."""
    words = [_word("Cash", 12.0, 16.0, 25.0, 24.0)]
    report = verify_grid_against_page_ocr(_two_row_grid(), words)
    assert not report["clean"]
    assert [cut["position"] for cut in report["horizontal_cuts"]] == [20.0]


def test_clearance_is_configurable():
    words = [_word("Cash", 12.0, 13.0, 25.0, 19.995)]
    report = verify_grid_against_page_ocr(_two_row_grid(), words, clearance=0.0)
    assert report["clean"]
    assert report["horizontal_grazes"] == []
