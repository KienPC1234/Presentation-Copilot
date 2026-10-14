using NAudio.Wave;
using System.IO;

namespace PresentationCopilot.Services;

/// <summary>
/// Captures system audio via WASAPI loopback and resamples to 16kHz mono 16-bit PCM.
/// Employs a low-latency ring buffer of the last N seconds of audio.
/// Optimized with a zero-allocation fast-path converter for standard IEEE Float stereo formats.
/// </summary>
public sealed class AudioCaptureService : IDisposable
{
    private WasapiLoopbackCapture? _capture;
    private readonly object _bufferLock = new();

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

    /// <summary>Raised each time a chunk of 16kHz mono PCM data is ready.</summary>
    public event EventHandler<byte[]>? DataAvailable;

    public void Initialize(int bufferSeconds)
    {
        BufferSeconds = bufferSeconds;
        int bufferSize = _targetFormat.AverageBytesPerSecond * bufferSeconds;
        _ringBuffer = new byte[bufferSize];
        _writePos = 0;
        _bytesWritten = 0;
    }

    public void Start()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        _capture = new WasapiLoopbackCapture();
        var srcFormat = _capture.WaveFormat;

        // If not matching fast-path format, initialize persistent resampler once
        if (!IsFastPathSupported(srcFormat))
        {
            _fallbackWaveProvider = new BufferedWaveProvider(srcFormat)
            {
                DiscardOnBufferOverflow = true,
                BufferLength = srcFormat.AverageBytesPerSecond * 2
            };
            _fallbackResampler = new MediaFoundationResampler(_fallbackWaveProvider, _targetFormat)
            {
                ResamplerQuality = 60
            };
        }

        _capture.DataAvailable += OnRawDataAvailable;
        _capture.RecordingStopped += OnRecordingStopped;
        _capture.StartRecording();
    }

    public void Stop()
    {
        _capture?.StopRecording();
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

        byte[] pcm = ConvertTo16kMonoPcm(e.Buffer, e.BytesRecorded, _capture.WaveFormat);
        if (pcm.Length == 0) return;

        lock (_bufferLock)
        {
            WriteToRingBuffer(pcm);
        }

        DataAvailable?.Invoke(this, pcm);
    }

    private static bool IsFastPathSupported(WaveFormat fmt)
    {
        // Windows WASAPI Loopback default is 32-bit IEEE float, 2 channels, 48000Hz or 44100Hz
        return fmt.Encoding == WaveFormatEncoding.IeeeFloat &&
               fmt.BitsPerSample == 32 &&
               (fmt.Channels == 2 || fmt.Channels == 1) &&
               (fmt.SampleRate == 48000 || fmt.SampleRate == 16000);
    }

    /// <summary>
    /// Converts input audio buffer to 16kHz 16-bit mono PCM.
    /// Fast path handles 48kHz / 16kHz float with high speed and zero COM allocations.
    /// </summary>
    private byte[] ConvertTo16kMonoPcm(byte[] raw, int length, WaveFormat sourceFormat)
    {
        // Fast-path: 48kHz Stereo Float -> 16kHz Mono 16-bit PCM (Step 3:1)
        if (sourceFormat.Encoding == WaveFormatEncoding.IeeeFloat &&
            sourceFormat.BitsPerSample == 32 &&
            sourceFormat.SampleRate == 48000 &&
            sourceFormat.Channels == 2)
        {
            int totalInputFrames = length / 8; // 4 bytes per float * 2 channels = 8 bytes/frame
            int outputSampleCount = totalInputFrames / 3;
            byte[] output = new byte[outputSampleCount * 2]; // 16-bit = 2 bytes/sample

            unsafe
            {
                fixed (byte* pRaw = raw)
                fixed (byte* pOut = output)
                {
                    float* inSamples = (float*)pRaw;
                    short* outSamples = (short*)pOut;

                    for (int i = 0; i < outputSampleCount; i++)
                    {
                        int srcIdx = (i * 3) * 2; // Step 3 frames, stereo has 2 floats
                        float left = inSamples[srcIdx];
                        float right = inSamples[srcIdx + 1];
                        float mono = (left + right) * 0.5f;

                        // Clamp and convert to short (16-bit PCM)
                        if (mono > 1.0f) mono = 1.0f;
                        else if (mono < -1.0f) mono = -1.0f;

                        outSamples[i] = (short)(mono * 32767.0f);
                    }
                }
            }
            return output;
        }

        // Fast-path: 16kHz Stereo Float -> 16kHz Mono 16-bit PCM
        if (sourceFormat.Encoding == WaveFormatEncoding.IeeeFloat &&
            sourceFormat.BitsPerSample == 32 &&
            sourceFormat.SampleRate == 16000 &&
            sourceFormat.Channels == 2)
        {
            int outputSampleCount = length / 8;
            byte[] output = new byte[outputSampleCount * 2];

            unsafe
            {
                fixed (byte* pRaw = raw)
                fixed (byte* pOut = output)
                {
                    float* inSamples = (float*)pRaw;
                    short* outSamples = (short*)pOut;

                    for (int i = 0; i < outputSampleCount; i++)
                    {
                        float mono = (inSamples[i * 2] + inSamples[i * 2 + 1]) * 0.5f;
                        if (mono > 1.0f) mono = 1.0f;
                        else if (mono < -1.0f) mono = -1.0f;
                        outSamples[i] = (short)(mono * 32767.0f);
                    }
                }
            }
            return output;
        }

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
    }
}
