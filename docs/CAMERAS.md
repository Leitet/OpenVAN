# Security cameras in OpenVan

## What van/RV dwellers actually run

From 2026 buyer guides (Reolink, SmartHomeRV, SafeWise, CameraFitter) the field
is a handful of consumer ecosystems plus a couple of RV-specific and open options:

| System | Why van people pick it | Connectivity |
|--------|------------------------|--------------|
| **Reolink** (Argus / Go series) | 4G-LTE models work off-grid with no Wi-Fi; local microSD, no subscription | Wi-Fi, **4G LTE**, PoE, solar |
| **Eufy** (SoloCam / eufyCam) | local storage, long battery, privacy-first (no cloud required) | Wi-Fi, battery/solar |
| **Wyze / Tapo** | cheap interior cams | Wi-Fi |
| **Blink / Ring** | easy, battery, doorbell form factor for the entry | Wi-Fi (+ cloud) |
| **Arlo** | premium wireless | Wi-Fi + cloud |
| **Furrion Vision S / generic reversing** | the classic RV rear/observation camera | **wired** analog/digital |
| **Frigate NVR** (open source) | local AI object detection, Home-Assistant native — closest to OpenVan's ethos | RTSP/ONVIF |

Recurring needs: **off-grid (4G) connectivity**, **local recording / no subscription**,
**motion detection**, night vision, and a mix of one **wired rear/observation** cam
with a few **wireless** interior/exterior cams.

## How OpenVan models them

Cameras are a **plugin** like everything else (`plugins/cameras`). Because they're
not numeric sensors, each camera is a semantic `camera.*` **entity** whose state and
attributes are driven by three raw twin signals, so the bench can exercise them and
the product UI just reads entities (Rule 1):

- `camera.<id>.online`     → entity state `online` / `offline`
- `camera.<id>.motion`     → `attributes.motion`
- `camera.<id>.recording`  → `attributes.recording`

Each camera also carries a static `connection` attribute (`wired` | `wifi` | `4g`)
and a `location`, so the UI can badge an off-grid 4G cam differently from the wired
reversing cam. The default set mirrors a typical build: a **wired rear/observation**
cam, a **Wi-Fi cabin** cam, a **Wi-Fi entry/doorbell**, and a **4G side/awning** cam.

The **Security tab** shows a live grid of camera tiles (simulated feed + LIVE/REC/
motion overlays), the **away-mode** arm/disarm, and the sensor/alert status. When
away mode is armed, motion on **any** camera (or the door/motion sensors) raises the
`Intrusion` safety alert — the camera network becomes the tripwire.

> **Assumption / scope.** The simulator provides camera *metadata and a stylised
> placeholder feed*, not real video — there's no physical van and no way to fetch a
> stream here. The real integration (RTSP/ONVIF snapshots & streams, per-vendor
> cloud APIs, local recording/playback, a Frigate bridge) is a `Backend`-level job,
> captured in `backlog.md`. The point of this layer is the plugin + entity model
> and the whole UX around it, which is exactly what a real backend slots into.
