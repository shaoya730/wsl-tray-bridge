using System;
using System.Collections.Generic;
using System.Diagnostics;

internal static class ShutdownTests
{
    private static void Check(bool value, string message)
    {
        if (!value) throw new Exception(message);
    }

    private static void Expect<T>(Action action) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new Exception("Expected " + typeof(T).Name);
    }

    private static void Main()
    {
        try { Run(); }
        catch (Exception error) { Console.Error.WriteLine(error.Message); Environment.ExitCode = 1; }
    }

    private static void Run()
    {
        var steps = new List<string>();
        WslShutdown.TerminateAfterExit("Ubuntu-24.04", delegate { steps.Add("exit"); return true; },
            delegate(ProcessStartInfo command)
            {
                steps.Add("terminate");
                Check(command.Arguments == "--terminate \"Ubuntu-24.04\"", "Must target only the configured distro");
                Check(System.IO.Path.IsPathRooted(command.FileName) && command.FileName.EndsWith("wsl.exe"), "Must use system WSL executable");
                Check(!command.UseShellExecute && command.CreateNoWindow, "Termination must run without a shell or console");
                Check(command.RedirectStandardOutput && command.RedirectStandardError, "Must capture command failures");
                return 0;
            });
        Check(String.Join(",", steps) == "exit,terminate", "Must wait for tray cleanup before terminating WSL");

        bool invoked = false;
        Func<ProcessStartInfo, int> record = delegate { invoked = true; return 0; };
        Expect<TimeoutException>(delegate { WslShutdown.TerminateAfterExit("Ubuntu", () => false, record); });
        Check(!invoked, "A bridge exit timeout must leave WSL running");

        foreach (string invalid in new[] { null, "", "--shutdown", "Ubuntu; echo bad", "Ubuntu\" --shutdown", "Ubuntu\n" })
        {
            invoked = false;
            Expect<ArgumentException>(delegate { WslShutdown.TerminateAfterExit(invalid, () => true, record); });
            Check(!invoked, "Invalid configuration must never start a command");
        }
        Expect<InvalidOperationException>(delegate { WslShutdown.TerminateAfterExit("Ubuntu", () => true, command => 1); });
        Console.WriteLine("PASS: scoped command, tray exit ordering, timeout cancellation, invalid names and command failures. No WSL instance was stopped.");
    }
}
