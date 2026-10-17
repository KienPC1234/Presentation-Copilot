using System.Runtime.InteropServices;
using System.Windows.Input;
using System.Windows.Interop;

namespace PresentationCopilot.Services;

/// <summary>
/// Registers two global system hotkeys via Win32 RegisterHotKey:
///  • Analyze  — request a suggestion
///  • Toggle   — show/hide the HUD (also restores a hidden tray icon)
/// Listens for WM_HOTKEY messages through a hidden HwndSource.
/// Supports re-registering at runtime (e.g. after the user changes them in Settings).
/// </summary>
public sealed class HotkeyService : IDisposable
{
    private const int WM_HOTKEY = 0x0312;
    private const int HOTKEY_ID_ANALYZE = 0xBEEF;
    private const int HOTKEY_ID_TOGGLE  = 0xBEF0;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    private HwndSource? _hwndSource;
    private bool _disposed;
    private bool _analyzeRegistered;
    private bool _toggleRegistered;

    /// <summary>Raised on the UI thread when the analyze hotkey is pressed.</summary>
    public event EventHandler? AnalyzeHotkeyPressed;

    /// <summary>Raised on the UI thread when the show/hide (toggle) hotkey is pressed.</summary>
    public event EventHandler? ToggleHotkeyPressed;

    /// <summary>True when the analyze hotkey is currently registered.</summary>
    public bool AnalyzeRegistered => _analyzeRegistered;

    /// <summary>True when the toggle hotkey is currently registered.</summary>
    public bool ToggleRegistered => _toggleRegistered;

    /// <summary>
    /// Initializes the message-only window and registers both hotkeys.
    /// Safe to call again to change the combinations; previous ones are released first.
    /// Throws when the analyze hotkey cannot be taken; a toggle conflict is reported
    /// through <see cref="ToggleRegistered"/> instead of throwing.
    /// </summary>
    /// <param name="analyzeModifiers">MOD_* flags for analyze: 1=Alt, 2=Ctrl, 4=Shift, 8=Win.</param>
    /// <param name="analyzeKey">Virtual key code for analyze (e.g. 0x20 = Space).</param>
    /// <param name="toggleModifiers">MOD_* flags for show/hide.</param>
    /// <param name="toggleKey">Virtual key code for show/hide.</param>
    public void Register(uint analyzeModifiers, uint analyzeKey, uint toggleModifiers, uint toggleKey)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        // Release any previous registration so the hotkeys can be changed at runtime.
        UnregisterCore();

        // Create a message-only (HWND_MESSAGE) window to receive WM_HOTKEY
        var parameters = new HwndSourceParameters("HotkeyHost")
        {
            WindowStyle = 0,
            ExtendedWindowStyle = 0,
            PositionX = 0,
            PositionY = 0,
            Width = 0,
            Height = 0,
            ParentWindow = new IntPtr(-3) // HWND_MESSAGE
        };

        _hwndSource = new HwndSource(parameters);
        _hwndSource.AddHook(WndProc);

        _analyzeRegistered = RegisterHotKey(_hwndSource.Handle, HOTKEY_ID_ANALYZE, analyzeModifiers, analyzeKey);
        if (!_analyzeRegistered)
        {
            int error = Marshal.GetLastWin32Error();
            UnregisterCore();
            throw new InvalidOperationException(
                $"Failed to register the analyze hotkey (modifiers=0x{analyzeModifiers:X}, vk=0x{analyzeKey:X}). Win32 error: {error}");
        }

        _toggleRegistered = RegisterHotKey(_hwndSource.Handle, HOTKEY_ID_TOGGLE, toggleModifiers, toggleKey);
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == WM_HOTKEY)
        {
            int id = wParam.ToInt32();
            if (id == HOTKEY_ID_ANALYZE)
            {
                AnalyzeHotkeyPressed?.Invoke(this, EventArgs.Empty);
                handled = true;
            }
            else if (id == HOTKEY_ID_TOGGLE)
            {
                ToggleHotkeyPressed?.Invoke(this, EventArgs.Empty);
                handled = true;
            }
        }
        return IntPtr.Zero;
    }

    /// <summary>
    /// Formats a MOD_* mask and virtual key into a display string such as "Ctrl+Shift+Space".
    /// </summary>
    public static string Describe(uint modifiers, uint virtualKey)
    {
        var parts = new List<string>(4);
        if ((modifiers & 1) != 0) parts.Add("Alt");
        if ((modifiers & 2) != 0) parts.Add("Ctrl");
        if ((modifiers & 4) != 0) parts.Add("Shift");
        if ((modifiers & 8) != 0) parts.Add("Win");

        var key = KeyInterop.KeyFromVirtualKey((int)virtualKey);
        parts.Add(key == Key.None ? $"0x{virtualKey:X2}" : key.ToString());
        return string.Join("+", parts);
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        UnregisterCore();
    }

    private void UnregisterCore()
    {
        if (_hwndSource is null) return;

        if (_analyzeRegistered)
        {
            UnregisterHotKey(_hwndSource.Handle, HOTKEY_ID_ANALYZE);
            _analyzeRegistered = false;
        }
        if (_toggleRegistered)
        {
            UnregisterHotKey(_hwndSource.Handle, HOTKEY_ID_TOGGLE);
            _toggleRegistered = false;
        }

        _hwndSource.RemoveHook(WndProc);
        _hwndSource.Dispose();
        _hwndSource = null;
    }
}
