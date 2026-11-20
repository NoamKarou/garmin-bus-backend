# Garmin Bus — Connect IQ app

A watch app for the Venu 3 / Vivoactive family. It calls the backend's
`/arrivals` endpoint and shows the next bus arrival(s):

- **green** — the ETA came from a live SIRI vehicle position;
- **grey** — only the scheduled GTFS time is known;
- `STALE` in orange — the last update failed and cached data is being shown.

Tap (or press the start button) to refresh. Back exits.

## What is already set up

- Connect IQ SDK **9.3.0** at
  `C:\Users\yeled\AppData\Roaming\Garmin\ConnectIQ\Sdks\connectiq-sdk-win-9.3.0-2026-10-20-95888f262`
  (installed by the SDK Manager; the older copy under `AppData\Local` has no
  device packages).
- Device packages under `C:\Users\yeled\AppData\Roaming\Garmin\ConnectIQ\Devices`:
  the Vivoactive family (3/4/4s/5/6), Fenix E and Fenix Chronos. **Venu 3 is not
  downloaded yet.**
- VS Code extension `garmin.monkey-c` (1.1.3)
- Developer key: `frontend/developer_key.der` (keep it; it is git-ignored)
- Java 21
- The Vivoactive 5 build works and the app is verified running in the simulator.

> **SDK Manager path quirk (already fixed):** the compiler appends `Devices/` to
> the contents of
> `C:\Users\yeled\AppData\Roaming\Garmin\ConnectIQ\sdkmanager-download-location.cfg`,
> so that file must end with a backslash:
> `C:\Users\yeled\AppData\Roaming\Garmin\ConnectIQ\`. Without it the compiler
> looks in `…\ConnectIQDevices` and reports `Invalid device id`. If the SDK
> Manager rewrites this file, fix it again.

## Remaining manual step: Venu 3 (and Venu 3S) device data

Open the SDK Manager (**Monkey C: Open SDK Manager** in VS Code, or
`C:\Users\yeled\AppData\Local\Garmin\ConnectIQ\SdkManager\sdkmanager.exe`),
sign in, select **Venu 3** / **Venu 3S**, and download. Then `monkeyc -d venu3`
will work. Vivoactive 5 can be built and run now.

## Settings

`resources/settings/properties.xml` holds the defaults:

```xml
<property id="BackendUrl"   type="string">http://127.0.0.1:8000</property>
<property id="StationCode"  type="string">4170</property>
<property id="LineNumbers"  type="string">480</property>
<property id="RefreshSeconds" type="number">30</property>
```

- **LineNumbers** and **StationCode** are exposed as Garmin Connect app
  settings (`alphaNumeric`). `LineNumbers` may be a comma-separated list; the
  UI currently shows the first arrival across the configured lines.
- **BackendUrl** is intentionally *not* a setting: Connect IQ has no URL setting
  type and some settings editors reject `.`, `:` and `/`. Edit the default in
  `properties.xml` and rebuild (or use a store/private-beta install later).
- In the simulator, Garmin Connect settings are not fetched; edit
  `properties.xml` defaults instead.

## Hebrew text and fonts

Connect IQ's built-in `Graphics.FONT_*` bitmaps do not contain Hebrew glyphs,
so the station name is drawn with bundled Heebo bitmap fonts in
`resources/fonts/`:

- `hebrew_tiny.fnt` / `hebrew_small.fnt` / `hebrew_medium.fnt` plus their
  `_0.png` atlases — BMFont resources compiled by `monkeyc`.
- Pixel sizes are baked into bitmap fonts, so each product has its own set:
  the base `resources/` folder is sized for the 390×390 models
  (vivoactive5, venu3s); `resources-venu3/`, `resources-vivoactive4/` and
  `resources-vivoactive4s/` override the same ids with that product's
  `FONT_*` sizes from the Connect IQ Device Reference.
- `BusView` loads them with `Ui.loadResource(Rez.Fonts.HebrewSmall)` and uses
  `HebrewSmall` for the station name and `HebrewTiny` for the small line
  above it.
- **Draw the logical Hebrew string as-is.** The runtime performs the RTL /
  bidirectional reordering itself (verified in the simulator: `"תחנה 45"`
  and `"45 תחנה"` both render as `45 הנחת`). Reversing it in Monkey C would
  double-reverse it.
- Names wider than the chord of the round screen at their height scroll as a
  marquee inside a clipped window (`BusView.drawStationName`) instead of being
  truncated, so long Hebrew names can still be read in full. RTL names are
  anchored at their right edge and travel rightwards; LTR names travel leftwards.

Regenerate the fonts after changing the source font, the sizes, or the
character set:

```bash
cd frontend
python tools/gen_hebrew_fonts.py                       # installed Heebo-Regular
python tools/gen_hebrew_fonts.py --font path/to/font.ttf
```

Requires Pillow (`pip install pillow`); the generated `.fnt`/`.png` files are
committed, so building does not need Python. To add a product with different
font sizes, add it to `FONT_SETS` in `tools/gen_hebrew_fonts.py` and run it —
it writes the `resources-<product>/fonts/` set. Keep the source font's
license in mind for store distribution: Heebo is SIL OFL and safe to embed;
most Windows system fonts (Arial, David, …) are not redistributable.

## Background artwork

`resources/drawables/background.png` is drawn full-screen behind all the text
(`BusView.onUpdate`). Connect IQ cannot scale bitmaps at draw time on every
supported watch, so the artwork ships once per screen size in resource
qualifier folders, which override the base drawable id:

- `resources-round-390x390/` — venu3s, vivoactive5
- `resources-round-454x454/` — venu3
- `resources-round-260x260/` — vivoactive4
- `resources-round-218x218/` — vivoactive4s

After changing the artwork, regenerate the resized copies:

```bash
cd frontend
python tools/gen_backgrounds.py
```

## Build

```bash
cd frontend
SDK="C:/Users/yeled/AppData/Roaming/Garmin/ConnectIQ/Sdks/connectiq-sdk-win-9.3.0-2026-10-20-95888f262"

# build for Venu 3 (after the Venu 3 device package is downloaded)
"$SDK/bin/monkeyc" -f monkey.jungle -o bin/bus.prg -d venu3 -y developer_key.der

# 1) start the simulator and leave it running (separate window)
"$SDK/bin/simulator.exe"
# 2) in another shell: load the app
"$SDK/bin/monkeydo" bin/bus.prg venu3
```

Vivoactive 5 works today:

```bash
"$SDK/bin/monkeyc" -f monkey.jungle -o bin/bus_vivoactive5.prg -d vivoactive5 -y developer_key.der
"$SDK/bin/monkeydo" bin/bus_vivoactive5.prg vivoactive5
```

Add `-r` to `monkeyc` for a release build. To build for another device, change
`-d` to `venu3s`, `vivoactive5`, `vivoactive4` or `vivoactive4s`.

## Simulator notes

- Point `BackendUrl` at `http://127.0.0.1:8000` and start the backend:

  ```bash
  cd ../backend
  uv run uvicorn app.main:app --port 8000
  ```

- The simulator is more permissive than real hardware with HTTP; it can reach
  localhost.
- Verify: loading state → arrivals, green vs grey, tap-to-refresh, stopping the
  backend (stale/offline), an invalid station (404 → “Station not found”), and a
  station with no service (“No buses soon”).
- The Venu 3 is 454×454, the Vivoactive 5 / Venu 3S are 390×390 and the
  Vivoactive 4 is 260×260; the layout uses `dc.getWidth()`/`getHeight()`.

## Install on a physical watch

1. **HTTPS is required.** `makeWebRequest` rejects plain HTTP except to
   `127.0.0.1` on the phone. Deploy the backend (see `../backend/README.md`) or
   run an HTTPS tunnel:

   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

   Put the resulting `https://…` URL into `BackendUrl` and rebuild.

2. Sideload: build the `.prg`, connect the watch over USB, and copy it to
   `GARMIN/APPS` on the watch volume. Or install through the Connect IQ Store
   private beta (this is what makes Garmin Connect app settings editable).

3. Sideloaded builds use the `properties.xml` defaults; Garmin Connect app
   settings are only available for store/private-beta installs.

## Notes

- `manifest.xml` targets `venu3`, `venu3s`, `vivoactive5`, `vivoactive4`,
  `vivoactive4s` with `minApiLevel="3.1.0"` (Vivoactive 4 is API 3.3).
- The app requests the `Communications` permission and supports `eng` + `heb`.
- The launcher icon is a generated 70×70 PNG in `resources/drawables/`.
- The backend must be reachable by the phone paired to the watch. Live data is
  about 1–2 minutes old; the app shows the scheduled time in grey when the live
  overlay cannot produce a reliable ETA.
