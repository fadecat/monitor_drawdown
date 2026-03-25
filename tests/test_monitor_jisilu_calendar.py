from datetime import datetime
from pathlib import Path
from uuid import uuid4

import monitor_jisilu_calendar as mjc


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = False

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
            }
        )
        return self.response

    def close(self):
        self.closed = True


def test_load_calendar_rules_returns_list():
    config_dir = Path(".test_artifacts") / f"calendar-{uuid4().hex}"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "calendar_monitors:",
                '  - name: "下修股东会提醒"',
                '    qtype: "CNV"',
                '    window: "next_month"',
                '    webhook_env: "CALENDAR_WEBHOOK_URL"',
                "    title_keywords:",
                '      - "下修股东会"',
            ]
        ),
        encoding="utf-8",
    )

    rules = mjc.load_calendar_rules(str(config_path))

    assert len(rules) == 1
    assert rules[0]["webhook_env"] == "CALENDAR_WEBHOOK_URL"


def test_build_calendar_request_params_uses_next_month_window_by_default():
    current_time = datetime(2026, 3, 25, 15, 30, tzinfo=mjc.BEIJING_TZ)

    params = mjc.build_calendar_request_params("CNV", 45, current_time=current_time)

    assert params["qtype"] == "CNV"
    assert params["start"] == str(int(datetime(2026, 4, 1, 0, 0, tzinfo=mjc.BEIJING_TZ).timestamp()))
    assert params["end"] == str(int(datetime(2026, 5, 1, 0, 0, tzinfo=mjc.BEIJING_TZ).timestamp()))
    assert params["_"] == str(int(current_time.timestamp() * 1000))


def test_build_calendar_time_window_supports_lookahead_mode():
    start_dt, end_dt = mjc.build_calendar_time_window(
        window="current_to_lookahead",
        lookahead_days=10,
        current_time=datetime(2026, 3, 25, 15, 30, tzinfo=mjc.BEIJING_TZ),
    )

    assert start_dt == datetime(2026, 3, 25, 0, 0, tzinfo=mjc.BEIJING_TZ)
    assert end_dt == datetime(2026, 4, 4, 0, 0, tzinfo=mjc.BEIJING_TZ)


def test_extract_event_records_supports_nested_payload():
    payload = {
        "code": 1,
        "data": {
            "calendar": [
                {"title": "A"},
                {"title": "B"},
            ]
        },
    }

    records = mjc.extract_event_records(payload)

    assert [item["title"] for item in records] == ["A", "B"]


def test_filter_events_by_keywords_dedupes_same_title_and_time():
    events = [
        {"title": "美联转债下修股东会", "event_time": datetime(2026, 3, 30, tzinfo=mjc.BEIJING_TZ)},
        {"title": "美联转债下修股东会", "event_time": datetime(2026, 3, 30, tzinfo=mjc.BEIJING_TZ)},
        {"title": "普通公告", "event_time": datetime(2026, 3, 31, tzinfo=mjc.BEIJING_TZ)},
    ]

    matched = mjc.filter_events_by_keywords(events, ["下修股东会"])

    assert len(matched) == 1
    assert matched[0]["title"] == "美联转债下修股东会"


def test_fetch_calendar_events_normalizes_title_and_date():
    session = FakeSession(
        FakeResponse(
            [
                {
                    "id": "CNV51726",
                    "code": "113699",
                    "title": "美联转债下修股东会",
                    "start": "2026-04-10",
                    "description": "转债代码:113699",
                    "url": "/data/convert_bond_detail/113699",
                },
                {"title": "普通事项", "start": "1774800000"},
            ]
        )
    )

    events = mjc.fetch_calendar_events(
        "CNV",
        45,
        window="next_month",
        current_time=datetime(2026, 3, 25, 15, 30, tzinfo=mjc.BEIJING_TZ),
        session=session,
    )

    assert len(events) == 2
    assert events[0]["title"] == "美联转债下修股东会"
    assert events[0]["code"] == "113699"
    assert events[0]["url"] == "/data/convert_bond_detail/113699"
    assert events[0]["event_time"].strftime("%Y-%m-%d") == "2026-04-10"
    assert session.calls[0]["url"] == mjc.CALENDAR_URL
    assert session.calls[0]["params"]["start"] == str(int(datetime(2026, 4, 1, 0, 0, tzinfo=mjc.BEIJING_TZ).timestamp()))
    assert session.calls[0]["params"]["end"] == str(int(datetime(2026, 5, 1, 0, 0, tzinfo=mjc.BEIJING_TZ).timestamp()))
    assert session.closed is False


def test_build_calendar_webhook_payload_contains_titles():
    payload = mjc.build_calendar_webhook_payload(
        "下修股东会提醒",
        [
            {
                "title": "美联转债下修股东会",
                "code": "113699",
                "event_time": datetime(2026, 3, 30, tzinfo=mjc.BEIJING_TZ),
            }
        ],
        current_time=datetime(2026, 3, 25, 15, 30, tzinfo=mjc.BEIJING_TZ),
    )

    assert payload["msgtype"] == "markdown"
    assert "下修股东会提醒" in payload["markdown"]["content"]
    assert "美联转债下修股东会" in payload["markdown"]["content"]
    assert "113699" in payload["markdown"]["content"]
