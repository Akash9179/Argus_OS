"""The install verification's sovereignty verdict, as a test.

This decision was implemented wrong three times before it was pulled into
a pure function. Each version consulted something in the verifier's own
process rather than the running service's report, and each passed
everywhere, including where it should have failed. A check that cannot
fail is worse than no check, because it is reported as evidence.

So these tests do two jobs. They pin the decision to the service's report
and nothing else, and they prove, case by case, that the check fails: on a
deployment that carries something that leaves the machine, on one that
cannot say, on a service too old to say, and on a profile whose policy
permits cloud. If someone rewrites the verdict and every one of these
still passes, the rewrite kept the property that took three attempts to
get: falsifiability.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "verify_install",
    Path(__file__).resolve().parent.parent / "scripts" / "verify_install.py",
)
verify_install = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify_install)

sovereignty_verdicts = verify_install.sovereignty_verdicts
PASS, FAIL, SKIP = verify_install.PASS, verify_install.FAIL, verify_install.SKIP


def a_report(**overrides) -> dict:
    """A clean deployed report, the one shape that should fully pass."""
    report = {
        "profile": "deployed",
        "allows_cloud": False,
        "anything_leaves_the_machine": False,
    }
    report.update(overrides)
    return report


def statuses(report) -> dict[str, str]:
    return {name: status for name, status, _ in sovereignty_verdicts(report)}


def test_a_clean_deployed_report_passes_and_nothing_else_does():
    verdicts = statuses(a_report())
    assert FAIL not in verdicts.values()
    assert verdicts["The running deployment carries nothing that leaves the machine"] == PASS


def test_the_check_fails_when_the_service_says_something_leaves():
    """The reason this function exists. A deployment carrying a cloud
    adapter must fail even though the gateway would refuse it at runtime:
    carried is one configuration edit from allowed."""
    verdicts = statuses(a_report(anything_leaves_the_machine=True))
    assert verdicts["The running deployment carries nothing that leaves the machine"] == FAIL


def test_the_check_fails_when_the_service_cannot_say():
    """None means an adapter never got built and might have left the
    machine. An unverifiable sovereignty claim is not a satisfied one."""
    verdicts = statuses(a_report(anything_leaves_the_machine=None))
    assert verdicts["The running deployment carries nothing that leaves the machine"] == FAIL


def test_the_check_fails_when_the_service_is_too_old_to_say():
    """A missing field is not a pass. The first version of this check
    passed on a field the report never carried, which is precisely the
    mistake this case exists to make impossible."""
    report = a_report()
    del report["anything_leaves_the_machine"]
    verdicts = statuses(report)
    assert verdicts["The running deployment carries nothing that leaves the machine"] == FAIL


def test_the_check_fails_when_the_deployed_policy_permits_cloud():
    verdicts = statuses(a_report(allows_cloud=True))
    assert verdicts["The deployed profile forbids cloud"] == FAIL


def test_a_bench_profile_is_named_and_makes_no_sovereignty_claim():
    """A bench box is not failed, and it is not blessed either: the
    carries-nothing verdict simply is not made for it."""
    verdicts = statuses(a_report(profile="dev", allows_cloud=True))
    assert FAIL not in verdicts.values()
    assert not any("carries nothing" in name for name in verdicts)


def test_no_running_service_means_no_verdict_at_all():
    """SKIP, never PASS. Without the service there is no deployment to
    speak for, and building a gateway locally to speak for it is the
    third of the three mistakes."""
    verdicts = sovereignty_verdicts(None)
    assert [status for _, status, _ in verdicts] == [SKIP]


def test_a_service_that_hides_its_profile_is_a_failure_not_an_absence():
    verdicts = statuses({"can_hear": True})
    assert list(verdicts.values()) == [FAIL]


def test_the_verdict_reads_only_the_report_it_is_given(monkeypatch):
    """The decision must not look at this process's environment. Set the
    variables that misled the previous version and confirm the verdict on
    an adverse report is still adverse."""
    monkeypatch.setenv("ARGUS_AI_PROFILE", "deployed")
    monkeypatch.setenv("ARGUS_LOCAL_LLM", "http://127.0.0.1:11434/v1")
    verdicts = statuses(a_report(anything_leaves_the_machine=True))
    assert verdicts["The running deployment carries nothing that leaves the machine"] == FAIL


def test_the_verdict_names_only_facts_never_adapters():
    """Law 3 and the waterline: the verdict text may state the fact that
    something leaves, never which provider it is."""
    for report in (
        a_report(),
        a_report(anything_leaves_the_machine=True),
        a_report(anything_leaves_the_machine=None),
    ):
        for _, _, detail in sovereignty_verdicts(report):
            for word in ("anthropic", "openai", "mistral", "llama", "whisper", "piper"):
                assert word not in detail.lower()


def test_a_bench_profile_fails_a_handover_run():
    """The delta audit's warning: same failure shape as the skipped-check
    hole, one step earlier. An install script gating on --handover exit
    code alone must be stopped by the code when the target permits cloud,
    not by prose it never reads."""
    verdicts = {
        name: status
        for name, status, _ in sovereignty_verdicts(
            a_report(profile="dev", allows_cloud=True), handover=True
        )
    }
    assert verdicts["This deployment is on a bench profile"] == FAIL

    # And the same report on an ordinary run stays a named, passing fact.
    ordinary = {
        name: status
        for name, status, _ in sovereignty_verdicts(
            a_report(profile="dev", allows_cloud=True)
        )
    }
    assert ordinary["This deployment is on a bench profile"] == PASS


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
