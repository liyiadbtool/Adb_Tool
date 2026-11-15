using System;
using System.Threading;

class P
{
    static int Main(string[] a)
    {
        // 模拟"唤醒后 adb 卡在失效 USB 句柄上"：无论参数是什么都挂住
        Thread.Sleep(120000);
        Console.WriteLine("List of devices attached");
        return 0;
    }
}
