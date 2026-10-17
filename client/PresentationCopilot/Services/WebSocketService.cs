using System.Net.WebSockets;
using System.Text;
using Websocket.Client;

namespace PresentationCopilot.Services;

/// <summary>
/// Manages a persistent WebSocket connection to the Python backend.
/// Automatically reconnects on disconnect. Thread-safe send operations.
/// </summary>
public sealed class WebSocketService : IAsyncDisposable
{
    private WebsocketClient? _client;
    private readonly SemaphoreSlim _sendLock = new(1, 1);
    private bool _disposed;

    /// <summary>Raised on the ThreadPool when the server sends a JSON suggestion payload.</summary>
    public event EventHandler<string>? SuggestionReceived;

    /// <summary>Raised when connection state changes.</summary>
    public event EventHandler<bool>? ConnectionStateChanged;

    public bool IsConnected => _client?.IsRunning ?? false;

    public async Task ConnectAsync(string serverUri, CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        if (_client is not null)
        {
            await _client.Stop(WebSocketCloseStatus.NormalClosure, "Switching endpoint");
            _client.Dispose();
            _client = null;
        }

        if (!serverUri.EndsWith("/ws") && !serverUri.EndsWith("/ws/"))
        {
            serverUri = serverUri.TrimEnd('/') + "/ws";
        }
        var uri = new Uri(serverUri);
        var factory = new Func<ClientWebSocket>(() =>
        {
            var ws = new ClientWebSocket();
            ws.Options.KeepAliveInterval = TimeSpan.FromSeconds(30);
            var token = Environment.GetEnvironmentVariable("PRESENTATION_COPILOT_API_TOKEN");
            if (!string.IsNullOrWhiteSpace(token))
                ws.Options.SetRequestHeader("Authorization", "Bearer " + token);
            return ws;
        });

        _client = new WebsocketClient(uri, factory)
        {
            ReconnectTimeout = TimeSpan.FromSeconds(10),
            ErrorReconnectTimeout = TimeSpan.FromSeconds(5),
            IsReconnectionEnabled = true
        };

        _client.MessageReceived.Subscribe(OnMessageReceived);
        _client.ReconnectionHappened.Subscribe(info =>
        {
            System.Diagnostics.Debug.WriteLine($"[WebSocket] Reconnected: {info.Type}");
            ConnectionStateChanged?.Invoke(this, true);
        });
        _client.DisconnectionHappened.Subscribe(info =>
        {
            System.Diagnostics.Debug.WriteLine($"[WebSocket] Disconnected: {info.Type}");
            ConnectionStateChanged?.Invoke(this, false);
        });

        await _client.StartOrFail();
        ConnectionStateChanged?.Invoke(this, true);
    }

    /// <summary>
    /// Sends raw PCM audio bytes as a binary WebSocket frame.
    /// </summary>
    public async Task SendAudioAsync(byte[] pcmData, CancellationToken cancellationToken = default)
    {
        if (_client is null || !_client.IsRunning)
            throw new InvalidOperationException("WebSocket disconnected");

        await _sendLock.WaitAsync(cancellationToken);
        try
        {
            await _client.SendInstant(pcmData);
        }
        finally
        {
            _sendLock.Release();
        }
    }

    /// <summary>
    /// Sends a JSON text message to the server.
    /// </summary>
    public async Task SendTextAsync(string json, CancellationToken cancellationToken = default)
    {
        if (_client is null || !_client.IsRunning)
            throw new InvalidOperationException("WebSocket disconnected");

        await _sendLock.WaitAsync(cancellationToken);
        try
        {
            await _client.SendInstant(json);
        }
        finally
        {
            _sendLock.Release();
        }
    }

    public async Task DisconnectAsync()
    {
        if (_client is null) return;
        await _client.Stop(WebSocketCloseStatus.NormalClosure, "Client disconnecting");
        ConnectionStateChanged?.Invoke(this, false);
    }

    private void OnMessageReceived(ResponseMessage message)
    {
        if (message.MessageType == WebSocketMessageType.Text && message.Text is not null)
        {
            SuggestionReceived?.Invoke(this, message.Text);
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed) return;
        _disposed = true;

        if (_client is not null)
        {
            try { await _client.Stop(WebSocketCloseStatus.NormalClosure, "Dispose"); } catch { }
            _client.Dispose();
            _client = null;
        }

        _sendLock.Dispose();
    }
}

