from pathlib import Path

import local_env


def test_parse_env_file_supports_comments_quotes_and_export(tmp_path):
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "JISILU_USERNAME=demo_user",
                "JISILU_PASSWORD='demo_pass'",
                'CONFIG_PATH="./config.yaml"',
                "export WEBHOOK_URL=https://example.invalid/hook",
            ]
        ),
        encoding="utf-8",
    )

    values = local_env.parse_env_file(env_path)

    assert values == {
        "JISILU_USERNAME": "demo_user",
        "JISILU_PASSWORD": "demo_pass",
        "CONFIG_PATH": "./config.yaml",
        "WEBHOOK_URL": "https://example.invalid/hook",
    }


def test_get_env_value_prefers_process_env(monkeypatch):
    monkeypatch.setenv("JISILU_USERNAME", "from_env")

    value = local_env.get_env_value("JISILU_USERNAME", {"JISILU_USERNAME": "from_file"})

    assert value == "from_env"
