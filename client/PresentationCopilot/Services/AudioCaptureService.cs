using NAudio.CoreAudioApi;
using NAudio.Wave;
using PresentationCopilot.Models;
using System.IO;

namespace PresentationCopilot.Services;

/// <summary>
/// Captures audio either from the system output (WASAPI loopback: speakers / headphones)
/// or from a microphone, optionally from a specific device, and resamples to
/// 16kHz mono 16-bit PCM. Employs a low-latency ring buffer of the last N seconds
/// of audio and uses the Windows Media Foundation resampler with anti-alias filtering.
/// </summary>
public sealed class AudioCaptureService : IDisposable
{
    private IWaveIn? _capture;
    private MMDevice? _captureDevice;          // kept alive while capture runs
    private readonly object _bufferLock = new();
    private readonly object _converterLock = new();

    // Circular ring buffer
    private byte[] _ringBuffer = [];
    private int _writePos;
    private int _bytesWritten;

    private readonly WaveFormat _targetFormat = new WaveFormat(16000, 16, 1);
    private bool _disposed;

    // Persistent fallback resampler for non-standard formats
    private BufferedWaveProvider? _fallbackWaveProvider;
    private MediaFoundationResampler? _fallbackResampler;

    public int BufferSeconds { get; private set; }

    /// <summary>Loopback (speakers) or Microphone.</summary>
    public AudioSourceKind Source { get; private set; } = AudioSourceKind.Loopback;

    /// <summary>Selected endpoint id; empty means the system default for <see cref="Source"/>.</summary>
    public string? DeviceId { get; private set; }

    /// <summary>Raised each time a chunk of 16kHz mono PCM data is ready.</summary>
    public event EventHandler<byte[]>? DataAvailable;

    public void Initialize(int bufferSeconds)
    {
        lock (_bufferLock)
        {
            BufferSeconds = Math.Clamp(bufferSeconds, 5, 90);
            int bufferSize = _targetFormat.AverageBytesPerSecond * BufferSeconds;
            _ringBuffer = new byte[bufferSize];
            _writePos = 0;
            _bytesWritten = 0;
        }
    }

    /// <summary>
    /// Selects the capture device. Restarts capture if it is already running so the
    /// change takes effect immediately.
    /// </summary>
    public void ChangeSource(AudioSourceKind source, string? deviceId)
    {
        bool same = Source == source &&
                    string.Equals(DeviceId, deviceId, StringComparison.OrdinalIgnoreCase);
        if (same && _capture is not null) return;

        bool wasRunning = _capture is not null;
        if (wasRunning) Stop();
        Source = source;
        DeviceId = string.IsNullOrWhiteSpace(deviceId) ? null : deviceId;
        if (wasRunning) Start();
    }

    public void Start()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        lock (_converterLock)
        {
            if (_capture is not null) return;

            MMDevice? device = ResolveDevice(DeviceId);
            _captureDevice = device;

            IWaveIn capture;
            if (Source == AudioSourceKind.Microphone)
                capture = device is not null ? new WasapiCapture(device) : new WasapiCapture();
            else
                capture = device is not null ? new WasapiLoopbackCapture(device) : new WasapiLoopbackCapture();

            _capture = capture;
            var srcFormat = capture.WaveFormat;

            if (!IsTargetPcm(srcFormat))
            {
                _fallbackWaveProvider = new BufferedWaveProvider(srcFormat)
                {
                    ReadFully = false,
                    DiscardOnBufferOverflow = true,
                    BufferLength = srcFormat.AverageBytesPerSecond * 2
                };
                _fallbackResampler = new MediaFoundationResampler(_fallbackWaveProvider, _targetFormat)
                {
                    ResamplerQuality = 60
                };
            }

            capture.DataAvailable += OnRawDataAvailable;
            capture.RecordingStopped += OnRecordingStopped;
            capture.StartRecording();
        }
    }

    public void Stop()
    {
        lock (_converterLock)
        {
            if (_capture is not null)
            {
                _capture.DataAvailable -= OnRawDataAvailable;
                _capture.RecordingStopped -= OnRecordingStopped;
                try { _capture.StopRecording(); } catch { }
                _capture.Dispose();
                _capture = null;
            }
            _fallbackResampler?.Dispose();
            _fallbackResampler = null;
            _fallbackWaveProvider = null;

            _captureDevice?.Dispose();
            _captureDevice = null;
        }
    }

    /// <summary>
    /// Lists the selectable inputs: the two system defaults first, then every active
    /// playback device (loopback) and every active recording device (microphone).
    /// </summary>
    public static IReadOnlyList<AudioDeviceInfo> EnumerateDevices()
    {
        var list = new List<AudioDeviceInfo>
        {
            new("System audio — default speakers / headphones (loopback)", "", AudioSourceKind.Loopback),
            new("Microphone — default recording device", "", AudioSourceKind.Microphone)
        };

        try
        {
            using var enumerator = new MMDeviceEnumerator();
            foreach (var device in enumerator.EnumerateAudioEndPoints(DataFlow.Render, DeviceState.Active))
                list.Add(new AudioDeviceInfo($"System audio — {device.FriendlyName}", device.ID, AudioSourceKind.Loopback));
            foreach (var device in enumerator.EnumerateAudioEndPoints(DataFlow.Capture, DeviceState.Active))
                list.Add(new AudioDeviceInfo($"Microphone — {device.FriendlyName}", device.ID, AudioSourceKind.Microphone));
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[AudioCapture] Device enumeration failed: {ex.Message}");
        }

        return list;
    }

    private static MMDevice? ResolveDevice(string? id)
    {
        if (string.IsNullOrWhiteSpace(id)) return null;

        try
        {
            using var enumerator = new MMDeviceEnumerator();
            foreach (var flow in new[] { DataFlow.Render, DataFlow.Capture })
            {
                foreach (var device in enumerator.EnumerateAudioEndPoints(flow, DeviceState.Active))
                {
                    if (string.Equals(device.ID, id, StringComparison.OrdinalIgnoreCase))
                        return device;
                }
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[AudioCapture] Resolve device failed: {ex.Message}");
        }
        return null;
    }

    /// <summary>
    /// Returns a contiguous copy of the last <paramref name="seconds"/> of buffered audio.
    /// </summary>
    public byte[] GetLastSeconds(int seconds)
    {
        lock (_bufferLock)
        {
            int bytesNeeded = _targetFormat.AverageBytesPerSecond * seconds;
            int available = Math.Min(_bytesWritten, _ringBuffer.Length);
            int take = Math.Min(bytesNeeded, available);

            byte[] result = new byte[take];
            int readStart = (_writePos - take + _ringBuffer.Length) % _ringBuffer.Length;

            int firstChunk = Math.Min(take, _ringBuffer.Length - readStart);
            Buffer.BlockCopy(_ringBuffer, readStart, result, 0, firstChunk);
            if (firstChunk < take)
                Buffer.BlockCopy(_ringBuffer, 0, result, firstChunk, take - firstChunk);

            return result;
        }
    }

    private void OnRawDataAvailable(object? sender, WaveInEventArgs e)
    {
        if (e.BytesRecorded == 0 || _capture == null) return;

        byte[] pcm;
        lock (_converterLock)
        {
            if (_capture is null) return;
            pcm = ConvertTo16kMonoPcm(e.Buffer, e.BytesRecorded, _capture.WaveFormat);
        }
        if (pcm.Length == 0) return;

        lock (_bufferLock)
        {
            WriteToRingBuffer(pcm);
        }

        DataAvailable?.Invoke(this, pcm);
    }

    private static bool IsTargetPcm(WaveFormat fmt)
    {
        return fmt.Encoding == WaveFormatEncoding.Pcm && fmt.BitsPerSample == 16 &&
               fmt.Channels == 1 && fmt.SampleRate == 16000;
    }

    /// <summary>
    /// Converts input audio buffer to 16kHz 16-bit mono PCM.
    /// Media Foundation handles band-limited conversion for WASAPI float and PCM formats.
    /// </summary>
    private byte[] ConvertTo16kMonoPcm(byte[] raw, int length, WaveFormat sourceFormat)
    {
        if (IsTargetPcm(sourceFormat)) return raw.AsSpan(0, length).ToArray();

        // Persistent fallback resampler
        if (_fallbackWaveProvider != null && _fallbackResampler != null)
        {
            _fallbackWaveProvider.AddSamples(raw, 0, length);
            using var memStream = new MemoryStream();
            byte[] readBuf = new byte[4096];
            int read;
            while ((read = _fallbackResampler.Read(readBuf, 0, readBuf.Length)) > 0)
            {
                memStream.Write(readBuf, 0, read);
            }
            return memStream.ToArray();
        }

        return Array.Empty<byte>();
    }

    private void WriteToRingBuffer(byte[] data)
    {
        int len = data.Length;
        int bufLen = _ringBuffer.Length;

        if (len >= bufLen)
        {
            Buffer.BlockCopy(data, len - bufLen, _ringBuffer, 0, bufLen);
            _writePos = 0;
            _bytesWritten = bufLen;
            return;
        }

        int firstChunk = Math.Min(len, bufLen - _writePos);
        Buffer.BlockCopy(data, 0, _ringBuffer, _writePos, firstChunk);
        if (firstChunk < len)
            Buffer.BlockCopy(data, firstChunk, _ringBuffer, 0, len - firstChunk);

        _writePos = (_writePos + len) % bufLen;
        _bytesWritten = Math.Min(_bytesWritten + len, bufLen);
    }

    private void OnRecordingStopped(object? sender, StoppedEventArgs e)
    {
        if (e.Exception is not null)
            System.Diagnostics.Debug.WriteLine($"[AudioCapture] Recording stopped with error: {e.Exception.Message}");
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        Stop();
    }
}
