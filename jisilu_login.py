import binascii
import json
import logging
import os
import time
from typing import Optional

import requests

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
except ImportError:  # pragma: no cover
    AES = None
    pad = None


AES_KEY = "397151C04723421F"
LOGIN_URL = "https://www.jisilu.cn/webapi/account/login_process/"
ETF_LIST_URL = "https://www.jisilu.cn/data/etf/etf_list/"
JISILU_USERNAME = ""
JISILU_PASSWORD = ""
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.jisilu.cn",
    "Referer": "https://www.jisilu.cn/account/login/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}
ETF_LIST_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.jisilu.cn/data/etf/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def jslencode(text: str) -> str:
    """Use the legacy AES-ECB scheme required by the Jisilu login API."""
    if AES is None or pad is None:
        raise RuntimeError("缺少 pycryptodome 依赖，请先执行: pip install pycryptodome")

    key = AES_KEY.encode("utf-8")
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted_bytes = cipher.encrypt(pad(text.encode("utf-8"), AES.block_size))
    return binascii.hexlify(encrypted_bytes).decode("utf-8")


def build_cookie_string(cookies: requests.cookies.RequestsCookieJar) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items())


def build_etf_list_params() -> dict[str, str]:
    timestamp_ms = str(int(time.time() * 1000))
    return {
        "___jsl": f"LST___t={timestamp_ms}",
        "volume": "",
        "unit_total": "25",
        "rp": "25",
    }


def apply_cookie_string(session: requests.Session, cookie_str: str) -> None:
    for cookie_part in cookie_str.split(";"):
        piece = cookie_part.strip()
        if not piece or "=" not in piece:
            continue
        name, value = piece.split("=", 1)
        session.cookies.set(name.strip(), value.strip())


def login_jisilu(
    username: str,
    password: str,
    session: Optional[requests.Session] = None,
) -> str:
    """
    登录集思录并返回 Cookie 字符串。

    Returns:
        登录成功时返回 `key=value; key2=value2` 格式的 Cookie 字符串，失败返回空字符串。
    """
    if not username or not password:
        logger.error("用户名或密码为空，请在 jisilu_login.py 中填写，或设置环境变量。")
        return ""

    encrypted_username = jslencode(username)
    encrypted_password = jslencode(password)
    data = {
        "return_url": "https://www.jisilu.cn/",
        "user_name": encrypted_username,
        "password": encrypted_password,
        "auto_login": "1",
        "aes": "1",
    }

    request_session = session or requests.Session()

    try:
        response = request_session.post(LOGIN_URL, headers=HEADERS, data=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        logger.info("登录响应: %s", result)

        if result.get("code") != 200:
            logger.error("登录失败: %s", result.get("msg", "未知错误"))
            return ""

        cookie_str = build_cookie_string(response.cookies) or build_cookie_string(request_session.cookies)
        if not cookie_str:
            logger.error("登录成功但未获取到 Cookie")
            return ""

        logger.info("登录成功，获取到 Cookie: %s", cookie_str)
        return cookie_str
    except Exception as exc:  # pragma: no cover - requests exception mapping depends on runtime
        logger.exception("登录异常: %s", exc)
        return ""
    finally:
        if session is None:
            request_session.close()


def fetch_etf_list(
    cookie_str: str,
    session: Optional[requests.Session] = None,
) -> dict:
    if not cookie_str:
        logger.error("Cookie 为空，无法请求 ETF 列表。")
        return {}

    request_session = session or requests.Session()
    apply_cookie_string(request_session, cookie_str)

    try:
        response = request_session.get(
            ETF_LIST_URL,
            headers=ETF_LIST_HEADERS,
            params=build_etf_list_params(),
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
        logger.info("ETF 列表请求成功，返回键: %s", list(result.keys()))
        return result
    except Exception as exc:  # pragma: no cover - requests exception mapping depends on runtime
        logger.exception("请求 ETF 列表异常: %s", exc)
        return {}
    finally:
        if session is None:
            request_session.close()


def main() -> int:
    username = os.getenv("JISILU_USERNAME", JISILU_USERNAME).strip()
    password = os.getenv("JISILU_PASSWORD", JISILU_PASSWORD).strip()

    cookie = login_jisilu(username, password)
    if not cookie:
        return 1

    print(cookie)
    etf_data = fetch_etf_list(cookie)
    if not etf_data:
        return 1

    print(json.dumps(etf_data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
