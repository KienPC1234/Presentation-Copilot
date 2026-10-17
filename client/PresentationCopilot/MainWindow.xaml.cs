using Microsoft.Extensions.Configuration;
using PresentationCopilot.Models;
using PresentationCopilot.Services;
using PresentationCopilot.ViewModels;
using PresentationCopilot.Views;
using System.Text.Json;
using System.Windows;
using System.Windows.Threading;

namespace PresentationCopilot;

public partial class MainWindow : Window
{
    private readonly AppConfig _config;
    private readonly MainViewModel _viewModel;
    private readonly AudioCaptureService _audioService;
    private readonly WebSocketService _wsService;
    private readonly HotkeyService _hotkeyService;
    private HudWindow? _hudWindow;
    private readonly CancellationTokenSource _cts = new();
    private string? _pendingRequestId;
    private long _pendingAudioBytes;
    private const long MaxPendingAudioBytes = 4_000_000; // ~2 minutes of 16 kHz mono PCM

    // Audio VU meter state (written on the capture thread, read on the UI thread).
    private int _audioLevelMilli;
    private double _displayedLevel;
    private DispatcherTimer? _levelTimer;

    public MainWindow()
    {
        InitializeComponent();

        _config = LoadConfig();
        _audioService = new AudioCaptureService();
        _audioService.Initialize(_config.AudioBufferSeconds);
        _audioService.ChangeSource(_config.AudioSource, _config.AudioDeviceId);

        _wsService = new WebSocketService();
        _hotkeyService = new HotkeyService();

        _viewModel = new MainViewModel();

        _viewModel.OpacityTarget = _config.OpacityLevel;

        SetTrayIcon();
        WireEvents();

        // VU meter: sample the level ~15x/second on the UI thread instead of
        // updating per audio frame, so the meter never saturates the UI.
        _levelTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(66) };
        _levelTimer.Tick += OnLevelTick;
        _levelTimer.Start();

        _ = StartupAsync();
    }

    // ── Initialization ────────────────────────────────────────────────────

    private static AppConfig LoadConfig()
    {
        // Configuration lives next to the executable and is the single source of
        // truth. Builds never overwrite it once the file exists (see the csproj).
        var builder = new ConfigurationBuilder()
            .SetBasePath(AppContext.BaseDirectory)
            .AddJsonFile("appsettings.json", optional: true, reloadOnChange: false);

        IConfigurationRoot root = builder.Build();
        var cfg = new AppConfig();
        root.Bind(cfg);
        return cfg;
    }

    private void SetTrayIcon()
    {
        try
        {
            // Embedded resource so the tray icon is present even when the app is
            // published without loose files next to the executable.
            TrayIcon.IconSource = new System.Windows.Media.Imaging.BitmapImage(
                new Uri("pack://application:,,,/Resources/app.ico", UriKind.Absolute));
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[MainWindow] Tray icon load failed: {ex.Message}");
        }
    }

    private void WireEvents()
    {
        _wsService.ConnectionStateChanged += (_, connected) =>
        {
            Dispatcher.Invoke(() =>
            {
                _viewModel.IsConnected = connected;
                if (!connected)
                {
                    _pendingRequestId = null;
                    _viewModel.IsBusy = false;
                    _viewModel.StatusMessage = "Disconnected";
                }
                else
                {
                    _viewModel.StatusMessage = "Connected";
                }
            });
            // Re-send the topic on the first connect and after every reconnect:
            // the server gives each connection a fresh context.
            if (connected)
                _ = SendTopicAsync(_config.PresentationTopic);
        };

        _audioService.DataAvailable += OnAudioDataAvailable;

        _wsService.SuggestionReceived += (_, json) =>
        {
            Dispatcher.Invoke(() => OnSuggestionReceived(json));
        };

        _hotkeyService.AnalyzeHotkeyPressed += (_, _) =>
        {
            _ = TriggerAnalysisAsync();
        };

        _hotkeyService.ToggleHotkeyPressed += (_, _) => ToggleOverlay();
    }

    /// <summary>
    /// Streams converted audio to the server continuously so its sliding window
    /// always holds the recent question. Drops frames when the socket backs up
    /// instead of growing without bound.
    /// </summary>
    private void OnAudioDataAvailable(object? sender, byte[] pcm)
    {
        if (pcm.Length == 0) return;

        // The VU meter always runs, even when audio is not streamed to the server.
        UpdateLevel(pcm);

        if (!_config.StreamContinuously) return;
        if (!_viewModel.IsRecording) return;
        if (!_wsService.IsConnected) return;
        if (Interlocked.Read(ref _pendingAudioBytes) > MaxPendingAudioBytes) return;

        Interlocked.Add(ref _pendingAudioBytes, pcm.Length);
        _ = SendAudioSafeAsync(pcm);
    }

    /// <summary>Computes a cheap RMS level (0..1000) for the current chunk.</summary>
    private void UpdateLevel(byte[] pcm)
    {
        int samples = pcm.Length / 2;
        if (samples == 0) return;

        int step = Math.Max(1, samples / 512);
        double sum = 0;
        int count = 0;
        for (int i = 0; i < samples; i += step)
        {
            int idx = i * 2;
            short sample = (short)(pcm[idx] | (pcm[idx + 1] << 8));
            double v = sample / 32768.0;
            sum += v * v;
            count++;
        }

        double rms = Math.Sqrt(sum / Math.Max(1, count));
        int milli = (int)Math.Clamp(rms * 4.0 * 1000.0, 0, 1000);
        Interlocked.Exchange(ref _audioLevelMilli, milli);
    }

    /// <summary>Runs on the UI thread ~15x/second and pushes a smoothed level to the HUD.</summary>
    private void OnLevelTick(object? sender, EventArgs e)
    {
        double target = _viewModel.IsRecording ? Volatile.Read(ref _audioLevelMilli) / 1000.0 : 0.0;

        // Fast attack, gentle release — reads like a normal VU meter.
        _displayedLevel = target > _displayedLevel ? target : _displayedLevel * 0.82;
        if (_displayedLevel < 0.002) _displayedLevel = 0;

        _viewModel.AudioLevel = Math.Round(_displayedLevel, 3);
    }

    private async Task SendAudioSafeAsync(byte[] pcm)
    {
        try
        {
            await _wsService.SendAudioAsync(pcm, _cts.Token);
        }
        catch (Exception)
        {
            // Disconnected or cancelled mid-send: the ring buffer still holds the
            // audio, so nothing is lost from the presenter's point of view.
        }
        finally
        {
            Interlocked.Add(ref _pendingAudioBytes, -pcm.Length);
        }
    }

    private async Task SendTopicAsync(string topic)
    {
        var trimmed = (topic ?? string.Empty).Trim();
        if (trimmed.Length < 3 || trimmed.Length > 200) return;
        try
        {
            await _wsService.SendTextAsync(
                JsonSerializer.Serialize(new { type = "set_topic", topic = trimmed }), _cts.Token);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[MainWindow] set_topic failed: {ex.Message}");
        }
    }

    private async Task StartupAsync()
    {
        try
        {
            await _wsService.ConnectAsync(_config.ServerUri, _config.ApiToken, _cts.Token);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[MainWindow] WS connect failed: {ex.Message}");
        }

        try
        {
            // Start capture off the UI thread: device enumeration and the Media
            // Foundation resampler can take a moment and must not freeze the app.
            await Task.Run(() => _audioService.Start());
            Dispatcher.Invoke(() => _viewModel.IsRecording = true);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[MainWindow] Audio start failed: {ex.Message}");
            Dispatcher.Invoke(() =>
            {
                _viewModel.IsRecording = false;
                _viewModel.StatusMessage = $"Audio capture failed: {ex.Message}";
            });
        }

        try
        {
            _hotkeyService.Register(
                (uint)_config.HotKeyModifiers, (uint)_config.HotKeyCode,
                (uint)_config.ToggleHotKeyModifiers, (uint)_config.ToggleHotKeyCode);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[MainWindow] Hotkey register failed: {ex.Message}");
            Dispatcher.Invoke(() => _viewModel.StatusMessage = $"Hotkey not registered: {ex.Message}");
        }

        _viewModel.HotkeyHint = HotkeyService.Describe((uint)_config.HotKeyModifiers, (uint)_config.HotKeyCode);
        _viewModel.ToggleHotkeyHint = HotkeyService.Describe((uint)_config.ToggleHotKeyModifiers, (uint)_config.ToggleHotKeyCode);
        _viewModel.KeyPoint = $"Ready. Press {_viewModel.HotkeyHint} when asked a question.";

        Dispatcher.Invoke(() =>
        {
            _hudWindow = new HudWindow(_viewModel);
            _hudWindow.OpenSettingsRequested += (_, _) => Dispatcher.Invoke(OpenSettings);
            _hudWindow.ShowWithFade();   // bring the HUD up as soon as the app starts
        });
    }

    // ── Core Logic ────────────────────────────────────────────────────────

    private void ToggleRecording()
    {
        if (_viewModel.IsRecording)
        {
            _audioService.Stop();
            _viewModel.IsRecording = false;
            _viewModel.StatusMessage = "Recording paused";
        }
        else
        {
            try
            {
                _audioService.Start();
                _viewModel.IsRecording = true;
                _viewModel.StatusMessage = "Recording";
            }
            catch (Exception ex)
            {
                _viewModel.StatusMessage = $"Audio capture failed: {ex.Message}";
            }
        }
    }

    private async Task TriggerAnalysisAsync()
    {
        if (_viewModel.IsBusy) return;
        if (!_viewModel.IsConnected)
        {
            ShowNoAnswer("Not connected to the server — check the server URI in Settings.", "Disconnected");
            return;
        }
        if (!_viewModel.IsRecording)
        {
            ShowNoAnswer("Recording is paused — resume it, then press the hotkey.", "Recording is paused");
            return;
        }

        _viewModel.IsBusy = true;
        _viewModel.StatusMessage = "Analyzing…";

        try
        {
            string requestId = Guid.NewGuid().ToString("N");
            _pendingRequestId = requestId;

            if (_config.StreamContinuously)
            {
                // Audio is already streaming; the server analyses the last
                // `seconds` of its sliding window.
                int seconds = Math.Clamp(_config.AudioBufferSeconds, 5, 90);
                await _wsService.SendTextAsync(
                    JsonSerializer.Serialize(new { type = "trigger", request_id = requestId, seconds }), _cts.Token);
            }
            else
            {
                byte[] pcm = _audioService.GetLastSeconds(_config.AudioBufferSeconds);
                if (pcm.Length == 0)
                {
                    ShowNoAnswer("No audio captured yet — speak, then press the hotkey again.", "No audio captured yet");
                    return;
                }

                int seconds = Math.Clamp(_config.AudioBufferSeconds, 5, 90);
                await _wsService.SendAudioAsync(pcm, _cts.Token);
                await _wsService.SendTextAsync(
                    JsonSerializer.Serialize(new { type = "trigger", request_id = requestId, seconds }), _cts.Token);
            }

            Dispatcher.Invoke(() => _hudWindow?.ShowWithFade());
            _ = WatchRequestTimeoutAsync(requestId);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[MainWindow] Analysis error: {ex.Message}");
            ShowNoAnswer($"Could not send the request: {ex.Message}", "Send failed");
        }
    }

    private async Task WatchRequestTimeoutAsync(string requestId)
    {
        try
        {
            await Task.Delay(TimeSpan.FromMinutes(3), _cts.Token);
            if (_pendingRequestId == requestId)
            {
                ShowNoAnswer("No answer came back — the server may be busy. Try again.", "Analysis timed out");
            }
        }
        catch (OperationCanceledException) { }
    }

    /// <summary>
    /// Shows a clear "nothing to answer" card instead of leaving the previous
    /// suggestion on screen when a request produced no question/audio/speech.
    /// </summary>
    private void ShowNoAnswer(string cardText, string statusText)
    {
        _pendingRequestId = null;
        _viewModel.IsBusy = false;
        _viewModel.RetrievedSources = "";
        _viewModel.ApplySuggestion(cardText, [], [], "");
        _viewModel.StatusMessage = statusText;
        _hudWindow?.ShowWithFade();
    }

    private static string FriendlyAnalysisMessage(string serverMessage) => serverMessage switch
    {
        "No audio buffered" => "No audio yet — speak, then press the hotkey again.",
        "No speech detected" => "No speech detected — speak clearly and try again.",
        "Analysis already in progress" => "Still analyzing the previous question…",
        _ => serverMessage
    };

    private void OnSuggestionReceived(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (!root.TryGetProperty("type", out var typeProp)) return;
            string? type = typeProp.GetString();
            if (type == "ping" || type == "cleared") return;

            // Live caption: partial transcript pushed while the client streams.
            // Shows the question forming before the hotkey is pressed.
            if (type == "caption")
            {
                if (!_config.LiveCaptions) return;
                string caption = root.TryGetProperty("text", out var captionProp)
                    ? captionProp.GetString() ?? "" : "";
                if (string.IsNullOrWhiteSpace(caption)) return;
                _viewModel.SetLiveCaption(caption);
                _viewModel.StatusMessage = "Listening…";
                _hudWindow?.ShowWithFade();
                return;
            }

            string? requestId = root.TryGetProperty("request_id", out var idProp) ? idProp.GetString() : null;
            if (type == "error" && requestId == null)
            {
                _viewModel.StatusMessage = root.TryGetProperty("message", out var globalMessage)
                    ? globalMessage.GetString() ?? "Server error" : "Server error";
                return;
            }
            if (requestId == null || requestId != _pendingRequestId) return;
            if (type == "processing")
            {
                _viewModel.StatusMessage = "Transcribing audio…";
                return;
            }
            if (type == "transcript")
            {
                // Prefer the normalizer agent's clean question for readability.
                string cleaned = root.TryGetProperty("normalized", out var normalizedProp)
                    ? normalizedProp.GetString() ?? "" : "";
                if (string.IsNullOrWhiteSpace(cleaned))
                    cleaned = root.TryGetProperty("transcript", out var rawProp) ? rawProp.GetString() ?? "" : "";
                if (!string.IsNullOrWhiteSpace(cleaned))
                    _viewModel.QuestionText = cleaned;
                _viewModel.StatusMessage = "Generating response…";
                return;
            }
            if (type == "error")
            {
                string serverMessage = root.TryGetProperty("message", out var message)
                    ? message.GetString() ?? "Analysis failed" : "Analysis failed";
                ShowNoAnswer(FriendlyAnalysisMessage(serverMessage), serverMessage);
                return;
            }
            if (type != "suggestion") return;

            string transcript = root.TryGetProperty("transcript", out var tr) ? tr.GetString() ?? "" : "";
            string questionText = root.TryGetProperty("normalized_question", out var nq)
                && !string.IsNullOrWhiteSpace(nq.GetString())
                ? nq.GetString()! : transcript;
            string keyPoint = root.TryGetProperty("key_point", out var kp) ? kp.GetString() ?? "" : "";
            string[] keywords = root.TryGetProperty("keywords", out var kw)
                ? kw.EnumerateArray().Select(e => e.GetString() ?? "").ToArray()
                : [];
            string[] steps = root.TryGetProperty("framework_steps", out var fs)
                ? fs.EnumerateArray().Select(e => e.GetString() ?? "").ToArray()
                : [];

            _viewModel.ApplySuggestion(keyPoint, keywords, steps, questionText);
            var sourceList = root.TryGetProperty("retrieved_sources", out var sources) &&
                sources.ValueKind == JsonValueKind.Array
                ? sources.EnumerateArray().Select(e => e.GetString()).Where(s => !string.IsNullOrWhiteSpace(s)).ToArray()
                : [];
            _viewModel.RetrievedSources = sourceList.Length > 0
                ? "Related sources: " + string.Join(" · ", sourceList) : "";
            if (root.TryGetProperty("timings_ms", out var timings) &&
                timings.TryGetProperty("total", out var elapsed))
                _viewModel.StatusMessage = $"Ready · {elapsed.GetInt32()} ms";
            else
                _viewModel.StatusMessage = "Ready";

            _pendingRequestId = null;
            _viewModel.IsBusy = false;

            _hudWindow?.ShowWithFade();
        }
        catch (JsonException ex)
        {
            System.Diagnostics.Debug.WriteLine($"[MainWindow] JSON parse error: {ex.Message}");
            _viewModel.StatusMessage = "Invalid server response";
            _pendingRequestId = null;
            _viewModel.IsBusy = false;
        }
    }

    // ── HUD / tray visibility ─────────────────────────────────────────────

    /// <summary>Shows/hides the HUD and always restores the tray icon if it was hidden.</summary>
    private void ToggleOverlay()
    {
        Dispatcher.Invoke(() =>
        {
            ShowTrayIcon();
            if (_hudWindow is null) return;

            if (_hudWindow.IsVisible)
                _hudWindow.HideWithFade();
            else
                _hudWindow.ShowWithFade();
        });
    }

    private void ShowTrayIcon()
    {
        TrayIcon.Visibility = Visibility.Visible;
    }

    // ── Tray Menu Handlers ────────────────────────────────────────────────

    private void MenuShowHud_Click(object sender, RoutedEventArgs e)
    {
        if (_hudWindow is null) return;

        if (_hudWindow.IsVisible)
            _hudWindow.HideWithFade();
        else
            _hudWindow.ShowWithFade();
    }

    private void MenuSettings_Click(object sender, RoutedEventArgs e)
    {
        OpenSettings();
    }

    private void MenuTogglePin_Click(object sender, RoutedEventArgs e)
    {
        _hudWindow?.SetClickThrough(!_viewModel.IsClickThrough);
    }

    private void MenuAnalyze_Click(object sender, RoutedEventArgs e)
    {
        _ = TriggerAnalysisAsync();
    }

    private void MenuToggleRecording_Click(object sender, RoutedEventArgs e)
    {
        ToggleRecording();
    }

    private void MenuHideTray_Click(object sender, RoutedEventArgs e)
    {
        // Never leave the user unable to get back: only hide the icon when the
        // show/hide hotkey is actually working.
        if (!_hotkeyService.ToggleRegistered)
        {
            _viewModel.StatusMessage = "Cannot hide tray icon: the show/hide hotkey is not registered.";
            return;
        }

        ShowTrayIcon();
        TrayIcon.Visibility = Visibility.Collapsed;
        _viewModel.StatusMessage = $"Tray icon hidden. Press {_viewModel.ToggleHotkeyHint} to restore it.";
    }

    private void OpenSettings()
    {
        var previousUri = _config.ServerUri;
        var previousToken = _config.ApiToken;
        var previousTopic = _config.PresentationTopic;
        var previousBufferSeconds = _config.AudioBufferSeconds;
        var previousAudioSource = _config.AudioSource;
        var previousAudioDeviceId = _config.AudioDeviceId;
        var previousHotKeyModifiers = _config.HotKeyModifiers;
        var previousHotKeyCode = _config.HotKeyCode;
        var previousToggleModifiers = _config.ToggleHotKeyModifiers;
        var previousToggleCode = _config.ToggleHotKeyCode;

        var settings = new SettingsWindow(_config);
        settings.SettingsSaved += async (_, updatedConfig) =>
        {
            if (_hudWindow is not null)
            {
                _hudWindow.Opacity = updatedConfig.OpacityLevel;
                _viewModel.OpacityTarget = updatedConfig.OpacityLevel;
            }

            if (previousAudioSource != updatedConfig.AudioSource ||
                !string.Equals(previousAudioDeviceId, updatedConfig.AudioDeviceId, StringComparison.OrdinalIgnoreCase))
            {
                try
                {
                    // Switch + restart capture off the UI thread so the dialog never stalls.
                    await Task.Run(() =>
                    {
                        _audioService.ChangeSource(updatedConfig.AudioSource, updatedConfig.AudioDeviceId);
                        _audioService.Initialize(updatedConfig.AudioBufferSeconds);
                    });
                    _viewModel.StatusMessage = updatedConfig.AudioSource == AudioSourceKind.Microphone
                        ? "Audio source: microphone"
                        : "Audio source: system audio (loopback)";
                }
                catch (Exception ex)
                {
                    _viewModel.StatusMessage = $"Could not switch audio source: {ex.Message}";
                }
            }
            else if (previousBufferSeconds != updatedConfig.AudioBufferSeconds)
            {
                _audioService.Initialize(updatedConfig.AudioBufferSeconds);
            }

            bool hotkeysChanged =
                previousHotKeyModifiers != updatedConfig.HotKeyModifiers ||
                previousHotKeyCode != updatedConfig.HotKeyCode ||
                previousToggleModifiers != updatedConfig.ToggleHotKeyModifiers ||
                previousToggleCode != updatedConfig.ToggleHotKeyCode;

            if (hotkeysChanged)
            {
                try
                {
                    _hotkeyService.Register(
                        (uint)updatedConfig.HotKeyModifiers, (uint)updatedConfig.HotKeyCode,
                        (uint)updatedConfig.ToggleHotKeyModifiers, (uint)updatedConfig.ToggleHotKeyCode);

                    _viewModel.HotkeyHint = HotkeyService.Describe((uint)updatedConfig.HotKeyModifiers, (uint)updatedConfig.HotKeyCode);
                    _viewModel.ToggleHotkeyHint = HotkeyService.Describe((uint)updatedConfig.ToggleHotKeyModifiers, (uint)updatedConfig.ToggleHotKeyCode);
                    _viewModel.StatusMessage = _hotkeyService.ToggleRegistered
                        ? "Hotkeys updated"
                        : "Analyze hotkey updated; show/hide hotkey is already taken by another app";
                }
                catch (Exception ex)
                {
                    // Could not take the new analyze combination; put the old ones back.
                    try
                    {
                        _hotkeyService.Register(
                            (uint)previousHotKeyModifiers, (uint)previousHotKeyCode,
                            (uint)previousToggleModifiers, (uint)previousToggleCode);
                    }
                    catch { }
                    _viewModel.StatusMessage = $"Hotkey not applied: {ex.Message}";
                }
            }

            bool mustReconnect = previousUri != updatedConfig.ServerUri || previousToken != updatedConfig.ApiToken;
            if (mustReconnect)
            {
                _pendingRequestId = null;
                _viewModel.IsBusy = false;
                try { await _wsService.ConnectAsync(updatedConfig.ServerUri, updatedConfig.ApiToken, _cts.Token); }
                catch (Exception ex) { _viewModel.StatusMessage = $"Connection failed: {ex.Message}"; }
            }
            else if (previousTopic != updatedConfig.PresentationTopic)
            {
                await SendTopicAsync(updatedConfig.PresentationTopic);
            }
        };
        settings.ShowDialog();
    }

    private void MenuExit_Click(object sender, RoutedEventArgs e)
    {
        _ = ShutdownAsync();
    }

    private async Task ShutdownAsync()
    {
        _levelTimer?.Stop();
        _cts.Cancel();
        _hotkeyService.Dispose();
        _audioService.Stop();
        _audioService.Dispose();
        await _wsService.DisposeAsync();
        TrayIcon.Dispose();
        System.Windows.Application.Current.Shutdown();
    }

    protected override void OnClosed(EventArgs e)
    {
        _levelTimer?.Stop();
        _cts.Cancel();
        _hotkeyService.Dispose();
        _audioService.Stop();
        _audioService.Dispose();
        _ = _wsService.DisposeAsync();
        base.OnClosed(e);
    }
}
