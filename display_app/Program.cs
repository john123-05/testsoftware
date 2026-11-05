// Liftpictures Display
//
// Ein kleines Windows-Programm, das die lokalen Seiten des Agenten zeigt:
//   LiftpicturesDisplay.exe --presentation   Presentation, Vollbild auf dem 2. Monitor
//   LiftpicturesDisplay.exe --station        Station (Systemzustand), Vollbild auf dem Hauptmonitor
//   LiftpicturesDisplay.exe --kiosk          Verkaufsprogramm (Liftpictures Kiosk) am Touch-Bildschirm,
//                                            mit Kartenterminal, Muenzgeraet, Drucker, Gesichtssuche
//                                            (siehe Kiosk\KioskHost.cs)
// Weitere Schalter: --dir <Ordner>  --screen <Nummer, ab 1>  --windowed  --app <Ordner der Kiosk-App>
//
// Die Seiten schreibt Liftpic Sync (presentation.py / station.py) nach
// C:\liftpic\presentation bzw. C:\liftpic\station. Sie laufen ohne Internet.
// Lizenz und Inhalte steuert das CRM ueber den Agenten - dieses Programm
// zeigt nur an, was der Agent freigibt.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Liftpictures.Display
{
    internal sealed class Options
    {
        public string Mode = "presentation";
        public string Dir;
        public string AppDir;
        public int ScreenNumber = -1;
        public bool Windowed;

        public bool IsStation => Mode == "station";
        public bool IsKiosk => Mode == "kiosk";
        public string Title => IsKiosk ? "Liftpictures Kiosk" : IsStation ? "Liftpictures Station" : "Liftpictures Presentation";

        public static Options Parse(string[] args)
        {
            var o = new Options();
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i].Trim().ToLowerInvariant();
                if (a == "--station") o.Mode = "station";
                else if (a == "--presentation") o.Mode = "presentation";
                else if (a == "--kiosk") o.Mode = "kiosk";
                else if (a == "--app" && i + 1 < args.Length) o.AppDir = args[++i];
                else if (a == "--windowed") o.Windowed = true;
                else if (a == "--dir" && i + 1 < args.Length) o.Dir = args[++i];
                else if (a == "--screen" && i + 1 < args.Length && int.TryParse(args[++i], out int n)) o.ScreenNumber = n;
            }
            if (string.IsNullOrWhiteSpace(o.Dir))
                o.Dir = o.IsKiosk ? @"C:\liftpic\kiosk-data" : o.IsStation ? @"C:\liftpic\station" : @"C:\liftpic\presentation";
            if (string.IsNullOrWhiteSpace(o.AppDir))
                o.AppDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "kiosk");
            return o;
        }
    }

    internal static class NativeMethods
    {
        [DllImport("user32.dll")] internal static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        [DllImport("user32.dll")] internal static extern bool SetProcessDPIAware();
        [DllImport("shcore.dll")] internal static extern int SetProcessDpiAwareness(int value);
    }

    internal static class Program
    {
        [STAThread]
        private static void Main(string[] args)
        {
            var options = Options.Parse(args);
            // Scharf auf Touch-Bildschirmen mit Skalierung (sonst zieht Windows das Bild unscharf hoch).
            try { if (NativeMethods.SetProcessDpiAwareness(2) != 0) NativeMethods.SetProcessDPIAware(); }
            catch { try { NativeMethods.SetProcessDPIAware(); } catch { } }
            // Je Ansicht nur ein Fenster: ein zweiter Start holt das vorhandene nach vorn.
            using (var mutex = new Mutex(true, @"Local\Liftpictures.Display." + options.Mode, out bool first))
            {
                if (!first)
                {
                    BringToFront(options.Title);
                    return;
                }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new DisplayForm(options));
                GC.KeepAlive(mutex);
            }
        }

        private static void BringToFront(string title)
        {
            var me = Process.GetCurrentProcess();
            foreach (var p in Process.GetProcessesByName(me.ProcessName))
            {
                if (p.Id == me.Id || p.MainWindowHandle == IntPtr.Zero || p.MainWindowTitle != title) continue;
                NativeMethods.ShowWindow(p.MainWindowHandle, 9); // SW_RESTORE
                NativeMethods.SetForegroundWindow(p.MainWindowHandle);
            }
        }
    }

    internal sealed class DisplayForm : Form
    {
        private readonly Options _o;
        private readonly WebView2 _web = new WebView2();
        private readonly System.Windows.Forms.Timer _retry = new System.Windows.Forms.Timer { Interval = 5000 };
        private readonly string _page;
        private bool _waiting;
        private Rectangle _windowedBounds;
        private Kiosk.KioskHost _kiosk;
        private bool _allowClose;

        public DisplayForm(Options o)
        {
            _o = o;
            _page = Path.Combine(o.Dir, "index.html");
            Text = o.Title;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { /* Standardsymbol */ }
            BackColor = o.IsKiosk ? Color.FromArgb(0x06, 0x18, 0x2B) : o.IsStation ? Color.FromArgb(245, 247, 250) : Color.FromArgb(0x39, 0x77, 0xBD);
            StartPosition = FormStartPosition.Manual;

            var screen = PickScreen();
            var area = screen.WorkingArea;
            _windowedBounds = new Rectangle(area.X + 60, area.Y + 60,
                Math.Max(800, Math.Min(1400, area.Width - 120)), Math.Max(600, Math.Min(900, area.Height - 120)));
            if (o.Windowed)
            {
                FormBorderStyle = FormBorderStyle.Sizable;
                Bounds = _windowedBounds;
            }
            else
            {
                FormBorderStyle = FormBorderStyle.None;
                Bounds = screen.Bounds;
            }

            _web.Dock = DockStyle.Fill;
            _web.DefaultBackgroundColor = BackColor;
            Controls.Add(_web);

            _retry.Tick += (s, e) => Navigate();
            Load += async (s, e) => await StartAsync();
            KeyPreview = true;
            KeyDown += (s, e) => { if (e.KeyCode == Keys.F11) ToggleFullscreen(); };
            // Das Verkaufsprogramm schliesst nur ueber das Personal-Menue (PIN) - nicht aus Versehen.
            FormClosing += (s, e) =>
            {
                if (_o.IsKiosk && !_allowClose && e.CloseReason == CloseReason.UserClosing) e.Cancel = true;
            };
            FormClosed += (s, e) => _kiosk?.Dispose();
        }

        /// <summary>Vom Personal-Menue (PIN) aus: Programm wirklich beenden.</summary>
        internal void CloseForGood()
        {
            _allowClose = true;
            Close();
        }

        private Screen PickScreen()
        {
            var all = Screen.AllScreens;
            if (_o.ScreenNumber >= 1 && _o.ScreenNumber <= all.Length) return all[_o.ScreenNumber - 1];
            if (!_o.IsStation && !_o.IsKiosk)
            {
                var second = all.FirstOrDefault(x => !x.Primary);
                if (second != null) return second;
            }
            return Screen.PrimaryScreen;
        }

        private void ToggleFullscreen()
        {
            if (FormBorderStyle == FormBorderStyle.None)
            {
                FormBorderStyle = FormBorderStyle.Sizable;
                Bounds = _windowedBounds;
            }
            else
            {
                _windowedBounds = Bounds;
                FormBorderStyle = FormBorderStyle.None;
                Bounds = Screen.FromControl(this).Bounds;
            }
        }

        private async Task StartAsync()
        {
            try
            {
                string data = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Liftpictures", "WebView2-" + _o.Mode);
                var env = await CoreWebView2Environment.CreateAsync(null, data);
                await _web.EnsureCoreWebView2Async(env);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this,
                    "Microsoft Edge WebView2 could not be started.\n\n" + ex.Message,
                    Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                Close();
                return;
            }

            var core = _web.CoreWebView2;
            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.AreDevToolsEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.IsZoomControlEnabled = false;
            core.Settings.AreBrowserAcceleratorKeysEnabled = false;

            if (_o.IsKiosk)
            {
                // Verkaufsprogramm: eigene App, eigene Geraete-Bruecke, eigene Navigation.
                try
                {
                    _kiosk = new Kiosk.KioskHost(this, core, _o.AppDir, _o.Dir);
                    _kiosk.Start();
                }
                catch (Exception ex)
                {
                    core.NavigateToString(KioskErrorHtml(ex.Message));
                }
                core.ProcessFailed += (s, e) =>
                {
                    if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited) Application.Restart();
                    else _kiosk?.Reload();
                };
                return;
            }

            // "Hide screen" in der Station schliesst das Fenster.
            core.WindowCloseRequested += (s, e) => Close();
            core.WebMessageReceived += (s, e) =>
            {
                string msg = null;
                try { msg = e.TryGetWebMessageAsString(); } catch { }
                if (msg == "close") Close();
            };
            // Keine weiteren Fenster oder Links nach draussen.
            core.NewWindowRequested += (s, e) => { e.Handled = true; };
            core.NavigationStarting += (s, e) =>
            {
                if (!e.Uri.StartsWith("file:", StringComparison.OrdinalIgnoreCase) &&
                    !e.Uri.StartsWith("data:", StringComparison.OrdinalIgnoreCase) &&
                    !e.Uri.StartsWith("about:", StringComparison.OrdinalIgnoreCase))
                    e.Cancel = true;
            };
            core.NavigationCompleted += (s, e) =>
            {
                if (!e.IsSuccess || _waiting) _retry.Start(); else _retry.Stop();
            };
            // Stuerzt die Anzeige ab, startet das Programm sich selbst neu.
            core.ProcessFailed += (s, e) =>
            {
                if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited)
                {
                    Application.Restart();
                    return;
                }
                _retry.Start();
            };
            Navigate();
        }

        private void Navigate()
        {
            var core = _web.CoreWebView2;
            if (core == null) return;
            if (File.Exists(_page))
            {
                _waiting = false;
                core.Navigate(new Uri(_page).AbsoluteUri);
            }
            else
            {
                _waiting = true;
                core.NavigateToString(WaitingHtml());
                _retry.Start();
            }
        }

        private static string KioskErrorHtml(string message)
        {
            return "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head>" +
                   "<body style=\"margin:0;height:100vh;display:flex;align-items:center;justify-content:center;" +
                   "background:#06182b;color:#fff;font:26px 'Segoe UI',Arial,sans-serif\">" +
                   "<div style=\"text-align:center\">Liftpictures Kiosk<br><span style=\"font-size:17px;opacity:.75\">" +
                   System.Net.WebUtility.HtmlEncode(message) + "</span></div></body></html>";
        }

        private string WaitingHtml()
        {
            string bg = _o.IsStation ? "#f5f7fa" : "#3977BD";
            string fg = _o.IsStation ? "#1f2933" : "#ffffff";
            return "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head>" +
                   "<body style=\"margin:0;height:100vh;display:flex;align-items:center;justify-content:center;" +
                   "background:" + bg + ";color:" + fg + ";font:26px 'Segoe UI',Arial,sans-serif\">" +
                   "<div style=\"text-align:center\">" + _o.Title +
                   "<br><span style=\"font-size:17px;opacity:.75\">Waiting for Liftpictures Sync (" +
                   System.Net.WebUtility.HtmlEncode(_o.Dir) + ")</span></div></body></html>";
        }
    }
}
