// Gesichtssuche mit FaceAiSharp - wie im alten Verkaufsprogramm (FaceRecognitionHelper):
//   FaceAiSharpClient.exe -d "<Ordner>" beobachtet einen Ordner und legt zu jedem Bild
//   <Ordner>\faces\<datei>_<Groesse>_<Aenderungszeit-Ticks>.xml an (Gesichter mit Lage und Merkmalsvektor).
//   Gesucht wird per Kosinus-Aehnlichkeit der Merkmale, ab 0,3 gilt es als Treffer.
// Ein Beobachter laeuft fuer den Fotoordner, ein zweiter fuer das Suchbild des Gastes
// (kiosk-data\face-query). Das Suchbild wird gleich nach der Suche geloescht - mitsamt Merkmalen.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Xml;

namespace Liftpictures.Display.Kiosk
{
    internal sealed class FaceSearch : IDisposable
    {
        private sealed class Face { public double Area; public float[] Vector; }

        private readonly Func<HostConfig> _cfg;
        private readonly List<Process> _watchers = new List<Process>();
        private readonly ConcurrentDictionary<string, List<Face>> _cache = new ConcurrentDictionary<string, List<Face>>();
        private readonly SemaphoreSlim _one = new SemaphoreSlim(1, 1);
        private string _queryDir;

        public FaceSearch(Func<HostConfig> cfg)
        {
            _cfg = cfg;
        }

        public bool Available { get; private set; }

        public void Start()
        {
            if (Available) return;
            var c = _cfg();
            if (!File.Exists(c.FaceClient)) { Log.Write("face: client missing " + c.FaceClient); return; }
            _queryDir = Path.Combine(c.DataDir, "face-query");
            try
            {
                Directory.CreateDirectory(_queryDir);
                foreach (var f in Directory.GetFiles(_queryDir, "*", SearchOption.AllDirectories)) TryDelete(f);
                // Wie das alte Programm: alte Beobachter beenden, dann eigene starten.
                foreach (var p in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(c.FaceClient)))
                {
                    try { p.Kill(); } catch { }
                }
                _watchers.Add(Watch(c.FaceClient, c.FacePhotoDir ?? c.PhotoDir));
                _watchers.Add(Watch(c.FaceClient, _queryDir));
                Available = true;
                Log.Write("face: watching " + (c.FacePhotoDir ?? c.PhotoDir));
            }
            catch (Exception ex) { Log.Write("face: " + ex.Message); }
        }

        private static Process Watch(string client, string dir)
        {
            var psi = new ProcessStartInfo(client, "-d \"" + dir.TrimEnd('\\') + "\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = Path.GetDirectoryName(client),
            };
            var p = Process.Start(psi);
            try { p.PriorityClass = ProcessPriorityClass.BelowNormal; } catch { }
            return p;
        }

        private static string TemplatePath(string image)
        {
            var fi = new FileInfo(image);
            return Path.Combine(fi.DirectoryName, "faces",
                fi.Name + "_" + fi.Length.ToString(CultureInfo.InvariantCulture) + "_" + fi.LastWriteTime.Ticks.ToString(CultureInfo.InvariantCulture) + ".xml");
        }

        private static double D(XmlNode n, string name)
        {
            var v = n.SelectSingleNode(name)?.InnerText;
            return double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out double d) ? d : 0;
        }

        /// <summary>Gesichter aus einer Merkmalsdatei (XmlSerializer von FacesDetected/FaceDetected).</summary>
        private static List<Face> Read(string template)
        {
            var faces = new List<Face>();
            var doc = new XmlDocument();
            doc.Load(template);
            foreach (XmlNode emb in doc.GetElementsByTagName("FaceEmbedding"))
            {
                var owner = emb.ParentNode;
                var values = new List<float>();
                if (emb.HasChildNodes && emb.FirstChild.NodeType == XmlNodeType.Element)
                {
                    foreach (XmlNode v in emb.ChildNodes)
                        if (float.TryParse(v.InnerText, NumberStyles.Float, CultureInfo.InvariantCulture, out float f)) values.Add(f);
                }
                else
                {
                    foreach (var part in emb.InnerText.Split(new[] { ' ', ',', ';', '\n', '\r', '\t' }, StringSplitOptions.RemoveEmptyEntries))
                        if (float.TryParse(part, NumberStyles.Float, CultureInfo.InvariantCulture, out float f)) values.Add(f);
                }
                if (values.Count < 16) continue;
                faces.Add(new Face { Area = D(owner, "FaceWidth") * D(owner, "FaceHeight"), Vector = values.ToArray() });
            }
            return faces;
        }

        private static double Cosine(float[] a, float[] b)
        {
            int n = Math.Min(a.Length, b.Length);
            double dot = 0, na = 0, nb = 0;
            for (int i = 0; i < n; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
            return na > 0 && nb > 0 ? dot / Math.Sqrt(na * nb) : 0;
        }

        private List<Face> Faces(string image)
        {
            string template;
            try { template = TemplatePath(image); } catch { return null; }
            if (_cache.TryGetValue(template, out var hit)) return hit;
            if (!File.Exists(template)) return null;
            try
            {
                var faces = Read(template);
                if (_cache.Count > 5000) _cache.Clear();
                _cache[template] = faces;
                return faces;
            }
            catch { return null; }
        }

        private static void TryDelete(string path)
        {
            try { if (File.Exists(path)) File.Delete(path); } catch { }
        }

        /// <summary>Fotos (Dateinamen) mit dem Gesicht vom Suchbild, beste zuerst.</summary>
        public async Task<string[]> SearchAsync(string imageDataUrl, string[] files)
        {
            if (!Available || string.IsNullOrEmpty(imageDataUrl) || files == null || files.Length == 0) return new string[0];
            await _one.WaitAsync().ConfigureAwait(false);
            string query = null, template = null;
            try
            {
                int comma = imageDataUrl.IndexOf(',');
                byte[] jpg = Convert.FromBase64String(comma >= 0 ? imageDataUrl.Substring(comma + 1) : imageDataUrl);
                query = Path.Combine(_queryDir, "q" + DateTime.Now.Ticks.ToString(CultureInfo.InvariantCulture) + ".jpg");
                File.WriteAllBytes(query, jpg);
                template = TemplatePath(query);

                List<Face> mine = null;
                var until = DateTime.UtcNow.AddSeconds(25);
                while (DateTime.UtcNow < until)
                {
                    if (File.Exists(template))
                    {
                        await Task.Delay(150).ConfigureAwait(false);
                        try { mine = Read(template); break; } catch { /* wird noch geschrieben */ }
                    }
                    await Task.Delay(250).ConfigureAwait(false);
                }
                var me = mine?.OrderByDescending(f => f.Area).FirstOrDefault();
                if (me == null) { Log.Write("face: no face in the query image"); return new string[0]; }

                var c = _cfg();
                string dir = c.FacePhotoDir ?? c.PhotoDir;
                var hits = new List<KeyValuePair<string, double>>();
                foreach (var file in files)
                {
                    if (!Media.SafeName(file)) continue;
                    var faces = Faces(Path.Combine(dir, file));
                    if (faces == null || faces.Count == 0) continue;
                    double best = faces.Max(f => Cosine(me.Vector, f.Vector));
                    if (best >= c.FaceThreshold) hits.Add(new KeyValuePair<string, double>(file, best));
                }
                Log.Write("face: " + hits.Count + " matches in " + files.Length + " photos");
                return hits.OrderByDescending(h => h.Value).Take(80).Select(h => h.Key).ToArray();
            }
            catch (Exception ex)
            {
                Log.Write("face search: " + ex.Message);
                return new string[0];
            }
            finally
            {
                // Datenschutz: Suchbild und Merkmale sofort wieder weg.
                if (template != null) TryDelete(template);
                if (query != null) TryDelete(query);
                _one.Release();
            }
        }

        public void Dispose()
        {
            foreach (var p in _watchers)
            {
                try { if (!p.HasExited) p.Kill(); } catch { }
                try { p.Dispose(); } catch { }
            }
            _watchers.Clear();
            Available = false;
        }
    }
}
