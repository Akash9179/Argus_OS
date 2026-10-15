# Third-party licences

The licensing law: every third-party model, library and dataset has its
licence verified for military use before integration. This file is the
record. A dependency that is not listed here has not been checked, and
adding one without adding a line here is the thing the law forbids.

Known constraint carried from the plan: Meta Llama licences carve out
military use for non-US and non-allied users and are disqualified. Apache
2.0 weights are the baseline for local models.

**Scope of this record.** Every direct dependency is listed: anything named
in `requirements.txt`, `link/package.json`, `c2/package.json`, or installed
by name in `pilot/docker/Dockerfile`. Transitive dependencies are not
enumerated one by one, because the list churns and a stale list is worse
than an honest boundary. Instead, before anything ships, the full resolved
tree gets a licence scan and any copyleft or field-of-use-restricted result
is recorded here. That scan has **not been run yet**, and it is a Stage 5
task. Models are exempt from this and are always listed individually,
whether direct or not.

## Verified and in use

| Component | Version | Licence | Where | Verdict |
|---|---|---|---|---|
| IBM Plex Sans (via @fontsource/ibm-plex-sans) | 5.3.0 | SIL Open Font License 1.1 | c2/, drive/cockpit/ (bundled, self-hosted) | Permissive; embedding and redistribution allowed; no CDN at runtime (law 8). |
| JetBrains Mono (via @fontsource/jetbrains-mono) | 5.3.0 | SIL Open Font License 1.1 | c2/, drive/cockpit/ (bundled, self-hosted) | Permissive; same terms as above. |
| ROS2 Humble core (`rclpy`, `tf2_ros`, message packages) | Humble Hawksbill | Apache 2.0 | PILOT container | Clear. Permissive, no field-of-use restriction. |
| Navigation2 (`navigation2`, `nav2_bringup`, `nav2_simple_commander`, MPPI controller) | Humble | Apache 2.0 | PILOT container | Clear. Permissive, no field-of-use restriction. |
| `tf_transformations` | Humble packaging | BSD 3-Clause | PILOT container | Clear. |
| `paho-mqtt` | >=2.1 | EPL 2.0 / EDL 1.0 (dual) | PILOT, TRACK, sim | Clear under EDL 1.0 (BSD-style). Used unmodified as a library; no copyleft obligation attaches. |
| `protobuf` (Python runtime) | >=5.28 | BSD 3-Clause | everywhere | Clear. |
| FastAPI, Starlette | current | MIT / BSD 3-Clause | TRACK | Clear. |
| `pydantic` | current | MIT | TRACK, used directly for request models | Clear. |
| `uvicorn[standard]` | >=0.32 | BSD 3-Clause | TRACK | Clear. The `standard` extra pulls `uvloop` (MIT/Apache 2.0), `httptools` (MIT), `websockets` (BSD 3-Clause), `watchfiles` (MIT) and `python-dotenv` (BSD 3-Clause). All permissive. `watchfiles` is a development convenience and does not need to ship. |
| `pytest`, `pytest-asyncio` | current | MIT / Apache 2.0 | tests only, not shipped | Clear. |
| `redis-py` | >=5.2 | MIT | TRACK | Clear. |
| Redis server | 7.x | RSALv2 / SSPLv1 | TRACK deployment | **Read before shipping.** Fine for internal deployment; the restriction is on offering Redis itself as a managed service, which we do not. Revisit if the deployment model changes. Valkey (BSD 3-Clause) is the drop-in escape hatch if it ever becomes awkward. |
| Mosquitto | 2.x | EPL 2.0 / EDL 1.0 | broker | Clear under EDL 1.0. Used unmodified. |
| SQLite | bundled | Public domain | TRACK | Clear. |
| `python-ulid`, `PyYAML`, `httpx` | current | MIT / MIT / BSD 3-Clause | everywhere | Clear. |
| React, Vite, Leaflet | current | MIT / MIT / BSD 2-Clause | C2 | Clear. |
| pyserial | 3.5 or later | BSD-3-Clause | drive/pilot/hal/drivers/ugv01/ (the two vehicle boards' serial ports; imported only when a real port is opened, 13 Oct 2026) | Clear. Permissive. |
| Arduino AVR core (compiles the Nano sketch; not shipped in this repo) | 1.8.8 | LGPL-2.1 | bodies/ugv-01/firmware/nano_throttle_watchdog/, built by build.sh on the Jetson (and once in Gulshan Shah's Arduino IDE, 14 Oct 2026) | Clear for firmware that links it; nothing of it is copied here. |
| Arduino core for ESP32 (compiles the drive module; not shipped) | espressif32 7.1.3 via PlatformIO | LGPL-2.1 | bodies/ugv-01/firmware/esp32_drive_4.1.5_src/, built by build.sh on the Jetson | Clear, same terms. |
| PlatformIO Core (build tool only) | 6.2.0 | Apache-2.0 | the Jetson's ~/argus-tools and developer machines | Clear. Not deployed. |
| arduino-cli (build tool only) | latest Linux ARM64 at 15 Oct 2026 | GPL-3.0 | the Jetson's ~/argus-tools, driven by bodies/ugv-01/firmware/build.sh | Clear. A build tool that is run, not linked or shipped; GPL imposes nothing on the firmware it compiles. |
| Vehicle firmware (ESP32-S3 4.1.4, Nano AC 1.2, written by Gulshan Shah) | 13 Oct 2026 | Company-owned (founder, 14 Oct 2026, decision D-24) | bodies/ugv-01/firmware/vendor-2026-10-13/ | Clear. Ours. |

C2's dev-only tooling never ships: `eslint`, `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `globals` and `vitest`. All are MIT, checked with `npm view <pkg> license` on 12 Oct 2026. They stay outside the shipped-software tables by decision, not by omission.

## Map imagery (D-22 local cache)

| Dataset | Licence | Where | Verdict |
|---|---|---|---|
| Copernicus Sentinel-2 L2A true colour, scene `S2B_44QLL_20260211_0_L2A` (11 Feb 2026), read once from the AWS open-data bucket via the Element84 earth-search STAC and rendered to `var/tiles/jabalpur.mbtiles` (Jabalpur demo site, z10 to 16) | Copernicus free, full and open data policy (Commission Delegated Regulation (EU) No 1159/2013); any use including commercial and military, attribution required | TRACK tile cache, shown by C2 | Clear. Attribution string carried in the file's metadata and shown on the map: "Contains modified Copernicus Sentinel data 2026". 10 m native resolution, so anything sharper needs a separately licensed source. No tile service is contacted at runtime. |

## Speech (Stage 4)

| Component | Licence | Where | Verdict |
|---|---|---|---|
| whisper.cpp | MIT | gateway, local STT adapter | Clear. |
| Whisper `ggml-base.en` weights | MIT (OpenAI) | gateway | Clear. US origin, so the sovereignty law is satisfied too. |
| Piper (`piper-tts`) | MIT (Rhasspy / OHF) | gateway, local TTS adapter | Clear. **The engine's licence is not the voice's licence.** Each voice must be checked separately. |
| Piper voice `en_US-libritts_r-medium` | **CC BY 4.0** (LibriTTS-R, OpenSLR 141) | gateway | Clear, attribution required. Derived from LibriVox public-domain audiobooks. This is the voice in use. |

### Speech models rejected

| Component | Licence | Why not |
|---|---|---|
| Piper voice `en_US-lessac-medium` | Blizzard 2013 **Research Licence Agreement** | Research use only, granted individually to a named person or organisation, non-transferable. Downloaded, checked, and deleted. It is Piper's most commonly used English voice, which is exactly why it is worth recording as a trap. |
| Piper voice `en_US-ryan-medium` | CC BY-NC-SA 4.0 | Non-commercial. |
| Fish Audio (`fish-speech`, OpenAudio S1) | Fish Audio Research License | "Any Commercial use of the Materials requires a separate license from Fish Audio." Research licence, so law 9 blocks it without a negotiated commercial deal. Separately, the model's authorship is Chinese, so law 8 blocks it even if the licence were bought. Best-sounding of the open voices, and not available to us. |
| Coqui XTTS v2 | CPML (non-commercial) | Non-commercial. |

## Chosen but not yet integrated

| Component | Licence | Verdict |
|---|---|---|
| RF-DETR, Apache-designated tiers (Nano, Small, Medium, Large) | Apache 2.0 | Chosen for Stage 3B. US origin (Roboflow), clears the sovereignty law. **The XL and 2XL tiers and the `rfdetr_plus` package are PML 1.0 and are not usable.** See plan section 10, decision 3. |

## Rejected, and why

| Component | Licence | Why not |
|---|---|---|
| Ultralytics YOLOv5 / v8 / v11 / v26 | AGPL-3.0 | Would require open-sourcing the larger work containing it. Incompatible with the closed core. An enterprise licence would lift this and was not taken. |
| RT-DETR (Baidu) | Apache 2.0 | Chinese origin. Sovereignty law. |
| YOLOX (Megvii) | Apache 2.0 | Chinese origin. Sovereignty law. |
| D-FINE (USTC) | Apache 2.0 | Chinese origin. Sovereignty law. |
| LW-DETR (Baidu) | Apache 2.0 | Chinese origin. Sovereignty law. |
| Meta Llama family | Llama Community Licence | Military-use carve-out for non-US and non-allied users. Disqualified by the plan. |

## Open and unverified

| Component | Status |
|---|---|
| Stereolabs ZED SDK, and Terra if used | **Unverified, and the biggest programme risk.** Offline and air-gapped activation terms and per-unit field licensing are not confirmed with Stereolabs. This is a vendor-response-time problem, so it should be raised with them well before Stage 3B needs an answer. Perception sits behind a swappable interface partly because of this. |
| NVIDIA JetPack, CUDA, TensorRT | Not yet verified. Redistribution and embedded-deployment terms need reading before anything ships on a Jetson. |
| **The local language model, whichever it turns out to be** | **Nothing has been chosen and nothing has been verified.** The `deployed` profile needs a local model, and no model or server has cleared law 9. Ollama is a convenient runner and its own licence has not been read; the weights it pulls carry their own terms, separately, and a tag like `mistral:7b-instruct` is not pinned to a revision, so what arrives today and what arrives next month are not necessarily the same licence. Meta Llama is already disqualified above. **Verify a specific model at a specific revision before a deployed target uses one**, and record it here. Until then the air-gapped language path is unproven in licensing as well as in operation. |
