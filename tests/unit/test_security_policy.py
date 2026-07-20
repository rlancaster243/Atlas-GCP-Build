"""Sprint 7 Phase 8: security-policy scanner regression tests."""

from __future__ import annotations

from atlas.governance import security_policy as sp


def test_live_managed_iam_is_clean() -> None:
    assert sp.scan_managed_iam() == []


def test_live_data_exposure_is_clean() -> None:
    # Governed Atlas artifacts must never commit secret-like values.
    assert sp.scan_data_exposure() == []


def test_scan_text_flags_private_key() -> None:
    reasons = sp.scan_text("-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END-----")
    assert "private key material" in reasons


def test_scan_text_flags_gcp_api_key() -> None:
    reasons = sp.scan_text("key=AIza" + "A" * 35)
    assert "GCP API key" in reasons


def test_scan_text_flags_service_account_json() -> None:
    assert "service-account JSON" in sp.scan_text('{"type": "service_account"}')


def test_scan_text_flags_slack_webhook() -> None:
    reasons = sp.scan_text("url: https://hooks.slack.com/services/T000/B000/xxxxxxxx")
    assert "Slack webhook URL" in reasons


def test_scan_text_flags_personal_email() -> None:
    assert "personal email address" in sp.scan_text("recipient: someone@gmail.com")


def test_scan_text_allows_variable_references() -> None:
    # Variable references are not secrets and must not be flagged.
    assert sp.scan_text("Authorization: Bearer $token") == []
    assert sp.scan_text("channel: ${NOTIFICATION_CHANNEL}") == []


def test_scan_text_clean_string() -> None:
    assert sp.scan_text("just a normal config line with no secrets") == []
