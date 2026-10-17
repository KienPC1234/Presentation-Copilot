namespace PresentationCopilot.Models;

/// <summary>Where the client captures audio from.</summary>
public enum AudioSourceKind
{
    /// <summary>System playback via WASAPI loopback (speakers / headphones).</summary>
    Loopback = 0,

    /// <summary>Default recording device (microphone).</summary>
    Microphone = 1
}

/// <summary>A selectable audio input, shown in the Settings dropdown.</summary>
/// <param name="Label">Friendly text shown to the user.</param>
/// <param name="Id">WASAPI endpoint id; empty means "the system default for this kind".</param>
/// <param name="Kind">Loopback (render) or microphone (capture).</param>
public sealed record AudioDeviceInfo(string Label, string Id, AudioSourceKind Kind)
{
    public override string ToString() => Label;
}

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

    /// <summary>Second hotkey: shows/hides the HUD and restores a hidden tray icon.</summary>
    public string ToggleHotKey { get; set; } = "Ctrl+Alt+H";
    public int ToggleHotKeyModifiers { get; set; } = 3;   // Alt (1) + Ctrl (2)
    public int ToggleHotKeyCode { get; set; } = 72;       // 'H'

    /// <summary>Seconds of audio analysed on each hotkey press.</summary>
    public int AudioBufferSeconds { get; set; } = 20;

    public double OpacityLevel { get; set; } = 0.88;

    /// <summary>Stream audio to the server continuously instead of only
    /// when the hotkey is pressed. Keeps the server's sliding window current.</summary>
    public bool StreamContinuously { get; set; } = true;

    /// <summary>Show the server's live captions on the HUD while audio is being
    /// streamed, so the question appears as it is being asked.</summary>
    public bool LiveCaptions { get; set; } = true;

    /// <summary>Capture the system output (loopback) or the microphone.</summary>
    public AudioSourceKind AudioSource { get; set; } = AudioSourceKind.Loopback;

    /// <summary>Specific WASAPI endpoint id to capture. Empty = system default for <see cref="AudioSource"/>.</summary>
    public string AudioDeviceId { get; set; } = "";
}
