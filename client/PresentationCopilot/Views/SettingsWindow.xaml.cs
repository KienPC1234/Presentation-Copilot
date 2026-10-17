using PresentationCopilot.Models;
using PresentationCopilot.Services;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace PresentationCopilot.Views;

public partial class SettingsWindow : Window
{
    private readonly AppConfig _config;
    private IReadOnlyList<AudioDeviceInfo> _devices = [];

    // Hotkeys captured from the keyboard; applied to the config on Save.
    private uint _pendingAnalyzeModifiers;
    private int _pendingAnalyzeKey;
    private uint _pendingToggleModifiers;
    private int _pendingToggleKey;

    /// <summary>Raised when the user confirms changes. Contains the updated config.</summary>
    public event EventHandler<AppConfig>? SettingsSaved;

    public SettingsWindow(AppConfig config)
    {
        InitializeComponent();
        _config = config;

        _pendingAnalyzeModifiers = (uint)config.HotKeyModifiers;
        _pendingAnalyzeKey = config.HotKeyCode;
        _pendingToggleModifiers = (uint)config.ToggleHotKeyModifiers;
        _pendingToggleKey = config.ToggleHotKeyCode;

        TxtVersion.Text = "Version " + (Assembly.GetExecutingAssembly().GetName().Version?.ToString() ?? "dev");
        LoadCurrentValues();
    }

    private void LoadCurrentValues()
    {
        TxtServerUri.Text = _config.ServerUri;
        TxtApiToken.Password = _config.ApiToken;
        TxtTopic.Text = _config.PresentationTopic;
        ChkStream.IsChecked = _config.StreamContinuously;
        ChkLiveCaptions.IsChecked = _config.LiveCaptions;

        PopulateAudioDevices();
        SelectAudioDevice(_config.AudioSource, _config.AudioDeviceId);

        RefreshHotkeyBoxes();

        SliderOpacity.Value = _config.OpacityLevel;
        TxtOpacityValue.Text = _config.OpacityLevel.ToString("P0");

        SliderBuffer.Value = _config.AudioBufferSeconds;
        TxtBufferValue.Text = $"{_config.AudioBufferSeconds}s";
    }

    // ── Audio device dropdown ─────────────────────────────────────────────

    private void PopulateAudioDevices()
    {
        _devices = AudioCaptureService.EnumerateDevices();
        CmbAudioDevice.ItemsSource = _devices;
    }

    private void SelectAudioDevice(AudioSourceKind kind, string? id)
    {
        string wanted = string.IsNullOrWhiteSpace(id) ? "" : id;

        var match = _devices.FirstOrDefault(d =>
                        d.Kind == kind && string.Equals(d.Id, wanted, StringComparison.OrdinalIgnoreCase))
                    ?? _devices.FirstOrDefault(d => d.Kind == kind && d.Id.Length == 0)
                    ?? _devices.FirstOrDefault();

        CmbAudioDevice.SelectedItem = match;
    }

    private void RefreshHotkeyBoxes()
    {
        TxtHotkey.Text = HotkeyService.Describe(_pendingAnalyzeModifiers, (uint)_pendingAnalyzeKey);
        TxtToggleHotkey.Text = HotkeyService.Describe(_pendingToggleModifiers, (uint)_pendingToggleKey);
    }

    private void SliderOpacity_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (TxtOpacityValue is not null)
            TxtOpacityValue.Text = e.NewValue.ToString("P0");
    }

    private void SliderBuffer_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (TxtBufferValue is not null)
            TxtBufferValue.Text = $"{(int)e.NewValue}s";
    }

    // ── Hotkey capture ────────────────────────────────────────────────────

    private void HotkeyBox_GotKeyboardFocus(object sender, KeyboardFocusChangedEventArgs e)
    {
        TxtHotkeyStatus.Text = "Press the new combination now (Esc to cancel)…";
    }

    private void HotkeyBox_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (sender is not TextBox box) return;
        bool isToggle = (box.Tag as string) == "toggle";

        Key key = e.Key == Key.System ? e.SystemKey : e.Key;

        if (key == Key.Escape)
        {
            e.Handled = true;
            RefreshHotkeyBoxes();
            TxtHotkeyStatus.Text = "Cancelled. Press Esc while capturing to cancel.";
            return;
        }

        // Let Tab move focus when no combination is being captured.
        if (key == Key.Tab && Keyboard.Modifiers == ModifierKeys.None)
            return;

        e.Handled = true;

        if (key is Key.LeftCtrl or Key.RightCtrl or Key.LeftShift or Key.RightShift
            or Key.LeftAlt or Key.RightAlt or Key.LWin or Key.RWin
            or Key.None)
        {
            TxtHotkeyStatus.Text = "Hold a modifier (Ctrl / Shift / Alt) and press a key.";
            return;
        }

        uint modifiers = 0;
        ModifierKeys mods = Keyboard.Modifiers;
        if ((mods & ModifierKeys.Alt) != 0) modifiers |= 1;
        if ((mods & ModifierKeys.Control) != 0) modifiers |= 2;
        if ((mods & ModifierKeys.Shift) != 0) modifiers |= 4;

        if (modifiers == 0)
        {
            TxtHotkeyStatus.Text = "Add Ctrl, Shift or Alt so the hotkey does not clash with normal typing.";
            return;
        }

        int vk = KeyInterop.VirtualKeyFromKey(key);
        if (vk == 0)
        {
            TxtHotkeyStatus.Text = "That key is not supported.";
            return;
        }

        if (isToggle)
        {
            _pendingToggleModifiers = modifiers;
            _pendingToggleKey = vk;
        }
        else
        {
            _pendingAnalyzeModifiers = modifiers;
            _pendingAnalyzeKey = vk;
        }

        RefreshHotkeyBoxes();
        TxtHotkeyStatus.Text = "Captured — press Save to apply.";
    }

    // ── Connection test ───────────────────────────────────────────────────

    private async void BtnTest_Click(object sender, RoutedEventArgs e)
    {
        BtnTest.IsEnabled = false;
        SetStatus("Testing…", Color.FromRgb(0xAA, 0xAA, 0xCC));

        try
        {
            string uriText = TxtServerUri.Text.Trim();
            if (!Uri.TryCreate(uriText, UriKind.Absolute, out var parsed) ||
                (parsed.Scheme != "ws" && parsed.Scheme != "wss"))
            {
                SetStatus("Invalid ws:// or wss:// URI.", Color.FromRgb(0xF4, 0x43, 0x36));
                return;
            }

            Uri wsUri = uriText.EndsWith("/ws") ? parsed : new Uri(uriText.TrimEnd('/') + "/ws");
            using var socket = new System.Net.WebSockets.ClientWebSocket();
            string token = TxtApiToken.Password.Trim();
            if (token.Length > 0)
                socket.Options.SetRequestHeader("Authorization", "Bearer " + token);

            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(6));
            await socket.ConnectAsync(wsUri, cts.Token);
            SetStatus($"Connected to {wsUri}", Color.FromRgb(0x3F, 0xB9, 0x50));
        }
        catch (Exception ex)
        {
            SetStatus($"Failed: {ex.Message}", Color.FromRgb(0xF4, 0x43, 0x36));
        }
        finally
        {
            BtnTest.IsEnabled = true;
        }
    }

    private void SetStatus(string text, Color color)
    {
        TxtTestStatus.Text = text;
        TxtTestStatus.Foreground = new SolidColorBrush(color);
    }

    private void BtnReset_Click(object sender, RoutedEventArgs e)
    {
        var defaults = new AppConfig();

        TxtServerUri.Text = defaults.ServerUri;
        TxtApiToken.Password = defaults.ApiToken;
        TxtTopic.Text = defaults.PresentationTopic;

        _pendingAnalyzeModifiers = (uint)defaults.HotKeyModifiers;
        _pendingAnalyzeKey = defaults.HotKeyCode;
        _pendingToggleModifiers = (uint)defaults.ToggleHotKeyModifiers;
        _pendingToggleKey = defaults.ToggleHotKeyCode;
        RefreshHotkeyBoxes();

        SelectAudioDevice(defaults.AudioSource, defaults.AudioDeviceId);
        ChkStream.IsChecked = defaults.StreamContinuously;
        ChkLiveCaptions.IsChecked = defaults.LiveCaptions;
        SliderOpacity.Value = defaults.OpacityLevel;
        SliderBuffer.Value = defaults.AudioBufferSeconds;

        TxtHotkeyStatus.Text = "Defaults restored — press Save to apply.";
    }

    private void BtnSave_Click(object sender, RoutedEventArgs e)
    {
        var uri = TxtServerUri.Text.Trim();
        if (!Uri.TryCreate(uri, UriKind.Absolute, out var parsed) ||
            (parsed.Scheme != "ws" && parsed.Scheme != "wss"))
        {
            System.Windows.MessageBox.Show(
                "Invalid WebSocket URI. Must start with ws:// or wss://",
                "Validation Error",
                MessageBoxButton.OK,
                MessageBoxImage.Warning);
            return;
        }

        _config.ServerUri = uri;
        _config.ApiToken = TxtApiToken.Password.Trim();
        _config.PresentationTopic = TxtTopic.Text.Trim();
        _config.StreamContinuously = ChkStream.IsChecked == true;
        _config.LiveCaptions = ChkLiveCaptions.IsChecked == true;
        _config.OpacityLevel = Math.Round(SliderOpacity.Value, 2);
        _config.AudioBufferSeconds = (int)SliderBuffer.Value;

        if (CmbAudioDevice.SelectedItem is AudioDeviceInfo device)
        {
            _config.AudioSource = device.Kind;
            _config.AudioDeviceId = device.Id;
        }

        _config.HotKeyModifiers = (int)_pendingAnalyzeModifiers;
        _config.HotKeyCode = _pendingAnalyzeKey;
        _config.HotKey = HotkeyService.Describe(_pendingAnalyzeModifiers, (uint)_pendingAnalyzeKey);

        _config.ToggleHotKeyModifiers = (int)_pendingToggleModifiers;
        _config.ToggleHotKeyCode = _pendingToggleKey;
        _config.ToggleHotKey = HotkeyService.Describe(_pendingToggleModifiers, (uint)_pendingToggleKey);

        // Persist next to the executable: that file is the single source of truth
        // and the build never overwrites it once it exists.
        try
        {
            var configPath = System.IO.Path.Combine(AppContext.BaseDirectory, "appsettings.json");
            var json = System.Text.Json.JsonSerializer.Serialize(_config, new System.Text.Json.JsonSerializerOptions { WriteIndented = true });
            System.IO.File.WriteAllText(configPath, json);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[SettingsWindow] Error saving config: {ex.Message}");
            System.Windows.MessageBox.Show(
                $"Could not write settings to:\n{System.IO.Path.Combine(AppContext.BaseDirectory, "appsettings.json")}\n\n{ex.Message}",
                "Could not save settings", MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }

        SettingsSaved?.Invoke(this, _config);
        DialogResult = true;
        Close();
    }

    private void BtnCancel_Click(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }
}
