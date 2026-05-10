from src.backend.services.extractor import _node_id
from src.backend.services.parser import _is_skip_meta, _norm


def test_norm_collapses_whitespace_and_fullwidth_space() -> None:
    assert _norm("  第一章　绪论\r\n  第一节  ") == "第一章 绪论 第一节"


def test_is_skip_meta_detects_short_front_matter() -> None:
    assert _is_skip_meta("目录")
    assert _is_skip_meta("前言")
    assert not _is_skip_meta("第一章 细胞和组织的适应与损伤")


def test_node_id_is_stable_for_same_concept() -> None:
    first = _node_id("book1", "ch1", "炎症")
    second = _node_id("book1", "ch1", "炎症")
    other = _node_id("book1", "ch1", "发热")

    assert first == second
    assert first != other
    assert first.startswith("book1_ch1_")
