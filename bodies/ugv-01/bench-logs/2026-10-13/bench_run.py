"""Scripted bench phase for ugv-01, driven over SSH with the founder's
spoken go. Opens both boards ONCE, runs the given steps with bounded
pulses, prints a snapshot after each, logs every frame, closes.

  python3 bench_run.py --drive PORT --accel PORT --log FILE step step ...

Steps: snap | wait:MS | light:low | ind:left | horn | gear:N | speed:1 |
       steer:left:MS | steer:stop | brake:apply:MS | brake:release:MS |
       brake:stop | throttle:PCT:MS | throttle:0 | steer_to:DEG | safe
"""
import argparse, json, sys, threading, time
sys.path.insert(0, "/home/tessy_01/argus/drive")
from pilot.hal.drivers.ugv01.controls import LinkError, Refused, Ugv01Controls
from pilot.hal.drivers.ugv01.link import PySerialPort

ap = argparse.ArgumentParser()
ap.add_argument("--drive", required=True); ap.add_argument("--accel", required=True)
ap.add_argument("--log", required=True); ap.add_argument("--max-duty", type=int, default=30)
ap.add_argument("--steer-sense", default=None); ap.add_argument("--brake-on-stop", action="store_true")
ap.add_argument("steps", nargs="*")
a = ap.parse_args()
logf = open(a.log, "a", buffering=1)
def log(kind, **f):
    r = {"ts": time.time(), "kind": kind}; r.update(f); logf.write(json.dumps(r, default=str) + "\n")
def say(*x): print(*x, flush=True)

c = Ugv01Controls(drive_port=PySerialPort(a.drive), accel_port=PySerialPort(a.accel),
                  max_duty=a.max_duty, steer_sense=a.steer_sense, brake_on_stop=a.brake_on_stop,
                  on_line=lambda n, l: log("rx", link=n, line=l),
                  on_tx=lambda n, f: log("tx", link=n, frame=f.decode("ascii", "replace").strip()))
say("opening", a.drive, "and", a.accel)
try:
    c.start()
except LinkError as e:
    say("START FAILED:", e); log("start_failed", error=str(e)); sys.exit(2)
snap = c.snapshot(); log("started", snapshot=snap)
def brief(s):
    return ("drive v%s answering=%s | accel v%s alive=%s duty_acked=%s | steer %s deg (limits %s) | "
            "brake %s deg (limits %s) applied=%s | faults=%s | stop=%s | status=%s") % (
        s["drive"]["firmware"], s["drive"]["answering"], s["accel"]["firmware"], s["accel"]["alive"],
        s["accel"]["duty_acked"], s["steer"]["angle_deg"], s["steer"]["limits_deg"],
        s["brake"]["angle_deg"], s["brake"]["limits_deg"], s["brake"]["applied"], s["faults"],
        s["stop"], s["drive"]["status_raw"])
say("STARTED:", brief(snap))
stop = threading.Event()
silent = threading.Event()      # set: the host says nothing at all (link-loss test)
def ticker():
    while not stop.is_set():
        if not silent.is_set():
            c.heartbeat(); c.tick()
        time.sleep(0.05)
threading.Thread(target=ticker, daemon=True).start()

def run(step):
    p = step.split(":"); op = p[0]; arg = p[1] if len(p) > 1 else None
    ms = int(p[2]) if len(p) > 2 else None
    before = c.snapshot(); log("step", step=step, before=before); err = None
    try:
        if op == "snap": pass
        elif op == "status": c.read_status()
        elif op == "expect":
            # abandon the list unless the last STATUS reply contains this text
            if arg not in (c.snapshot()["drive"]["status_raw"] or ""):
                err = "expected %s in status, got %s" % (arg, c.snapshot()["drive"]["status_raw"])
        elif op == "wait": time.sleep(int(arg) / 1000.0)
        elif op == "light": c.light(arg)
        elif op == "ind": c.indicator(arg)
        elif op == "horn": c.horn()
        elif op == "gear": c.gear(arg)
        elif op == "speed": c.speed_mode(int(arg))
        elif op == "steer":
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
        elif op == "throttle_hold":
            c.set_throttle(int(arg))          # held until a later throttle:0 or the silence test
        elif op == "silence":
            # the host goes quiet: no heartbeat, no tick, no poll, no probe, ports
            # left open. What the boards do now is what they do when the
            # computer dies. The human at the key is the only stop.
            say("HOST SILENT for %d ms: nothing is sent, watch the wheels" % int(arg))
            log("silence_begin", ms=int(arg)); silent.set()
            time.sleep(int(arg) / 1000.0)
            silent.clear(); log("silence_end")
            c.set_throttle(0)
        elif op == "steer_to": c.steer_to(float(arg))
        elif op == "safe": c.safe_stop()
        else: err = "unknown step"
    except (Refused, ValueError) as e:
        err = str(e)
    time.sleep(0.6)
    after = c.snapshot(); log("after", step=step, refused=err, after=after)
    say(("REFUSED " + err + " | ") if err else "", "after", step, "->", brief(after))
    global last_err; last_err = err

last_err = None
try:
    for s in a.steps:
        run(s)
        if c.snapshot()["faults"] or (s.startswith("expect:") and last_err):
            say("ABANDONED after", s, "faults:", c.snapshot()["faults"], "reason:", last_err); log("abandoned", step=s, faults=c.snapshot()["faults"], reason=last_err)
            break
finally:
    stop.set()
    say("closing (stop first)"); c.close(); log("closed", snapshot=c.snapshot())
    say("CLOSED:", brief(c.snapshot()))
