# DigiPi GPS Position Updater

When a DigiPi installation is performed, it is assumed the Raspberry Pi will not be moved from its initial installed position. This is often not a true assumption and thus automated tools are needed to update position information if the DigiPi is moved. This document describes an add-on that reads the GPS every time the Pi starts. If the station has moved, it updates the position everywhere DigiPi keeps it, and in WeeWX too if WeeWX is installed. Nothing needs to be done when you move the station except power it up where the GPS can see the sky.

**Version:** 1.6 — see `CHANGELOG.md` for what changed in each version, and why.

**Works on:** any Raspberry Pi running DigiPi, with a GPS receiver that DigiPi's `gpsd` can read.

**WeeWX:** optional. With WeeWX installed its position is kept up to date as well; without it, only DigiPi is updated. The same files work either way.

---

## Why GPS updates are needed

DigiPi asks for your latitude, longitude and grid square **once**, when you press **Initialize** on its setup page. It copies them into a dozen config files and never looks at them again. DigiPi's own notes advise against running Initialize a second time, so after a move the only way to correct the position is to edit those files by hand, on a read-only filesystem, without missing one.

That is fine for a station that never moves. A DigiPi that goes portable, to a field day, an emergency deployment or a new weather site, keeps telling the world it is still at the old address:

- **APRS beacons** from the digipeater and iGate modes put the station on [aprs.fi](https://aprs.fi) and other maps at the old position. Other operators judge coverage and paths from that.
- **Winlink.** The RMS gateway's listing and Pat's position use the grid square. Winlink users choose a gateway by its location.
- **WSJT-X and JS8Call** send your grid square in every exchange, and other stations log it.
- **The DigiPi display** works out the distance and bearing to each station heard from your position, so all of those figures are wrong.
- **WeeWX**, if installed, stamps its weather reports with the station's position, so the APRS weather beacon shows the weather at the wrong place. WeeWX can also use the altitude when it works out sea-level barometric pressure.

In the field there is often no internet to look up coordinates either. A GPS already knows where the station is; this add-on simply copies that into every place DigiPi and WeeWX need it, at every boot.

---

## How it works

1. You flash and **initialize DigiPi as normal**, typing in a position on the setup page.
2. You install this add-on once (below).
3. At **every boot**, a service starts in the background and waits for the GPS to get a fix (up to 10 minutes). It takes 10 readings and uses the middle one.
4. It compares the GPS with the position saved in DigiPi, and in WeeWX if installed. If the GPS position appears to have changed by more than **100 m**, the script will:
   - stop the DigiPi mode that is running (TNC, digipeater, Winlink and so on),
   - write the new position into every file listed below, keeping the previous version of each as a backup,
   - start that mode again and restart WeeWX if it is running.
5. It then **keeps watching** the GPS. While the station is moving, it changes nothing. Once the station has been parked at a new place for **10 minutes**, it updates the files the same way. No reboot is needed.
6. It records each change in the system log, and adds a line to the position history file, `/home/pi/gps-position-history.txt`.

Because it runs in the background, a slow GPS never holds up the rest of the boot. Until the fix arrives, the station uses the position it had before.

**Also when the RMS gateway starts.** Each time Winlink RMS gateway mode is selected, the same check runs first, waiting at most 30 seconds for a fix. The gateway then registers with Winlink using the current grid square, even after a move without a reboot. If there is no fix, RMS starts with the grid it had, and a problem in this step never stops RMS from starting.

**Waiting for a Winlink session to finish.** If an AX.25 connection is in progress when an update is due, such as a Winlink session through the RMS gateway or a node user, the update waits until it has finished. It waits at most **10 minutes**, then goes ahead anyway, in case the connection is stuck. A stuck connection doesn't stop other stations from connecting, and Linux drops it on its own after a few minutes.

### What gets updated

| Program | File | Setting |
|---|---|---|
| Direwolf (TNC, digipeater, iGate modes) | `/home/pi/direwolf*.conf` | `lat=` and `long=` on the `PBEACON` lines |
| DigiPi display and start scripts | `/home/pi/localize.env` | `NEWLAT`, `NEWLON`, `NEWGRID` (and the matching `OLD...` lines) |
| APRSD web chat | `/home/pi/config/aprsd/aprsd.conf` | `latitude`, `longitude` |
| Direwolf dashboard | `/home/pi/config/direwolf-dashboard/config.yaml` | `latitude`, `longitude` |
| Pat (Winlink) | `/home/pi/config/pat/config.json` | `locator` (6-character grid) |
| Winlink RMS gateway | `gateway.conf`, `sysop.xml` and `channels.xml` in `/usr/local/etc/rmsgw/` and `/etc/rmsgw/`, whichever exist | grid square |
| WSJT-X and JS8Call | `/home/pi/config/WSJT-X.ini`, `JS8Call.ini` | `MyGrid` (4-character grid) |
| WeeWX, if installed | `/etc/weewx/weewx.conf` or `/home/pi/weewx-data/weewx.conf` | `[Station]` `latitude`, `longitude` (and `altitude`, only if you turn that on) |

The weather packet made by the weewx-aprs extension takes its position from WeeWX's `[Station]` settings, so APRS weather beacons follow the GPS too.

DigiPi's **Tracker** mode is not changed. It already beacons the live GPS position.

DigiPi images differ in where the RMS gateway keeps its files, and some of them are symlinks to others. The add-on edits each real file once and leaves the links as they are.

### When it changes nothing

- **DigiPi has not been initialized** yet. Initialize first, as normal.
- **No GPS fix within 10 minutes**, for example indoors. The previous position is kept; the watcher updates once a fix arrives and the station has been still for 10 minutes.
- **The station is moving.** Nothing changes until it has been parked for 10 minutes.
- **The station has moved less than 100 m.** Normal GPS wander does not rewrite the files.
- **WeeWX altitude** is left as you set it. GPS altitude is much less accurate than position, and a wrong altitude makes WeeWX's sea-level pressure wrong. To have it updated too, run `sudo digipi-gps-position.py --set update-altitude on`; it then changes only when a reading's estimated vertical error is 15 m or less and the altitude is more than 30 m off.

---

## Files

| File | Installed as | What it is |
|---|---|---|
| `digipi-gps-position.py` | `/usr/local/bin/digipi-gps-position.py` | The program that reads the GPS and updates the files |
| `digipi-gps-position.service` | `/etc/systemd/system/digipi-gps-position.service` | Runs the program at every boot and keeps it watching |
| `digipi-gps-nmea-relay.py` | `/usr/local/bin/digipi-gps-nmea-relay.py` | GPS data for Winlink Express on the LAN (optional, off) |
| `digipi-gps-nmea-relay.service` | `/etc/systemd/system/digipi-gps-nmea-relay.service` | Runs the relay when that option is on |
| `install-gps-position.sh` | (not installed) | Installs or upgrades everything above, sets the GPS device by its permanent name, and adds the RMS start step |
| (made by the installer) | `/etc/systemd/system/winlinkrms.service.d/gps-position.conf` | Runs the program each time RMS gateway mode starts, without editing DigiPi's own RMS service |
| `DigiPi-GPS-Position.md` | (not installed) | This guide |
| `CHANGELOG.md` | (not installed) | What changed in each version, and why |

All seven files come in `digipi-gps-position.zip`. The program also creates `/home/pi/gps-position-history.txt`, its record of every position change. It keeps the previous version of each file it changes as `<file>.gps-backup`, and any settings you change in `/etc/digipi-gps-position.conf`.

---

## Before you start

1. **DigiPi is flashed and initialized**, and you can log in over SSH as `pi`.
2. **The GPS is plugged in** and its antenna can see the sky.
3. **DigiPi's GPS device is set.** On the DigiPi setup page this is the **GPS Device** field, for example `ttyACM1` or `ttyUSB0`. It ends up on the `DEVICES` line of `/etc/default/gpsd`. The installer then switches it to the GPS's permanent `/dev/serial/by-id/` name, once gpsd confirms which device is the GPS, so it can't be swapped with a radio cable.
4. **The GPS works.** On the Pi run `cgps` (press **q** to quit). It should show a **3D FIX** with a latitude and longitude. The **GPS** link on the DigiPi web page shows the same thing. If the satellite table is missing, widen the Terminal window.

---

## Install

### Step 1 — Copy the zip from your computer to the Pi

Download `digipi-gps-position.zip` from the [Scott-weewx-aprs repository](https://github.com/sonoaltercocker/Scott-weewx-aprs/tree/main/gps). Your computer saves it in its **Downloads** folder. Then follow the steps for your computer: a **Mac** or a **Windows 11 PC**.

On a Mac, open **Terminal** and unzip it:

```bash
cd ~/Downloads
unzip -o digipi-gps-position.zip
```

This makes a `digipi-gps-position` folder. Safari often unzips downloads by itself; if the folder is already there, skip the `unzip` command.

DigiPi keeps its filesystem read-only, so make it writable, then copy the folder to the Pi. Replace `<pi-address>` with your Pi's address, for example `10.0.0.5` when you are on the DigiPi hotspot, its address on your home network, or `digipi.local`:

```bash
ssh pi@<pi-address> sudo remount
scp -r ~/Downloads/digipi-gps-position pi@<pi-address>:~/
```

If you have an entry for the Pi in `~/.ssh/config`, you can use its name instead of `pi@<pi-address>`.

On a Windows 11 PC, open **PowerShell** (right-click the **Start** button, then choose **Terminal**). Windows 11 has `ssh` and `scp` built in. Unzip the file and copy it to the Pi, replacing `<pi-address>` as above and leaving out the `<` and `>`, which PowerShell treats as special characters:

```powershell
cd $HOME\Downloads
Expand-Archive -Force digipi-gps-position.zip -DestinationPath .
ssh pi@<pi-address> sudo remount
scp -r $HOME\Downloads\digipi-gps-position pi@<pi-address>:~/
```

If you unzip with File Explorer's **Extract All** instead, it puts the files one folder deeper, in `Downloads\digipi-gps-position\digipi-gps-position`. Copy that inner folder to the Pi.

The first time you connect, `ssh` asks you to confirm the Pi's key: type `yes`. An entry for the Pi in `C:\Users\<you>\.ssh\config` works the same way as on a Mac.

Don't open the scripts in Notepad and save them. Notepad can change their line endings, and the Pi then can't run them.

### Step 2 — Run the installer on the Pi

Log in to the Pi from Terminal on a Mac or PowerShell on Windows, and run the installer:

```bash
ssh pi@<pi-address>
cd ~/digipi-gps-position
sudo bash install-gps-position.sh
```

The installer copies the program and the service into place, turns the service on, adds the RMS gateway start step, writes the first line of the position history, and then shows:

- **the GPS device.** If gpsd confirms which device is the GPS and it's set by a number such as `/dev/ttyACM1`, the installer switches it to the permanent name and says so. If it can't confirm, it changes nothing and lists the devices by their permanent names.
- whether **WeeWX was found**. If not, only DigiPi is updated; if you install WeeWX later, it is picked up at the next boot with no need to install this again.
- whether **the position watcher is running**. On a first install it starts at the next boot, or straight away with `sudo systemctl start digipi-gps-position`.

The two optional features are installed but switched off. See **Optional features** below.

### Step 3 — Try it without changing anything

```bash
sudo /usr/local/bin/digipi-gps-position.py --dry-run --force
```

After the GPS gets a fix, this lists every line it *would* change, with the old line marked `-` and the new one `+`. Nothing is written.

### Step 4 — Reboot

```bash
sudo reboot
```

The Pi comes back read-only, and from now on the position is checked at every boot.

### Upgrading from an earlier version

Copy the new folder to the Pi as in Step 1, and run the installer again as in Step 2. Your settings, the optional features you turned on and the position history are kept. No reboot is needed; the installer restarts the watcher.

---

## Optional features

Two features are installed but switched off. Each is turned on or off with one command on the Pi, with no reboot, and stays that way across reboots and upgrades. `sudo digipi-gps-position.py --status` shows which are on.

### Live beacons while moving

```bash
sudo digipi-gps-position.py --enable live-beacons
```

In the digipeater and iGate modes, Direwolf then beacons the live GPS position with SmartBeaconing instead of the fixed position: often while moving, extra beacons on turns, and every 30 minutes when parked. The command switches off the fixed `PBEACON` line in those Direwolf configs (it is kept, and still updated), adds `GPSD`, `TBEACON` and `SMARTBEACONING` lines, and restarts the running mode. Tracker mode already works this way and is not changed.

| | Impact |
|---|---|
| Pi | Almost none; Direwolf reads gpsd, which is already running |
| Radio | More beacons while moving: at most one every 3 minutes at speed, plus turns. About the same as now when parked |
| No GPS fix | No beacons until the fix returns; the station drops off the APRS map after a while |
| Battery | Slightly more transmitting while moving |
| RMS gateway | Not affected; the Winlink mode has no beacon |

The beacon rates are the `smartbeaconing` setting (see **Settings**). `--disable live-beacons` puts the fixed beacon back.

### GPS for Winlink Express on the LAN

```bash
sudo digipi-gps-position.py --enable lan-nmea
```

This starts a small relay that sends the GPS data as NMEA sentences on TCP port 2948, for Winlink Express and other programs on computers on the same network. gpsd itself stays reachable only from the Pi.

In Winlink Express:

1. Open the GPS settings.
2. Choose the TCP/IP connection instead of a serial port.
3. Enter the DigiPi's address, for example `10.0.0.5` on the DigiPi hotspot, and port `2948`.
4. Apply the settings, and check that a position appears.

To check the port from Windows PowerShell, `Test-NetConnection <pi-address> -Port 2948` should report `TcpTestSucceeded : True`. From a Mac, use `nc -vz <pi-address> 2948`.

| | Impact |
|---|---|
| Pi | One small background program, about 10 MB of memory and almost no CPU |
| Radio | None |
| Network | A few hundred bytes a second to each connected computer |
| Privacy | Anyone on the network, including everyone on the DigiPi hotspot, can read the station's position from port 2948. Use it only on a network you trust, and never forward the port to the internet |

`--disable lan-nmea` stops the relay.

---

## Testing a move

1. **Before moving, look at the position history** on the Pi:

   ```bash
   cat /home/pi/gps-position-history.txt
   ```

   The last line is the position the station has now: the `installed` line on a new install, or the latest `updated` line. There's nothing to write down; the file keeps the record.

2. **Move the station more than 100 m.** Either shut it down first and power it up at the new place, where the GPS antenna can see the sky:

   ```bash
   sudo shutdown -h now
   ```

   or move it while it's running; the watcher updates once it has been parked for 10 minutes.

3. **Wait a few minutes** after power-up, or 10 minutes after parking if it stayed on, then check the result:

   ```bash
   cat /run/digipi-gps-position.json
   ```

   - `"result": "updated"`: the position was changed, and `files` lists what was updated.
   - `"result": "unchanged"`: the station is within 100 m of its saved position.
   - `"result": "no fix"`: the GPS did not lock at boot; the watcher keeps trying.
   - **No file yet:** the service is still waiting for a fix.

4. **Look at the history again.** A new `updated` line shows the new position and grid square, and how far the station moved and from where:

   ```
   2026-11-06 14:05  installed  33.7748, -84.2963  EM73us  WeeWX 33.7748, -84.2963  (version 1.6)
   2026-11-08 09:12  updated    33.8320, -84.2682  EM73ut  moved 6870 m from 33.7748, -84.2963 EM73us
   ```

   To see the values in the config files themselves:

   ```bash
   grep -E "^NEW(LAT|LON|GRID)" /home/pi/localize.env
   sed -n '/^\[Station\]/,/^\[/p' /etc/weewx/weewx.conf | grep -E "latitude|longitude|altitude"
   ```

   The second command is only for stations with WeeWX. On a pip install of WeeWX the file is `/home/pi/weewx-data/weewx.conf`. You can also watch your next beacon on [aprs.fi](https://aprs.fi).

5. **Optional:** reboot without moving. The result should be `unchanged`, and no new line is added to the history.

---

## Logs

The program doesn't keep a log file of its own. What it prints goes to the system journal:

```bash
journalctl -u digipi-gps-position -b
```

`-b` shows only the current boot. A typical update looks like this:

```
digipi-gps-position 1.6
Waiting up to 600 s for a GPS fix ...
GPS position 33.832000, -84.268200
DigiPi position 33.7748, -84.2963 (EM73us); 6870 m from GPS
WeeWX position 33.7748, -84.2963; 6870 m from GPS
Stopping tnc
  updated /home/pi/direwolf.tnc.conf
  ...
WeeWX found (/etc/weewx/weewx.conf); updating its [Station] position.
  updated /etc/weewx/weewx.conf
History: updated    33.8320, -84.2682  EM73ut  moved 6870 m from 33.7748, -84.2963 EM73us
Position set to 33.8320, -84.2682 (EM73ut); 13 file(s) updated.
Starting tnc
Restarting weewx
Watching the GPS; an update follows once the station has been parked at a new place for 10 min.
```

`/run/digipi-gps-position.json` holds the result of the latest run, and `systemctl status digipi-gps-position` shows whether it is still running.

> **Read the log before the next reboot.** On DigiPi the journal is usually kept in memory only, so a reboot clears it. `journalctl --list-boots` shows how many boots are kept.

### Position history

`/home/pi/gps-position-history.txt` is the lasting record. Unlike the journal it is kept on the SD card, so it survives reboots. It gets one line when the add-on is installed and one line each time the position is changed; boots where nothing moved add nothing.

```bash
cat /home/pi/gps-position-history.txt
```

| Line starts with | Meaning |
|---|---|
| `installed` | The position DigiPi (and WeeWX) had when the add-on was installed or upgraded |
| `updated … moved … from …` | The station moved; the new position, grid square (and altitude, if `update-altitude` is on), and the old position |
| `updated … WeeWX position corrected from …` | DigiPi was right, but WeeWX had a different position, which was put right |
| `… (settled after a move)` | The watcher updated after the station was parked at a new place, without a reboot |
| `… (at RMS start)` | The update was made when RMS gateway mode started |
| `… (waited … for a connection to finish)` | An AX.25 connection was in progress, and the update waited for it |
| `… (connection still open after 10 min; updated anyway)` | A connection was still open after the busy-wait limit |
| `… (forced)` | The update was run by hand with `--force`, without a move |

---

## Running it by hand

| Command (as root, with `sudo`) | What it does |
|---|---|
| `digipi-gps-position.py` | Check the GPS once and update if the station has moved |
| `digipi-gps-position.py --dry-run` | Show what would change; write nothing |
| `digipi-gps-position.py --force` | Update even if the station has not moved |
| `digipi-gps-position.py --timeout 60` | Wait at most 60 seconds for a fix |
| `digipi-gps-position.py --status` | Show the version, which optional features are on, the settings and the last result |
| `digipi-gps-position.py --enable live-beacons` (or `lan-nmea`) | Turn an optional feature on; `--disable` turns it off |
| `digipi-gps-position.py --set busy-wait 15` | Change a setting; `--set busy-wait default` puts it back |
| `digipi-gps-position.py --set-gps-device` | Point gpsd at the GPS by its permanent `/dev/serial/by-id/` name (the installer does this; run it again after changing GPS) |
| `digipi-gps-position.py --rms-start` | The quick check run when RMS gateway mode starts: waits at most 30 seconds and leaves the DigiPi modes alone |
| `digipi-gps-position.py --record-install` | Add an `installed` line with the current position to the history (the installer does this) |
| `digipi-gps-position.py --version` | Show the installed version |

No `sudo remount` is needed: the program makes the filesystem writable when it changes something, then puts it back.

## Settings

Settings are changed with a command, not by editing the program, and are kept when you install a newer version:

```bash
sudo digipi-gps-position.py --set busy-wait 15
sudo digipi-gps-position.py --set busy-wait default
sudo digipi-gps-position.py --status
```

The watcher uses a new setting after the next boot, or straight away after `sudo systemctl restart digipi-gps-position`.

| Setting | Default | Meaning |
|---|---|---|
| `fix-timeout` | `600` | Seconds to wait for a GPS fix at boot |
| `rms-fix-timeout` | `30` | Seconds to wait for a GPS fix when RMS gateway mode starts |
| `fix-samples` | `10` | Readings taken; the middle value is used |
| `move-threshold` | `100` | Moves smaller than this, in metres, are ignored |
| `settle-minutes` | `10` | Minutes the station must be parked at a new place before the watcher updates |
| `busy-wait` | `10` | Minutes to wait for an AX.25 connection to finish before updating anyway |
| `update-altitude` | `off` | `on` also updates WeeWX's altitude from the GPS |
| `alt-max-error` | `15` | With `update-altitude` on: GPS altitude is used only if its estimated vertical error is at most this, in metres |
| `alt-threshold` | `30` | With `update-altitude` on: WeeWX altitude is changed only if this far off, in metres |
| `decimals` | `4` | Decimal places written for latitude and longitude (4 is about 11 m). Use `2` to publish a less exact position |
| `smartbeaconing` | `60 3:00 5 30:00 0:30 30 255` | Beacon rates for live beacons: fast speed (mph), fast rate, slow speed (mph), slow rate, turn time, turn angle, turn slope. After changing it, turn live beacons off and on again |

---

## Troubleshooting

| Symptom | What to check |
|---|---|
| **Always `no fix`** | Run `cgps`. No data at all means `gpsd` is reading the wrong device: check `DEVICES` in `/etc/default/gpsd`. Data but no fix means the antenna can't see enough sky |
| **GPS and radio fight over `ttyACM0`** | Both enumerate as `ttyACM…` and can swap after a reboot. Run `sudo digipi-gps-position.py --set-gps-device`, which switches gpsd to the GPS's permanent `/dev/serial/by-id/` name |
| **`DigiPi has not been initialized yet`** | Run DigiPi's Initialize from its setup page first |
| **No update after moving the station while it was running** | The watcher waits until the station has been parked for `settle-minutes` (10). `systemctl status digipi-gps-position` should show it running; `journalctl -u digipi-gps-position -b` shows what it saw |
| **The old position is beaconed right after boot** | Expected. Beacons sent before the GPS locks use the previous position; the new one follows once the fix arrives |
| **No beacons with live beacons on** | Direwolf needs a GPS fix to beacon. Check with `cgps`, or turn live beacons off to go back to the fixed beacon |
| **Winlink Express gets no position** | Check that `lan-nmea` is on (`--status`), that `Test-NetConnection` to port 2948 succeeds, and that Winlink Express uses port 2948, not 2947 |
| **The RMS gateway registers an old grid** | `systemctl cat winlinkrms` should end with the `gps-position.conf` step; if not, run the installer again. `journalctl -u winlinkrms -b` shows what the RMS start check did |
| **WeeWX shows an old position after its settings were rewritten** | Something reset WeeWX's `[Station]` position. This add-on puts the GPS position back at the next boot |
| **Changes vanish after a reboot** | A file was edited by hand without `sudo remount`. The add-on itself does this automatically |

## Version history

| Version | Date | Changes |
|---|---|---|
| 1.6 | 2026-11-08 | WeeWX altitude left alone unless `update-altitude` is turned on, and then only from accurate readings. The installer sets the GPS device by its permanent name; also `--set-gps-device`. The installer says whether the watcher is running |
| 1.5 | 2026-11-06 | Keeps watching after boot and updates once the station has settled at a new place, waiting up to `busy-wait` minutes for an AX.25 connection to finish. Optional live beacons (SmartBeaconing) and LAN NMEA feed for Winlink Express. Settings by command, kept across upgrades. Keeps the previous copy of each changed file. LAN NMEA relay based on work by Scott Curie, NS7C |
| 1.4 | 2026-11-06 | RMS gateway: also checks the GPS each time RMS gateway mode starts; updates the RMS files in both `/usr/local/etc/rmsgw/` and `/etc/rmsgw/`, following symlinks. Based on work by Scott Curie, NS7C |
| 1.3 | 2026-11-06 | Keeps a position history in `/home/pi/gps-position-history.txt` |
| 1.2 | 2026-11-06 | Also checks WeeWX's saved position. Version shown in the log and with `--version` |
| 1.1 | 2026-11-06 | Detects whether WeeWX is installed and says so in the log |
| 1.0 | 2026-11-06 | First release |

The reasons for each change are in `CHANGELOG.md`, in the zip and in the [repository folder](https://github.com/sonoaltercocker/Scott-weewx-aprs/tree/main/gps).

## Removing it

```bash
sudo digipi-gps-position.py --disable live-beacons
sudo digipi-gps-position.py --disable lan-nmea
sudo remount
sudo systemctl disable digipi-gps-position
sudo rm /etc/systemd/system/digipi-gps-position.service /etc/systemd/system/digipi-gps-nmea-relay.service
sudo rm /usr/local/bin/digipi-gps-position.py /usr/local/bin/digipi-gps-nmea-relay.py
sudo rm /etc/systemd/system/winlinkrms.service.d/gps-position.conf /etc/digipi-gps-position.conf
sudo systemctl daemon-reload
sudo reboot
```

The first two commands put the fixed beacon back and stop the LAN feed, so run them before removing the files. The position stays as it was last set; edit the files by hand to change it after that. The position history and the `.gps-backup` copies stay too; delete them if you don't want to keep them. gpsd keeps using the GPS's permanent name, which works without the add-on.

## Credits

The RMS gateway handling (the check when RMS starts, and the support for both RMS file locations) and the LAN NMEA relay are based on work by Scott Curie, NS7C, who runs DigiPi gateways in ARES communications trailers.

---

*Scott Sheppard, KJ4ZZB*
