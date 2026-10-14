using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;

namespace PresentationCopilot.Converters;

/// <summary>
/// Converts a <see cref="bool"/> to a <see cref="Brush"/>.
/// True  → green (#4CAF50)
/// False → red   (#F44336)
/// </summary>
[ValueConversion(typeof(bool), typeof(Brush))]
public sealed class BoolToColorConverter : IValueConverter
{
    private static readonly SolidColorBrush GreenBrush =
        new(System.Windows.Media.Color.FromRgb(0x4C, 0xAF, 0x50));

    private static readonly SolidColorBrush RedBrush =
        new(System.Windows.Media.Color.FromRgb(0xF4, 0x43, 0x36));

    static BoolToColorConverter()
    {
        GreenBrush.Freeze();
        RedBrush.Freeze();
    }

    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => value is bool b && b ? GreenBrush : (object)RedBrush;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>
/// Converts a <see cref="bool"/> to <see cref="Visibility"/>.
/// True  → Visible
/// False → Collapsed
/// </summary>
[ValueConversion(typeof(bool), typeof(Visibility))]
public sealed class BoolToVisibilityConverter : IValueConverter
{
    public static readonly BoolToVisibilityConverter Instance = new();

    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => value is bool b && b ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

