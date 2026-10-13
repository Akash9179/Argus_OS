# Reference material from the Jetson, 13 Oct 2026

What a session needs to work on ugv-01 without the Jetson being on. Our
own evidence is here; the team's material stays outside git.

| File | What it is |
|---|---|
| `inv0.out` to `inv4.out` | The read-only inventory outputs: identity, processes, port owners, udev, services, USB, camera modules, ZED SDK, network, the team's workspace layout, the ROS graph, camera topics. |
| `front_snapshot.jpg`, `front_safe.jpg` | The front ZED X colour frame and the team's drivable-area view at 20:16 IST (a sheet 1.4 m ahead, called STOP). |
| `pilot_build.log` | The PILOT container image build on the Jetson (arm64, 173 s). |
| `pilot_run.log`, `pilot_run_prefix_argus.log` | PILOT's first two boots on the Jetson: simulated drivers, registry served, MQTT link up; the second, with `--prefix argus`, registered in TRACK. |
| `zed_x_daemon.log` | The ZED X daemon's journal (no errors). |

The bench frames are in `../../bench-logs/2026-10-13/`.

Kept outside both repos, on the founder's Mac at
`~/Projects/Argus/_reference/ugv-01-team-2026-10-13/`, because it is the
team's own work: the drive module's spec PDF (4.1.3, written by Gulshan
Shah), a verbatim copy of their `serial_control` ROS 2 package (their
encoders and serial node, with their observations of what the boards
accept), a git bundle and source archive of their whole `ros2_new`
workspace, and their stack's log from 13 Oct.

Still needed from Gulshan and not on the Jetson: the firmware source for
both boards.
