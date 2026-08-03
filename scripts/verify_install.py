#!/usr/bin/env python3
"""Prove that ARGUS is actually installed and working on this machine.

This is deliberately not the test suite. `pytest -q` proves the code is
sound: it runs in one process against in-memory transports and never opens
a socket, so it passes on a machine where nothing is installed at all. That
is the right thing for CI and the wrong thing for an installer, who needs
to know that this box, with these brokers and these models, actually works.

So every check here goes through the real thing: a running server over
HTTP, a real broker, a real simulated machine connecting over the contract,
a real order coming back. Each check states what it proves and prints pass
or fail. Nothing is inferred from a check that did not run.

Usage:
    .venv/bin/python scripts/verify_install.py
    .venv/bin/python scripts/verify_install.py --platform http://192.168.1.10:8100

Exit code is 0 only if every check that ran passed.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Run from anywhere: an installer should not have to be standing in the
# repository root for the verification to import what it is verifying.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PASS = "pass"
FAIL = "FAIL"
SKIP = "skip"

results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    line = f"  {status:<4}  {name}"
    print(line if not detail else f"{line}\n          {detail}")


def get(url: str, token: str = "", timeout: float = 6.0):
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def post(url: str, token: str, body: dict, timeout: float = 8.0):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST"
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# -- the checks -------------------------------------------------------------


def check_brokers(mqtt_host: str) -> None:
    """Every machine reaches the platform through these. No broker, no fleet."""
    if port_open("127.0.0.1", 6379):
        record("Redis is listening", PASS)
    else:
        record("Redis is listening", FAIL, "start it: redis-server --daemonize yes")

    if port_open(mqtt_host, 1883):
        record(f"MQTT broker is listening on {mqtt_host}", PASS)
    else:
        record(
            f"MQTT broker is listening on {mqtt_host}",
            FAIL,
            "start it: mosquitto -d. Machines cannot reach the platform without it.",
        )


def check_platform(base: str) -> bool:
    """The world model answers, and says which contract it speaks."""
    try:
        health = get(f"{base}/health")
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        record("The world model answers", FAIL, f"{base}/health: {error}")
        return False
    if health.get("status") != "ok":
        record("The world model answers", FAIL, f"health said {health}")
        return False
    record(
        "The world model answers",
        PASS,
        f"contract v{health.get('link_version')}, ontology v{health.get('ontology_version')}",
    )
    return True


def check_token(base: str, token: str) -> bool:
    """An operator's key opens the interfaces, and no key does not."""
    try:
        who = get(f"{base}/v1/me", token)
    except urllib.error.HTTPError as error:
        record("An operator key is accepted", FAIL, f"got {error.code} from /v1/me")
        return False
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        record("An operator key is accepted", FAIL, str(error))
        return False
    # Which key this is, not merely that it worked. After the rotation
    # INSTALL.md section 6 demands, the first key in the file may well be an
    # administrator's, and verifying with one proves the wrong thing.
    role = who.get("role", "unknown")
    record(
        "An operator key is accepted",
        PASS,
        f'it belongs to {who.get("display_name")}, role "{role}"'
        + ("" if role == "operator" else ". That is not an operator key."),
    )

    try:
        get(f"{base}/v1/assets")
        record(
            "An unsigned caller is refused",
            FAIL,
            "the interfaces answered without a key, which is a security fault",
        )
        return False
    except urllib.error.HTTPError as error:
        if error.code == 401:
            record("An unsigned caller is refused", PASS)
            return True
        record("An unsigned caller is refused", FAIL, f"expected 401, got {error.code}")
        return False
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        record("An unsigned caller is refused", FAIL, str(error))
        return False


def _heard_since(asset: dict, since: float) -> bool:
    """Has this machine been heard from since the given moment?"""
    stamp = asset.get("last_heartbeat")
    if not stamp:
        return False
    try:
        from datetime import datetime  # noqa: PLC0415

        beat = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return beat >= since


def _an_answering_machine(base: str, token: str) -> dict | None:
    """A machine already installed and currently answering, if there is one."""
    try:
        assets = get(f"{base}/v1/assets", token)
    except Exception:  # noqa: BLE001
        return None
    fresh = time.time() - 20
    for asset in assets:
        if asset.get("status") == "ASSET_STATUS_OFFLINE":
            continue
        if _heard_since(asset, fresh) and (asset.get("position") or {}).get("latitude_deg"):
            return asset
    return None


def _order_and_check(base: str, token: str, asset: dict, ours: bool) -> None:
    """Give a machine somewhere to go, through the endpoint a click uses.

    `ours` says whether this verification started the machine. A machine it
    did not start is a real vehicle that may be carrying out real work, and
    sending it a hundred metres to prove a code path is not a check, it is
    an incident. So a machine we did not start is only ordered when the
    installer says so explicitly.
    """
    if not ours:
        record(
            "A machine takes an order",
            SKIP,
            f'"{asset.get("display_name")}" is a machine this check did not start, '
            "so it was not ordered anywhere. Pass --order-existing-machine if it "
            "is safe to drive, or run this with no machine connected and a "
            "temporary one will be used.",
        )
        return

    position = asset.get("position") or {}
    lat = position.get("latitude_deg")
    lon = position.get("longitude_deg")
    if lat is None or lon is None:
        record("A machine takes an order", SKIP, "the machine has not reported a position")
        return

    try:
        task = post(
            f"{base}/v1/tasks",
            token,
            {
                "asset_id": asset["asset_id"],
                "task_type": "navigate",
                "waypoints": [{"latitude_deg": lat + 0.0009, "longitude_deg": lon + 0.0009}],
                "channel": "map",
            },
        )
    except urllib.error.HTTPError as error:
        body = error.read().decode()[:200]
        record("A machine takes an order", FAIL, f"{error.code}: {body}")
        return

    accepted = False
    try:
        for _ in range(30):
            time.sleep(0.5)
            try:
                current = get(f"{base}/v1/tasks/{task['task_id']}", token)
            except Exception:  # noqa: BLE001
                continue
            if current.get("status") in (
                "TASK_STATE_ACCEPTED",
                "TASK_STATE_RUNNING",
                "TASK_STATE_SUCCEEDED",
            ):
                accepted = True
                break
        if accepted:
            record(
                "A machine takes an order",
                PASS,
                f'it was told to {task.get("phrase")} and accepted it',
            )
        else:
            record(
                "A machine takes an order",
                FAIL,
                "the order was created but the machine never acknowledged it",
            )
    finally:
        # Withdrawn whatever happened. On the timeout path the order may
        # still be in flight, and a check that has already reported failure
        # must not leave a vehicle driving off behind it.
        try:
            post(f"{base}/v1/tasks/{task['task_id']}/cancel", token, {})
        except Exception:  # noqa: BLE001
            record(
                "The verification's own order was withdrawn",
                FAIL,
                f"{task['task_id']} could not be cancelled. Stop it from the "
                "operator screen before leaving.",
            )


def check_machine_and_order(
    base: str, token: str, mqtt_host: str, order_existing: bool
) -> None:
    """The whole point: a machine connects over the contract and takes an order.

    A short-lived simulated machine is started, watched onto the map, given
    somewhere to go, and stopped. This is the one check that proves the
    brokers, the contract, the world model and the tasking path all work
    together on this box rather than each being individually plausible.
    """
    # An existing machine is preferred, because the alternative leaves a
    # record behind. The world model has no way to forget an asset, so every
    # verification that registers one puts another vehicle on the operator's
    # map that does not exist. Using a machine the installer already has
    # proves the same thing and leaves nothing.
    existing = _an_answering_machine(base, token)
    if existing:
        record(
            "A machine connects over the contract",
            PASS,
            f'"{existing.get("display_name")}" is already answering, so no test machine was made',
        )
        _order_and_check(base, token, existing, ours=order_existing)
        return

    from track.ids import new_id  # noqa: PLC0415

    asset_id = new_id()
    python = sys.executable
    machine = None
    registered = False
    try:
        machine = subprocess.Popen(
            [
                python, "-m", "sim.main",
                "--asset-id", asset_id,
                "--host", mqtt_host,
                "--duration", "70",
            ],
            cwd=REPO,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Wait for a heartbeat newer than this run, not merely for the record
        # to exist. A previous verification leaves the asset behind, and
        # matching that would prove only that the database remembers a
        # machine we are no longer talking to.
        started = time.time()
        seen = None
        for _ in range(40):
            if machine.poll() is not None:
                break
            time.sleep(0.5)
            try:
                assets = get(f"{base}/v1/assets", token)
            except Exception:
                continue
            found = next((a for a in assets if a["asset_id"] == asset_id), None)
            if found:
                # It reached the world model, so a record now exists whether
                # or not the rest of this check succeeds.
                registered = True
            if found and _heard_since(found, started):
                seen = found
                break

        if not seen:
            detail = "the machine never appeared on the platform"
            if machine.poll() is not None:
                stderr = (machine.stderr.read() or b"").decode()[-400:]
                detail += f". It exited: {stderr.strip()}"
            record("A machine connects over the contract", FAIL, detail)
            record("A machine takes an order", SKIP, "no machine to order")
            return

        record(
            "A machine connects over the contract",
            PASS,
            f'it is called "{seen.get("display_name")}" on the map',
        )
        _order_and_check(base, token, seen, ours=True)
    finally:
        # Recorded whatever else happened, but only when the machine really
        # did register. Naming an identifier that may not exist would be a
        # different kind of untruth, and it would end every clean run in a
        # skipped verdict for nothing.
        if registered:
            record(
                "A test machine was registered and cannot be removed",
                SKIP,
                f"{asset_id} is now on the operator's map as a machine that is "
                "not answering, and the world model has no way to forget an "
                "asset. See INSTALL.md section 6 before handing this over.",
            )
        if machine and machine.poll() is None:
            machine.terminate()
            try:
                machine.wait(timeout=10)
            except subprocess.TimeoutExpired:
                machine.kill()


def sovereignty_verdicts(
    report: dict | None, handover: bool = False
) -> list[tuple[str, str, str]]:
    """The sovereignty verdicts for what the running service reported.

    Pure: report in, verdicts out, no environment and no network, so the
    decision itself is testable. This function earned that treatment by
    being wrong three times. Each version consulted something in the
    verifier's own process (a key the report never carried, then a field
    the gateway zeroes for exactly the adapters being sought, then a fresh
    Gateway whose facts came from this shell's environment) and each
    passed everywhere, including where it should have failed.

    Every fact asserted here comes from the service's own report, because
    the service is the process that holds the adapters. Nothing local is
    evidence.
    """
    if report is None:
        return [
            (
                "The AI profile of the running deployment",
                SKIP,
                "the voice service is not answering, so the policy actually in "
                "force cannot be read. Start it and run this again before "
                "handover.",
            )
        ]

    profile = report.get("profile", "")
    if not profile:
        return [
            (
                "The AI profile of the running deployment",
                FAIL,
                "the voice service did not say which profile it resolved. It "
                "is too old for this check, or something is wrong with it.",
            )
        ]

    verdicts = [(f"The running deployment is on profile '{profile}'", PASS, "")]

    if profile != "deployed":
        # On an ordinary run a bench profile is simply named. On a handover
        # run it is a failure, because handing over a cloud-permitting
        # target is the thing INSTALL.md section 6 exists to prevent, and
        # an install script gating on the exit code has to be stopped by
        # the code, not by prose it never reads.
        verdicts.append(
            (
                "This deployment is on a bench profile",
                FAIL if handover else PASS,
                f"'{profile}' permits cloud. Correct for a bench, wrong for "
                "anything else. INSTALL.md section 6 requires "
                "ARGUS_AI_PROFILE=deployed before handover.",
            )
        )
        return verdicts

    if report.get("allows_cloud") is not False:
        verdicts.append(
            (
                "The deployed profile forbids cloud",
                FAIL,
                "the profile named 'deployed' permits cloud adapters. This is "
                "a sovereignty failure in policy_profiles.yaml, not a runtime "
                "one.",
            )
        )
    else:
        verdicts.append(("The deployed profile forbids cloud", PASS, ""))

    # Plan section 7: a deployed target does not merely refuse what leaves
    # the machine, it does not carry it. The service answers with one value:
    # True, False, or null for cannot-say. Only False passes. Null fails,
    # because an unverifiable sovereignty claim is not a satisfied one, and
    # a missing field fails the same way for the same reason.
    leaves = report.get("anything_leaves_the_machine", "absent")
    if leaves is False:
        verdicts.append(
            ("The running deployment carries nothing that leaves the machine", PASS, "")
        )
    elif leaves is True:
        verdicts.append(
            (
                "The running deployment carries nothing that leaves the machine",
                FAIL,
                "the running service says something in this deployment would "
                "send data off the machine. Refused or not, it is one "
                "configuration edit from allowed, and plan section 7 says a "
                "deployed target does not carry it at all.",
            )
        )
    else:
        verdicts.append(
            (
                "The running deployment carries nothing that leaves the machine",
                FAIL,
                "the running service could not say whether anything it carries "
                "leaves the machine"
                + (
                    ", because it did not report the fact at all. It predates "
                    "this check; upgrade it and run this again."
                    if leaves == "absent"
                    else ". An unverifiable sovereignty claim is not a "
                    "satisfied one."
                ),
            )
        )
    return verdicts


def check_ai_profile(report: dict | None, handover: bool = False) -> None:
    """What this deployment's AI may do, and what it refuses.

    A wrong answer here is a sovereignty failure, not a convenience one, so
    the verdicts come from the running service's own report, never from
    anything built in this process.
    """
    verdicts = sovereignty_verdicts(report, handover=handover)
    for name, status, detail in verdicts:
        record(name, status, detail)

    # Supplementary only, and only ever adverse. Enumerating adapters here
    # reads this shell's environment, not the deployment's, so a clean
    # result proves nothing and is not recorded. A dirty result is still
    # worth a failure: whatever the running service says, this checkout
    # carries something it should not.
    if report is None or report.get("profile") != "deployed":
        return
    try:
        from gateway import Gateway  # noqa: PLC0415
        from gateway.policy import load_profiles  # noqa: PLC0415

        local = Gateway(profile=load_profiles()["deployed"]).check()
    except Exception:  # noqa: BLE001
        # No local gateway to enumerate (a remote verifier, for instance).
        # The authoritative check already ran; silence, not a verdict.
        return
    carried = [
        f"{capability}/{entry['adapter']}"
        for capability, entries in (local.get("capabilities") or {}).items()
        for entry in entries
        if entry.get("leaves_the_machine") is not False
    ]
    if carried:
        record(
            "This checkout also carries something that leaves the machine",
            FAIL,
            f"found locally, separate from the running service: {', '.join(carried)}.",
        )


def check_voice(voice_url: str, token: str) -> dict | None:
    """Voice says honestly which of hearing, speaking and thinking it has."""
    try:
        caps = get(f"{voice_url}/v1/voice/capabilities", token)
    except urllib.error.HTTPError as error:
        # A service that answered and refused is a fault, not an absence.
        # Reporting it as "voice is optional" would hide a broken install.
        record(
            "The voice service answers",
            FAIL,
            f"{voice_url} replied {error.code}. It is running and not working.",
        )
        return None
    except (urllib.error.URLError, OSError, TimeoutError):
        record(
            "The voice service answers",
            SKIP,
            f"nothing is listening at {voice_url}. Voice is optional; the map works without it.",
        )
        return None
    record(
        "The voice service answers",
        PASS,
        f"hear={caps.get('can_hear')} speak={caps.get('can_speak')} understand={caps.get('can_understand')}",
    )
    if not caps.get("can_understand"):
        record(
            "Voice can understand an order",
            SKIP,
            "no language adapter is usable, so the voice bar disables itself. "
            "That is honest, not broken. See INSTALL.md 2.7.",
        )
    return caps


# -- main -------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default="http://127.0.0.1:8100")
    parser.add_argument("--voice", default="http://127.0.0.1:8300")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument(
        "--token",
        default="",
        help="An operator key. Defaults to var/op.token, then TOKENS_PATH.",
    )
    parser.add_argument(
        "--handover",
        action="store_true",
        help=(
            "Treat a skipped check as a failure. For the final run before a "
            "deployment is handed over, when a check that did not run is not "
            "good enough."
        ),
    )
    parser.add_argument(
        "--order-existing-machine",
        action="store_true",
        help=(
            "Allow the tasking check to drive a machine this check did not "
            "start. Only safe when you know that vehicle is clear to move."
        ),
    )
    args = parser.parse_args()
    handover = args.handover

    token = args.token
    if not token:
        for candidate in (REPO / "var" / "op.token",):
            if candidate.exists():
                token = candidate.read_text().strip()
                break
    if not token:
        tokens_file = REPO / "var" / "tokens.yaml"
        if tokens_file.exists():
            for line in tokens_file.read_text().splitlines():
                if "token:" in line:
                    token = line.split("token:", 1)[1].strip()
                    break

    print("Verifying the ARGUS install on this machine")
    print("===========================================")
    print(f"  platform  {args.platform}")
    print(f"  broker    {args.mqtt_host}:1883")
    print()

    # Nothing is known about the running deployment's AI policy until the
    # voice service says so, and it may never be reached.
    voice_report: dict | None = None

    check_brokers(args.mqtt_host)

    if check_platform(args.platform):
        if not token:
            record(
                "An operator key is accepted",
                FAIL,
                "no key found. Start the platform once to generate var/tokens.yaml, "
                "or pass --token.",
            )
        elif check_token(args.platform, token):
            check_machine_and_order(
                args.platform, token, args.mqtt_host, args.order_existing_machine
            )
            voice_report = check_voice(args.voice, token)
    else:
        for name in (
            "An operator key is accepted",
            "A machine connects over the contract",
            "A machine takes an order",
        ):
            record(name, SKIP, "the platform is not answering")

    check_ai_profile(voice_report, handover)

    failed = [name for name, status, _ in results if status == FAIL]
    skipped = [name for name, status, _ in results if status == SKIP]

    print()
    print("Verdict")
    if failed:
        print(f"  NOT WORKING. {len(failed)} check(s) failed:")
        for name in failed:
            print(f"    - {name}")
        print("  INSTALL.md section 5 lists the usual causes.")
        return 1
    if skipped:
        print(f"  Working, with {len(skipped)} check(s) skipped:")
        for name in skipped:
            print(f"    - {name}")
        print("  A skipped check proves nothing. Read the note beside each one.")
        if handover:
            # An install script gating on the exit code alone would otherwise
            # hand over a target whose sovereignty check never ran. At
            # handover, a check that did not run is a check that failed.
            print("  This is a handover run, so unproven is failing. Exit 1.")
            return 1
        return 0
    print("  Working. Every check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
