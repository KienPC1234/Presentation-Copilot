using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows.Input;

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

    private string _suggestionText = string.Empty;
    public string SuggestionText
    {
        get => _suggestionText;
        set => SetField(ref _suggestionText, value);
    }

    private string _keyPoint = "Ready. Press hotkey (Ctrl+Shift+Space) when asked a question.";
    public string KeyPoint
    {
        get => _keyPoint;
        set => SetField(ref _keyPoint, value);
    }

    private string _keywords = string.Empty;
    public string Keywords
    {
        get => _keywords;
        set => SetField(ref _keywords, value);
    }

    private string _retrievedSources = string.Empty;
    public string RetrievedSources
    {
        get => _retrievedSources;
        set => SetField(ref _retrievedSources, value);
    }

    private ObservableCollection<string> _frameworkSteps = [];
    public ObservableCollection<string> FrameworkSteps
    {
        get => _frameworkSteps;
        set => SetField(ref _frameworkSteps, value);
    }

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
        set => SetField(ref _isRecording, value);
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
        set => SetField(ref _isAntiCaptureActive, value);
    }

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

    // ── Commands ──────────────────────────────────────────────────────────

    public ICommand ToggleRecordingCommand { get; }
    public ICommand TriggerAnalysisCommand { get; }

    private readonly Action _toggleRecording;
    private readonly Action _triggerAnalysis;

    public MainViewModel(Action toggleRecording, Action triggerAnalysis)
    {
        _toggleRecording = toggleRecording;
        _triggerAnalysis = triggerAnalysis;

        ToggleRecordingCommand = new RelayCommand(
            execute: _ => _toggleRecording(),
            canExecute: _ => IsConnected);

        TriggerAnalysisCommand = new RelayCommand(
            execute: _ => _triggerAnalysis(),
            canExecute: _ => IsConnected && IsRecording && !IsBusy);
    }

    /// <summary>
    /// Applies a parsed suggestion payload to the view model properties.
    /// Must be called on the UI thread.
    /// </summary>
    public void ApplySuggestion(string keyPoint, IEnumerable<string> keywords, IEnumerable<string> steps, string rawJson, string question = "")
    {
        QuestionText = question;
        KeyPoint = string.IsNullOrWhiteSpace(keyPoint) ? "No concise answer generated." : keyPoint;

        var kwList = keywords.ToList();
        Keywords = string.Join("  ·  ", kwList);

        KeywordsCollection.Clear();
        foreach (var kw in kwList)
            KeywordsCollection.Add(kw);

        SuggestionText = rawJson;

        FrameworkSteps.Clear();
        NumberedSteps.Clear();
        int i = 1;
        foreach (var step in steps)
        {
            FrameworkSteps.Add(step);
            NumberedSteps.Add(new NumberedStep(i.ToString(), step));
            i++;
        }

        OnPropertyChanged(nameof(HasSteps));
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

// ── Minimal RelayCommand ──────────────────────────────────────────────────

public sealed class RelayCommand : ICommand
{
    private readonly Action<object?> _execute;
    private readonly Predicate<object?>? _canExecute;

    public RelayCommand(Action<object?> execute, Predicate<object?>? canExecute = null)
    {
        _execute = execute;
        _canExecute = canExecute;
    }

    public event EventHandler? CanExecuteChanged
    {
        add => CommandManager.RequerySuggested += value;
        remove => CommandManager.RequerySuggested -= value;
    }

    public bool CanExecute(object? parameter) => _canExecute?.Invoke(parameter) ?? true;
    public void Execute(object? parameter) => _execute(parameter);
}
