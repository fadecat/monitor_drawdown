import cb_index_history as module


def test_parse_jisilu_page_extracts_date_and_data_variables():
    body = """
    <script>
    var __date = ['2026-05-28','2026-05-29'];
    var __data = {
      'price':[4880.1,4892.121],
      'avg_price':[161.5,162.102],
      'temperature':[78.5,79.08],
      'idx_price':[4010.5,4030.8]
    };
    </script>
    """

    records = module.parse_jisilu_page(body)

    assert records == [
        {
            "date": "2026-05-28",
            "index_value": "4880.1",
            "avg_price": "161.5",
            "temperature": "78.5",
            "idx_price": "4010.5",
        },
        {
            "date": "2026-05-29",
            "index_value": "4892.121",
            "avg_price": "162.102",
            "temperature": "79.08",
            "idx_price": "4030.8",
        },
    ]


def test_parse_jisilu_page_raises_clear_error_when_date_missing():
    body = """
    <script>
    var __data = {'price':[4892.121]};
    </script>
    """

    try:
        module.parse_jisilu_page(body)
    except RuntimeError as error:
        assert str(error) == "missing var __date"
    else:
        raise AssertionError("expected RuntimeError")


def test_merge_records_updates_same_date_and_preserves_old_fields():
    history = [
        {"date": "2026-05-28", "index_value": "4875.0", "legacy_only": "keep"},
        {"date": "2026-05-29", "index_value": "4888.0", "avg_price": "160.0"},
    ]
    live = [
        {"date": "2026-05-29", "index_value": "4892.121", "temperature": "79.08"},
        {"date": "2026-05-30", "index_value": "4900.000", "temperature": "80.00"},
    ]

    merged, stats = module.merge_records(history, live)

    assert merged == [
        {"date": "2026-05-28", "index_value": "4875.0", "legacy_only": "keep"},
        {"date": "2026-05-29", "index_value": "4892.121", "avg_price": "160.0", "temperature": "79.08"},
        {"date": "2026-05-30", "index_value": "4900.000", "temperature": "80.00"},
    ]
    assert stats == {"history": 2, "updated": 1, "added": 1}


def test_merge_records_raises_clear_error_when_live_record_date_missing():
    history = [{"date": "2026-05-28", "index_value": "4875.0"}]
    live = [{"index_value": "4892.121"}]

    try:
        module.merge_records(history, live)
    except ValueError as error:
        assert str(error) == "live record missing date"
    else:
        raise AssertionError("expected ValueError")
