# Development status and next milestones

The first reliability and security pass is implemented in the local checkout. The server uses loopback access by default, supports a bearer token for remote clients, checks browser Origin, caps audio buffering, and no longer gives the agent a shell tool. Requests have IDs and the client waits for the matching final response before accepting another trigger. The server emits an intermediate transcript and reports STT and agent timings. Audio conversion uses Media Foundation's resampler. Re-ingestion uses stable chunk IDs and replaces obsolete chunks for each indexed file.

## Verification

- `dotnet build client/PresentationCopilot/PresentationCopilot.csproj`
- From the repository root: `PYTHONPATH=server python -m unittest discover -s server/tests -v` (PowerShell: `$env:PYTHONPATH='server'; python -m unittest discover -s server/tests -v`)
- `python -m compileall -q server`

## Remaining work

1. Run an end-to-end session with Ollama and Whisper installed. From `server/`, use `python benchmark.py --wav path/to/question.wav --runs 3` and save the output for the target hardware. The benchmark measures standalone retrieval; retrieval invoked inside the agent is included in `agent_ms`. The live `timings_ms` covers STT and the complete agent.
2. Add streaming STT and incremental answer generation. The current `transcript` event is one early result, not token streaming.
3. Evaluate transcription and answer quality on recorded Vietnamese and English presentation questions. Include expected source passages and mark unsupported claims.
4. Add document lifecycle controls for removed files, stronger citations within each generated claim, and evidence display in the HUD.
5. Extend provider configuration and automatic question detection only after the measured baseline and quality checks are reliable.

The repository is AGPL-3.0 licensed. Review obligations before incorporating changes into another product.
