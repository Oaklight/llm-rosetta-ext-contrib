"""The Antigravity quota probe reads the CLI's ``/usage`` payload."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from llm_rosetta.contracts.quota import QuotaProbeError

from llm_rosetta_shim_contrib.providers.antigravity.quota import (
    PROBES,
    AntigravityUsageProbe,
)

# A real ``agy -p "/usage" --output-format json`` reply, shortened to the
# fields the probe reads.
USAGE = {
    "conversation_id": "",
    "status": "SUCCESS",
    "response": "",
    "command": {
        "name": "usage",
        "data": {
            "groups": [
                {
                    "name": "Gemini Models",
                    "buckets": [
                        {
                            "id": "gemini-weekly",
                            "name": "Weekly Limit Remaining",
                            "window": "weekly",
                            "remaining_fraction": 0.99,
                            "reset_time": "2026-11-30T20:13:39Z",
                        },
                        {
                            "id": "gemini-5h",
                            "name": "Five Hour Limit Remaining",
                            "window": "5h",
                            "remaining_fraction": 0.986,
                            "reset_time": "2026-11-24T01:13:39Z",
                        },
                    ],
                },
                {
                    "name": "Claude and GPT models",
                    "buckets": [
                        {
                            "id": "3p-weekly",
                            "name": "Weekly Limit Remaining",
                            "window": "weekly",
                            "remaining_fraction": 1,
                            "reset_time": "2026-11-30T23:06:05Z",
                        },
                        {
                            "id": "3p-5h",
                            "name": "Five Hour Limit Remaining",
                            "window": "5h",
                            "remaining_fraction": 1,
                            "reset_time": "2026-11-24T04:06:05Z",
                        },
                    ],
                },
            ]
        },
    },
}


class TestAntigravityUsageProbe:
    probe = AntigravityUsageProbe()

    def test_the_module_exports_the_probe(self):
        assert [probe.id for probe in PROBES] == ["antigravity_usage"]

    def test_the_lane_has_no_http_usage_endpoint(self):
        assert self.probe.match("http://agy.local") == ""
        assert self.probe.default_url is None
        assert self.probe.headers("any-key") == {}
        assert self.probe.inband(429, {}) is None

    def test_an_http_read_is_refused(self):
        with pytest.raises(QuotaProbeError, match="own CLI"):
            self.probe.parse({"groups": []})

    def test_remains_are_turned_into_used_percent(self):
        plan, windows = self.probe.parse_local(USAGE)

        assert plan is None
        assert [window.name for window in windows] == [
            "Gemini Models — 7 days",
            "Gemini Models — 5 hours",
            "Claude and GPT models — 7 days",
            "Claude and GPT models — 5 hours",
        ]
        assert windows[0].used_percent == pytest.approx(1.0)
        assert windows[1].used_percent == pytest.approx(1.4, abs=0.01)
        assert windows[2].used_percent == pytest.approx(0.0)
        assert windows[0].span_seconds == 7 * 24 * 3600
        assert windows[1].span_seconds == 5 * 3600
        assert windows[0].resets_at == datetime(
            2026, 11, 30, 20, 13, 39, tzinfo=timezone.utc
        )
        assert all(window.status == "ok" for window in windows)

    def test_a_bare_groups_payload_is_accepted(self):
        _, windows = self.probe.parse_local(USAGE["command"]["data"])

        assert len(windows) == 4

    def test_a_disabled_bucket_is_skipped(self):
        payload = {
            "groups": [
                {
                    "name": "Gemini Models",
                    "buckets": [
                        {"window": "weekly", "remaining_fraction": 0.5},
                        {
                            "window": "5h",
                            "remaining_fraction": 0.5,
                            "disabled": True,
                        },
                    ],
                }
            ]
        }

        _, windows = self.probe.parse_local(payload)

        assert [window.name for window in windows] == ["Gemini Models — 7 days"]

    def test_a_bucket_without_a_share_is_skipped(self):
        payload = {
            "groups": [
                {
                    "name": "Gemini Models",
                    "buckets": [{"window": "weekly"}, {"window": "5h"}],
                }
            ]
        }

        with pytest.raises(QuotaProbeError, match="no allowance window"):
            self.probe.parse_local(payload)

    def test_a_failed_command_is_explained(self):
        payload = {"status": "FAILED", "response": "Not logged in"}

        with pytest.raises(QuotaProbeError, match="Not logged in"):
            self.probe.parse_local(payload)

    @pytest.mark.parametrize(
        ("body", "name"),
        [("not json at all", "str"), ([1, 2], "list"), (None, "NoneType")],
    )
    def test_a_non_object_payload_names_its_type(self, body, name):
        with pytest.raises(QuotaProbeError, match=f"printed a {name}"):
            self.probe.parse_local(body)

    def test_an_unknown_window_key_still_reports_the_group(self):
        payload = {
            "groups": [
                {
                    "name": "Gemini Models",
                    "buckets": [{"window": "monthly", "remaining_fraction": 0.5}],
                }
            ]
        }

        _, windows = self.probe.parse_local(payload)

        assert [window.name for window in windows] == ["Gemini Models — monthly"]
        assert windows[0].span_seconds is None
