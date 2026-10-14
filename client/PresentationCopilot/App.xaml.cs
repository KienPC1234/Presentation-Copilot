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
        if (e.ExceptionObject is Exception ex)
            ShowFatalError(ex);
    }

    private void OnUnobservedTaskException(object? sender, UnobservedTaskExceptionEventArgs e)
    {
        e.SetObserved();
        Dispatcher.Invoke(() => ShowFatalError(e.Exception.InnerException ?? e.Exception));
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

