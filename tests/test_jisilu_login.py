import requests

import jisilu_login as jl


class FakeResponse:
    def __init__(self, payload, cookies=None):
        self._payload = payload
        self.cookies = cookies or requests.cookies.RequestsCookieJar()

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.cookies = requests.cookies.RequestsCookieJar()
        self.closed = False
        self.calls = []

    def post(self, url, headers=None, data=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "data": data,
                "timeout": timeout,
            }
        )
        return self.response

    def close(self):
        self.closed = True


class FakeGetResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeGetSession:
    def __init__(self, response):
        self.response = response
        self.cookies = requests.cookies.RequestsCookieJar()
        self.closed = False
        self.calls = []

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


def test_jslencode_returns_expected_hex():
    assert jl.jslencode("test") == "166f0e14ec865b270ef3644d44dc5a7f"


def test_build_cookie_string_joins_cookie_pairs():
    jar = requests.cookies.RequestsCookieJar()
    jar.set("kbz__user_login", "token1")
    jar.set("kbzw__Session", "token2")

    assert jl.build_cookie_string(jar) == "kbz__user_login=token1; kbzw__Session=token2"


def test_login_jisilu_returns_cookie_string_on_success(monkeypatch):
    response_cookies = requests.cookies.RequestsCookieJar()
    response_cookies.set("kbz__user_login", "token1")
    response_cookies.set("kbzw__Session", "token2")
    fake_response = FakeResponse({"code": 200}, response_cookies)
    fake_session = FakeSession(fake_response)

    monkeypatch.setattr(jl, "jslencode", lambda value: f"enc-{value}")

    cookie = jl.login_jisilu("demo_user", "demo_pass", session=fake_session)

    assert cookie == "kbz__user_login=token1; kbzw__Session=token2"
    assert fake_session.calls[0]["url"] == jl.LOGIN_URL
    assert fake_session.calls[0]["data"]["user_name"] == "enc-demo_user"
    assert fake_session.calls[0]["data"]["password"] == "enc-demo_pass"
    assert fake_session.closed is False


def test_login_jisilu_returns_empty_string_when_credentials_missing():
    assert jl.login_jisilu("", "") == ""


def test_build_etf_list_params_formats_timestamp(monkeypatch):
    monkeypatch.setattr(jl.time, "time", lambda: 1774341889.785)

    assert jl.build_etf_list_params() == {
        "___jsl": "LST___t=1774341889785",
        "volume": "",
        "unit_total": "25",
        "rp": "25",
    }


def test_apply_cookie_string_sets_session_cookies():
    session = requests.Session()

    jl.apply_cookie_string(session, "kbzw__Session=abc123; kbzw__user_login=xyz456")

    assert session.cookies.get("kbzw__Session") == "abc123"
    assert session.cookies.get("kbzw__user_login") == "xyz456"


def test_fetch_etf_list_uses_cookie_and_returns_json(monkeypatch):
    fake_session = FakeGetSession(FakeGetResponse({"rows": [{"id": "159001"}]}))
    monkeypatch.setattr(jl, "build_etf_list_params", lambda: {"___jsl": "LST___t=1", "rp": "25"})

    result = jl.fetch_etf_list(
        "kbzw__Session=abc123; kbzw__user_login=xyz456",
        session=fake_session,
    )

    assert result == {"rows": [{"id": "159001"}]}
    assert fake_session.calls[0]["url"] == jl.ETF_LIST_URL
    assert fake_session.calls[0]["headers"] == jl.ETF_LIST_HEADERS
    assert fake_session.calls[0]["params"] == {"___jsl": "LST___t=1", "rp": "25"}
    assert fake_session.cookies.get("kbzw__Session") == "abc123"
    assert fake_session.cookies.get("kbzw__user_login") == "xyz456"
    assert fake_session.closed is False
