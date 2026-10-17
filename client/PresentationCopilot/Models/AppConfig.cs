namespace PresentationCopilot.Models;

public sealed class AppConfig
{
    public string ServerUri { get; set; } = "ws://localhost:8765";

    /// <summary>Bearer token matching API_TOKEN on the server. Falls back to the
    /// PRESENTATION_COPILOT_API_TOKEN environment variable when empty.</summary>
    public string ApiToken { get; set; } = "";

    /// <summary>Optional product/topic name sent to the server to anchor retrieval.</summary>
    public string PresentationTopic { get; set; } = "";

    public string HotKey { get; set; } = "Ctrl+Shift+Space";
    public int HotKeyModifiers { get; set; } = 6;
    public int HotKeyCode { get; set; } = 32;

    /// <summary>Seconds of audio analysed on each hotkey press.</summary>
    public int AudioBufferSeconds { get; set; } = 20;

    public double OpacityLevel { get; set; } = 0.88;

    /// <summary>Stream loopback audio to the server continuously instead of only
    /// when the hotkey is pressed. Keeps the server's sliding window current.</summary>
    public bool StreamContinuously { get; set; } = true;

    /// <summary>Show the server's live captions on the HUD while audio is being
    /// streamed, so the question appears as it is being asked.</summary>
    public bool LiveCaptions { get; set; } = true;
}
