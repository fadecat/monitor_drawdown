from pathlib import Path


def test_etf_rotation_v2_email_workflow_installs_chart_dependencies():
    workflow = Path(".github/workflows/etf_rotation_v2_email.yml").read_text(encoding="utf-8")

    assert "fonts-noto-cjk" in workflow
    assert "matplotlib" in workflow
