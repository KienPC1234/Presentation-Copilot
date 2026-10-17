# Presentation Copilot — Client Setup Guide

## Prerequisites

| Requirement | Version |
|---|---|
| .NET SDK | 10.0+ |
| Windows | 10 / 11 (WASAPI loopback requires Windows) |
| Visual Studio | 2022 17.8+ (or `dotnet` CLI) |

## Quick Start

```powershell
# 1. Clone / navigate to the client directory
cd client

# 2. Restore NuGet packages
dotnet restore PresentationCopilot.sln

# 3. Build
dotnet build PresentationCopilot.sln -c Release

# 4. Run
dotnet run --project PresentationCopilot/PresentationCopilot.csproj
```

Or open `PresentationCopilot.sln` in Visual Studio 2022, restore NuGet, and press **F5**.

## Configuration

Edit `PresentationCopilot/appsettings.json` before building:

```json
{
  "ServerUri":              "ws://localhost:8765",
  "ApiToken":               "",
  "PresentationTopic":      "",
  "HotKey":                 "Ctrl+Shift+Space",
  "HotKeyModifiers":        6,
  "HotKeyCode":             32,
  "ToggleHotKey":           "Ctrl+Alt+H",
  "ToggleHotKeyModifiers":  3,
  "ToggleHotKeyCode":       72,
  "AudioBufferSeconds":     20,
  "OpacityLevel":           0.88,
  "StreamContinuously":     true,
  "LiveCaptions":           true,
  "AudioSource":            "Loopback"
}
```

| Field | Meaning |
|---|---|
| `ServerUri` | WebSocket endpoint of the server (`ws://` locally, `wss://` across untrusted networks) |
| `ApiToken` | Must match `API_TOKEN` on the server; empty falls back to `PRESENTATION_COPILOT_API_TOKEN` |
| `PresentationTopic` | Optional product/topic name sent once so retrieval is anchored |
| `HotKey` / `HotKeyModifiers` / `HotKeyCode` | Global hotkey that asks for a suggestion |
| `ToggleHotKey` / `ToggleHotKeyModifiers` / `ToggleHotKeyCode` | Global hotkey that shows/hides the HUD and restores a hidden tray icon |
| `AudioBufferSeconds` | Seconds analysed on each hotkey press (5–90) |
| `StreamContinuously` | Stream audio while connected so the server always holds the recent question |
| `LiveCaptions` | Show the server's partial transcript on the HUD while you speak, before the analyze hotkey |
| `AudioSource` | `Loopback` (system output: speakers / headphones) or `Microphone` (default recording device) |

You can also set these from the tray icon → **Settings…**, which saves back to `appsettings.json` next to the built executable. The build only creates that file when it is missing, so your settings are never overwritten. The token is stored there as plain text; keep that file private.

### Hotkey Reference

| Field | Value | Meaning |
|---|---|---|
| `HotKeyModifiers` | `6` | `Ctrl (2) + Shift (4)` |
| `HotKeyCode` | `32` | `Space (0x20)` |

Default combination: **Ctrl + Shift + Space** to ask for a suggestion, and **Ctrl + Alt + H** to show/hide the HUD (this also restores the tray icon after you hide it). Both can be changed in **Settings → Hotkeys** by clicking the field and pressing a combination.

To change the hotkey, update both fields using the Win32 modifier and virtual-key constants:

| Modifier | Flag |
|---|---|
| Alt | 1 |
| Ctrl | 2 |
| Shift | 4 |
| Win | 8 |

Combine with bitwise OR: `Ctrl + Shift = 2 + 4 = 6`.

## NuGet Packages

| Package | Version | Purpose |
|---|---|---|
| `NAudio` | 2.2.1 | WASAPI loopback audio capture + resampling |
| `Websocket.Client` | 5.1.2 | Persistent WebSocket with auto-reconnect |
| `Microsoft.Extensions.Configuration.Json` | 8.0.0 | JSON config binding |
| `Hardcodet.NotifyIcon.Wpf` | 1.1.0 | System tray icon in WPF |

## Architecture Overview

```
MainWindow (tray host)
├── AudioCaptureService   ← WASAPI loopback or microphone → 16kHz PCM ring buffer
├── WebSocketService      ← ws://server → sends PCM, receives JSON
├── HotkeyService         ← RegisterHotKey (analyze + show/hide)
├── MainViewModel         ← INotifyPropertyChanged, commands, VU level
└── HudWindow             ← Transparent always-on-top overlay
```

### Data Flow

1. System audio (loopback) or the chosen microphone is continuously captured and converted to 16 kHz mono PCM into a local ring buffer. The HUD opens as soon as the app starts and shows a VU meter plus a REC badge.
2. When `StreamContinuously` is on (default), the PCM is also streamed to the server as binary WebSocket frames, so the server's rolling window always holds the recent audio. Frames are dropped (never queued without bound) if the socket backs up.
3. If the server has **live captions** enabled it periodically transcribes the recent window and pushes `{"type":"caption","text":"…"}`. With `LiveCaptions` on (default) the HUD shows the question forming as the judge speaks.
4. **Hotkey pressed** → the client sends `{"type":"trigger","request_id":"…","seconds":N}`; the server analyses the last N seconds of its window and clears it, so an earlier question cannot leak into this answer. With streaming off, the client first sends the last N seconds of its local ring buffer.
5. Python server processes audio → returns JSON:
   ```json
   {
     "key_point": "Explain the architecture clearly",
     "keywords": ["microservices", "scalability", "latency"],
     "framework_steps": ["State the problem", "Show the solution", "Quantify impact"]
   }
   ```
6. Client parses JSON → updates `MainViewModel` → HUD fades in with the suggestion.

## Running the Python Server

See the `server/` directory. Start it before launching the client:

```bash
python server/main.py
```

The server must listen on the URI configured in `appsettings.json` (default `ws://localhost:8765`).

## Troubleshooting

| Issue | Fix |
|---|---|
| Hotkey already registered | Another app uses Ctrl+Shift+Space. Pick a new combination in **Settings → Hotkey** (the change applies immediately) or edit `HotKeyCode` / `HotKeyModifiers` in `appsettings.json`. |
| HUD pinned through and you cannot click it | Click-through only covers the HUD body; the header toolbar (PIN/UNPIN, COPY, SETTINGS, HIDE) always stays clickable. You can also right-click the HUD header, or use the tray icon → **Pin / Unpin HUD**. |
| Tray icon missing | It may have been hidden via **Hide tray icon**. Press the show/hide hotkey (default Ctrl+Alt+H) to restore it. The icon is only hidden while that hotkey is registered. |
| Microphone records nothing | Switch **Audio source** back to the system loopback if your audio plays through headphones, or confirm a default recording device is set in Windows. |
| Tray menu does not open | Both mouse buttons open the menu (`MenuActivation=LeftOrRightClick`); if it still does not respond, the icon may be in the tray overflow area — drag it onto the taskbar to pin it. |
| No audio captured | Ensure a default playback device is set and system audio is not muted. |
| WebSocket fails to connect | Confirm the Python server is running and `ServerUri` matches. |
| HUD not visible | Right-click tray icon → "Show / Hide HUD". Check that a suggestion was returned by the server. |

