using System.Runtime.InteropServices;
using System.Windows.Interop;

namespace PresentationCopilot.Services;

/// <summary>
/// Registers a global system hotkey via Win32 RegisterHotKey.
/// Listens for WM_HOTKEY messages through a hidden HwndSource.
/// </summary>
public sealed class HotkeyService : IDisposable
{
    private const int WM_HOTKEY = 0x0312;
    private const int HOTKEY_ID = 0xBEEF;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    private HwndSource? _hwndSource;
    private bool _disposed;
    private bool _registered;

    /// <summary>Raised on the UI thread when the registered hotkey combination is pressed.</summary>
    public event EventHandler? HotkeyPressed;

    /// <summary>
    /// Initializes the message-only window and registers the hotkey.
    /// Must be called after the application's main window handle is available.
    /// </summary>
    /// <param name="modifiers">MOD_* flags: 1=Alt, 2=Ctrl, 4=Shift, 8=Win. Combine with bitwise OR.</param>
    /// <param name="virtualKey">Virtual key code (e.g. 0x20 = Space).</param>
    public void Register(uint modifiers, uint virtualKey)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

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

        _registered = RegisterHotKey(_hwndSource.Handle, HOTKEY_ID, modifiers, virtualKey);
        if (!_registered)
        {
            int error = Marshal.GetLastWin32Error();
            throw new InvalidOperationException(
                $"Failed to register hotkey (modifiers=0x{modifiers:X}, vk=0x{virtualKey:X}). Win32 error: {error}");
        }
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == WM_HOTKEY && wParam.ToInt32() == HOTKEY_ID)
        {
            HotkeyPressed?.Invoke(this, EventArgs.Empty);
            handled = true;
        }
        return IntPtr.Zero;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        if (_hwndSource is not null)
        {
            if (_registered)
            {
                UnregisterHotKey(_hwndSource.Handle, HOTKEY_ID);
                _registered = false;
            }

            _hwndSource.RemoveHook(WndProc);
            _hwndSource.Dispose();
            _hwndSource = null;
        }
    }
}

