from unittest.mock import MagicMock

from table_recognition_mineru.ocr_utils import extract_table_ocr_words_pct


def test_extract_table_ocr_words_pct_converts_pixels():
    page = MagicMock()
    page.image_width = 2000
    page.image_height = 1000
    page.extract_area_words.return_value = [
        {"ocr_text": "Cash", "left": 200, "top": 300, "right": 400, "bottom": 340},
    ]

    words = extract_table_ocr_words_pct(
        page,
        {"left": 10, "top": 20, "right": 90, "bottom": 80},
    )

    assert len(words) == 1
    assert words[0]["top"] >= 20.0
    assert words[0]["ocr_text"] == "Cash"
    assert words[0]["left"] == 10.0
    assert words[0]["top"] == 30.0
    page.extract_area_words.assert_called_once_with(
        left=200.0,
        right=1800.0,
        top=200.0,
        bottom=800.0,
        threshold=0.3,
    )
