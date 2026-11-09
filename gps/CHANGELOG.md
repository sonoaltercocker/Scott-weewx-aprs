# DigiPi GPS Position Updater — Changelog

What changed in each version, and why. Newest first.

---

## 1.6 — 2026-11-08

### WeeWX altitude: off by default, and only from an accurate reading

**What changed**

- New setting `update-altitude`, **off** by default. Latitude and longitude are still updated in every file, including WeeWX; the altitude in WeeWX is left as you set it.
- When `update-altitude` is turned on, an altitude reading is used only from a 3D fix whose estimated vertical error, as reported by gpsd, is at most `alt-max-error` metres (default 15). Most readings must pass; otherwise the altitude is left alone and the log says why.

**Why**

In the first real-world test, indoors with only 4 satellites in use, the GPS reported the altitude as 300 m one minute and 333 m three minutes later. The station is at 901 ft (275 m). The 333 m reading was over the 30 m threshold, so version 1.5 changed WeeWX's altitude from 901 ft to 1,093 ft. WeeWX uses the altitude to work out sea-level pressure, so that error would have made the barometer reading about 0.2 inHg wrong.

GPS altitude is much less accurate than GPS position, especially with few satellites or a poor view of the sky. Most stations stay at about the same height when they are moved, and their altitude is better taken from a map or a survey. So the altitude is no longer changed unless asked for, and when it is, poor readings are ignored.

### The GPS device is set by its permanent name

**What changed**

- The installer asks gpsd which device it has recognised as the GPS. If `/etc/default/gpsd` names that device by a number, such as `/dev/ttyACM1`, it is switched to the device's permanent `/dev/serial/by-id/…` name. The old line is kept, commented out.
- Nothing is changed unless gpsd confirms which device is the GPS. One exception is left alone: DigiPi's own workaround for an IC-705 on a Pi Zero 2 or 3A+.
- The same check can be run any time with `sudo digipi-gps-position.py --set-gps-device`, for example after plugging in a different GPS.

**Why**

The test DigiPi has two USB serial devices: an AIOC radio cable and a u-blox 7 GPS. Linux numbers them `ttyACM0` and `ttyACM1` in the order it finds them, and that order can change after a reboot or replugging. If the numbers swap, gpsd reads the radio cable instead of the GPS, and the position is never updated — a fault that is easy to miss and hard to diagnose. The permanent name always means the same device.

### Smaller changes

- **The installer says whether the watcher is running.** On a first install it doesn't start until the next boot, and the installer now says so and shows how to start it straight away. *Why:* in testing, `--status` showed the service as "inactive" right after installing, which looked like a fault.
- **The history no longer shows an altitude that wasn't written.** *Why:* with altitude updates off, a GPS altitude on the history line would suggest WeeWX had been changed.
- The NMEA relay and service files are unchanged apart from their version number, so all files in the set carry the same version.

---

## 1.5 — 2026-11-06

**What changed**

- After the boot check, the program **keeps watching** the GPS. Once the station has been parked at a new place for `settle-minutes` (10), it updates everything once. While moving, or parked where the files already say, it does nothing.
- If an **AX.25 connection** is in progress when an update is due (a Winlink session or a node user), the update waits until it has finished, at most `busy-wait` minutes (10), then goes ahead anyway.
- Two **optional features**, installed but off: live beacons with Direwolf SmartBeaconing (`--enable live-beacons`), and GPS data for Winlink Express on the LAN on port 2948 (`--enable lan-nmea`). `--disable` reverses either one exactly.
- **Settings by command** (`--set`, `--status`), kept in `/etc/digipi-gps-position.conf` so they survive upgrades.
- The previous version of each changed file is kept as `<file>.gps-backup`.

**Why**

- *Watcher:* until 1.5, a station moved while switched on kept its old position until the next reboot. Waiting for the station to settle avoids rewriting files and restarting programs again and again while it is being driven.
- *Waiting for connections:* updating restarts the running DigiPi mode, which would cut off a Winlink message being sent through the gateway. Traffic is sporadic and sessions are short, so a short wait costs little. The limit is there because a dead AX.25 connection can look "connected" for a long time; it doesn't block other stations, so there is no reason to wait for it indefinitely. 10 minutes was chosen over 30 as long enough for a normal session.
- *Live beacons:* the boot-time update can't make beacons follow a station while it's moving; only Direwolf, reading the GPS itself, can. SmartBeaconing beacons often while moving and rarely when parked. It is off by default because a station with no GPS fix then sends no beacon at all, and because a parked station's beacons would show GPS wander.
- *LAN feed:* lets laptops in a comms trailer take their position from the DigiPi's GPS. Unlike the original relay, gpsd itself stays reachable only from the Pi; only port 2948 is opened. Off by default because anyone on the network can read the station's position from it.
- *Settings by command:* editing the program would be overwritten by the next version.
- *Backups:* a hand fallback if a change ever needs undoing. Only the latest copy is kept, so the SD card doesn't fill up.

---

## 1.4 — 2026-11-06

**What changed**

- The position is also checked **each time RMS gateway mode starts**, through a drop-in for DigiPi's `winlinkrms.service` (DigiPi's own file isn't edited). It waits at most 30 seconds for a fix and never stops RMS from starting.
- RMS gateway files are updated in both `/usr/local/etc/rmsgw/` and `/etc/rmsgw/`, whichever exist. Symlinks are followed, so each real file is edited once and links stay links. `GRIDSQUARE = …` with spaces is accepted.

**Why**

Scott Curie, NS7C, runs DigiPi RMS gateways in ARES communications trailers. His guides showed that some DigiPi images keep the RMS files in `/etc/rmsgw/`, which 1.3 didn't look at, and that some of the files are symlinks, which 1.3 would have replaced with plain files. His approach of updating the grid just before RMS registers with Winlink also catches a move without a reboot. Folding his RMS work into this add-on means users install one set of scripts instead of two.

---

## 1.3 — 2026-11-06

**What changed**

- A **position history** in `/home/pi/gps-position-history.txt`: an `installed` line from the installer, and one line for each change, with the new position, grid square, and how far the station moved and from where.

**Why**

The test procedure told readers to note the current values before moving the station, which meant writing them down by hand. The history keeps that record automatically, and survives reboots, unlike the system journal, which DigiPi usually keeps only in memory.

---

## 1.2 — 2026-11-06

**What changed**

- WeeWX's saved position is checked as well as DigiPi's. If either is more than 100 m from the GPS, both are updated.
- The version is shown in the log and with `--version`.

**Why**

Re-running a WeeWX setup script resets WeeWX's position to its own typed-in values. 1.1 compared the GPS only with DigiPi's position, so it would have left WeeWX wrong for good.

---

## 1.1 — 2026-11-06

**What changed**

- Detects whether WeeWX is installed and says so in the log and the installer.

**Why**

DigiPi and WeeWX are separate programs, and many DigiPi stations don't run WeeWX. The same files must work with or without it, without the user having to configure anything.

---

## 1.0 — 2026-11-06

First release.

**Why**

DigiPi asks for the station's position once, at Initialize, and copies it into about a dozen config files. A station that is set up on the bench and then deployed elsewhere, or moved from place to place, keeps telling the world it is at the old address: in APRS beacons, the Winlink gateway listing, WSJT-X and JS8Call, the DigiPi display, and WeeWX. Version 1.0 reads the GPS at every boot and, if the station has moved more than 100 m, updates the position in all of them.

---

*Scott Sheppard, KJ4ZZB*
