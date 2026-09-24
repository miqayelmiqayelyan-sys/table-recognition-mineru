import pytest

from table_recognition_mineru.table_extractor import MinerUTableBlock, _refine_table_bbox


def test_refine_table_bbox_pushes_top_below_title():
    block = MinerUTableBlock(
        index=0,
        page_idx=0,
        bbox_norm=[93.0, 109.0, 861.0, 638.0],
        table_body_html="<table></table>",
    )
    content_list = [
        {
            "type": "text",
            "page_idx": 0,
            "bbox": [297, 66, 656, 113],
            "text": "AVIAGAMES INC ... IN THOUSANDS USD",
        },
        {
            "type": "table",
            "page_idx": 0,
            "bbox": [93, 109, 861, 638],
        },
    ]
    refined = _refine_table_bbox(block, content_list, middle={})
    assert refined.bbox_norm[1] == 113.0
    assert refined.bbox_norm[1] > 109.0


def test_refine_table_bbox_pushes_top_below_table_caption_in_preproc_blocks():
    block = MinerUTableBlock(
        index=1,
        page_idx=0,
        bbox_norm=[93.0, 694.0, 861.0, 931.0],
        table_body_html="<table></table>",
    )
    middle = {
        "pdf_info": [
            {
                "page_idx": 0,
                "page_size": [612, 792],
                "preproc_blocks": [
                    {
                        "type": "table",
                        "bbox": [57, 550, 527, 738],
                        "blocks": [
                            {
                                "type": "table_caption",
                                "bbox": [160, 517, 424, 552],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    refined = _refine_table_bbox(block, [], middle)
    assert refined.bbox_norm[1] == pytest.approx(697.0, abs=0.1)
    assert refined.bbox_norm[1] > 694.0
