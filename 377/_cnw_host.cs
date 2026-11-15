
using System;
using System.Diagnostics;
using System.Threading;
class H {
    static void Main(string[] a) {
        bool cnw = a.Length > 0 && a[0] == "1";
        string child = a.Length > 1 ? a[1] : "child.exe";
        string outp  = a.Length > 2 ? a[2] : "out.txt";
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = child;
        psi.Arguments = "\"" + outp + "\"";
        psi.UseShellExecute = false;
        psi.CreateNoWindow = cnw;
        using (Process p = Process.Start(psi)) { p.WaitForExit(); }
        Thread.Sleep(300);
    }
}
