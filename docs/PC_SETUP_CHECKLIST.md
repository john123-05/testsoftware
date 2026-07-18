# Attraction PC Setup Checklist (Field Knowledge)

Source: voice-message debrief from Tom (father, builds and installs the
legacy systems) on 2026-07-17, transcribed and structured. This is
hard-won field experience from years of installs. A clean install takes
about 1.5 hours when nothing goes wrong; the pitfalls below are why it
sometimes takes much longer.

This checklist covers the parts Liftpic Sync deliberately does NOT try to
automate: Windows, BIOS, drivers, licensing of the legacy programs, and
payment hardware. Tom's assessment - and the design assumption of this
repo - is that a fully automatic PC install is unrealistic because the
failure modes depend on Windows build, PC hardware, and attached devices.
Automate in small steps; keep this list current.

## Base PC preparation (always, in this order)

1. **AnyDesk** - install the OLD version (~6.8.x). Newer versions demand
   payment. During install, disable auto-update. The old version then runs
   stable and free indefinitely.
2. **BIOS: auto-restart after power failure** - use a WIRED keyboard
   (Bluetooth is not connected yet during boot). Press F1 / F4 / Esc
   repeatedly right at power-on to enter BIOS, then enable "restore power
   after AC loss" in the power options. Critical for PCs mounted in
   switch cabinets that nobody can physically reach.
3. **Disable Windows power saving** - disk and display must never sleep.
4. **Copy the full install directory** onto the PC, then activate,
   license, and test each program individually, installing runtimes as
   needed (details below).
5. When everything is tested: pack the PC and ship it. The customer only
   connects cables per the setup sheet.

## Known pitfalls per component

### .NET Framework 3.5 (required by the Samuel viewer software)

The automatic .NET 3.5 install sometimes loads forever and never
finishes. Downloading the package from Microsoft directly does NOT fix
it. Installing a newer .NET (e.g. 4.x) does NOT satisfy the software -
it strictly requires 3.5. The reliable trick: **first install ALL pending
Windows 11 updates, even ones not yet due; afterwards .NET 3.5 installs
normally.** Nobody knows why. It just works.

### Printer

Install is usually easy, but set the color mixing options in the printer
driver. If forgotten, prints look pale/washed out.

### Touchscreen

Usually plug-and-play. Occasionally it demands a driver Windows cannot
find; wrong drivers can be near-impossible to remove again. If driver
hell strikes, swapping to a spare PC is faster than fighting it.

### Coin validator (Muenzpruefer)

Connect it, select it in the Samuel software, done. Almost never a
problem (one desk PC at home never worked; cause never found).

### Second monitor

If the second monitor shows nothing: update the graphics driver first.
Older Samuel versions also required the second monitor to be powered ON
before the PC boots, or the monitor order got swapped; current versions
can auto-detect and pin the display monitor in settings.

### AidaTest (speed measurement, from programmer "Kose" in Paderborn)

No installation needed, but licensing is a ritual:

1. Run it once - it writes an error code into its log because no license
   exists yet.
2. Feed that code plus the current date into the separate license tool;
   it generates a key.
3. Write code, date, and key into `AidaTest.ini`. Now it runs.

Serial ports: the PC has two COM ports for light-barrier signals 1 and 2.
Customers with only ONE light barrier need a different operating mode in
the INI. If the COM port is not recognized, install a COM driver; if that
also fails (rare), use a different PC.

### Camera flash output

The flash output is wired directly to the studio flash. This normally
works fine but is sensitive to voltage spikes (observed surge damage
after thunderstorms / frequent power cycling). Consider a protective
isolation circuit in between; a repaired camera will fail again in weeks
otherwise.

## Credit card terminal (Telecash + EasyZVT)

The chain: Samuel software -> EasyZVT interface (bought-in library,
company near Kreuznach) -> physical terminal -> Telecash (the payment
provider; money lands on a Telecash escrow account first).

Setup order, with known traps:

1. **Telecash account for the customer.** Trap: for Schausteller
   (traveling operators) Telecash wants the Gewerbekarte, and the photo
   automat must be listed on it. An outdated card silently stalls the
   process in their back office. If a case stalls for weeks, escalate to
   Telecash management - it works.
2. Telecash issues the **Terminal-ID**.
3. With that ID, request the matching **license code from EasyZVT**.
4. **Terminal IP:** the terminal briefly shows its router-assigned IP
   during boot - photograph the display. The IP stays stable afterwards
   but you need it once.
5. Terminal vendor software: connect to the terminal via that IP, enter
   password, write the Terminal-ID into the terminal. Wait until it
   connects to the Telecash server and confirms ("married").
6. **EasyZVT INI:** terminal IP, Terminal-ID, license code plus other
   parameters. Use the small helper tool (external commission) that
   flags missing/incorrect parameters instead of editing blind.
7. **Samuel settings INI:** declare that a terminal exists and which
   device it is.
8. Test with a real credit card purchase.

Mobile/foreign installs: the router SIM needs data roaming enabled and
(if prepaid) actual credit. A dead SIM looks exactly like a broken
terminal setup and can cost you a day.

## Photo numbering constraints (relevant for this repo)

- Some cameras (e.g. Nikon) do NOT reset their file counter at the
  nightly cleanup - they keep counting. The 4 digits used for the
  guest-visible photo ID must therefore carry enough positions that the
  machine survives >= 20 days without a camera restart. Long-term wish:
  two extra digits (up to 99,000 photos, ~1 year).
- Which digit positions of the camera number form the guest-visible ID
  should be configurable (positions 2-5 today, better 3-6).
- The last 4 digits appended by AidaTest are the SPEED value; the Speed
  Monitor program (same author, Kose) sorts its top-6 display by them.
  Anything consuming legacy filenames must not confuse speed digits with
  picture-number digits.

## Tom's uploader stability requirements (acceptance criteria)

From the same debrief - these are the failure modes he has seen in years
of running uploaders, kept here as the acceptance bar for Liftpic Sync:

| Requirement | Liftpic Sync status |
| --- | --- |
| Wait until a file is fully written before touching it (camera may still be writing; naive access can hang the whole program) | `FILE_STABLE_SECONDS` stability check in the scanner |
| Never blast 20 files at once; pace uploads | serial queue, max 10 per cycle |
| Verify the transfer actually completed; resend if not | two-phase begin/commit upload with server confirmation |
| Watchdog: restart the program if it died | runs as scheduled task/service; heartbeat visible in dashboard (`last_seen_at`) |
| Log file with last entry + error counts for post-mortem | local logs + read-only operational log health in heartbeat |
| Filenames compatible with the target system | `filename_codec` reproduces the legacy 16-digit format exactly |
