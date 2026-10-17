using PresentationCopilot.ViewModels;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;

namespace PresentationCopilot.Views;

public partial class HudWindow : Window
{
    // ── Win32 Extended Window Style ───────────────────────────────────────
    private const int GWL_EXSTYLE = -20;
    private const int WS_EX_TRANSPARENT = 0x00000020;
    private const int WS_EX_TOOLWINDOW  = 0x00000080;
    private const int WS_EX_NOACTIVATE  = 0x08000000;

    // ── SetWindowDisplayAffinity (Windows 10 2004+ / Windows 11) ──────────
    // WDA_NONE (0x00): Default capture behavior.
    // WDA_MONITOR (0x01): Window appears blacked out in captures (Win7 / Win8 / older Win10).
    // WDA_EXCLUDEFROMCAPTURE (0x11): Modern Windows 10 2004+ / Win 11 API.
    // Window is completely removed from captured visual stream (invisible to Zoom, Teams, Meet, OBS, Discord).
    private const uint WDA_NONE               = 0x00000000;
    private const uint WDA_MONITOR            = 0x00000001;
    private const uint WDA_EXCLUDEFROMCAPTURE = 0x00000011;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern int GetWindowLong(IntPtr hwnd, int nIndex);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern int SetWindowLong(IntPtr hwnd, int nIndex, int dwNewLong);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowDisplayAffinity(IntPtr hwnd, uint dwAffinity);

    // ─────────────────────────────────────────────────────────────────────

    private readonly MainViewModel _viewModel;
    private bool _isClickThrough;
    private int HideFadeToken;

    public HudWindow(MainViewModel viewModel)
    {
        InitializeComponent();
        _viewModel = viewModel;
        DataContext = viewModel;
        SourceInitialized += OnSourceInitialized;
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        var hwnd = new WindowInteropHelper(this).Handle;

        // Set toolwindow + noactivate style
        int exStyle = GetWindowLong(hwnd, GWL_EXSTYLE);
        SetWindowLong(hwnd, GWL_EXSTYLE, exStyle | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE);

        // Apply modern Anti-Capture display affinity
        ApplyAntiCaptureAffinity(hwnd, enable: true);
    }

    /// <summary>
    /// Applies WDA_EXCLUDEFROMCAPTURE (0x11) on Windows 10 2004+ or falls back to WDA_MONITOR (0x01).
    /// </summary>
    public void ApplyAntiCaptureAffinity(IntPtr hwnd, bool enable)
    {
        if (!enable)
        {
            SetWindowDisplayAffinity(hwnd, WDA_NONE);
            _viewModel.IsAntiCaptureActive = false;
            return;
        }

        // Try modern 0x11 first
        bool success = SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE);
        if (!success)
        {
            int err = Marshal.GetLastWin32Error();
            System.Diagnostics.Debug.WriteLine($"[HudWindow] WDA_EXCLUDEFROMCAPTURE failed (err={err}), trying WDA_MONITOR fallback");
            // Fallback for older OS versions
            success = SetWindowDisplayAffinity(hwnd, WDA_MONITOR);
        }

        _viewModel.IsAntiCaptureActive = success;
        System.Diagnostics.Debug.WriteLine($"[HudWindow] Anti-Capture Affinity result: {success}");
    }

    /// <summary>
    /// Enables click-through: mouse events pass through the HUD to windows below (e.g. presentation slide).
    /// </summary>
    public void SetClickThrough(bool enable)
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        int current = GetWindowLong(hwnd, GWL_EXSTYLE);
        if (enable)
        {
            SetWindowLong(hwnd, GWL_EXSTYLE, current | WS_EX_TRANSPARENT);
            BtnClickThrough.Content = "📍 UNPIN";
            BtnClickThrough.Foreground = System.Windows.Media.Brushes.Gold;
        }
        else
        {
            SetWindowLong(hwnd, GWL_EXSTYLE, current & ~WS_EX_TRANSPARENT);
            BtnClickThrough.Content = "📌 PIN";
            BtnClickThrough.Foreground = new System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Color.FromArgb(0x99, 0xFF, 0xFF, 0xFF));
        }

        _isClickThrough = enable;
        _viewModel.IsClickThrough = enable;
    }

    private void DragHandle_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState == MouseButtonState.Pressed)
            DragMove();
    }

    private void BtnClickThrough_Click(object sender, RoutedEventArgs e)
    {
        SetClickThrough(!_isClickThrough);
    }

    private void BtnCopy_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var sb = new StringBuilder();
            if (!string.IsNullOrWhiteSpace(_viewModel.QuestionText))
                sb.AppendLine($"Q: {_viewModel.QuestionText}");

            sb.AppendLine($"Key Point: {_viewModel.KeyPoint}");

            if (_viewModel.NumberedSteps.Count > 0)
            {
                sb.AppendLine("Framework:");
                foreach (var step in _viewModel.NumberedSteps)
                    sb.AppendLine($"  {step.Index}. {step.Text}");
            }

            Clipboard.SetText(sb.ToString());
            _viewModel.StatusMessage = "Copied to clipboard!";
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Clipboard copy failed: {ex.Message}");
        }
    }

    /// <summary>Raised when the user clicks the gear icon on the HUD.</summary>
    public event EventHandler? OpenSettingsRequested;

    private void BtnSettings_Click(object sender, RoutedEventArgs e)
    {
        OpenSettingsRequested?.Invoke(this, EventArgs.Empty);
    }

    private void BtnHide_Click(object sender, RoutedEventArgs e)
    {
        HideWithFade();
    }

    private void Window_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Escape)
        {
            HideWithFade();
        }
    }

    /// <summary>Slides the HUD into view with a smooth fade-in.</summary>
    public void ShowWithFade()
    {
        HideFadeToken++;              // cancel a pending hide's Completed callback
        Opacity = 0;
        Show();
        var anim = new System.Windows.Media.Animation.DoubleAnimation(
            0, _viewModel.OpacityTarget,
            new System.Windows.Duration(TimeSpan.FromMilliseconds(180)));
        BeginAnimation(OpacityProperty, anim);
    }

    /// <summary>Fades the HUD out then hides it.</summary>
    public void HideWithFade()
    {
        int token = ++HideFadeToken;
        var anim = new System.Windows.Media.Animation.DoubleAnimation(
            Opacity, 0,
            new System.Windows.Duration(TimeSpan.FromMilliseconds(150)));
        anim.Completed += (_, _) =>
        {
            // Only hide if no newer show/hide started in the meantime.
            if (token == HideFadeToken) Hide();
        };
        BeginAnimation(OpacityProperty, anim);
    }
}
