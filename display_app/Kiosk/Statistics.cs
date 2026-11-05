// Verkaeufe festhalten - so, dass die bestehende Kette unveraendert weiterlaeuft:
//   Statistic.txt  wie das alte Programm (StatisticEntry.ToString):
//                  "dd.MM.yyyy HH:mm:ss::<Foto mit Pfad>::<Art>||<Zahlart>||<Preis 0,00>"
//                  Art 3 = Druck, 4 = Web/QR (digital); Zahlart 2 = Karte, 1 = bar, 0 = sonst.
//                  Daraus liest der Agent verkaufte Fotos (sold_via_statistic) und Zahlungen.
//   Verkauft-Ordner (qrcode) Kopie jedes verkauften Fotos - der Agent laedt sie hoch (sold_only).
//   PrintCount.txt gedruckte Fotos (zaehlt hoch, Papier-Warnung im Dashboard).
//   sales\JJJJ-MM-TT.jsonl  der ganze Verkauf (neu): Tageszahlen und Freischaltung der Download-Codes.
using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace Liftpictures.Display.Kiosk
{
    internal sealed class Statistics
    {
        public static readonly CultureInfo German = CultureInfo.GetCultureInfo("de-DE");
        private static readonly Encoding Utf8 = new UTF8Encoding(false);
        private readonly Func<HostConfig> _cfg;
        private readonly object _lock = new object();

        public Statistics(Func<HostConfig> cfg)
        {
            _cfg = cfg;
        }

        private static bool SafeName(string file)
        {
            return !string.IsNullOrEmpty(file) && file.IndexOfAny(new[] { '\\', '/', ':' }) < 0 && !file.Contains("..");
        }

        /// <summary>Ein Verkauf aus der App (SaleRecord, siehe kiosk_app/src/hardware.ts).</summary>
        public void Record(object rec)
        {
            var c = _cfg();
            string method = Json.Str(rec, "method", "other");
            int payType = method == "card" ? 2 : method == "cash" ? 1 : 0;
            var items = Json.Arr(Json.Get(rec, "items")) ?? new object[0];
            DateTime at = DateTime.Now;
            lock (_lock)
            {
                try
                {
                    string dir = Path.Combine(c.DataDir, "sales");
                    Directory.CreateDirectory(dir);
                    File.AppendAllText(Path.Combine(dir, at.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) + ".jsonl"),
                        Json.Write(rec) + "\n", Utf8);
                }
                catch (Exception ex) { Log.Write("sales log: " + ex.Message); }

                var lines = new StringBuilder();
                foreach (var it in items)
                {
                    string file = Json.Str(it, "file");
                    if (!SafeName(file)) continue;
                    string format = Json.Str(it, "format", "digital");
                    int type = format == "digital" ? 4 : 3;
                    double price = Json.Num(it, "price_cents") / 100.0;
                    string full = Path.Combine(c.PhotoDir, file);
                    lines.Append(at.ToString("dd.MM.yyyy HH:mm:ss", CultureInfo.InvariantCulture))
                         .Append("::").Append(full).Append("::").Append(type)
                         .Append("||").Append(payType).Append("||").Append(price.ToString("0.00", German))
                         .Append(Environment.NewLine);
                    CopySold(c, full, file);
                }
                if (lines.Length > 0 && !string.IsNullOrEmpty(c.StatisticFile))
                {
                    try { File.AppendAllText(c.StatisticFile, lines.ToString(), Utf8); }
                    catch (Exception ex) { Log.Write("statistic: " + ex.Message); }
                }
            }
            Log.Write("sale " + Json.Str(rec, "id") + " " + method + " " + Json.Int(rec, "amount_cents") + " ct, " + items.Length + " photos");
        }

        private static void CopySold(HostConfig c, string full, string file)
        {
            if (string.IsNullOrEmpty(c.SoldDir)) return;
            try
            {
                Directory.CreateDirectory(c.SoldDir);
                string target = Path.Combine(c.SoldDir, file);
                if (File.Exists(full) && !File.Exists(target)) File.Copy(full, target);
            }
            catch (Exception ex) { Log.Write("sold copy " + file + ": " + ex.Message); }
        }

        /// <summary>Zahlung kam an, nachdem der Gast weg war - fuer die Erstattung festhalten.</summary>
        public void LateCard(int cents)
        {
            Record(new System.Collections.Generic.Dictionary<string, object>
            {
                ["id"] = "late-" + DateTime.Now.Ticks.ToString(CultureInfo.InvariantCulture),
                ["at"] = DateTimeOffset.Now.ToString("yyyy-MM-ddTHH:mm:sszzz", CultureInfo.InvariantCulture),
                ["method"] = "card_late",
                ["amount_cents"] = cents,
                ["change_cents"] = 0,
                ["voucher"] = null,
                ["items"] = new object[0],
                ["note"] = "card approved after the guest cancelled - please refund",
            });
        }

        public void CountPrint()
        {
            var c = _cfg();
            if (string.IsNullOrEmpty(c.PrintCountFile)) return;
            lock (_lock)
            {
                try
                {
                    int n = 0;
                    if (File.Exists(c.PrintCountFile))
                        int.TryParse(File.ReadAllText(c.PrintCountFile).Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out n);
                    File.WriteAllText(c.PrintCountFile, (n + 1).ToString(CultureInfo.InvariantCulture), Utf8);
                }
                catch (Exception ex) { Log.Write("print count: " + ex.Message); }
            }
        }

        /// <summary>Alte Verkaufsprotokolle (sales\*.jsonl) nach 400 Tagen loeschen.</summary>
        public void Tidy()
        {
            try
            {
                string dir = Path.Combine(_cfg().DataDir, "sales");
                if (!Directory.Exists(dir)) return;
                foreach (var f in new DirectoryInfo(dir).GetFiles("*.jsonl").Where(f => f.LastWriteTime < DateTime.Now.AddDays(-400)))
                    f.Delete();
            }
            catch { }
        }
    }
}
