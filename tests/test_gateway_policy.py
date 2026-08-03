"""The sovereignty law, as a test.

All deployment targets are air-gapped. No cloud dependency in any mission
path. Cloud adapters are permitted only in development and demonstration
profiles, never in deployed ones.

That is a claim about what the system does when nobody is looking, so it
is checked here rather than trusted to a configuration file. Two of these
tests would fail if someone added a cloud adapter to the shipped deployed
profile, and one would fail even if the profile were correct but the
gateway had stopped enforcing it.
"""

from __future__ import annotations

import pytest

from gateway.adapters.base import known_adapters
from gateway.capabilities import Capability, CapabilityUnavailable, LanguageRequest
from gateway.policy import DEFAULT_PROFILE, Profile, load_active_profile, load_profiles
from gateway.service import Gateway


class PretendCloud:
    """An adapter that admits it leaves the machine."""

    name = "pretend_cloud"

    def capabilities(self) -> set[Capability]:
        return {Capability.UNDERSTAND_ORDER, Capability.ANSWER_QUESTION}

    @property
    def leaves_the_machine(self) -> bool:
        return True

    def available(self) -> tuple[bool, str]:
        return True, "ready"

    def understand(self, request):  # pragma: no cover - must never be reached
        raise AssertionError("a cloud adapter answered under a deployed profile")


def test_the_shipped_deployed_profile_contains_no_cloud_adapter():
    """The configuration itself, before any code runs.

    Checked against the adapters' own declarations rather than a list of
    provider names, because a rule that recognised clouds by name would
    pass the day someone added a provider it had never heard of.
    """
    deployed = load_profiles()["deployed"]
    assert deployed.allows_cloud is False

    registry = known_adapters()
    for capability, names in deployed.adapters.items():
        assert names, f"deployed has no adapter for {capability}"
        for name in names:
            factory = registry.get(name)
            assert factory is not None, f"deployed names an adapter that does not exist: {name}"
            assert not factory().leaves_the_machine, (
                f"the deployed profile lists {name}, which leaves the machine"
            )


def test_a_deployed_profile_refuses_a_cloud_adapter_even_if_one_is_listed():
    """The enforcement, not the configuration.

    This is the case that matters: someone edits a profile, lists a cloud
    adapter under `deployed`, and nothing in the YAML stops them. The
    gateway does.
    """
    profile = Profile(
        name="deployed",
        adapters={"understand_order": ["pretend_cloud"]},
        allows_cloud=False,
    )
    gateway = Gateway(profile=profile, adapters={"pretend_cloud": PretendCloud()})

    with pytest.raises(CapabilityUnavailable) as refused:
        gateway.understand_order(
            LanguageRequest(character_prompt="", utterance="send scout one to gate three")
        )

    assert "leave the machine" in str(refused.value)


def test_the_same_adapter_is_allowed_under_a_profile_that_permits_cloud():
    """The rule is the profile, not the adapter. Otherwise the refusal
    above would just be a broken adapter rather than a policy working."""
    profile = Profile(
        name="dev", adapters={"understand_order": ["pretend_cloud"]}, allows_cloud=True
    )
    gateway = Gateway(profile=profile, adapters={"pretend_cloud": PretendCloud()})

    chosen = gateway._pick(Capability.UNDERSTAND_ORDER)
    assert chosen.name == "pretend_cloud"


def test_an_unknown_profile_is_refused_rather_than_defaulted():
    """A typo in an install script must not quietly produce a system with
    cloud adapters enabled."""
    with pytest.raises(ValueError) as refused:
        load_active_profile(env={"ARGUS_AI_PROFILE": "depoyed"})
    assert "no AI policy profile" in str(refused.value)


def test_the_default_profile_is_the_air_gapped_one():
    """A missing configuration must fail toward the air-gapped behaviour,
    never toward the one that reaches the internet."""
    assert DEFAULT_PROFILE == "deployed"
    assert load_active_profile(env={}).allows_cloud is False


def test_a_refusal_by_policy_is_distinguishable_from_a_failure():
    """A deployed system with no cloud adapters is working correctly, and
    a caller has to be able to tell that apart from something broken."""
    profile = Profile(name="deployed", adapters={}, allows_cloud=False)
    gateway = Gateway(profile=profile, adapters={})

    with pytest.raises(CapabilityUnavailable):
        gateway.understand_order(LanguageRequest(character_prompt="", utterance="hello"))


def test_no_provider_or_model_name_appears_in_code_outside_the_gateway():
    """The gateway law, checked against every source tree, not just one.

    An earlier version of this test scanned only `voice/` and `c2/src`,
    which is exactly why a provider dependency in the gateway's own
    non-adapter code could have slipped past it. Everything that runs is
    scanned now; only the adapters are exempt.

    Configuration and documentation are not scanned. A policy profile has
    to name the adapter it permits and an install guide has to say what to
    install; the law is about what callers can see.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    forbidden = ("anthropic", "openai", "claude-", "gpt-4", "mistral", "llama", "whisper", "piper")
    exempt = root / "gateway" / "adapters"

    trees = [root / "voice", root / "track", root / "sim", root / "pilot", root / "gateway"]
    paths = [p for tree in trees for p in tree.rglob("*.py")]
    # The install tooling is executable code, not documentation, and it once
    # named a speech binary and two model files that only the gateway's
    # adapters may know. Scanned so that cannot drift back in.
    paths += list((root / "scripts").rglob("*.py"))
    paths += list((root / "scripts").rglob("*.sh"))
    # Not just source: a provider named in a config, a stylesheet or a
    # bundled JSON is just as much a caller learning what answers it.
    for suffix in ("*.ts", "*.tsx", "*.css", "*.json"):
        paths += list((root / "c2" / "src").rglob(suffix))
    for tree in (root / "voice", root / "pilot", root / "track", root / "sim"):
        paths += list(tree.rglob("*.yaml"))
    paths += list((root / "c2" / "public").rglob("*")) if (root / "c2" / "public").exists() else []

    offenders = []
    for path in paths:
        if str(path).startswith(str(exempt)) or "__pycache__" in str(path):
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text().lower()
        except (UnicodeDecodeError, OSError):
            continue  # a font or an image cannot name a provider
        for word in forbidden:
            if word in text:
                offenders.append(f"{path.relative_to(root)} mentions {word!r}")

    assert not offenders, "a provider or model is named outside the gateway: " + "; ".join(offenders)


def test_the_report_says_which_adapters_would_leave_the_machine():
    """An installer has to be able to check the sovereignty claim, not trust it.

    `scripts/verify_install.py` reads exactly this to decide whether a
    deployed target is honest. The first version of that check looked for a
    key the report never carried, so it passed on every machine including
    ones where a cloud adapter was live. A check that cannot fail is worse
    than no check, because it is reported as evidence.
    """
    profile = Profile(
        name="dev", adapters={"understand_order": ["pretend_cloud"]}, allows_cloud=True
    )
    report = Gateway(profile=profile, adapters={"pretend_cloud": PretendCloud()}).check()

    entry = report["capabilities"]["understand_order"][0]
    assert entry["adapter"] == "pretend_cloud"
    assert entry["usable"] is True
    assert entry["leaves_the_machine"] is True, (
        "the report must say this adapter leaves the machine, or the "
        "installer's sovereignty check has nothing to read"
    )


def test_a_deployed_report_shows_a_cloud_adapter_as_refused_and_leaving():
    """Both facts, separately: it would leave, and it is not usable.

    Collapsing them would hide the difference between an adapter that is
    safe and one that is merely broken today.
    """
    profile = Profile(
        name="deployed",
        adapters={"understand_order": ["pretend_cloud"]},
        allows_cloud=False,
    )
    report = Gateway(profile=profile, adapters={"pretend_cloud": PretendCloud()}).check()

    entry = report["capabilities"]["understand_order"][0]
    assert entry["leaves_the_machine"] is True
    assert entry["usable"] is False
    assert "refused" in entry["detail"]

    # The exact shape scripts/verify_install.py applies, stated here so the
    # installer's check cannot drift away from what the report provides.
    #
    # It deliberately does not consult `usable`. The gateway sets that to
    # False for precisely the adapters worth finding, so a check written
    # against it is empty by construction and can never fail. Two versions
    # of this check shipped that way before anyone noticed.
    carried = [
        f"{capability}/{entry['adapter']}"
        for capability, entries in report["capabilities"].items()
        for entry in entries
        if entry.get("leaves_the_machine") is not False
    ]
    assert carried == ["understand_order/pretend_cloud"], (
        "the check must see a cloud adapter that a deployed build carries, "
        "even though the gateway refuses it at runtime: present and refused "
        "is one edit from present and allowed"
    )

    assert report["allows_cloud"] is False


def test_the_report_answers_the_whole_sovereignty_question_itself():
    """One field, computed by the process that holds the adapters.

    A caller enumerating the entries in its own process reads its own
    environment, which is how the install verification shipped wrong three
    times. The aggregate exists so the caller has nothing to compute.
    """
    # A deployed profile that carries a cloud adapter: refused at runtime,
    # but carried, so the answer is True.
    carrying = Profile(
        name="deployed",
        adapters={"understand_order": ["pretend_cloud"]},
        allows_cloud=False,
    )
    report = Gateway(profile=carrying, adapters={"pretend_cloud": PretendCloud()}).check()
    assert report["anything_leaves_the_machine"] is True, (
        "refused is not the question. Carried is, and this build carries it."
    )

    # Everything known local: the one shape allowed to say False.
    local = Profile(
        name="deployed",
        adapters={"understand_order": ["stays"]},
        allows_cloud=False,
    )

    class Stays(PretendCloud):
        name = "stays"

        @property
        def leaves_the_machine(self) -> bool:
            return False

    report = Gateway(profile=local, adapters={"stays": Stays()}).check()
    assert report["anything_leaves_the_machine"] is False


def test_an_unconstructable_adapter_makes_the_sovereignty_answer_unknown():
    """None, not False. An adapter that never got built might have left the
    machine, and saying False would be saying more than is known. The
    installer's check treats None as a failure on a deployed target."""
    profile = Profile(
        name="deployed",
        adapters={"understand_order": ["never_registered"]},
        allows_cloud=False,
    )
    report = Gateway(profile=profile, adapters={}).check()
    assert report["anything_leaves_the_machine"] is None


def test_an_adapter_under_an_unknown_capability_key_still_counts():
    """The open-vocabulary rule, applied to the sovereignty aggregate.

    A profile can name a capability this build's enum has never heard of:
    a newer build's vocabulary, or a misspelling. The adapters under it are
    carried either way, so they must be enumerated either way. The audit
    that demanded this test found that they were not, which let a cloud
    adapter sit invisibly under an unknown key while the aggregate said
    everything was known local.
    """
    hiding = Profile(
        name="deployed",
        adapters={"summarise_patrol": ["pretend_cloud"]},
        allows_cloud=False,
    )
    report = Gateway(profile=hiding, adapters={"pretend_cloud": PretendCloud()}).check()

    assert report["anything_leaves_the_machine"] is True, (
        "a cloud adapter under an unknown capability key must not disappear "
        "from the sovereignty answer"
    )
    assert report["capabilities"]["summarise_patrol"][0]["adapter"] == "pretend_cloud"

    # And an unregistered adapter under an unknown key is unknown, not clean.
    murky = Profile(
        name="deployed",
        adapters={"summarise_patrol": ["never_registered"]},
        allows_cloud=False,
    )
    report = Gateway(profile=murky, adapters={}).check()
    assert report["anything_leaves_the_machine"] is None
