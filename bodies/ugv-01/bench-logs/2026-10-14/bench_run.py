"""Scripted bench phase for ugv-01, 14 Oct 2026: the silence re-test with
the watchdog firmware (Nano AC 1.3, drive module 4.1.5). Driven over SSH
from the founder's Mac, Gulshan at the key, drive wheels on jacks. Opens
both boards ONCE, runs the given steps, prints a snapshot after each,
logs every frame, closes with a stop. Exit status 0 only if every step
ran and every expectation held.

  python3 bench_run.py --drive PORT --accel PORT --log FILE [--max-angle-step DEG] step ...

Steps: snap | status | readback | wait:MS | expect:TEXT | clear |
       light:low | ind:left | horn | gear:D | speed:1 |
       steer:left:MS | steer:stop | brake:apply:MS | brake:release:MS |
       brake:stop | throttle:PCT:MS | throttle:0 |
       throttle_silence:PCT:MS | steer_silence:DIR:MS | safe

The two silence steps (shaped by Codex Astra's two reviews of the plan):
  throttle_silence:PCT:MS  duty PCT sent and acknowledged (0x02;OK;PCT
       seen on the wire), then the host says nothing for MS: no
       heartbeat, no tick, no poll, no probe, ports open. The ticker
       confirms it is quiet before silence_begin is logged. When the
       silence ends the FIRST frame is the AC 1.3 read-back (0x03), so
       the board's own duty and timeout count are seen before the host
       touches the throttle. Then the host ALWAYS requests a stop (duty
       zero, brake actuator stop, steering stop), whatever the read-back
       said, inside a finally, and only then does the ticker resume.
       Pass on the wire: the fault list is exactly ["accel board took a
       timeout on its own (N)"] with N one more than before. Anything
       else, including no fault, is a FAIL.
  steer_silence:DIR:MS     steering DIR sent and acknowledged, then
       silence as above. The drive module is expected to print
       0x00;WD;TIMEOUT on its own; the reader thread hands it to the
       controls, which fault and stop at once (that stop is logged after
       the notice). After the silence the host requests a stop again
       regardless. Pass on the wire: fault list exactly ["drive module
       WD TIMEOUT: it stopped its actuators itself"] AND a fresh STATUS
       whose WD count is one above the count before the step. The step
       refuses to start unless the live angle leaves room toward the
       limit in that direction for the whole interval: MS plus 0.9 s
       (command latency, ticker quiescence, ack drain, a stale 5 Hz
       sample, stop latency) at 70 deg/s, plus 10 deg.
  A plain steer:DIR:MS step also checks room: (MS + 0.25 s) at 70 deg/s
       plus 5 deg.
  --max-angle-step  the controls' plausibility step (default 30 deg).
       A steering move across a silence of 800 ms is about 54 deg, which
       the default would reject for good (the last good reading never
       updates). Run 2 passes 120 for that reason, and uses no horn.

After a silence step passes, its fault stays latched in the controls
until `clear`. Read-only steps in between (snap, status, readback,
wait, expect) must see exactly that fault and nothing more; any new
fault abandons. `clear` first requires the last stop batch acknowledged
and compares the faults once more, then clears, sends duty zero and
waits for its acknowledgement. Any REFUSED step, any fault outside the
expected one, or a logging failure abandons the list; the process
closes with a stop regardless and exits 1.

Claims this runner can support: the board reported its own trip and
rested its output as read back over serial, consistent with what the
human saw. It cannot time the physical stop; that needs a meter on the
output and is the electrical gate in README-WATCHDOG.md.
"""
import argparse, collections, json, sys, threading, time
sys.path.insert(0, "/home/tessy_01/argus/drive")
from pilot.hal.drivers.ugv01.controls import LinkError, Refused, Ugv01Controls
from pilot.hal.drivers.ugv01.link import PySerialPort
from pilot.hal.drivers.ugv01 import protocol as p

ap = argparse.ArgumentParser()
ap.add_argument("--drive", required=True); ap.add_argument("--accel", required=True)
ap.add_argument("--log", required=True); ap.add_argument("--max-duty", type=int, default=30)
ap.add_argument("--steer-sense", default="left_increases"); ap.add_argument("--brake-on-stop", action="store_true")
ap.add_argument("--max-angle-step", type=float, default=30.0)
ap.add_argument("steps", nargs="*")
a = ap.parse_args()

log_broken = []
logf = open(a.log, "a", buffering=1)
def log(kind, **f):
    r = {"ts": time.time(), "kind": kind}; r.update(f)
    try:
        logf.write(json.dumps(r, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log_broken.append("%s: %s" % (kind, e))
def say(*x):
    try:
        print(*x, flush=True)
    except Exception:  # noqa: BLE001
        pass

rx = collections.deque(maxlen=400)          # (ts, link, line) every decoded line
rx_count = [0]
def on_line(n, l):
    rx_count[0] += 1; rx.append((time.time(), n, l)); log("rx", link=n, line=l)
def on_tx(n, f):
    log("tx", link=n, frame=f.decode("ascii", "replace").strip())

def saw_line(prefix, link, since_count, timeout=1.0):
    """True once a line on `link` starting with `prefix` has arrived after
    the rx count was `since_count`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        seen = list(rx)[-(rx_count[0] - since_count):] if rx_count[0] > since_count else []
        for _, n, l in seen:
            if n == link and l.strip().upper().startswith(prefix.upper()):
                return True
        time.sleep(0.02)
    return False

def wd_count(status_raw):
    if not status_raw:
        return None
    for part in status_raw.split(","):
        if part.startswith("WD="):
            try:
                return int(part[3:], 16)
            except ValueError:
                return None
    return None

def fresh_status(timeout=1.0):
    """Send STATUS and wait for ITS reply. Returns status_raw or None."""
    n0 = rx_count[0]
    c.read_status()
    if not saw_line("0x%02X;OK" % p.STATUS, "drive", n0, timeout):
        return None
    time.sleep(0.05)
    return c.snapshot()["drive"]["status_raw"]

c = Ugv01Controls(drive_port=PySerialPort(a.drive), accel_port=PySerialPort(a.accel),
                  max_duty=a.max_duty, steer_sense=a.steer_sense, brake_on_stop=a.brake_on_stop,
                  max_angle_step_deg=a.max_angle_step, on_line=on_line, on_tx=on_tx)
say("opening", a.drive, "and", a.accel)
log("started", args=vars(a))
try:
    c.start()
except LinkError as e:
    say("START FAILED:", e); log("start_failed", error=str(e))
    try: c.close()
    finally: sys.exit(2)
snap = c.snapshot(); log("open", snapshot=snap)
def brief(s):
    return ("drive v%s | accel v%s readback=%s alive=%s duty acked %s read %s timeouts %s | steer %s deg | "
            "brake %s deg | faults %s | stop=%s | status=%s") % (
        s["drive"].get("firmware"), s["accel"].get("firmware"), s["accel"].get("read_back"),
        s["accel"].get("alive"), s["accel"].get("duty_acked"), s["accel"].get("duty_read"),
        s["accel"].get("timeouts"), s["steer"]["angle_deg"], s["brake"]["angle_deg"],
        s["faults"], s["stop"], s["drive"]["status_raw"])
say("STARTED:", brief(snap))

stop = threading.Event()
silent = threading.Event()      # set: the host says nothing at all
quiet = threading.Event()       # set by the ticker once it has seen `silent`
def ticker():
    while not stop.is_set():
        if silent.is_set():
            quiet.set()
        else:
            quiet.clear()
            c.heartbeat(); c.tick()
        time.sleep(0.05)
threading.Thread(target=ticker, daemon=True).start()

ACCEL_TO = "accel board took a timeout on its own (%d)"
DRIVE_WD = "drive module WD TIMEOUT: it stopped its actuators itself"
SPEED = 70.0                    # deg/s steering, measured 67 on 13 Oct

def go_silent(ms):
    """Pause the ticker, confirm it is quiet, let pending acks land, then
    say nothing for ms. Returns with the ticker still paused."""
    silent.set()
    if not quiet.wait(0.2):
        raise ValueError("ticker did not go quiet")
    time.sleep(0.15)
    say("HOST SILENT for %d ms: nothing is sent. WATCH THE WHEELS AND THE STEERING." % ms)
    log("silence_begin", ms=ms, snapshot=c.snapshot())
    time.sleep(ms / 1000.0)
    log("silence_end")

def end_silence():
    """First frame after silence: the Nano read-back. Then the host
    requests a stop whatever it saw, inside a finally. Then the ticker
    resumes."""
    try:
        try:
            c.read_accel()
        except (Refused, ValueError) as e:
            log("readback_refused", error=str(e))
        time.sleep(0.3)
    finally:
        c.safe_stop()
        log("host_stop", why="after silence, unconditional", snapshot=c.snapshot())
        time.sleep(0.3)
        silent.clear()

def room_toward(direction):
    s = c.snapshot()
    ang, lim = s["steer"]["angle_deg"], s["steer"]["limits_deg"]
    if ang is None or not lim:
        return None, "no angle or limits"
    toward_hi = (direction == "left") == (a.steer_sense == "left_increases")
    room = (lim[1] - ang) if toward_hi else (ang - lim[0])
    return room, "angle %.1f, room %.1f deg toward the %s limit" % (ang, room, "upper" if toward_hi else "lower")

def need_room(ms, extra_s, pad):
    return (ms / 1000.0 + extra_s) * SPEED + pad

def wait_stop_acked(timeout=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if c.snapshot()["stop"]["acked"]:
            return True
        time.sleep(0.05)
    return False

allowed = []                    # faults verified by a silence step, latched until clear

def run(step):
    """Returns (refused_text_or_None, expected_faults_or_None)."""
    err = None; expected = None
    before = c.snapshot(); log("step", step=step, before=before)
    try:
        parts = step.split(":"); op = parts[0]; arg = parts[1] if len(parts) > 1 else None
        ms = int(parts[2]) if len(parts) > 2 else None
        if op == "snap": pass
        elif op == "status":
            if fresh_status() is None: err = "STATUS not answered"
        elif op == "readback": c.read_accel()
        elif op == "clear":
            if not wait_stop_acked():
                raise ValueError("clear refused: last stop batch not acknowledged")
            if c.snapshot()["faults"] != allowed:
                raise ValueError("clear refused: faults %s are not the verified %s" % (c.snapshot()["faults"], allowed))
            say("CLEAR: the human says the vehicle is safe; latch cleared, duty zero sent")
            c.clear_faults(); allowed.clear()
            deadline = time.time() + 1.5
            while time.time() < deadline and not c.snapshot()["accel"]["alive"]:
                time.sleep(0.05)
            if not c.snapshot()["accel"]["alive"]:
                err = "clear: duty zero not acknowledged"
        elif op == "expect":
            st = fresh_status()
            if st is None: err = "STATUS not answered"
            elif arg not in st: err = "expected %s in a fresh STATUS, got %s" % (arg, st)
        elif op == "wait": time.sleep(int(arg) / 1000.0)
        elif op == "light": c.light(arg)
        elif op == "ind": c.indicator(arg)
        elif op == "horn": c.horn()
        elif op == "gear": c.gear(arg)
        elif op == "speed": c.speed_mode(int(arg))
        elif op == "steer":
            if arg != "stop":
                room, why = room_toward(arg)
                need = need_room(ms or 300, 0.25, 5.0)
                if room is None or room < need:
                    raise ValueError("steer refused by the bench: %s, need %.1f" % (why, need))
            c.steer(arg)
            if arg != "stop":
                time.sleep((ms or 300) / 1000.0); c.steer("stop")
        elif op == "brake":
            c.brake(arg)
            if arg != "stop":
                time.sleep((ms or 300) / 1000.0); c.brake("stop")
        elif op == "throttle":
            c.set_throttle(int(arg))
            if int(arg) > 0:
                time.sleep((ms or 1000) / 1000.0); c.set_throttle(0)
        elif op == "throttle_silence":
            t0 = before["accel"]["timeouts"]
            if t0 is None:
                raise ValueError("timeout count unknown before silence (read-back never answered)")
            pct = min(int(arg), a.max_duty)
            n0 = rx_count[0]
            c.set_throttle(int(arg))
            if not saw_line("0x02;OK;%02X" % pct, "accel", n0, 0.5):
                raise ValueError("duty %d not acknowledged on the wire" % pct)
            go_silent(ms or 1500)
            end_silence()
            expected = [ACCEL_TO % (t0 + 1)]
        elif op == "steer_silence":
            room, why = room_toward(arg)
            need = need_room(ms or 1000, 0.9, 10.0)
            if room is None or room < need:
                raise ValueError("steer_silence refused by the bench: %s, need %.1f" % (why, need))
            say("steering margin:", why, "need %.1f" % need)
            wd0 = wd_count(fresh_status())
            if wd0 is None:
                raise ValueError("WD count unknown before silence")
            n0 = rx_count[0]
            c.steer(arg)
            if not saw_line("0x05;OK;%02X" % p._STEER[arg], "drive", n0, 0.5):
                raise ValueError("steer %s not acknowledged on the wire" % arg)
            go_silent(ms or 1000)
            end_silence()
            wd1 = wd_count(fresh_status())
            log("wd_count", before=wd0, after=wd1)
            if wd1 != wd0 + 1:
                err = "WD count %s, expected %d" % (wd1, wd0 + 1)
            expected = [DRIVE_WD]
        elif op == "safe": c.safe_stop()
        else: err = "unknown step"
    except (Refused, ValueError) as e:
        err = str(e)
    time.sleep(0.6)
    after = c.snapshot(); log("after", step=step, refused=err, expected_faults=expected, after=after)
    say(("REFUSED " + err + " | ") if err else "", "after", step, "->", brief(after))
    return err, expected

failed = None
try:
    for s in a.steps:
        err, expected = run(s)
        faults = c.snapshot()["faults"]
        if err:
            failed = "refused or failed: %s" % err
        elif expected is not None:
            if faults != expected:
                failed = "silence step: faults %s, expected exactly %s" % (faults, expected)
            else:
                allowed[:] = expected
                say("SILENCE STEP PASSED on the wire:", faults, "(the human's eyes decide the rest)")
                log("silence_pass", step=s, faults=faults)
        elif faults != allowed:
            failed = "unexpected fault: %s (allowed %s)" % (faults, allowed)
        if log_broken:
            failed = (failed + "; " if failed else "") + "log failed: %s" % log_broken[0]
        if failed:
            say("ABANDONED after", s, "|", failed)
            log("abandoned", step=s, faults=faults, reason=failed)
            break
finally:
    stop.set()
    try:
        c.close()
    finally:
        log("closed", snapshot=c.snapshot(), failed=failed)
        say("CLOSED:", brief(c.snapshot()))
sys.exit(1 if failed else 0)
