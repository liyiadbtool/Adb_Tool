
using System;
using System.Diagnostics;
using System.Threading;
class P {
    static void Main(string[] a) {
        bool cnw = a.Length > 0 && a[0] == "1";
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = Environment.GetEnvironmentVariable("COMSPEC");
        if (string.IsNullOrEmpty(psi.FileName)) psi.FileName = "cmd.exe";
        psi.Arguments = "/c ping -n 4 127.0.0.1 > nul";
        psi.UseShellExecute = false;
        psi.CreateNoWindow = cnw;
        using (Process p = Process.Start(psi)) { p.WaitForExit(); }
        Thread.Sleep(2500);
    }
}
