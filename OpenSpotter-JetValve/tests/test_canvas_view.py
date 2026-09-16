from views.canvas_view import CanvasView


def test_r2r_progress_maps_nonfinal_row_to_first_display_row():
    keys = {
        CanvasView._spot_key(0, 3, 0, 20.0, 23.0, 0),
        CanvasView._spot_key(0, 3, 1, 21.0, 23.0, 0),
    }

    state = CanvasView._r2r_progress_by_grid(keys, {0: 10})[0]

    assert state["current_row_display"] == 4
    assert state["display_rows"] == [3, 4]
    assert state["finished_cols_by_row"][3] == {0, 1}
    assert 4 not in state["finished_cols_by_row"]


def test_r2r_progress_maps_final_row_to_second_display_row_and_keeps_first_finished():
    keys = {
        CanvasView._spot_key(0, 8, 0, 20.0, 28.0, 0),
        CanvasView._spot_key(0, 8, 1, 21.0, 28.0, 0),
        CanvasView._spot_key(0, 9, 0, 20.0, 29.0, 0),
    }

    state = CanvasView._r2r_progress_by_grid(keys, {0: 10})[0]

    assert state["current_row_display"] == 10
    assert state["display_rows"] == [8, 9]
    assert state["finished_cols_by_row"][8] == {0, 1}
    assert state["finished_cols_by_row"][9] == {0}
