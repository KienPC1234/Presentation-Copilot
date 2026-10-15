# Presentation Copilot

Meeting and technical defense assistant. Captures system loopback audio, transcribes speaker queries using faster-whisper, retrieves relevant project context via ChromaDB vector store, and sends a transcript followed by a structured answer outline to an overlay HUD. Windows display affinity requests exclusion from compatible capture methods; verify behavior with the screen sharing software you use.

## System Architecture

```
[Google Meet / Zoom / MS Teams]
         | (System Audio Output)
         v
[C# WPF Client (Windows)] ----------(PCM Audio / WebSocket)----------> [Python Server (:8765)]
  * WASAPI Loopback Capture (48kHz to 16kHz fast-path)                   * faster-whisper (STT)
  * WDA_EXCLUDEFROMCAPTURE (Hidden from screen share)                    * ChromaDB (RAG Vector Store)
  * Global Hotkey: Ctrl + Shift + Space                                  * LangChain ReAct Agent
  * Transparent Acrylic HUD <--------(JSON Suggestion Stream)------------ * Web Dashboard (:8765)
```

## Quick Start

### 1. Server Setup (Python 3.10+)

Automated setup via script:

```powershell
.\server\setup.bat       # Creates virtualenv, installs deps, pulls Ollama models
.\server\start.bat       # Launches FastAPI server and Web Dashboard on port 8765
```

Manual setup:

```bash
cd server
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

# Pull required local models
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# Run server
uvicorn main:app --host 127.0.0.1 --port 8765 --reload
```

### 2. Client Setup (C# / .NET 8)

Open `client/PresentationCopilot.sln` in Visual Studio 2022, or run from terminal:

```powershell
dotnet run --project client\PresentationCopilot\PresentationCopilot.csproj
```

## Web Dashboard (`http://localhost:8765`)

The web interface provides real-time control over the engine:

* **Repository Ingestion**: Input any local directory path (codebase, slide PDFs, documentation). Click `Verify Path & Permissions` to validate readability before indexing into ChromaDB. Supported formats include `.pdf`, `.md`, `.txt`, `.cs`, `.py`, `.ts`, `.js`, `.json`, `.sql`, `.yaml`.
* **Language & STT Tuning**: Select target language (`vi`, `en`, `auto`, `ja`, `zh`) and configure vocabulary biasing prompts to prevent phonetic confusion on technical terms.
* **Persona Selection**: Switch presets (`tech_hackathon`, `startup_pitch`, `academic_defense`, `custom`) to adapt suggestion style and metric depth.
* **Simulation Sandbox**: Test queries and inspect RAG context chunks directly from the browser.

## Client Controls (Windows HUD)

* **Anti-Screen Capture (`WDA_EXCLUDEFROMCAPTURE`)**: The HUD window is excluded from screen capture APIs (Zoom, Google Meet, Teams, Discord, OBS, PrintScreen). It is visible only on the physical display of the presenter.
* **Hotkey Trigger**: Press `Ctrl + Shift + Space` to capture the trailing 12 seconds of loopback audio and run analysis.
* **PIN Button**: Toggles `WS_EX_TRANSPARENT` click-through mode, allowing mouse clicks to pass through the HUD to underlying slides.
* **COPY Button**: Copies the generated key point and answer framework to clipboard.
* **Settings Gear**: Opens configuration to adjust WebSocket endpoint, opacity, and audio buffer duration with automatic persistence to `appsettings.json`.
* **Esc**: Hides the overlay immediately.

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE) for details.
