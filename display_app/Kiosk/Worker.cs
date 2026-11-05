// Eigene Arbeits-Threads: Bilder (WPF-Bildverarbeitung braucht STA), Druck, Muenzgeraet.
// Je Thread laeuft eine Aufgabe nach der anderen - Geraetetreiber sind selten threadsicher.
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Liftpictures.Display.Kiosk
{
    internal sealed class Worker : IDisposable
    {
        private readonly BlockingCollection<Action> _queue = new BlockingCollection<Action>();
        private readonly Thread _thread;

        public Worker(string name, bool sta, ThreadPriority priority = ThreadPriority.Normal)
        {
            _thread = new Thread(Run) { IsBackground = true, Name = name, Priority = priority };
            if (sta) _thread.SetApartmentState(ApartmentState.STA);
            _thread.Start();
        }

        public int Pending => _queue.Count;

        private void Run()
        {
            foreach (var job in _queue.GetConsumingEnumerable())
            {
                try { job(); }
                catch (Exception ex) { Log.Write("worker " + _thread.Name + ": " + ex.Message); }
            }
        }

        public void Post(Action job)
        {
            if (!_queue.IsAddingCompleted) _queue.Add(job);
        }

        public Task<T> Run<T>(Func<T> job)
        {
            var tcs = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
            Post(() =>
            {
                try { tcs.SetResult(job()); }
                catch (Exception ex) { tcs.SetException(ex); }
            });
            return tcs.Task;
        }

        public void Dispose()
        {
            _queue.CompleteAdding();
        }
    }

    /// <summary>Protokoll unter kiosk-data\logs\display-JJJJMMTT.log (liest der Agent mit).</summary>
    internal static class Log
    {
        private static readonly object Lock = new object();
        public static string Dir;

        public static void Write(string message)
        {
            try
            {
                if (string.IsNullOrEmpty(Dir)) return;
                lock (Lock)
                {
                    Directory.CreateDirectory(Dir);
                    string file = Path.Combine(Dir, "display-" + DateTime.Now.ToString("yyyyMMdd") + ".log");
                    File.AppendAllText(file, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + message + Environment.NewLine, Encoding.UTF8);
                }
            }
            catch { /* Protokoll darf nie stoeren */ }
        }
    }
}
