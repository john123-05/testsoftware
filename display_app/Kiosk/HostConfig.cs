// host.json: was der Agent (kiosk.py) fuer dieses Programm hinterlegt - Pfade und Geraete,
// gelesen aus der Settings.xml des alten Verkaufsprogramms. Fehlt die Datei, gelten die Vorgaben
// des alten Programms.
using System;
using System.IO;

namespace Liftpictures.Display.Kiosk
{
    internal sealed class PrintLayout
    {
        public string Name = "";
        public double PhotoWidthMm = 152, PhotoHeightMm = 102, LeftMm, TopMm;
        public bool Date = true, Time;
        public bool Qr = true;
        public double QrMm = 16, QrXMm = 125, QrYMm = 80;
        public string Logo = "";
        public double LogoXMm = 3, LogoYMm = 5, LogoWMm = 35;
    }

    internal sealed class HostConfig
    {
        public string DataDir;
        public string PhotoDir = @"C:\liftpic\fotos";
        public string StatisticFile;
        public string PrintCountFile;
        public string SoldDir;
        public string CoinStatsFile;

        public string CardExe = @"c:\liftpic\terminal\easyzvt.exe";
        public string CardWorkDir;
        public string CardAmountKey = @"Software\GUB\ZVT\Betrag";
        public string CardResultKey = @"Software\GUB\ZVT\Ergebnis";
        public int CardTimeoutSeconds = 120;

        public string CashLibDir = @"C:\liftpic\samuel_neu";

        public PrintLayout Print = new PrintLayout();

        public string FaceClient = @"C:\liftpic\samuel_neu\FaceAiSharp\FaceAiSharpClient.exe";
        public string FacePhotoDir;
        public double FaceThreshold = 0.3;

        public DateTime LoadedFrom = DateTime.MinValue;

        public static HostConfig Load(string dataDir)
        {
            var c = new HostConfig { DataDir = dataDir };
            string file = Path.Combine(dataDir, "host.json");
            object j = null;
            try
            {
                if (File.Exists(file))
                {
                    j = Json.Parse(File.ReadAllText(file));
                    c.LoadedFrom = File.GetLastWriteTimeUtc(file);
                }
            }
            catch { /* Vorgaben */ }
            if (j == null) { c.FacePhotoDir = c.PhotoDir; return c; }

            c.PhotoDir = Json.Str(j, "photo_dir", c.PhotoDir);
            c.StatisticFile = Json.Str(j, "statistic_file");
            c.PrintCountFile = Json.Str(j, "print_count_file");
            c.SoldDir = Json.Str(j, "sold_dir");
            c.CoinStatsFile = Json.Str(j, "coin_stats_file");

            var card = Json.Get(j, "card");
            c.CardExe = Json.Str(card, "exe", c.CardExe);
            c.CardWorkDir = Json.Str(card, "workdir");
            c.CardAmountKey = Json.Str(card, "amount_key", c.CardAmountKey);
            c.CardResultKey = Json.Str(card, "result_key", c.CardResultKey);
            c.CardTimeoutSeconds = Math.Max(20, Json.Int(card, "timeout_seconds", c.CardTimeoutSeconds));

            c.CashLibDir = Json.Str(Json.Get(j, "cash"), "lib_dir", c.CashLibDir);

            var p = Json.Get(j, "printer");
            var l = c.Print;
            l.Name = Json.Str(p, "name", "");
            l.PhotoWidthMm = Json.Num(p, "photo_w_mm", l.PhotoWidthMm);
            l.PhotoHeightMm = Json.Num(p, "photo_h_mm", l.PhotoHeightMm);
            l.LeftMm = Json.Num(p, "left_mm", 0);
            l.TopMm = Json.Num(p, "top_mm", 0);
            l.Date = Json.Bool(p, "date", true);
            l.Time = Json.Bool(p, "time", false);
            l.Qr = Json.Bool(p, "qr", true);
            l.QrMm = Json.Num(p, "qr_mm", l.QrMm);
            l.QrXMm = Json.Num(p, "qr_x_mm", l.QrXMm);
            l.QrYMm = Json.Num(p, "qr_y_mm", l.QrYMm);
            l.Logo = Json.Str(p, "logo", "");
            l.LogoXMm = Json.Num(p, "logo_x_mm", l.LogoXMm);
            l.LogoYMm = Json.Num(p, "logo_y_mm", l.LogoYMm);
            l.LogoWMm = Json.Num(p, "logo_w_mm", l.LogoWMm);

            var f = Json.Get(j, "face");
            c.FaceClient = Json.Str(f, "client", c.FaceClient);
            c.FacePhotoDir = Json.Str(f, "photo_dir", c.PhotoDir);
            c.FaceThreshold = Json.Num(f, "threshold", c.FaceThreshold);
            return c;
        }
    }
}
