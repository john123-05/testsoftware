// Kartenterminal - genau wie im alten Verkaufsprogramm (PaymentControl.RunCreditCardExecutable):
//   1. Betrag in Cent als DWORD nach HKCU\<CreditCardRegistryAmountParameter> (z. B. Software\GUB\ZVT\Betrag)
//   2. Ergebnis-Wert HKCU\<CreditCardRegistryResultParameter> auf 12345 setzen (= "noch nichts")
//   3. easyzvt.exe starten (spricht ZVT mit dem Terminal), warten bis es endet oder die Zeit um ist
//   4. Ergebnis lesen: 0 = bezahlt, sonst abgelehnt/abgebrochen
// Bricht der Gast ab, waehrend das Terminal noch auf die Karte wartet, wartet dieses Programm im
// Hintergrund weiter: geht die Zahlung doch noch durch, steht sie im Verkaufsprotokoll (zum Erstatten).
using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32;

namespace Liftpictures.Display.Kiosk
{
    internal sealed class CardTerminal
    {
        private const int Pending = 12345;
        private readonly Func<HostConfig> _cfg;
        private readonly Action<string, object> _emit;
        private readonly Action<int> _late;
        private volatile bool _cancelled;
        private int _busy;

        public CardTerminal(Func<HostConfig> cfg, Action<string, object> emit, Action<int> late)
        {
            _cfg = cfg;
            _emit = emit;
            _late = late;
        }

        public bool Available
        {
            get { try { return File.Exists(_cfg().CardExe); } catch { return false; } }
        }

        public void Cancel()
        {
            _cancelled = true;
        }

        public Task<string> PayAsync(int cents)
        {
            return Task.Run(() => Pay(cents));
        }

        private static void SetDword(string path, int value)
        {
            int cut = path.LastIndexOf('\\');
            if (cut <= 0) throw new ArgumentException("registry path: " + path);
            using (var key = Registry.CurrentUser.CreateSubKey(path.Substring(0, cut)))
                key.SetValue(path.Substring(cut + 1), value, RegistryValueKind.DWord);
        }

        private static int GetDword(string path)
        {
            int cut = path.LastIndexOf('\\');
            using (var key = Registry.CurrentUser.OpenSubKey(path.Substring(0, cut), false))
            {
                object v = key?.GetValue(path.Substring(cut + 1));
                return v is int i ? i : Pending;
            }
        }

        private string Pay(int cents)
        {
            if (cents <= 0) return "error";
            if (Interlocked.Exchange(ref _busy, 1) == 1) return "error";
            var c = _cfg();
            Process p = null;
            bool handedOff = false;
            try
            {
                _cancelled = false;
                if (!File.Exists(c.CardExe)) { Log.Write("card: program missing " + c.CardExe); return "error"; }
                SetDword(c.CardAmountKey, cents);
                SetDword(c.CardResultKey, Pending);
                Log.Write("card: start " + cents + " ct");
                _emit("card", "waiting");
                var psi = new ProcessStartInfo(c.CardExe)
                {
                    UseShellExecute = false,
                    WorkingDirectory = string.IsNullOrEmpty(c.CardWorkDir) ? Path.GetDirectoryName(c.CardExe) : c.CardWorkDir,
                };
                p = Process.Start(psi);
                var started = DateTime.UtcNow;
                bool exited = false;
                while (!_cancelled)
                {
                    if (p.WaitForExit(400)) { exited = true; break; }
                    if ((DateTime.UtcNow - started).TotalSeconds >= c.CardTimeoutSeconds) break;
                }
                if (!exited)
                {
                    string why = _cancelled ? "cancelled" : "timeout";
                    Log.Write("card: " + why + " while terminal still busy");
                    WatchLate(p, cents, c);
                    handedOff = true;
                    return why;
                }
                int result = GetDword(c.CardResultKey);
                Log.Write("card: result " + result);
                if (result == 0) return "approved";
                return result == Pending ? "error" : "declined";
            }
            catch (Exception ex)
            {
                Log.Write("card: " + ex.Message);
                return "error";
            }
            finally
            {
                // Laeuft easyzvt noch (Abbruch/Zeit um), bleibt das Terminal belegt, bis es fertig ist -
                // sonst stuenden zwei Zahlungen gleichzeitig an.
                if (!handedOff)
                {
                    p?.Dispose();
                    Interlocked.Exchange(ref _busy, 0);
                }
            }
        }

        private void WatchLate(Process p, int cents, HostConfig c)
        {
            Task.Run(() =>
            {
                try
                {
                    if (!p.WaitForExit(10 * 60 * 1000)) { Log.Write("card: terminal program still running after 10 min"); return; }
                    if (GetDword(c.CardResultKey) == 0)
                    {
                        Log.Write("card: LATE APPROVAL " + cents + " ct after the guest left - refund needed");
                        _late(cents);
                    }
                }
                catch { }
                finally
                {
                    p.Dispose();
                    Interlocked.Exchange(ref _busy, 0);
                }
            });
        }
    }
}
