# Presentation Copilot — Client Setup Guide

## Prerequisites

| Requirement | Version |
|---|---|
| .NET SDK | 8.0+ |
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
  "ServerUri":          "ws://localhost:8765",
  "HotKey":             "Ctrl+Shift+Space",
  "HotKeyModifiers":    6,
  "HotKeyCode":         32,
  "AudioBufferSeconds": 12,
  "OpacityLevel":       0.88
}
```

### Hotkey Reference

| Field | Value | Meaning |
|---|---|---|
| `HotKeyModifiers` | `6` | `Ctrl (2) + Shift (4)` |
| `HotKeyCode` | `32` | `Space (0x20)` |

Default combination: **Ctrl + Shift + Space**

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
├── AudioCaptureService   ← WASAPI loopback → 16kHz PCM ring buffer
├── WebSocketService      ← ws://server → sends PCM, receives JSON
├── HotkeyService         ← RegisterHotKey (Ctrl+Shift+Space)
├── MainViewModel         ← INotifyPropertyChanged, commands
└── HudWindow             ← Transparent always-on-top overlay
```

### Data Flow

1. System audio continuously captured and stored in a circular ring buffer (default 12 s).
2. **Hotkey pressed** → last N seconds of PCM grabbed from ring buffer → sent as binary WebSocket frame.
3. Python server processes audio → returns JSON:
   ```json
   {
     "key_point": "Explain the architecture clearly",
     "keywords": ["microservices", "scalability", "latency"],
     "framework_steps": ["State the problem", "Show the solution", "Quantify impact"]
   }
   ```
4. Client parses JSON → updates `MainViewModel` → HUD fades in with the suggestion.

## Running the Python Server

See the `server/` directory. Start it before launching the client:

```bash
python server/main.py
```

The server must listen on the URI configured in `appsettings.json` (default `ws://localhost:8765`).

## Troubleshooting

| Issue | Fix |
|---|---|
| Hotkey already registered | Another app uses Ctrl+Shift+Space. Change `HotKeyCode` / `HotKeyModifiers` in `appsettings.json`. |
| No audio captured | Ensure a default playback device is set and system audio is not muted. |
| WebSocket fails to connect | Confirm the Python server is running and `ServerUri` matches. |
| HUD not visible | Right-click tray icon → "Show / Hide HUD". Check that a suggestion was returned by the server. |

