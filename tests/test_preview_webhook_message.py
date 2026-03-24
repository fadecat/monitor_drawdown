import pandas as pd

import monitor_drawdown as md
import preview_webhook_message as pwm


def test_drop_current_day_row_removes_today_only():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-03-23", "2026-03-24", "2026-03-25"]),
            "close": [1.01, 1.02, 1.03],
        }
    )

    trimmed_df, removed_count = pwm.drop_current_day_row(
        df,
        md.datetime(2026, 3, 24, 23, 30, tzinfo=md.BEIJING_TZ),
    )

    assert removed_count == 1
    assert trimmed_df["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-23", "2026-03-25"]


def test_drop_current_day_row_handles_empty_dataframe():
    df = pd.DataFrame(columns=["date", "close"])

    trimmed_df, removed_count = pwm.drop_current_day_row(
        df,
        md.datetime(2026, 3, 24, 23, 30, tzinfo=md.BEIJING_TZ),
    )

    assert removed_count == 0
    assert trimmed_df.empty
