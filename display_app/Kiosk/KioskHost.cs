// Liftpictures Kiosk im Programm Liftpictures Display (--kiosk).
//
// Die App (kiosk_app, React) liegt neben dem Programm im Ordner "kiosk" und laeuft unter
// https://kiosk.liftpictures/ . Fotos, Vorschaubilder und data.js kommen von
// https://kiosk-media.liftpictures/ (siehe Media.cs) - alles lokal, ohne Internet.
//
// Geraete-Bruecke: die App schickt {type:'hw', id, method, args}, hier wird geantwortet mit
// {type:'hw-result', id, result}; Ereignisse gehen als {type:'hw-event', event, value} zurueck.
//   status | configure | cashEnable | cashDisable | cashPayout | cardPay | cardCancel |
//   print | pickup | faceSearch | sale | exit
// Welche Geraete gebraucht werden, sagt die App (configure) aus ihren Einstellungen (Version).
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;

namespace Liftpictures.Display.Kiosk
{
    internal sealed class KioskHost : IDisposable
    {
        public const string AppHost = "kiosk.liftpictures";
        public const string MediaHost = "kiosk-media.liftpictures";
        private const string MediaBase = "https://" + MediaHost + "/";

        private static readonly HttpClient PickupClient = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false })
        {
            Timeout = TimeSpan.FromSeconds(15),
        };

        private readonly DisplayForm _form;
        private readonly CoreWebView2 _core;
        private readonly string _appDir;
        private readonly string _dataDir;
        private HostConfig _config;
        private readonly Media _media;
        private readonly Statistics _stats;
        private readonly CardTerminal _card;
        private readonly PhotoPrinter _printer;
        private readonly FaceSearch _face;
        private CoinChanger _coins;
        private readonly Timer _tick = new Timer { Interval = 15000 };
        private bool _wantCard, _wantCash, _wantPrinter, _wantFace;
        private string _lastStatus;
        private string _printerState = "offline";

        public KioskHost(DisplayForm form, CoreWebView2 core, string appDir, string dataDir)
        {
            _form = form;
            _core = core;
            _appDir = appDir;
            _dataDir = dataDir;
            Directory.CreateDirectory(dataDir);
            Log.Dir = Path.Combine(dataDir, "logs");
            _config = HostConfig.Load(dataDir);
            _media = new Media(Config);
            _stats = new Statistics(Config);
            _card = new CardTerminal(Config, Emit, cents => _stats.LateCard(cents));
            _printer = new PhotoPrinter(Config);
            _face = new FaceSearch(Config);
        }

        /// <summary>host.json neu lesen, wenn der Agent es geaendert hat.</summary>
        private HostConfig Config()
        {
            try
            {
                string file = Path.Combine(_dataDir, "host.json");
                if (File.Exists(file) && File.GetLastWriteTimeUtc(file) != _config.LoadedFrom) _config = HostConfig.Load(_dataDir);
            }
            catch { }
            return _config;
        }

        public void Start()
        {
            if (!File.Exists(Path.Combine(_appDir, "index.html")))
                throw new FileNotFoundException("Kiosk app missing: " + Path.Combine(_appDir, "index.html"));
            Log.Write("kiosk: start " + Application.ProductVersion + ", app " + _appDir + ", data " + _dataDir);

            var s = _core.Settings;
            try { s.IsPinchZoomEnabled = false; } catch { }
            try { s.IsSwipeNavigationEnabled = false; } catch { }
            try { s.IsGeneralAutofillEnabled = false; s.IsPasswordAutosaveEnabled = false; } catch { }

            _core.SetVirtualHostNameToFolderMapping(AppHost, _appDir, CoreWebView2HostResourceAccessKind.DenyCors);
            _core.AddWebResourceRequestedFilter(MediaBase + "*", CoreWebView2WebResourceContext.All);
            _core.WebResourceRequested += OnResource;
            _core.WebMessageReceived += OnMessage;
            _core.NewWindowRequested += (o, e) => { e.Handled = true; };
            _core.NavigationStarting += (o, e) =>
            {
                string u = e.Uri ?? "";
                if (!u.StartsWith("https://" + AppHost + "/", StringComparison.OrdinalIgnoreCase) &&
                    !u.StartsWith("data:", StringComparison.OrdinalIgnoreCase) &&
                    !u.StartsWith("about:", StringComparison.OrdinalIgnoreCase))
                    e.Cancel = true;
            };
            // Kamera fuer Gesichtssuche und QR-Scan: nur fuer die eigene App, ohne Rueckfrage.
            _core.PermissionRequested += (o, e) =>
            {
                bool own = (e.Uri ?? "").StartsWith("https://" + AppHost + "/", StringComparison.OrdinalIgnoreCase);
                if (own && (e.PermissionKind == CoreWebView2PermissionKind.Camera)) e.State = CoreWebView2PermissionState.Allow;
                else e.State = CoreWebView2PermissionState.Deny;
            };
            _tick.Tick += (o, e) => Tick();
            _tick.Start();
            Tick();
            Reload();
        }

        public void Reload()
        {
            _core.Navigate("https://" + AppHost + "/index.html");
        }

        // ------------------------------------------------------------------ Medien

        private CoreWebView2WebResourceResponse Respond(byte[] body, string type, string cache)
        {
            return _core.Environment.CreateWebResourceResponse(new MemoryStream(body), 200, "OK",
                "Content-Type: " + type + "\r\nCache-Control: " + cache + "\r\nAccess-Control-Allow-Origin: https://" + AppHost);
        }

        private CoreWebView2WebResourceResponse NotFound()
        {
            return _core.Environment.CreateWebResourceResponse(new MemoryStream(new byte[0]), 404, "Not Found", "Cache-Control: no-store");
        }

        private static byte[] ReadShared(string path)
        {
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (var ms = new MemoryStream())
            {
                fs.CopyTo(ms);
                return ms.ToArray();
            }
        }

        private void OnResource(object sender, CoreWebView2WebResourceRequestedEventArgs e)
        {
            string path;
            try { path = Uri.UnescapeDataString(new Uri(e.Request.Uri).AbsolutePath.TrimStart('/')); }
            catch { e.Response = NotFound(); return; }
            try
            {
                if (path == "data.js")
                {
                    string f = Path.Combine(_dataDir, "data.js");
                    e.Response = File.Exists(f) ? Respond(ReadShared(f), "text/javascript; charset=utf-8", "no-store") : NotFound();
                    return;
                }
                if (path == "park-logo")
                {
                    string f = Path.Combine(_dataDir, "park-logo");
                    e.Response = File.Exists(f) ? Respond(ReadShared(f), LogoType(f), "max-age=3600") : NotFound();
                    return;
                }
                bool thumb = path.StartsWith("thumb/", StringComparison.Ordinal);
                bool view = path.StartsWith("photo/", StringComparison.Ordinal);
                if (!thumb && !view) { e.Response = NotFound(); return; }
                string file = path.Substring(6);
                if (!Media.SafeName(file)) { e.Response = NotFound(); return; }
                var task = _media.ScaledAsync(file, thumb ? Media.ThumbWidth : Media.ViewWidth);
                if (task.IsCompleted)
                {
                    e.Response = task.Result != null ? Respond(ReadShared(task.Result), "image/jpeg", "max-age=86400") : NotFound();
                    return;
                }
                var deferral = e.GetDeferral();
                task.ContinueWith(t =>
                {
                    byte[] body = null;
                    try { if (t.Status == TaskStatus.RanToCompletion && t.Result != null) body = ReadShared(t.Result); } catch { }
                    _form.BeginInvoke((Action)(() =>
                    {
                        try { e.Response = body != null ? Respond(body, "image/jpeg", "max-age=86400") : NotFound(); }
                        catch { }
                        finally { deferral.Complete(); }
                    }));
                });
            }
            catch (Exception ex)
            {
                Log.Write("media " + path + ": " + ex.Message);
                try { e.Response = NotFound(); } catch { }
            }
        }

        private static string LogoType(string file)
        {
            try
            {
                var head = new byte[12];
                using (var fs = File.OpenRead(file)) fs.Read(head, 0, head.Length);
                if (head[0] == 0x89 && head[1] == 0x50) return "image/png";
                if (head[0] == 0xFF && head[1] == 0xD8) return "image/jpeg";
                if (head[0] == 0x52 && head[1] == 0x49 && head[8] == 0x57) return "image/webp";
                if (head[0] == 0x3C) return "image/svg+xml";
            }
            catch { }
            return "application/octet-stream";
        }

        // ------------------------------------------------------------------ Bruecke

        private void Post(object message)
        {
            string json = Json.Write(message);
            if (_form.InvokeRequired) _form.BeginInvoke((Action)(() => SafePost(json)));
            else SafePost(json);
        }

        private void SafePost(string json)
        {
            try { _core.PostWebMessageAsJson(json); } catch { }
        }

        private void Emit(string name, object value)
        {
            Post(new Dictionary<string, object> { ["type"] = "hw-event", ["event"] = name, ["value"] = value });
        }

        private async void OnMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            if (!(e.Source ?? "").StartsWith("https://" + AppHost + "/", StringComparison.OrdinalIgnoreCase)) return;
            object msg;
            try { msg = Json.Parse(e.WebMessageAsJson); } catch { return; }
            if (Json.Str(msg, "type") != "hw") return;
            object id = Json.Get(msg, "id");
            string method = Json.Str(msg, "method", "");
            var args = Json.Arr(Json.Get(msg, "args")) ?? new object[0];
            object result = null;
            try { result = await Dispatch(method, args); }
            catch (Exception ex) { Log.Write("hw " + method + ": " + ex.Message); }
            Post(new Dictionary<string, object> { ["type"] = "hw-result", ["id"] = id, ["result"] = result });
        }

        private static object Arg(object[] args, int i)
        {
            return i < args.Length ? args[i] : null;
        }

        private async Task<object> Dispatch(string method, object[] args)
        {
            switch (method)
            {
                case "status":
                    return Status();
                case "configure":
                    await Configure(Arg(args, 0));
                    return Status();
                case "cashEnable":
                    if (_coins == null || !_coins.IsOpen) return false;
                    return await _coins.EnableAsync();
                case "cashDisable":
                    if (_coins != null) await _coins.DisableAsync();
                    return true;
                case "cashPayout":
                    if (_coins == null) return 0;
                    int paid = await _coins.PayoutAsync((int)Json.ToNum(Arg(args, 0)));
                    PushStatus();
                    return paid;
                case "cardPay":
                    string r = await _card.PayAsync((int)Json.ToNum(Arg(args, 0)));
                    _form.BeginInvoke((Action)(() => _form.Activate()));
                    return r;
                case "cardCancel":
                    _card.Cancel();
                    return true;
                case "pickup":
                    return await PickupAsync(Arg(args, 0), Arg(args, 1));
                case "print":
                    var jobs = Json.Arr(Arg(args, 0)) ?? new object[0];
                    PushStatus("printing");
                    bool ok = await _printer.PrintAsync(jobs, Arg(args, 1),
                        (done, total) => Emit("print", new Dictionary<string, object> { ["done"] = done, ["total"] = total }),
                        () => _stats.CountPrint());
                    _printerState = _printer.State();
                    PushStatus();
                    return ok;
                case "faceSearch":
                    if (!_wantFace) return new string[0];
                    _face.Start();
                    var files = (Json.Arr(Arg(args, 1)) ?? new object[0]).Select(o => Convert.ToString(o, CultureInfo.InvariantCulture)).ToArray();
                    return await _face.SearchAsync(Convert.ToString(Arg(args, 0), CultureInfo.InvariantCulture), files);
                case "sale":
                    var rec = Arg(args, 0);
                    await Task.Run(() => _stats.Record(rec));
                    return true;
                case "exit":
                    Log.Write("kiosk: closed from the staff menu");
                    _form.BeginInvoke((Action)(() => _form.CloseForGood()));
                    return true;
                default:
                    return null;
            }
        }

        private async Task<object> PickupAsync(object data, object files)
        {
            var c = Config();
            if (!_wantPrinter || string.IsNullOrEmpty(c.PickupMachineId) || string.IsNullOrEmpty(c.PickupDeviceToken))
                return new Dictionary<string, object> { ["status"] = "unavailable" };

            string phase = Json.Str(data, "phase");
            if (phase == "claim")
            {
                if (_printer.State() != "ready") return new Dictionary<string, object> { ["status"] = "printer" };
                var names = Json.Arr(files) ?? new object[0];
                if (names.Length == 0 || names.Any(name => !(name is string file) || !Media.SafeName(file) ||
                    !File.Exists(Path.Combine(c.PhotoDir, file))))
                    return new Dictionary<string, object> { ["status"] = "missing" };
            }

            const string url = "https://kvpcwlcfgmsmarjtwpsx.supabase.co/functions/v1/online-photo-sales/kiosk-pickup";
            using (var request = new HttpRequestMessage(HttpMethod.Post, url))
            {
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", c.PickupDeviceToken);
                request.Headers.Add("x-machine-id", c.PickupMachineId);
                request.Content = new StringContent(Json.Write(data), Encoding.UTF8, "application/json");
                try
                {
                    using (var response = await PickupClient.SendAsync(request))
                        return Json.Parse(await response.Content.ReadAsStringAsync());
                }
                catch (HttpRequestException) { }
                catch (TaskCanceledException) { }
            }
            return new Dictionary<string, object> { ["status"] = "offline" };
        }

        private async Task Configure(object want)
        {
            _wantCard = Json.Bool(want, "card");
            _wantCash = Json.Bool(want, "cash");
            _wantPrinter = Json.Bool(want, "printer");
            _wantFace = Json.Bool(want, "face");
            var c = Config();
            if (_wantCash && _coins == null)
            {
                _coins = new CoinChanger(cents => Emit("coin", cents), problem => PushStatus()) { StatsFile = c.CoinStatsFile };
                bool open = await _coins.OpenAsync(c.CashLibDir);
                if (!open) Log.Write("kiosk: cash not available: " + _coins.LastError);
            }
            if (_coins != null) _coins.StatsFile = c.CoinStatsFile;
            if (_wantPrinter) _printerState = await Task.Run(() => _printer.State());
            PushStatus();
        }

        private Dictionary<string, object> Status(string printer = null)
        {
            return new Dictionary<string, object>
            {
                ["card"] = _wantCard && _card.Available,
                ["cash"] = _wantCash && _coins != null && _coins.IsOpen,
                ["change"] = _wantCash && _coins != null && _coins.IsOpen && _coins.HasChange,
                ["printer"] = _wantPrinter ? (printer ?? _printerState) : "offline",
                ["face"] = _wantFace && _face.Installed,
                ["camera"] = _wantFace,
            };
        }

        private void PushStatus(string printer = null)
        {
            var st = Status(printer);
            string json = Json.Write(st);
            if (json == _lastStatus) return;
            _lastStatus = json;
            Emit("status", st);
        }

        /// <summary>Alle 15 s: Drucker pruefen, Lebenszeichen fuer den Agenten (alive.json).</summary>
        private async void Tick()
        {
            try
            {
                if (_wantPrinter && !_printer.Printing) _printerState = await Task.Run(() => _printer.State());
                PushStatus();
                var alive = new Dictionary<string, object>
                {
                    ["at"] = DateTimeOffset.Now.ToString("yyyy-MM-ddTHH:mm:sszzz", CultureInfo.InvariantCulture),
                    ["version"] = Application.ProductVersion,
                    ["devices"] = Status(),
                    ["cash_error"] = _coins?.LastError,
                };
                string file = Path.Combine(_dataDir, "alive.json");
                File.WriteAllText(file + ".tmp", Json.Write(alive), new UTF8Encoding(false));
                if (File.Exists(file)) File.Delete(file);
                File.Move(file + ".tmp", file);
                if (DateTime.Now.Minute == 0) _stats.Tidy();
            }
            catch (Exception ex) { Log.Write("tick: " + ex.Message); }
        }

        public void Dispose()
        {
            _tick.Stop();
            try { _coins?.Dispose(); } catch { }
            try { _face.Dispose(); } catch { }
            try { _printer.Dispose(); } catch { }
            try { _media.Dispose(); } catch { }
            Log.Write("kiosk: stop");
        }
    }
}
