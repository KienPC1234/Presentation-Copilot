using Microsoft.Extensions.Configuration;
using PresentationCopilot.Models;
using PresentationCopilot.Services;
using PresentationCopilot.ViewModels;
using PresentationCopilot.Views;
using System.IO;
using System.Text.Json;
using System.Windows;

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

    public MainWindow()
    {
        InitializeComponent();

        _config = LoadConfig();
        _audioService = new AudioCaptureService();
        _audioService.Initialize(_config.AudioBufferSeconds);

        _wsService = new WebSocketService();
        _hotkeyService = new HotkeyService();

        _viewModel = new MainViewModel(
            toggleRecording: ToggleRecording,
            triggerAnalysis: () => _ = TriggerAnalysisAsync());

        _viewModel.OpacityTarget = _config.OpacityLevel;

        SetTrayIcon();
        WireEvents();

        _ = StartupAsync();
    }

    // ── Initialization ────────────────────────────────────────────────────

    private static AppConfig LoadConfig()
    {
        string userConfig = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                                         "PresentationCopilot", "appsettings.json");
        var builder = new ConfigurationBuilder()
            .SetBasePath(AppContext.BaseDirectory)
            .AddJsonFile("appsettings.json", optional: false, reloadOnChange: false)
            .AddJsonFile(userConfig, optional: true, reloadOnChange: false);

        IConfigurationRoot root = builder.Build();
        var cfg = new AppConfig();
        root.Bind(cfg);
        return cfg;
    }

    private void SetTrayIcon()
    {
        try
        {
            var iconPath = Path.Combine(AppContext.BaseDirectory, "Resources", "app.ico");
            if (File.Exists(iconPath))
            {
                // Hardcodet.NotifyIcon.Wpf uses System.Drawing.Icon internally
                TrayIcon.IconSource = new System.Windows.Media.Imaging.BitmapImage(
                    new Uri(iconPath, UriKind.Absolute));
            }
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

        _hotkeyService.HotkeyPressed += (_, _) =>
        {
            _ = TriggerAnalysisAsync();
        };
    }

    /// <summary>
    /// Streams converted audio to the server continuously so its sliding window
    /// always holds the recent question. Drops frames when the socket backs up
    /// instead of growing without bound.
    /// </summary>
    private void OnAudioDataAvailable(object? sender, byte[] pcm)
    {
        if (!_config.StreamContinuously || pcm.Length == 0) return;
        if (!_viewModel.IsRecording) return;
        if (!_wsService.IsConnected) return;
        if (Interlocked.Read(ref _pendingAudioBytes) > MaxPendingAudioBytes) return;

        Interlocked.Add(ref _pendingAudioBytes, pcm.Length);
        _ = SendAudioSafeAsync(pcm);
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
            _audioService.Start();
            Dispatcher.Invoke(() => _viewModel.IsRecording = true);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[MainWindow] Audio start failed: {ex.Message}");
        }

        try
        {
            _hotkeyService.Register((uint)_config.HotKeyModifiers, (uint)_config.HotKeyCode);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[MainWindow] Hotkey register failed: {ex.Message}");
        }

        Dispatcher.Invoke(() =>
        {
            _hudWindow = new HudWindow(_viewModel);
            _hudWindow.OpenSettingsRequested += (_, _) => Dispatcher.Invoke(OpenSettings);
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
            _audioService.Start();
            _viewModel.IsRecording = true;
            _viewModel.StatusMessage = "Recording";
        }
    }

    private async Task TriggerAnalysisAsync()
    {
        if (_viewModel.IsBusy || !_viewModel.IsConnected) return;

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
                    _viewModel.StatusMessage = "No audio captured yet";
                    _pendingRequestId = null;
                    _viewModel.IsBusy = false;
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
            _viewModel.StatusMessage = $"Error: {ex.Message}";
            _pendingRequestId = null;
            _viewModel.IsBusy = false;
        }
    }

    private async Task WatchRequestTimeoutAsync(string requestId)
    {
        try
        {
            await Task.Delay(TimeSpan.FromMinutes(3), _cts.Token);
            if (_pendingRequestId == requestId)
            {
                _pendingRequestId = null;
                _viewModel.IsBusy = false;
                _viewModel.StatusMessage = "Analysis timed out";
            }
        }
        catch (OperationCanceledException) { }
    }

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
            // Show the question forming before the hotkey is pressed.
            if (type == "caption")
            {
                if (!_config.LiveCaptions) return;
                string caption = root.TryGetProperty("text", out var captionProp)
                    ? captionProp.GetString() ?? "" : "";
                if (string.IsNullOrWhiteSpace(caption)) return;
                _viewModel.QuestionText = caption;
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
                _viewModel.StatusMessage = "Generating response…";
                return;
            }
            if (type == "error")
            {
                _pendingRequestId = null;
                _viewModel.IsBusy = false;
                _viewModel.StatusMessage = root.TryGetProperty("message", out var message)
                    ? message.GetString() ?? "Analysis failed" : "Analysis failed";
                return;
            }
            if (type != "suggestion") return;

            string transcript = root.TryGetProperty("transcript", out var tr) ? tr.GetString() ?? "" : "";
            string keyPoint = root.TryGetProperty("key_point", out var kp) ? kp.GetString() ?? "" : "";
            string[] keywords = root.TryGetProperty("keywords", out var kw)
                ? kw.EnumerateArray().Select(e => e.GetString() ?? "").ToArray()
                : [];
            string[] steps = root.TryGetProperty("framework_steps", out var fs)
                ? fs.EnumerateArray().Select(e => e.GetString() ?? "").ToArray()
                : [];

            _viewModel.ApplySuggestion(keyPoint, keywords, steps, json, transcript);
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

    private void OpenSettings()
    {
        var previousUri = _config.ServerUri;
        var previousToken = _config.ApiToken;
        var previousTopic = _config.PresentationTopic;
        var previousBufferSeconds = _config.AudioBufferSeconds;
        var settings = new SettingsWindow(_config);
        settings.SettingsSaved += async (_, updatedConfig) =>
        {
            if (_hudWindow is not null)
            {
                _hudWindow.Opacity = updatedConfig.OpacityLevel;
                _viewModel.OpacityTarget = updatedConfig.OpacityLevel;
            }
            if (previousBufferSeconds != updatedConfig.AudioBufferSeconds)
                _audioService.Initialize(updatedConfig.AudioBufferSeconds);

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
        _cts.Cancel();
        _hotkeyService.Dispose();
        _audioService.Stop();
        _audioService.Dispose();
        _ = _wsService.DisposeAsync();
        base.OnClosed(e);
    }
}

