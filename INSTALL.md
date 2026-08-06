# Installing ARGUS

Written to be executed by a coding agent with shell access, on the machine
being installed. A person can follow it too, but the shape is for an agent:
ordered steps, an explicit check after each one, and a stated failure mode
where a step can plausibly fail.

**Read this whole file before running anything.** Section 1 decides which
of the two install targets you are on, and the rest of the file depends on
that answer.

---

## If you are an agent, start here

Three commands bracket the whole install. Run the first one now.

```bash
bash scripts/preflight.sh            # if this box will run both, for development
bash scripts/preflight.sh --platform # a laptop, server or ground station
bash scripts/preflight.sh --machine  # a Jetson or any vehicle computer
```

Pass the scope if you know it. The two installs need different things, and
without the flag a correctly provisioned platform box is failed for Docker
it will never use. Section 1 tells you which you are on.

It installs nothing and decides nothing. It reports what this machine is,
what is already present, what is missing, and **which parts of ARGUS have
actually been run on a target like this one**. That last part is the one
worth reading: a step nobody has executed on this architecture is not a
step that is known to work. Exit code 0 means ready, 1 means something is
missing, 2 means this target is not supported by this build.

Then follow this document from section 1.

When you believe you are finished, prove it:

```bash
.venv/bin/python scripts/verify_install.py
```

This is **not** the test suite, and running `pytest` instead does not
substitute for it. `pytest -q` proves the code is sound: it runs in one
process against in-memory transports and never opens a socket, so it
passes on a machine where nothing is installed at all. The verification
goes through the real thing instead, on this box: real brokers, a real
machine connecting over the contract, a real order coming back.

Exit code 0 means nothing failed. It does **not** mean everything was
checked: a check that could not run is reported as skipped and still exits
0, because a skipped check is not a failure and pretending otherwise would
teach an installer to ignore the exit code. Read the verdict, not just the
status.

The exception is the final run before a deployment is handed over:

```bash
.venv/bin/python scripts/verify_install.py --handover
```

At handover a check that did not run is not good enough, so `--handover`
exits 1 on any skip. Everything must actually be running and actually be
proven, including the sovereignty of the AI policy in force.

**Report honestly.** If a check fails, say which one and stop. If a check
is skipped, say so and do not describe the install as complete: a skipped
check proves nothing. Do not work around a failure by editing the
verification.

---

## 0. What is honest about this document

This describes what can be installed **today**, from this repository, and
marks what cannot. Stages 1, 2, 3A and 4 exist. Stage 3B (real sensor and
motor drivers) and Stage 5 (packaging, offline bundles, demo script) do
not, and no amount of following these steps will produce them.

Specifically, **not yet true**:

- There is no offline bundle. Every step here needs network access at
  install time. The real targets are air-gapped, so the shipping form is a
  saved image tarball copied on a USB stick, and that does not exist yet.
- There is no versioned release. You install from a git checkout.
- A machine installed by this document drives on **simulated** locomotion
  and perception drivers. It is a complete, honest machine that speaks the
  real contract; it just has no hardware under it.
- The fully air-gapped path is unproven. Speech runs locally, but the
  language model has only been run against a cloud API in the `dev`
  profile. The `deployed` profile refuses cloud adapters and is enforced by
  a test, but nobody has yet run a local language model behind it.

If any of those matter for what you are about to do, stop and say so
rather than proceeding.

---

## 1. Decide which target this is

Two different things get installed, and they are not the same install.

```bash
# Run this. It does not decide for you; it tells you what you are on.
uname -m; uname -s
test -f /etc/nv_tegra_release && echo "TARGET: this looks like a Jetson (a machine)" \
  || echo "TARGET: not a Jetson (probably the platform)"
```

| If this is | You are installing | Go to |
|---|---|---|
| A Jetson, or any vehicle computer | **A machine** (PILOT) | Section 3 |
| A laptop, server, or ground station | **The platform** (TRACK, gateway, voice, C2) | Section 2 |

You can install both on one box for development. In the field they are
different computers, and the machine is the one that must keep working
when the platform is unreachable.

---

## 2. The platform

Runs the world model, the AI gateway, the voice service, and serves the
operator application.

### 2.1 Prerequisites

```bash
python3 --version   # need 3.11 or newer
node --version      # need 20 or newer
git --version
```

**If Python is older than 3.11**, install a newer one before continuing.
Do not proceed on 3.10: the world model uses syntax that will fail to
import, and the failure appears later as a confusing traceback.

### 2.2 Get the code and build the environment

```bash
git clone <this repository> argus && cd argus
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install ./link
```

**Verify.** This must print the contract version and nothing else:

```bash
.venv/bin/python -c "from link.v1.messages_pb2 import Heartbeat; print('contract ok')"
```

Expected output: `contract ok`

**If it fails with `ModuleNotFoundError: No module named 'link'`**, the
contract package did not install. Confirm `link/gen/python/link/v1/` is
populated; if it is empty, the generated bindings were not committed and
you need `buf generate` in `link/` with `buf` installed.

### 2.3 Brokers

```bash
# macOS
brew install redis mosquitto && redis-server --daemonize yes && mosquitto -d

# Debian or Ubuntu
sudo apt-get install -y redis-server mosquitto
sudo systemctl enable --now redis-server mosquitto
```

**Verify:**

```bash
redis-cli ping                                    # expect: PONG
(exec 3<>/dev/tcp/127.0.0.1/1883) && echo "mqtt ok"  # expect: mqtt ok
```

### 2.4 Run the world model

```bash
mkdir -p var
DB_PATH=var/track.db TOKENS_PATH=var/tokens.yaml PORT=8100 \
  .venv/bin/python -m track.main
```

Access tokens are generated into `var/tokens.yaml` on first run. Read them:

```bash
cat var/tokens.yaml
```

**Verify** (from another shell):

```bash
curl -s localhost:8100/health
```

Expected: `{"status":"ok","link_version":1,"ontology_version":1}`

**If the port is in use**, change `PORT` and remember it for every later
step. Do not kill the process holding it without checking what it is.

### 2.5 Choose an AI policy profile

This is the sovereignty decision and it is made once, at install time, by
an administrator. It is not reachable from any operator surface.

| Profile | Use for | Cloud |
|---|---|---|
| `deployed` | The real thing, air-gapped | Refused |
| `dev` | A bench, while building | Permitted |
| `demo` | A demonstration on a connected network | Permitted |

**The default is `deployed`.** A missing profile falls back to it, and a
**misspelled** one is refused outright with an error rather than defaulted,
so a typo in an install script cannot quietly enable cloud.

### 2.6 Speech (every profile needs this)

Local, offline, roughly 200MB.

```bash
# macOS
brew install whisper-cpp ffmpeg
.venv/bin/pip install piper-tts

# Debian or Ubuntu: build whisper.cpp from source, then
sudo apt-get install -y ffmpeg
.venv/bin/pip install piper-tts

mkdir -p var/models
curl -L -o var/models/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
(cd var/models && ../../.venv/bin/python -m piper.download_voices en_US-libritts_r-medium)
```

**Use that exact voice.** Piper's engine is MIT but each voice carries its
own licence, and the most common English one (`lessac`) is research-only.
`libritts_r` is CC BY 4.0. See LICENSES.md before substituting one.

**Verify the round trip** (it should print back what it said):

```bash
echo "the machine is standing by" | .venv/bin/python -m piper \
  -m var/models/en_US-libritts_r-medium.onnx -s 0 -f /tmp/t.wav
ffmpeg -y -i /tmp/t.wav -ar 16000 -ac 1 /tmp/t16.wav 2>/dev/null
whisper-cli -m var/models/ggml-base.en.bin -f /tmp/t16.wav -nt 2>/dev/null
```

Expected: roughly `The machine is standing by.`

### 2.7 Language

**For `dev` or `demo`:** set the API key.

```bash
.venv/bin/pip install -r requirements-bench.txt   # the cloud client is not in the base install
export ANTHROPIC_API_KEY=sk-ant-...
```

The cloud client is deliberately absent from `requirements.txt`. Plan
section 7 says a deployed profile has cloud adapters *not installed*, not
merely refused, so a deployed image never carries it and the adapter never
registers.

**For `deployed`:** you need a local OpenAI-compatible model server and a
set of weights.

**Stop and read LICENSES.md before you pull anything.** No local language
model has been chosen and none has been licence-verified for this project.
Law 9 requires verifying every third-party licence for military use before
integration, and that has not been done here. A model runner and its
weights carry separate licences, and an unpinned tag can change what it
resolves to between one install and the next. Meta Llama is already
disqualified by the plan's sovereignty carve-out.

So this step cannot be completed by following a command, and this document
will not print one that would look like permission. Choose a model, verify
its licence at a specific revision, record it in LICENSES.md, then:

```bash
# Whatever OpenAI-compatible server you settled on, pointed at the weights
# you verified. These two variables are all the gateway needs.
export ARGUS_LOCAL_LLM=http://127.0.0.1:11434/v1
export ARGUS_LOCAL_MODEL=<the model you verified, pinned>
```

Until that is done, `deployed` will refuse to answer and say so plainly,
which is the correct behaviour and not a fault to work around.

**Verify what the gateway can actually do.** This is the important check,
because it reports refusals and failures separately:

```bash
# Whichever profile this deployment will actually run under. Checking a
# bench profile proves nothing about a deployed one, and section 6 sends
# you back here to confirm the refusal, which only happens on `deployed`.
ARGUS_AI_PROFILE="${ARGUS_AI_PROFILE:-deployed}" .venv/bin/python -c "
from gateway import Gateway
import json; print(json.dumps(Gateway().check(), indent=2))"
```

Speech should list an adapter with `"usable": true`.

Two entries are **not** faults, and both are expected on a correct
`deployed` box:

- **"refused: this profile does not permit cloud adapters"** is the
  sovereignty law working.
- **"no model has been chosen and verified"** on `understand_order` and
  `answer_question` is the licensing law working. Until a local model has
  been licence-checked and named in `ARGUS_LOCAL_MODEL`, a deployed target
  correctly has no language adapter at all, and voice will hear and speak
  but not understand.

An entry saying **"no API key is configured"** or **"the speech model is
missing"** is a fault, and section 2.6 or 2.7 was not completed.

### 2.8 Run the voice service

```bash
ARGUS_AI_PROFILE=dev TRACK_URL=http://127.0.0.1:8100 VOICE_PORT=8300 \
  .venv/bin/python -m voice.main
```

**Verify:**

```bash
curl -s localhost:8300/health
```

Expected: `{"status":"ok","character":"ops","characters":["demo","ops"]}`

### 2.9 Build and serve the operator application

```bash
cd c2 && npm install && npm run build
```

**Verify:** `c2/dist/index.html` exists. Serve `c2/dist` with any static
server, or run `npm run dev` for development.

Sign in with the operator token from `var/tokens.yaml`.

### 2.10 Prove the platform works

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass in roughly ten seconds. **If they do not, stop.**
The suite is the definition of done for every stage built so far, and a
failure here means something in the environment is wrong, not that the
tests are out of date.

---

## 3. A machine

PILOT runs containerized. ROS2 Humble has no supported native macOS path,
and on a Jetson the container is how it ships anyway.

### 3.1 Prerequisites

```bash
docker --version && docker info >/dev/null && echo "docker ok"
```

**If Docker is not installed**, install it before continuing. On a Jetson,
install NVIDIA Container Toolkit too, or the container cannot reach the
GPU when Stage 3B needs it.

### 3.2 Build the runtime image

```bash
cd argus
docker build -f drive/pilot/docker/Dockerfile -t argus-pilot:dev .
```

This takes several minutes: it installs ROS2 Humble and Nav2.

**On a Jetson, read this before building.** `pilot/docker/Dockerfile`
uses `ros:humble-ros-base`, which gives you ROS2 and Nav2 but **no CUDA
and no TensorRT**. That is correct for Stage 3A, where perception is
simulated. It is not correct for Stage 3B: the real perception path needs
an NVIDIA L4T base image instead. If you are installing to run real
sensors, that base image change has not been made yet and this document
cannot help you do it.

**Verify:**

```bash
docker run --rm argus-pilot:dev bash -lc \
  'python3 -c "from pilot.runtime import boot; print(boot(\"/opt/argus/pilot/manifests/ugv-reference.yaml\").manifest.name)"'
```

Expected: `Scout 1`

### 3.3 Write this machine's manifest

**This is the only per-machine step.** Copy the reference manifest and
edit it:

```bash
cp drive/pilot/manifests/ugv-reference.yaml /etc/argus/manifest.yaml
```

What you must change:

| Field | Set it to |
|---|---|
| `asset_id` | A unique 26-character ULID for this machine |
| `name` | What operators should call it on the map |
| `max_speed_mps`, `max_turn_rate_dps`, `max_accel_mps2`, `max_decel_mps2` | This machine's real limits |
| `min_turn_radius_m` | `0.0` if it turns in place, otherwise its radius |
| `dimensions` | Its real length, width and height in metres |
| `drivers` → `comms` → `host` | The address of the platform's MQTT broker |

**Do not leave the movement limits at the reference values.** They are one
machine's numbers. A machine that does not declare its own gets
deliberately cautious defaults, which is safe but slow, and that is by
design.

Leave the locomotion and sensor drivers as `simulated_*` unless Stage 3B
has landed and real drivers exist. There is no partial state here: a
manifest naming a driver this build does not carry refuses to boot, which
is better than a machine that boots half-equipped and drives.

### 3.4 Run the machine

Without ROS2 in the path (simplest, good for checking the link):

```bash
docker run --rm --network host -v /etc/argus:/etc/argus argus-pilot:dev \
  python3 -m pilot.main --manifest /etc/argus/manifest.yaml --prefix argus
```

With Nav2 doing the navigating:

```bash
docker compose -f drive/pilot/docker/compose.yaml up nav2 pilot
```

**Verify from the machine:**

```bash
curl -s localhost:8200/registry | head -40
```

That is the machine describing itself: installed drivers and versions,
what its buses report, the configuration in force, and each driver's
health. If `"healthy": false`, read the `health` list, which says which
driver is unhappy and why in a sentence.

**Verify from the platform** (it should appear by the name its manifest
declared, not a composed one):

```bash
curl -s -H "Authorization: Bearer <operator token>" localhost:8100/v1/assets
```

### 3.5 Prove the machine works

```bash
docker run --rm -e ROS_DOMAIN_ID=42 argus-pilot:dev \
  bash /opt/argus/pilot/docker/run_nav2_tests.sh pilot/ros/tests -q
```

Expected: 4 tests pass in roughly 50 seconds. This exercises the bridge
between Nav2 and the locomotion driver and drives a real Nav2 route.

---

## 4. Adding a second machine

The test of whether any of this was worth building. It should be:

1. Write a manifest (section 3.3).
2. Run the same image with it (section 3.4).

Nothing else. No code change, no rebuild, no per-machine branch anywhere.
**If a second machine needs more than that, the hardware abstraction layer
has failed and the fix belongs in `pilot/`, not in this document.** There
is a test for exactly this claim in `tests/test_pilot_loop.py`.

---

## 5. When something is wrong

| Symptom | Where to look |
|---|---|
| A machine does not appear on the map | Both sides point at the same MQTT broker and the same `--prefix`. The platform defaults to `argus`. |
| It appears but is named "Ground vehicle 00A1" | Its registry has not arrived yet. It rides telemetry and is sent on change; wait a few seconds. The composed name is the server being honest that the machine has not told it a name. |
| The voice button is disabled | `curl -H "Authorization: Bearer $TOKEN" localhost:8300/v1/voice/capabilities` (it needs a key). It says which of hearing, speaking and understanding is unavailable. |
| Voice says "I cannot reach the language service" | Section 2.7. Under `deployed` this also appears when no local model is running, which is correct: it refuses rather than reaching out. |
| Nav2 never becomes active | Its costmaps wait for the locomotion bridge to publish `base_link` against `odom`. Anything that waits for Nav2 before starting the machine deadlocks. |
| Tests fail on a fresh clone | Report it. The suite is the definition of done and is expected to pass from a clean checkout. |

---

## 6. What an installer still owes the deployment

Not covered by this document, and not optional before anything real runs:

- **Rotate the generated tokens.** `var/tokens.yaml` is generated on first
  run for convenience. It is not a credential policy.
- **Remove any machine the verification registered.** If no machine was
  answering when `scripts/verify_install.py` ran, it started a temporary
  one to prove the contract path, and the world model has no way to forget
  an asset. The verification says so when this happens, and names the
  identifier. Left in place it appears on the operator's map for ever as a
  machine that is not answering, which is exactly the kind of thing the
  disconnection wording exists to make operators take seriously. Removing
  it currently means editing the database directly, which is a gap: there
  is no administrative path for retiring a machine.
- **Set `ARGUS_AI_PROFILE=deployed`** on anything that is not a bench, and
  confirm with the section 2.7 check that cloud adapters report as refused.
- **Read LICENSES.md** before substituting any model or voice. Two of the
  obvious substitutions are research-only or non-commercial, and one whole
  category is excluded by the sovereignty law.
