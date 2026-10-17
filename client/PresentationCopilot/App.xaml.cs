using System.Windows;
using System.Windows.Threading;

namespace PresentationCopilot;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        DispatcherUnhandledException += OnDispatcherUnhandledException;
        AppDomain.CurrentDomain.UnhandledException += OnDomainUnhandledException;
        TaskScheduler.UnobservedTaskException += OnUnobservedTaskException;
    }

    private void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        ShowFatalError(e.Exception);
        e.Handled = true;
        Shutdown(1);
    }

    private void OnDomainUnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
        // Raised on the faulting (possibly non-UI) thread; showing a MessageBox here
        // can deadlock. Log it and let the process terminate.
        System.Diagnostics.Debug.WriteLine($"[App] Unhandled domain exception: {e.ExceptionObject}");
    }

    private void OnUnobservedTaskException(object? sender, UnobservedTaskExceptionEventArgs e)
    {
        // Faulted tasks that nobody awaited (common in networking libraries) must not
        // pop a blocking fatal-error dialog. Observe and log instead.
        e.SetObserved();
        System.Diagnostics.Debug.WriteLine($"[App] Unobserved task exception: {e.Exception}");
    }

    private static void ShowFatalError(Exception ex)
    {
        System.Windows.MessageBox.Show(
            $"An unexpected error occurred:\n\n{ex.Message}\n\n{ex.StackTrace}",
            "Presentation Copilot — Fatal Error",
            MessageBoxButton.OK,
            MessageBoxImage.Error);
    }
}

