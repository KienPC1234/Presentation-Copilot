using PresentationCopilot.Models;
using System.Windows;

namespace PresentationCopilot.Views;

public partial class SettingsWindow : Window
{
    private readonly AppConfig _config;

    /// <summary>Raised when the user confirms changes. Contains the updated config.</summary>
    public event EventHandler<AppConfig>? SettingsSaved;

    public SettingsWindow(AppConfig config)
    {
        InitializeComponent();
        _config = config;
        LoadCurrentValues();
    }

    private void LoadCurrentValues()
    {
        TxtServerUri.Text = _config.ServerUri;
        TxtHotkey.Text = _config.HotKey;

        SliderOpacity.Value = _config.OpacityLevel;
        TxtOpacityValue.Text = $"{_config.OpacityLevel:P0}";

        SliderBuffer.Value = _config.AudioBufferSeconds;
        TxtBufferValue.Text = $"{_config.AudioBufferSeconds}s";
    }

    private void SliderOpacity_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (TxtOpacityValue is not null)
            TxtOpacityValue.Text = $"{e.NewValue:P0}";
    }

    private void SliderBuffer_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (TxtBufferValue is not null)
            TxtBufferValue.Text = $"{(int)e.NewValue}s";
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
        _config.OpacityLevel = Math.Round(SliderOpacity.Value, 2);
        _config.AudioBufferSeconds = (int)SliderBuffer.Value;

        // Persist to appsettings.json
        try
        {
            var configPath = System.IO.Path.Combine(AppContext.BaseDirectory, "appsettings.json");
            var json = System.Text.Json.JsonSerializer.Serialize(_config, new System.Text.Json.JsonSerializerOptions { WriteIndented = true });
            System.IO.File.WriteAllText(configPath, json);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[SettingsWindow] Error saving config: {ex.Message}");
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

