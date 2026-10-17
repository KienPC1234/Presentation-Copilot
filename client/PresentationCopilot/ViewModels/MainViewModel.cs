using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace PresentationCopilot.ViewModels;

/// <summary>Wraps a framework step string with a 1-based display index.</summary>
public sealed record NumberedStep(string Index, string Text);

public sealed class MainViewModel : INotifyPropertyChanged
{
    // ── Observable Properties ─────────────────────────────────────────────

    private string _questionText = string.Empty;
    public string QuestionText
    {
        get => _questionText;
        set => SetField(ref _questionText, value);
    }

    private string _keyPoint = "Ready. Press your hotkey when asked a question.";
    public string KeyPoint
    {
        get => _keyPoint;
        set => SetField(ref _keyPoint, value);
    }

    /// <summary>Human-readable hotkey shown in the HUD footer (e.g. "Ctrl+Shift+Space").</summary>
    private string _hotkeyHint = "Ctrl+Shift+Space";
    public string HotkeyHint
    {
        get => _hotkeyHint;
        set => SetField(ref _hotkeyHint, value);
    }

    /// <summary>Human-readable show/hide hotkey shown in the HUD footer.</summary>
    private string _toggleHotkeyHint = "Ctrl+Alt+H";
    public string ToggleHotkeyHint
    {
        get => _toggleHotkeyHint;
        set => SetField(ref _toggleHotkeyHint, value);
    }

    private string _retrievedSources = string.Empty;
    public string RetrievedSources
    {
        get => _retrievedSources;
        set
        {
            if (SetField(ref _retrievedSources, value))
                OnPropertyChanged(nameof(HasSources));
        }
    }

    /// <summary>True when at least one related source was returned.</summary>
    public bool HasSources => !string.IsNullOrWhiteSpace(_retrievedSources);

    private bool _isConnected;
    public bool IsConnected
    {
        get => _isConnected;
        set => SetField(ref _isConnected, value);
    }

    private bool _isRecording;
    public bool IsRecording
    {
        get => _isRecording;
        set
        {
            if (SetField(ref _isRecording, value))
                OnPropertyChanged(nameof(RecordingStateText));
        }
    }

    /// <summary>Short "REC" / "PAUSED" badge shown next to the VU meter.</summary>
    public string RecordingStateText => _isRecording ? "REC" : "PAUSED";

    /// <summary>Input level, 0..1, for the HUD's VU meter.</summary>
    private double _audioLevel;
    public double AudioLevel
    {
        get => _audioLevel;
        set => SetField(ref _audioLevel, value);
    }

    private bool _isBusy;
    public bool IsBusy
    {
        get => _isBusy;
        set => SetField(ref _isBusy, value);
    }

    private bool _isAntiCaptureActive = true;
    public bool IsAntiCaptureActive
    {
        get => _isAntiCaptureActive;
        set
        {
            if (SetField(ref _isAntiCaptureActive, value))
                OnPropertyChanged(nameof(AntiCaptureText));
        }
    }

    /// <summary>Badge label reflecting whether the HUD is really hidden from screen capture.</summary>
    public string AntiCaptureText => _isAntiCaptureActive ? "ANTI-CAPTURE" : "CAPTURE VISIBLE";

    private bool _isClickThrough;
    public bool IsClickThrough
    {
        get => _isClickThrough;
        set => SetField(ref _isClickThrough, value);
    }

    private string _statusMessage = "Ready";
    public string StatusMessage
    {
        get => _statusMessage;
        set => SetField(ref _statusMessage, value);
    }

    /// <summary>Opacity value forwarded to the HUD window animation target.</summary>
    private double _opacityTarget = 0.90;
    public double OpacityTarget
    {
        get => _opacityTarget;
        set => SetField(ref _opacityTarget, value);
    }

    /// <summary>Split keyword list for chip-style rendering in the HUD.</summary>
    private ObservableCollection<string> _keywordsCollection = [];
    public ObservableCollection<string> KeywordsCollection
    {
        get => _keywordsCollection;
        set => SetField(ref _keywordsCollection, value);
    }

    /// <summary>Numbered step wrappers for ordered list rendering in the HUD.</summary>
    private ObservableCollection<NumberedStep> _numberedSteps = [];
    public ObservableCollection<NumberedStep> NumberedSteps
    {
        get => _numberedSteps;
        set => SetField(ref _numberedSteps, value);
    }

    public bool HasSteps => _numberedSteps.Count > 0;
    public bool HasQuestion => !string.IsNullOrWhiteSpace(_questionText);

    // ── Mutations (UI thread only) ────────────────────────────────────────

    /// <summary>
    /// Applies a parsed suggestion payload to the view model properties.
    /// Must be called on the UI thread.
    /// </summary>
    public void ApplySuggestion(string keyPoint, IEnumerable<string> keywords, IEnumerable<string> steps, string question = "")
    {
        QuestionText = question;
        KeyPoint = string.IsNullOrWhiteSpace(keyPoint) ? "No concise answer generated." : keyPoint;

        KeywordsCollection.Clear();
        foreach (var kw in keywords)
            KeywordsCollection.Add(kw);

        NumberedSteps.Clear();
        int i = 1;
        foreach (var step in steps)
        {
            NumberedSteps.Add(new NumberedStep(i.ToString(), step));
            i++;
        }

        OnPropertyChanged(nameof(HasSteps));
        OnPropertyChanged(nameof(HasQuestion));
    }

    /// <summary>
    /// Sets the question text from a live caption and makes sure the HUD shows the
    /// question panel. Must be called on the UI thread.
    /// </summary>
    public void SetLiveCaption(string text)
    {
        QuestionText = text;
        OnPropertyChanged(nameof(HasQuestion));
    }

    // ── INotifyPropertyChanged ────────────────────────────────────────────

    public event PropertyChangedEventHandler? PropertyChanged;

    private void OnPropertyChanged([CallerMemberName] string? name = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(name);
        return true;
    }
}
