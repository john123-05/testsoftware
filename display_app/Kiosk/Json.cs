// Kleine JSON-Hilfen ueber JavaScriptSerializer (ist in .NET Framework 4.8 dabei).
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Web.Script.Serialization;

namespace Liftpictures.Display.Kiosk
{
    internal static class Json
    {
        private static JavaScriptSerializer Serializer()
        {
            return new JavaScriptSerializer { MaxJsonLength = int.MaxValue, RecursionLimit = 64 };
        }

        public static object Parse(string json)
        {
            if (string.IsNullOrWhiteSpace(json)) return null;
            try { return Serializer().DeserializeObject(json); }
            catch { return null; }
        }

        public static string Write(object value)
        {
            return Serializer().Serialize(value);
        }

        public static Dictionary<string, object> Obj(object o)
        {
            return o as Dictionary<string, object>;
        }

        public static object[] Arr(object o)
        {
            if (o is object[] a) return a;
            if (o is ArrayList l) return l.ToArray();
            return null;
        }

        public static object Get(object o, string key)
        {
            var d = Obj(o);
            return d != null && d.TryGetValue(key, out var v) ? v : null;
        }

        public static string Str(object o, string key, string fallback = null)
        {
            var v = Get(o, key);
            if (v == null) return fallback;
            var s = Convert.ToString(v, CultureInfo.InvariantCulture);
            return string.IsNullOrEmpty(s) ? fallback : s;
        }

        public static double Num(object o, string key, double fallback = 0)
        {
            return ToNum(Get(o, key), fallback);
        }

        public static double ToNum(object v, double fallback = 0)
        {
            if (v == null) return fallback;
            try { return Convert.ToDouble(v, CultureInfo.InvariantCulture); }
            catch { return fallback; }
        }

        public static int Int(object o, string key, int fallback = 0)
        {
            return (int)Math.Round(Num(o, key, fallback));
        }

        public static bool Bool(object o, string key, bool fallback = false)
        {
            var v = Get(o, key);
            return v is bool b ? b : fallback;
        }
    }
}
