#!/usr/bin/env python3
"""Listen-only capture of whatever the ugv-01 MCU emits on serial.

    ############################################################
    #  DO NOT RUN THIS UNLESS BOTH ARE TRUE:                   #
    #                                                          #
    #    1. DRIVE POWER IS ISOLATED, or the drive wheels are   #
    #       off the ground.                                    #
    #    2. A HUMAN IS PRESENT AT THE VEHICLE.                 #
    #                                                          #
    #  This machine is a Jeep-chassis UGV that can move.       #
    ############################################################

WHAT THIS DOES
    Opens the MCU serial port, reads, and writes the traffic to a log.
    It never transmits. There is no code path in this file that calls
    write(), and the port object is wrapped at runtime so that any attempt
    to write raises instead of reaching the wire (see _NoWrite).

WHY IT IS STILL NOT RISK-FREE  (read this before running)
    Opening a serial port is not a purely passive act. On boards with the
    usual auto-reset circuit, the FTDI adapter's DTR line is wired to the
    MCU's reset pin through a capacitor, so asserting DTR reboots the MCU.
    The adapter on this vehicle is an FTDI FT232R (S/N A5069RR4).

    This script sets dtr=False and rts=False on the port object BEFORE
    calling open(), which is the best mitigation available from Python.
    It is a mitigation, not a guarantee: the kernel's tty layer may still
    momentarily assert the modem lines during open(), and pyserial applies
    its line-state configuration immediately after the file descriptor is
    created, not before.

    If the MCU resets when you run this, that is the known failure mode and
    not a surprise. It matters because the vehicle's power-on behaviour is
    UNKNOWN - no firmware source has ever been found on the Jetson. That is
    exactly why rule 1 above is not optional.

    A stronger mitigation, if you have root and want it, is to clear HUPCL
    on the port first so the line is not dropped on close:

        stty -F /dev/ttyUSB0 -hupcl

    Run that once before the first open, in the same session.

USAGE
    python3 listen.py                          # /dev/ttyUSB0 @ 115200, Ctrl-C to stop
    python3 listen.py --seconds 60             # stop by itself after a minute
    python3 listen.py --out capture.log        # choose the log path
    python3 listen.py --device /dev/ttyUSB1

OUTPUT
    Every decoded line is printed and logged with a wall-clock timestamp and
    a monotonic offset from start. The raw bytes are logged as hex alongside
    the text, so a non-ASCII or non-newline framing is not lost - if the MCU
    turns out to speak binary, the hex column is the record that survives.

    Bytes that never terminate in a newline are flushed to the log as a
    PARTIAL record when the capture ends, so a framing that does not use \\n
    still leaves evidence rather than vanishing from the buffer.

WHAT TO LOOK FOR AFTERWARDS
    - Does the MCU speak unprompted at all, or only in reply to commands?
    - Battery, pedal positions, gear state, speed, steering angle. The ROS
      console already scans for `steer=` / `steering=` / `angle=` and
      `heading=` / `hdg=`, so those spellings are worth grepping for first.
    - Anything containing ERR, FAULT or ALERT - cmd_node.py treats those
      substrings as alert triggers.
    - The framing itself: line-oriented ASCII, or something else.

Written during the 2026-08-11 survey. NOT RUN by the survey agent - the
survey opened no serial port at all. This exists so the bench session can
start with a reviewed tool instead of improvising one at the vehicle.
"""

import argparse
import datetime
import signal
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial is not installed. Install with: python3 -m pip install --user pyserial")


DEFAULT_DEVICE = '/dev/ttyUSB0'   # FTDI FT232R, S/N A5069RR4 - the only USB serial device on this machine
DEFAULT_BAUD = 115200             # from bridge.py's default and the Go bridge's hardcoded config


class _NoWrite:
    """Wraps a Serial object and makes every transmit path raise.

    Belt and braces: this file already contains no write call, but the MCU
    protocol is unknown and the vehicle can move, so a stray write must fail
    loudly rather than reach the wire.
    """

    _BLOCKED = ('write', 'writelines', 'write_timeout', 'send_break',
                'sendBreak', 'flushOutput', 'reset_output_buffer')

    def __init__(self, port):
        object.__setattr__(self, '_port', port)

    def __getattr__(self, name):
        if name in self._BLOCKED:
            raise RuntimeError(
                'listen.py attempted to %s() on the MCU port. This script is '
                'listen-only by design; refusing.' % name)
        return getattr(object.__getattribute__(self, '_port'), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, '_port'), name, value)


def open_listen_only(device, baud, read_timeout=0.2):
    """Open the port with the modem control lines held low.

    Configure-then-open matters: setting dtr/rts on an unopened Serial
    object stores the intent, so pyserial applies them as part of bringing
    the port up rather than after the MCU has already seen DTR asserted.
    """
    port = serial.Serial()
    port.port = device
    port.baudrate = baud
    port.timeout = read_timeout

    # Suppress the auto-reset pulse as far as Python allows. See the module
    # docstring - this is a mitigation, not a guarantee.
    port.dtr = False
    port.rts = False

    port.open()

    # Discard anything the driver buffered while the port was coming up; it
    # may be a fragment of a line that started before we were listening.
    try:
        port.reset_input_buffer()
    except Exception:  # noqa: BLE001 - never let cleanup abort a capture
        pass

    return _NoWrite(port)


def main():
    ap = argparse.ArgumentParser(
        description='Listen-only MCU serial capture for ugv-01. Never transmits.')
    ap.add_argument('--device', default=DEFAULT_DEVICE, help='serial device (default: %(default)s)')
    ap.add_argument('--baud', type=int, default=DEFAULT_BAUD, help='baud rate (default: %(default)s)')
    ap.add_argument('--out', default=None,
                    help='log file path (default: mcu-capture-<timestamp>.log in the cwd)')
    ap.add_argument('--seconds', type=float, default=None,
                    help='stop automatically after this many seconds (default: run until Ctrl-C)')
    args = ap.parse_args()

    stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
    out_path = args.out or ('mcu-capture-%s.log' % stamp)

    print('listen.py - LISTEN ONLY, never transmits', flush=True)
    print('  device : %s @ %d baud' % (args.device, args.baud), flush=True)
    print('  log    : %s' % out_path, flush=True)
    print('  Confirm drive power is isolated and a human is present.', flush=True)
    print('  Ctrl-C to stop.\n', flush=True)

    try:
        port = open_listen_only(args.device, args.baud)
    except serial.SerialException as err:
        sys.exit('could not open %s: %s\n'
                 'If this is a permissions error, the port is root:dialout 0660 - '
                 'check membership with: getent group dialout' % (args.device, err))

    stopping = {'now': False}

    def _stop(signum, frame):  # noqa: ARG001
        stopping['now'] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    started = time.monotonic()
    lines = 0
    total_bytes = 0
    buf = bytearray()

    with open(out_path, 'w', encoding='utf-8') as log:
        log.write('# ugv-01 MCU listen-only capture\n')
        log.write('# device=%s baud=%d started=%s\n'
                  % (args.device, args.baud, datetime.datetime.now().isoformat()))
        log.write('# columns: <wall clock> <+seconds since start> <TEXT|PARTIAL> <decoded> | hex=<raw bytes>\n')
        log.flush()

        def emit(kind, raw):
            nonlocal lines
            lines += 1
            now = datetime.datetime.now().isoformat(timespec='milliseconds')
            offset = time.monotonic() - started
            text = raw.decode('utf-8', 'replace').rstrip('\r')
            record = '%s +%08.3f %-7s %s | hex=%s' % (now, offset, kind, text, raw.hex(' '))
            print(record, flush=True)
            log.write(record + '\n')
            log.flush()   # flush per line: a capture that dies mid-session keeps what it saw

        try:
            while not stopping['now']:
                if args.seconds is not None and (time.monotonic() - started) >= args.seconds:
                    break

                try:
                    chunk = port.read(port.in_waiting or 1)
                except serial.SerialException as err:
                    print('\nserial error: %s' % err, flush=True)
                    log.write('# serial error: %s\n' % err)
                    break

                if not chunk:
                    continue

                total_bytes += len(chunk)
                buf.extend(chunk)

                while b'\n' in buf:
                    line, _, rest = buf.partition(b'\n')
                    buf = bytearray(rest)
                    emit('TEXT', bytes(line))

        finally:
            # Anything left unterminated is evidence too - a framing that does
            # not use \n would otherwise be invisible.
            if buf:
                emit('PARTIAL', bytes(buf))

            elapsed = time.monotonic() - started
            summary = ('\ncaptured %d records, %d bytes, over %.1f s -> %s'
                       % (lines, total_bytes, elapsed, out_path))
            if total_bytes == 0:
                summary += ('\nNOTE: the MCU sent nothing at all. That is a finding: either it '
                            'only speaks when spoken to, it is unpowered, the baud rate is wrong, '
                            'or it is not on this port.')
            print(summary, flush=True)
            log.write('# %s\n' % summary.strip().replace('\n', '\n# '))

            try:
                port.close()
            except Exception:  # noqa: BLE001
                pass


if __name__ == '__main__':
    main()
