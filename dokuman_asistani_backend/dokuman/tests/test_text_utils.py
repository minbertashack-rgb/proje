from dokuman.services.text_utils import build_newline_indices, char_to_line_col


def test_build_newline_indices_collects_all_newline_offsets():
    text = "ilk satir\nikinci satir\nucuncu satir"

    assert build_newline_indices(text) == [9, 22]


def test_char_to_line_col_maps_offsets_across_lines_in_log_time_helper():
    text = "alpha\nbeta\ngamma"
    newline_indices = build_newline_indices(text)

    assert char_to_line_col(-3, newline_indices) == (1, 1)
    assert char_to_line_col(0, newline_indices) == (1, 1)
    assert char_to_line_col(5, newline_indices) == (1, 6)
    assert char_to_line_col(6, newline_indices) == (2, 1)
    assert char_to_line_col(10, newline_indices) == (2, 5)
    assert char_to_line_col(11, newline_indices) == (3, 1)
    assert char_to_line_col(len(text) - 1, newline_indices) == (3, 5)


def test_char_to_line_col_handles_single_line_text_without_indices():
    assert char_to_line_col(4, []) == (1, 5)
