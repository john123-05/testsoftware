// Fotodrucker (z. B. DNP DS-RX1) ueber den Windows-Treiber.
// Aufbau wie im alten Verkaufsprogramm, Masse in Millimetern aus dessen Settings.xml (host.json):
//   Foto an LeftMarginPhoto/TopMarginPhoto in PhotoWidth x PhotoHeight (randlos zugeschnitten),
//   QR-Code (Kauf-Link, zeichnet die App) an QrCodePositionX/Y in QrCodeSize,
//   Logo an SinglePhotoLogoX/Y in SinglePhotoLogoWidth, Datum (und Uhrzeit) unten links.
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Printing;
using System.IO;
using System.Linq;
using System.Management;

namespace Liftpictures.Display.Kiosk
{
    internal sealed class PhotoPrinter : IDisposable
    {
        private readonly Func<HostConfig> _cfg;
        private readonly Worker _worker = new Worker("print", true);
        public volatile bool Printing;

        public PhotoPrinter(Func<HostConfig> cfg)
        {
            _cfg = cfg;
        }

        private string PrinterName()
        {
            string name = _cfg().Print.Name;
            if (!string.IsNullOrWhiteSpace(name)) return name;
            try { return new PrinterSettings().PrinterName; } catch { return ""; }
        }

        /// <summary>ready | printing | paper_out | offline</summary>
        public string State()
        {
            if (Printing) return "printing";
            string name = PrinterName();
            if (string.IsNullOrEmpty(name) || !PrinterSettings.InstalledPrinters.Cast<string>().Any(p => string.Equals(p, name, StringComparison.OrdinalIgnoreCase)))
                return "offline";
            try
            {
                using (var q = new ManagementObjectSearcher("SELECT WorkOffline, PrinterStatus, DetectedErrorState FROM Win32_Printer WHERE Name = '" + name.Replace("\\", "\\\\").Replace("'", "\\'") + "'"))
                {
                    foreach (ManagementObject p in q.Get())
                    {
                        if (p["WorkOffline"] is bool off && off) return "offline";
                        int err = Convert.ToInt32(p["DetectedErrorState"] ?? 0);
                        if (err == 4) return "paper_out";            // No Paper
                        if (err == 9) return "offline";              // Offline
                        int st = Convert.ToInt32(p["PrinterStatus"] ?? 3);
                        if (st == 7) return "offline";
                    }
                }
            }
            catch { /* WMI nicht verfuegbar: Treiber ist da, also bereit */ }
            return "ready";
        }

        /// <summary>Druckt nacheinander; meldet den Fortschritt. Gibt zurueck, ob alles gedruckt wurde.</summary>
        public System.Threading.Tasks.Task<bool> PrintAsync(object[] jobs, object opts, Action<int, int> progress, Action counted)
        {
            return _worker.Run(() =>
            {
                Printing = true;
                try
                {
                    string state = State();
                    if (state == "offline" || state == "paper_out") { Log.Write("print: printer " + state); return false; }
                    for (int i = 0; i < jobs.Length; i++)
                    {
                        progress(i, jobs.Length);
                        if (!PrintOne(jobs[i], opts)) return false;
                        counted();
                    }
                    progress(jobs.Length, jobs.Length);
                    return true;
                }
                finally { Printing = false; }
            });
        }

        private static Bitmap FromDataUrl(string dataUrl)
        {
            if (string.IsNullOrEmpty(dataUrl)) return null;
            int comma = dataUrl.IndexOf(',');
            if (comma < 0) return null;
            var bytes = Convert.FromBase64String(dataUrl.Substring(comma + 1));
            using (var ms = new MemoryStream(bytes))
            using (var img = Image.FromStream(ms))
                return new Bitmap(img);
        }

        /// <summary>Foto fuer den Druck laden: hoechstens 2400 px breit (reicht fuer 300 dpi auf 20 cm).</summary>
        private static Bitmap LoadPhoto(string path)
        {
            var src = Media.Decode(path, 2400);
            var enc = new System.Windows.Media.Imaging.BmpBitmapEncoder();
            enc.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(src));
            using (var ms = new MemoryStream())
            {
                enc.Save(ms);
                ms.Position = 0;
                using (var img = Image.FromStream(ms))
                    return new Bitmap(img);
            }
        }

        private bool PrintOne(object job, object opts)
        {
            var c = _cfg();
            var l = c.Print;
            string file = Json.Str(job, "file");
            if (!Media.SafeName(file)) { Log.Write("print: bad file " + file); return false; }
            string path = Path.Combine(c.PhotoDir, file);
            if (!File.Exists(path)) { Log.Write("print: missing " + path); return false; }

            Bitmap photo = null, qr = null, logo = null;
            try
            {
                photo = LoadPhoto(path);
                if (Json.Bool(opts, "qr", true) && l.Qr) qr = FromDataUrl(Json.Str(job, "qr"));
                if (Json.Bool(opts, "logo", true) && !string.IsNullOrEmpty(l.Logo) && File.Exists(l.Logo))
                {
                    using (var img = Image.FromFile(l.Logo)) logo = new Bitmap(img);
                }
                long ts = (long)Json.Num(job, "ts");
                DateTime when = ts > 0 ? DateTimeOffset.FromUnixTimeSeconds(ts).LocalDateTime : DateTime.Now;
                string date = Json.Bool(opts, "date", true) && l.Date
                    ? when.ToString("dd.MM.yyyy") + (l.Time ? " " + when.ToString("HH:mm") : "")
                    : null;

                bool ok = true;
                using (var doc = new PrintDocument())
                {
                    string name = PrinterName();
                    if (!string.IsNullOrEmpty(name)) doc.PrinterSettings.PrinterName = name;
                    if (!doc.PrinterSettings.IsValid) { Log.Write("print: printer not valid " + name); return false; }
                    doc.PrintController = new StandardPrintController();
                    doc.DocumentName = "Liftpictures " + Json.Str(job, "number", file);
                    doc.DefaultPageSettings.Margins = new Margins(0, 0, 0, 0);
                    doc.DefaultPageSettings.Landscape = photo.Width >= photo.Height;
                    doc.PrintPage += (s, e) =>
                    {
                        try { Draw(e.Graphics, e.PageBounds, l, photo, qr, logo, date); }
                        catch (Exception ex) { ok = false; Log.Write("print page: " + ex.Message); }
                        e.HasMorePages = false;
                    };
                    doc.Print();
                }
                Log.Write("print: " + file + (ok ? " ok" : " failed"));
                return ok;
            }
            catch (Exception ex)
            {
                Log.Write("print " + file + ": " + ex.Message);
                return false;
            }
            finally
            {
                photo?.Dispose();
                qr?.Dispose();
                logo?.Dispose();
            }
        }

        private static void Draw(Graphics g, Rectangle page, PrintLayout l, Bitmap photo, Bitmap qr, Bitmap logo, string date)
        {
            g.PageUnit = GraphicsUnit.Millimeter;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.SmoothingMode = SmoothingMode.HighQuality;
            // PageBounds in 1/100 Zoll -> Millimeter
            float pw = page.Width * 0.254f, ph = page.Height * 0.254f;

            var area = new RectangleF((float)l.LeftMm, (float)l.TopMm, (float)l.PhotoWidthMm, (float)l.PhotoHeightMm);
            if (area.Width <= 1 || area.Height <= 1) area = new RectangleF(0, 0, pw, ph);
            if (area.Width > ph * 4 || area.Height > pw * 4) area = new RectangleF(0, 0, pw, ph);
            // Hochkant-Seite, querliegende Masse: drehen statt quetschen.
            if ((pw < ph) != (area.Width < area.Height)) area = new RectangleF(area.Y, area.X, area.Height, area.Width);

            // Randlos: Foto auf die Flaeche zuschneiden (Seitenverhaeltnis bleibt).
            float sx = photo.Width / area.Width, sy = photo.Height / area.Height, s = Math.Min(sx, sy);
            float cw = area.Width * s, ch = area.Height * s;
            var src = new RectangleF((photo.Width - cw) / 2, (photo.Height - ch) / 2, cw, ch);
            g.DrawImage(photo, area, src, GraphicsUnit.Pixel);

            if (logo != null && l.LogoWMm > 1)
            {
                float w = (float)l.LogoWMm, h = w * logo.Height / Math.Max(1, logo.Width);
                g.DrawImage(logo, new RectangleF(area.X + (float)l.LogoXMm, area.Y + (float)l.LogoYMm, w, h));
            }

            if (qr != null && l.QrMm > 4)
            {
                float size = (float)l.QrMm;
                float x = area.X + (float)l.QrXMm, y = area.Y + (float)l.QrYMm;
                if (x + size > area.Right - 1) x = area.Right - size - 2;
                if (y + size > area.Bottom - 1) y = area.Bottom - size - 2;
                using (var white = new SolidBrush(Color.White)) g.FillRectangle(white, x - 1, y - 1, size + 2, size + 2);
                var mode = g.InterpolationMode;
                g.InterpolationMode = InterpolationMode.NearestNeighbor;
                g.PixelOffsetMode = PixelOffsetMode.Half;
                g.DrawImage(qr, new RectangleF(x, y, size, size));
                g.InterpolationMode = mode;
                g.PixelOffsetMode = PixelOffsetMode.Default;
            }

            if (!string.IsNullOrEmpty(date))
            {
                using (var font = new Font("Segoe UI", 3.4f, FontStyle.Bold, GraphicsUnit.Millimeter))
                using (var shadow = new SolidBrush(Color.FromArgb(160, 0, 0, 0)))
                using (var ink = new SolidBrush(Color.White))
                {
                    var size = g.MeasureString(date, font);
                    float x = area.X + 4, y = area.Bottom - size.Height - 3;
                    g.DrawString(date, font, shadow, x + 0.35f, y + 0.35f);
                    g.DrawString(date, font, ink, x, y);
                }
            }
        }

        public void Dispose()
        {
            _worker.Dispose();
        }
    }
}
