import etf_rotation_v4_1_strategy as module


def test_trailing_peak_resets_on_each_new_position():
    state = module.build_trailing_stop_state(entry_price=100.0)
    state = module.update_trailing_stop_state(state, close_price=130.0)

    state = module.build_trailing_stop_state(entry_price=80.0)

    assert state["entry_price"] == 80.0
    assert state["trailing_peak"] == 80.0
    assert state["stop_triggered"] is False


def test_update_trailing_stop_state_triggers_from_peak_drawdown():
    state = module.build_trailing_stop_state(entry_price=100.0)
    state = module.update_trailing_stop_state(state, close_price=130.0, stop_loss_pct=0.10)

    state = module.update_trailing_stop_state(state, close_price=116.0, stop_loss_pct=0.10)

    assert state["trailing_peak"] == 130.0
    assert round(state["peak_drawdown"], 6) == round(116.0 / 130.0 - 1.0, 6)
    assert state["stop_triggered"] is True

