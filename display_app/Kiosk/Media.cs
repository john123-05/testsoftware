// Medien fuer die App unter https://kiosk-media.liftpictures/ :
//   data.js           vom Agenten (Fotos, Lizenz, Einstellungen)
//   park-logo         Logo des Parks
//   thumb/<datei>     Vorschaubild, 480 px breit   (zwischengespeichert in kiosk-data\cache)
//   photo/<datei>     Ansicht, 2048 px breit        (zwischengespeichert)
// Kamerafotos haben 20+ Megapixel - die App bekommt nie das Original, sonst ruckelt jeder PC.
// Verkleinert wird mit WIC (WPF): JPEG wird direkt verkleinert dekodiert, schnell und sparsam.
// Neue Fotos werden im Hintergrund vorbereitet, damit die Galerie sofort steht.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using WpfImaging = System.Windows.Media.Imaging;

namespace Liftpictures.Display.Kiosk
{
    internal sealed class Media : IDisposable
    {
        public const int ThumbWidth = 480;
        public const int ViewWidth = 2048;
        private readonly Func<HostConfig> _cfg;
        private readonly Worker _imaging = new Worker("imaging", true, ThreadPriority.BelowNormal);
        private readonly Dictionary<string, Task<string>> _inflight = new Dictionary<string, Task<string>>();
        private readonly Timer _prewarm;
        private int _prewarming;
        private DateTime _lastTidy = DateTime.MinValue;

        public Media(Func<HostConfig> cfg)
        {
            _cfg = cfg;
            _prewarm = new Timer(_ => Prewarm(), null, 4000, 5000);
        }

        private string CacheDir(int width)
        {
            return Path.Combine(_cfg().DataDir, "cache", width == ThumbWidth ? "thumb" : "view");
        }

        public static bool SafeName(string file)
        {
            if (string.IsNullOrEmpty(file) || file.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || file.Contains("..")) return false;
            string ext = Path.GetExtension(file).ToLowerInvariant();
            return ext == ".jpg" || ext == ".jpeg";
        }

        /// <summary>Pfad der verkleinerten Fassung (oder null, wenn das Foto nicht existiert).</summary>
        public Task<string> ScaledAsync(string file, int width)
        {
            var c = _cfg();
            string source = Path.Combine(c.PhotoDir, file);
            FileInfo info;
            try { info = new FileInfo(source); if (!info.Exists) return Task.FromResult<string>(null); }
            catch { return Task.FromResult<string>(null); }
            string target = Path.Combine(CacheDir(width),
                Path.GetFileNameWithoutExtension(file) + "_" + info.LastWriteTimeUtc.Ticks.ToString(CultureInfo.InvariantCulture) + "_" + info.Length.ToString(CultureInfo.InvariantCulture) + ".jpg");
            if (File.Exists(target)) return Task.FromResult(target);
            lock (_inflight)
            {
                if (_inflight.TryGetValue(target, out var running)) return running;
                var t = _imaging.Run(() =>
                {
                    try
                    {
                        if (!File.Exists(target))
                        {
                            Directory.CreateDirectory(Path.GetDirectoryName(target));
                            byte[] jpg = Scale(source, width, width == ThumbWidth ? 82 : 88);
                            string tmp = target + ".tmp";
                            File.WriteAllBytes(tmp, jpg);
                            if (File.Exists(target)) File.Delete(tmp); else File.Move(tmp, target);
                        }
                        return target;
                    }
                    catch (Exception ex)
                    {
                        Log.Write("scale " + file + ": " + ex.Message);
                        return null;
                    }
                    finally
                    {
                        lock (_inflight) _inflight.Remove(target);
                    }
                });
                _inflight[target] = t;
                return t;
            }
        }

        /// <summary>JPEG verkleinert dekodieren und neu speichern (auf dem STA-Bildthread).</summary>
        public static byte[] Scale(string source, int width, int quality)
        {
            var bmp = Decode(source, width);
            var enc = new WpfImaging.JpegBitmapEncoder { QualityLevel = quality };
            enc.Frames.Add(WpfImaging.BitmapFrame.Create(bmp));
            using (var ms = new MemoryStream())
            {
                enc.Save(ms);
                return ms.ToArray();
            }
        }

        public static WpfImaging.BitmapSource Decode(string source, int maxWidth)
        {
            var bi = new WpfImaging.BitmapImage();
            using (var fs = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                bi.BeginInit();
                bi.CacheOption = WpfImaging.BitmapCacheOption.OnLoad;
                bi.CreateOptions = WpfImaging.BitmapCreateOptions.IgnoreColorProfile;
                if (maxWidth > 0) bi.DecodePixelWidth = maxWidth;
                bi.StreamSource = fs;
                bi.EndInit();
            }
            bi.Freeze();
            return bi;
        }

        /// <summary>Neue Fotos schon vorbereiten (Vorschaubilder), neueste zuerst. Haelt den Zwischenspeicher klein.</summary>
        private void Prewarm()
        {
            if (Interlocked.Exchange(ref _prewarming, 1) == 1) return;
            try
            {
                var c = _cfg();
                if (!Directory.Exists(c.PhotoDir) || _imaging.Pending > 4) return;
                var since = DateTime.Now.AddHours(-20);
                var files = new DirectoryInfo(c.PhotoDir).EnumerateFiles()
                    .Where(f => SafeName(f.Name) && f.LastWriteTime >= since && f.LastWriteTime <= DateTime.Now.AddSeconds(-2))
                    .OrderByDescending(f => f.LastWriteTimeUtc)
                    .Take(400);
                int queued = 0;
                foreach (var f in files)
                {
                    var t = ScaledAsync(f.Name, ThumbWidth);
                    if (!t.IsCompleted && ++queued >= 10) break;
                }
                if (DateTime.Now - _lastTidy > TimeSpan.FromHours(1)) { _lastTidy = DateTime.Now; Tidy(); }
            }
            catch (Exception ex) { Log.Write("prewarm: " + ex.Message); }
            finally { Interlocked.Exchange(ref _prewarming, 0); }
        }

        private void Tidy()
        {
            foreach (int w in new[] { ThumbWidth, ViewWidth })
            {
                try
                {
                    var dir = new DirectoryInfo(CacheDir(w));
                    if (!dir.Exists) continue;
                    foreach (var f in dir.GetFiles().Where(f => f.LastWriteTime < DateTime.Now.AddDays(-2))) f.Delete();
                }
                catch { }
            }
        }

        public void Dispose()
        {
            _prewarm.Dispose();
            _imaging.Dispose();
        }
    }
}
