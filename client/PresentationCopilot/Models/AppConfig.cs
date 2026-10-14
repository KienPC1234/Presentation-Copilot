namespace PresentationCopilot.Models;

public sealed class AppConfig
{
    public string ServerUri { get; set; } = "ws://localhost:8765";
    public string HotKey { get; set; } = "Ctrl+Shift+Space";
    public int HotKeyModifiers { get; set; } = 6;
    public int HotKeyCode { get; set; } = 32;
    public int AudioBufferSeconds { get; set; } = 10;
    public double OpacityLevel { get; set; } = 0.88;
}

