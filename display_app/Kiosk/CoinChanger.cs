// Muenzpruefer/Wechsler (NRI) - ueber denselben Treiber wie das alte Verkaufsprogramm:
// PhotoViewerLib.dll (Klasse NRI.CoinChanger.CoinChanger) -> PaymentManager.dll -> NriHidAPI.dll,
// eingestellt in PaymentManager.ini. Alles liegt im Programmordner des alten Programms (samuel_neu).
//
// Der Treiber laeuft in einer eigenen AppDomain mit samuel_neu als Basisordner: so schreibt er sein
// Protokoll wie immer nach samuel_neu\Log\NRI.CoinCharger_MMJJJJ.txt - der Agent prueft daraus
// Einwurf gegen Auszahlung (payments.py). Ereignisse kommen als Fenster-Nachricht 1025 (WM_USER+1)
// an ein unsichtbares Fenster und werden nacheinander auf einem eigenen Thread verarbeitet.
using System;
using System.Collections;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Liftpictures.Display.Kiosk
{
    public interface ICoinSink
    {
        void Coin(int cents);
        void Status(int code, string message);
        void Error(int code, string message);
    }

    /// <summary>Laeuft in der AppDomain des Treibers.</summary>
    public sealed class CoinDomainWorker : MarshalByRefObject
    {
        private Type _t;
        private object _cc;
        private Type _msgArgs;
        private MethodInfo _pump;
        private MethodInfo _setpm;
        private MethodInfo _log;
        private PropertyInfo _ready;
        private ICoinSink _sink;

        public override object InitializeLifetimeService() { return null; }

        public void Open(string libDir, long hwnd, ICoinSink sink)
        {
            _sink = sink;
            var asm = Assembly.LoadFrom(Path.Combine(libDir, "PhotoViewerLib.dll"));
            _t = asm.GetType("NRI.CoinChanger.CoinChanger", true);
            _msgArgs = asm.GetType("NRI.CoinChanger.MessageEventArgs", true);
            const BindingFlags any = BindingFlags.Public | BindingFlags.NonPublic;
            _pump = _t.GetMethod("MessagePump_MessageReceived", any | BindingFlags.Instance);
            _setpm = _t.GetMethod("setpaymentmanager", any | BindingFlags.Static);
            _ready = _t.GetProperty("IsAceptorDeviceReady", any | BindingFlags.Instance);
            var logType = asm.GetType("NRI.CoinCharger.CoinChangerLog", false);
            _log = logType?.GetMethod("WriteLog", any | BindingFlags.Static, null, new[] { typeof(string) }, null);
            _cc = Activator.CreateInstance(_t);
            _t.GetProperty("Handler").SetValue(_cc, new IntPtr(hwnd), null);
            Hook("CoinAccepted", nameof(OnCoin));
            Hook("CoinChangerError", nameof(OnError));
            Hook("CoinChangerStatus", nameof(OnStatus));
            Call("Open");
            Call("Start");
        }

        private void Hook(string eventName, string handler)
        {
            var ev = _t.GetEvent(eventName);
            if (ev == null) return;
            var m = typeof(CoinDomainWorker).GetMethod(handler, BindingFlags.NonPublic | BindingFlags.Instance);
            ev.AddEventHandler(_cc, Delegate.CreateDelegate(ev.EventHandlerType, this, m));
        }

        private object Call(string method)
        {
            try { return _t.GetMethod(method, Type.EmptyTypes).Invoke(_cc, null); }
            catch (TargetInvocationException ex) when (ex.InnerException != null) { throw new InvalidOperationException(method + ": " + ex.InnerException.Message); }
        }

        private static object Prop(object o, string name)
        {
            return o?.GetType().GetProperty(name)?.GetValue(o, null);
        }

        private void OnCoin(object sender, EventArgs e)
        {
            _sink.Coin(Convert.ToInt32(Prop(e, "Nominal"), CultureInfo.InvariantCulture));
        }

        private void OnStatus(object sender, EventArgs e)
        {
            _sink.Status(Convert.ToInt32(Prop(e, "Code") ?? 0, CultureInfo.InvariantCulture), Convert.ToString(Prop(e, "Message")));
        }

        private void OnError(object sender, EventArgs e)
        {
            _sink.Error(Convert.ToInt32(Prop(e, "Code") ?? 0, CultureInfo.InvariantCulture), Convert.ToString(Prop(e, "Message")));
        }

        public void Pump(long hwnd, int msg, long wparam, long lparam)
        {
            var m = Message.Create(new IntPtr(hwnd), msg, new IntPtr(wparam), new IntPtr(lparam));
            object args = Activator.CreateInstance(_msgArgs, new object[] { m });
            try { _pump.Invoke(_cc, new object[] { null, args }); }
            catch (TargetInvocationException ex) when (ex.InnerException != null) { throw new InvalidOperationException("message: " + ex.InnerException.Message); }
        }

        public void Enable() { Call("EnableCoinAccepting"); }
        public void Disable() { Call("DisableCoinAccepting"); }

        public bool Ready()
        {
            try { return _ready != null && (bool)_ready.GetValue(_cc, null); }
            catch { return false; }
        }

        /// <summary>Auszahlen; gibt zurueck, was wirklich heraus kam (wie im NRI-Protokoll hinter "=>").</summary>
        public int Payout(int cents)
        {
            int r = Convert.ToInt32(_setpm.Invoke(null, new object[] { 1, 0, cents, 0 }), CultureInfo.InvariantCulture);
            // Dieselbe Zeile wie TryPayout des Treibers - der Agent rechnet damit.
            _log?.Invoke(null, new object[] { string.Format(CultureInfo.InvariantCulture, "try payout:  setpaymentmanager(1,0,{0},0) => {1}", cents, r) });
            return r < 0 ? 0 : Math.Min(r, cents);
        }

        /// <summary>Bestand: "nominal:anzahl:roehre;..."</summary>
        public string Coins()
        {
            var sb = new StringBuilder();
            if (!(_t.GetMethod("GetCoins", Type.EmptyTypes)?.Invoke(_cc, null) is IEnumerable list)) return "";
            foreach (var coin in list)
            {
                int nominal = Convert.ToInt32(Prop(coin, "Nominal") ?? 0, CultureInfo.InvariantCulture);
                int qty = Convert.ToInt32(Prop(coin, "Qty") ?? 0, CultureInfo.InvariantCulture);
                bool tube = Prop(coin, "IsTube") is bool b && b;
                if (nominal > 0) sb.Append(nominal).Append(':').Append(qty).Append(':').Append(tube ? 1 : 0).Append(';');
            }
            return sb.ToString();
        }

        public void Close()
        {
            try { Call("DisableCoinAccepting"); } catch { }
            try { Call("Stop"); } catch { }
            try { (_cc as IDisposable)?.Dispose(); } catch { }
        }
    }

    public sealed class CoinSink : MarshalByRefObject, ICoinSink
    {
        private readonly CoinChanger _owner;
        internal CoinSink(CoinChanger owner) { _owner = owner; }
        public override object InitializeLifetimeService() { return null; }
        public void Coin(int cents) { _owner.OnCoin(cents); }
        public void Status(int code, string message) { _owner.OnProblem(false, code, message); }
        public void Error(int code, string message) { _owner.OnProblem(true, code, message); }
    }

    internal sealed class CoinWindow : NativeWindow
    {
        private readonly Action<Message> _onMessage;

        public CoinWindow(Action<Message> onMessage)
        {
            _onMessage = onMessage;
            CreateHandle(new CreateParams { Caption = "LiftpicturesCoins", Parent = new IntPtr(-3) }); // HWND_MESSAGE
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == 1025) { _onMessage(m); m.Result = IntPtr.Zero; return; }
            base.WndProc(ref m);
        }
    }

    internal sealed class CoinChanger : IDisposable
    {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool SetDllDirectory(string path);

        private readonly Worker _worker = new Worker("coins", false);
        private readonly Action<int> _coin;
        private readonly Action<string> _problem;
        private AppDomain _domain;
        private CoinDomainWorker _remote;
        private CoinWindow _window;
        private volatile bool _active;
        private DateTime _lastStats = DateTime.MinValue;

        public bool IsOpen { get; private set; }
        public bool HasChange { get; private set; }
        public string LastError { get; private set; }

        public CoinChanger(Action<int> coin, Action<string> problem)
        {
            _coin = coin;
            _problem = problem;
        }

        /// <summary>Auf dem UI-Thread aufrufen (das Fenster braucht dessen Nachrichtenschleife).</summary>
        public Task<bool> OpenAsync(string libDir)
        {
            if (IsOpen) return Task.FromResult(true);
            if (_window == null)
                _window = new CoinWindow(m => { long h = m.HWnd.ToInt64(), w = m.WParam.ToInt64(), l = m.LParam.ToInt64(); int msg = m.Msg; _worker.Post(() => _remote?.Pump(h, msg, w, l)); });
            long hwnd = _window.Handle.ToInt64();
            return _worker.Run(() =>
            {
                try
                {
                    if (!File.Exists(Path.Combine(libDir, "PhotoViewerLib.dll")) || !File.Exists(Path.Combine(libDir, "PaymentManager.dll")))
                        throw new FileNotFoundException("NRI driver not found in " + libDir);
                    if (IntPtr.Size != 4) throw new InvalidOperationException("coin driver needs a 32-bit process");
                    SetDllDirectory(libDir);
                    // PaymentManager.ini liest der Treiber relativ - wie beim alten Programm aus samuel_neu.
                    Directory.SetCurrentDirectory(libDir);
                    var setup = new AppDomainSetup { ApplicationBase = libDir.TrimEnd('\\') + "\\" };
                    _domain = AppDomain.CreateDomain("LiftpicturesCoins", null, setup);
                    _remote = (CoinDomainWorker)_domain.CreateInstanceFromAndUnwrap(
                        typeof(CoinDomainWorker).Assembly.Location, typeof(CoinDomainWorker).FullName);
                    _remote.Open(libDir, hwnd, new CoinSink(this));
                    _remote.Disable();
                    IsOpen = true;
                    LastError = null;
                    UpdateStock(true);
                    Log.Write("coins: open (" + libDir + ")");
                    return true;
                }
                catch (Exception ex)
                {
                    LastError = ex.Message;
                    Log.Write("coins: " + ex.Message);
                    Unload();
                    return false;
                }
            });
        }

        internal void OnCoin(int cents)
        {
            if (_active) { _coin(cents); return; }
            // Muenze kam nach dem Abschalten an: sofort zurueckgeben.
            Log.Write("coins: " + cents + " ct while not accepting - returned");
            _worker.Post(() => { try { _remote?.Payout(cents); } catch (Exception ex) { Log.Write("coins: return " + ex.Message); } });
        }

        internal void OnProblem(bool error, int code, string message)
        {
            Log.Write("coins " + (error ? "error" : "status") + " " + code + ": " + message);
            if (error) _problem(message);
        }

        public Task<bool> EnableAsync()
        {
            return _worker.Run(() =>
            {
                if (_remote == null) return false;
                try { _remote.Enable(); _active = true; return true; }
                catch (Exception ex) { LastError = ex.Message; Log.Write("coins: enable " + ex.Message); return false; }
            });
        }

        public Task DisableAsync()
        {
            _active = false;
            return _worker.Run(() =>
            {
                try { _remote?.Disable(); } catch (Exception ex) { Log.Write("coins: disable " + ex.Message); }
                UpdateStock(false);
                return true;
            });
        }

        public Task<int> PayoutAsync(int cents)
        {
            return _worker.Run(() =>
            {
                if (_remote == null || cents <= 0) return 0;
                try
                {
                    int paid = _remote.Payout(cents);
                    Log.Write("coins: payout " + cents + " ct -> " + paid + " ct");
                    UpdateStock(true);
                    return paid;
                }
                catch (Exception ex) { Log.Write("coins: payout " + ex.Message); return 0; }
            });
        }

        /// <summary>Bestand lesen (Wechselgeld da?) und - hoechstens halbstuendlich - CoinStats.txt fortschreiben.</summary>
        private void UpdateStock(bool force)
        {
            if (_remote == null) return;
            try
            {
                string coins = _remote.Coins();
                long tubes = 0;
                var line = new StringBuilder();
                long total = 0;
                foreach (var part in coins.Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    var f = part.Split(':');
                    int nominal = int.Parse(f[0], CultureInfo.InvariantCulture), qty = int.Parse(f[1], CultureInfo.InvariantCulture);
                    if (f[2] == "1") tubes += (long)nominal * qty;
                    total += (long)nominal * qty;
                    if (line.Length > 0) line.Append('+');
                    line.Append(qty).Append('x').Append((nominal / 100m).ToString("0.00", Statistics.German)).Append('€');
                }
                HasChange = tubes > 0;
                if (StatsFile != null && line.Length > 0 && (force || DateTime.Now - _lastStats > TimeSpan.FromMinutes(30)))
                {
                    _lastStats = DateTime.Now;
                    File.AppendAllText(StatsFile, DateTime.Now.ToString("dd.MM.yyyy HH:mm", CultureInfo.InvariantCulture) + " " + line +
                        "=" + (total / 100m).ToString("0.00", Statistics.German) + "€" + Environment.NewLine, new UTF8Encoding(false));
                }
            }
            catch (Exception ex) { Log.Write("coins: stock " + ex.Message); }
        }

        public string StatsFile { get; set; }

        private void Unload()
        {
            try { _remote?.Close(); } catch { }
            _remote = null;
            if (_domain != null) { try { AppDomain.Unload(_domain); } catch { } _domain = null; }
            IsOpen = false;
        }

        public void Dispose()
        {
            _active = false;
            _worker.Run(() => { Unload(); return true; }).Wait(3000);
            _worker.Dispose();
            try { _window?.DestroyHandle(); } catch { }
        }
    }
}
