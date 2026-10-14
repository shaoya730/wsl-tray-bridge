using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal sealed class TrayEntry : IDisposable
{
    public readonly NotifyIcon Tray = new NotifyIcon();
    public Icon Icon;
    public string Title = "Linux application", Status = "Active";
    public string ImageData = "";
    public bool HasMenu, ItemIsMenu;
    public ContextMenuStrip Menu;
    public void Dispose()
    {
        Tray.Visible = false;
        Tray.Dispose();
        if (Menu != null) Menu.Dispose();
        if (Icon != null) Icon.Dispose();
    }
}

internal sealed class Bridge : ApplicationContext
{
    [DllImport("user32.dll")] private static extern bool DestroyIcon(IntPtr icon);
    [DllImport("user32.dll")] private static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    private readonly Form dispatch = new Form();
    private readonly NotifyIcon manager = new NotifyIcon();
    private readonly Dictionary<string, TrayEntry> entries = new Dictionary<string, TrayEntry>();
    private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 8 * 1024 * 1024 };
    private readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    private readonly ToolStripMenuItem status = new ToolStripMenuItem("Waiting for Ubuntu");
    private readonly string directory;
    private readonly string logFile;
    private readonly string distro;
    private bool closing, connected;
    private long sequence;
    private string pendingId;
    private long pendingRequest;
    private Point pendingPoint;
    private readonly bool selfTest;
    private StreamWriter transport;
    private bool testIcon, testMenu, testAction, testActivate;
    private DateTime deadline;

    public Bridge(string[] args)
    {
        selfTest = Array.IndexOf(args, "--self-test") >= 0;
        directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WSLTrayBridge");
        Directory.CreateDirectory(directory);
        logFile = Path.Combine(directory, selfTest ? "self-test.log" : "bridge.log");
        distro = "Ubuntu";
        string configuration = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "config.json");
        if (File.Exists(configuration))
        {
            Dictionary<string, object> options = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(configuration));
            distro = Text(options, "distro", distro);
        }
        try { SetThreadDpiAwarenessContext(new IntPtr(-4)); } catch (EntryPointNotFoundException) { }
        dispatch.ShowInTaskbar = false;
        dispatch.FormBorderStyle = FormBorderStyle.FixedToolWindow;
        IntPtr unused = dispatch.Handle;
        ContextMenuStrip controls = new ContextMenuStrip();
        status.Enabled = false;
        controls.Items.Add(status);
        controls.Items.Add("Refresh Linux icons", null, delegate { Send(new Dictionary<string, object> { { "action", "refresh" } }); });
        controls.Items.Add("Open logs", null, delegate { Process.Start("explorer.exe", directory); });
        controls.Items.Add(new ToolStripSeparator());
        controls.Items.Add("Exit bridge (keep Linux apps running)", null, delegate { ExitThread(); });
        manager.Icon = SystemIcons.Application;
        manager.Text = "WSL Tray Bridge";
        manager.ContextMenuStrip = controls;
        manager.Visible = true;
        manager.DoubleClick += delegate { Process.Start("explorer.exe", directory); };
        timer.Interval = 5000;
        timer.Tick += delegate
        {
            if (selfTest && ((testIcon && testMenu && testAction && testActivate) || DateTime.UtcNow > deadline)) FinishTest();
        };
        deadline = DateTime.UtcNow.AddSeconds(90);
        timer.Start();
        Log("Bridge started; mode=Linux-managed");
        WriteState();
        ReadLinuxTransport();
    }

    private void ReadLinuxTransport()
    {
        transport = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false));
        transport.AutoFlush = true;
        ThreadPool.QueueUserWorkItem(delegate
        {
            try
            {
                using (StreamReader input = new StreamReader(Console.OpenStandardInput(), Encoding.UTF8))
                {
                    string line;
                    while ((line = input.ReadLine()) != null)
                    {
                        string captured = line;
                        OnUI(delegate { Receive(captured); });
                    }
                }
            }
            catch (IOException error) { Log("Linux transport closed: " + error.Message); }
            finally
            {
                OnUI(delegate { Log("Linux service stopped; exiting Windows tray"); ExitThread(); });
            }
        });
    }

    private void OnUI(Action action)
    {
        if (closing || dispatch.IsDisposed) return;
        try { dispatch.BeginInvoke(action); } catch (InvalidOperationException) { }
    }

    private void Receive(string line)
    {
        try
        {
            Dictionary<string, object> data = json.Deserialize<Dictionary<string, object>>(line);
            string kind = Text(data, "event", "");
            if (kind == "ready")
            {
                connected = true;
                status.Text = "Connected to " + distro;
                Log("Linux ready; legacy=" + Text(data, "legacy", "false"));
            }
            else if (kind == "item") UpdateItem(data);
            else if (kind == "remove") Remove(Text(data, "id", ""));
            else if (kind == "menu") ShowMenu(data);
            else if (kind == "menu_changed")
            {
                // Refresh on next opening; a live update must not execute menu commands.
            }
            else if (kind == "action_done" || kind == "action_error")
            {
                string action = Text(data, "action", "");
                Log(kind + ": " + action + " " + Text(data, "message", ""));
                if (selfTest && kind == "action_done" && Text(data, "id", "").IndexOf("/BridgeTest") >= 0)
                {
                    if (action == "menu_event") testAction = true;
                    if (action == "activate") testActivate = true;
                }
            }
            else if (kind == "warning") Log(Text(data, "message", ""));
            WriteState();
        }
        catch (Exception error) { Log("Receive: " + error); }
    }

    private static Icon DecodeIcon(string encoded)
    {
        if (String.IsNullOrEmpty(encoded)) return (Icon)SystemIcons.Application.Clone();
        using (MemoryStream input = new MemoryStream(Convert.FromBase64String(encoded)))
        using (Bitmap bitmap = new Bitmap(input))
        {
            IntPtr raw = bitmap.GetHicon();
            try { using (Icon borrowed = Icon.FromHandle(raw)) return (Icon)borrowed.Clone(); }
            finally { DestroyIcon(raw); }
        }
    }

    private void UpdateItem(Dictionary<string, object> data)
    {
        string id = Text(data, "id", "");
        if (id.Length == 0) return;
        TrayEntry entry;
        bool added = !entries.TryGetValue(id, out entry);
        if (added)
        {
            entry = new TrayEntry();
            entries.Add(id, entry);
            TrayEntry captured = entry;
            entry.Tray.MouseUp += delegate(object sender, MouseEventArgs e)
            {
                if (e.Button == MouseButtons.Right || (e.Button == MouseButtons.Left && captured.ItemIsMenu)) RequestMenu(id);
                else if (e.Button == MouseButtons.Left) ItemAction(id, "activate");
                else if (e.Button == MouseButtons.Middle) ItemAction(id, "secondary");
            };
        }
        entry.Title = Text(data, "title", "Linux application");
        entry.Status = Text(data, "status", "Active");
        entry.HasMenu = Flag(data, "menu", false);
        entry.ItemIsMenu = Flag(data, "itemIsMenu", false);
        string image = Text(data, "icon", "");
        if (entry.Icon == null || image != entry.ImageData)
        {
            Icon previous = entry.Icon;
            entry.Icon = DecodeIcon(image);
            entry.Tray.Icon = entry.Icon;
            entry.ImageData = image;
            if (previous != null) previous.Dispose();
        }
        string tooltip = Text(data, "tooltip", entry.Title);
        if (String.IsNullOrWhiteSpace(tooltip)) tooltip = entry.Title;
        tooltip = Regex.Replace(tooltip, "<[^>]+>", "");
        entry.Tray.Text = tooltip.Substring(0, Math.Min(63, tooltip.Length));
        // Windows itself lets users hide icons; show Passive items too so they remain reachable.
        entry.Tray.Visible = true;
        if (added) Log("Icon added: " + entry.Title + " " + id);
        status.Text = "Connected: " + entries.Count + " Linux icons";
        if (selfTest && entry.Title == "Bridge integration test" && !testIcon)
        {
            System.Reflection.FieldInfo field = typeof(NotifyIcon).GetField("added", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
            testIcon = field != null && (bool)field.GetValue(entry.Tray);
            Log("Self-test Shell_NotifyIcon accepted=" + testIcon);
            ItemAction(id, "activate");
            RequestMenu(id);
        }
    }

    private void ItemAction(string id, string action)
    {
        Point point = Cursor.Position;
        Send(new Dictionary<string, object> { { "action", action }, { "id", id }, { "x", point.X }, { "y", point.Y }, { "request", ++sequence } });
    }

    private void RequestMenu(string id)
    {
        TrayEntry entry;
        if (!entries.TryGetValue(id, out entry)) return;
        pendingId = id; pendingPoint = Cursor.Position; pendingRequest = ++sequence;
        if (entry.HasMenu)
            Send(new Dictionary<string, object> { { "action", "menu" }, { "id", id }, { "request", pendingRequest } });
        else
        {
            // XEmbed proxies often expose only ContextMenu, rendered as a WSLg popup.
            ItemAction(id, "context");
        }
    }

    private void ShowMenu(Dictionary<string, object> data)
    {
        string id = Text(data, "id", "");
        if (id != pendingId || Convert.ToInt64(data["request"]) != pendingRequest) return;
        TrayEntry entry;
        if (!entries.TryGetValue(id, out entry)) return;
        if (entry.Menu != null) { entry.Menu.Close(); entry.Menu.Dispose(); }
        ContextMenuStrip menu = new ContextMenuStrip();
        BuildMenu(menu.Items, data["nodes"] as IEnumerable, id, 0);
        if (menu.Items.Count == 0)
        {
            menu.Items.Add(entry.Title, null, delegate { ItemAction(id, "activate"); });
            menu.Items.Add("Open Linux context menu", null, delegate { ItemAction(id, "context"); });
        }
        entry.Menu = menu;
        if (selfTest && entry.Title == "Bridge integration test")
        {
            testMenu = menu.Items.Count >= 2 && menu.Items[0].Text == "Test action";
            if (testMenu) menu.Items[0].PerformClick();
            Log("Self-test native menu=" + testMenu);
        }
        else menu.Show(pendingPoint);
    }

    private void BuildMenu(ToolStripItemCollection target, IEnumerable nodes, string itemId, int depth)
    {
        if (nodes == null || depth > 12) return;
        foreach (object raw in nodes)
        {
            Dictionary<string, object> node = raw as Dictionary<string, object>;
            if (node == null) continue;
            if (Flag(node, "separator", false)) { target.Add(new ToolStripSeparator()); continue; }
            ToolStripMenuItem menu = new ToolStripMenuItem(Text(node, "label", "").Replace("_", "&"));
            menu.Enabled = Flag(node, "enabled", true);
            menu.Checked = Flag(node, "checked", false);
            ICollection children = node.ContainsKey("children") ? node["children"] as ICollection : null;
            if (children != null && children.Count > 0) BuildMenu(menu.DropDownItems, children, itemId, depth + 1);
            else
            {
                int nodeId = Convert.ToInt32(node["id"]);
                menu.Click += delegate { Send(new Dictionary<string, object> { { "action", "menu_event" }, { "id", itemId }, { "node", nodeId }, { "request", ++sequence } }); };
            }
            target.Add(menu);
        }
    }

    private void Send(Dictionary<string, object> value)
    {
        try
        {
            transport.WriteLine(json.Serialize(value));
        }
        catch (Exception error) { Log("Send: " + error.Message); }
    }

    private void Remove(string id)
    {
        TrayEntry entry;
        if (entries.TryGetValue(id, out entry))
        {
            entry.Dispose(); entries.Remove(id); Log("Icon removed: " + id);
        }
    }
    private void ClearEntries()
    {
        foreach (TrayEntry entry in entries.Values) entry.Dispose();
        entries.Clear();
    }
    private void WriteState()
    {
        try
        {
            List<object> icons = new List<object>();
            foreach (KeyValuePair<string, TrayEntry> pair in entries)
                icons.Add(new { id = pair.Key, title = pair.Value.Title, menu = pair.Value.HasMenu, status = pair.Value.Status });
            string path = Path.Combine(directory, selfTest ? "self-test-state.json" : "state.json");
            File.WriteAllText(path, json.Serialize(new { connected = connected, pid = Process.GetCurrentProcess().Id, icons = icons, utc = DateTime.UtcNow.ToString("o") }), Encoding.UTF8);
        }
        catch (Exception error) { Log("State: " + error.Message); }
    }
    private void FinishTest()
    {
        bool passed = testIcon && testMenu && testAction && testActivate;
        File.WriteAllText(Path.Combine(directory, "self-test-result.json"), json.Serialize(new { passed = passed, shellNotifyIcon = testIcon, nativeMenu = testMenu, menuCallback = testAction, activateCallback = testActivate }));
        Environment.ExitCode = passed ? 0 : 1;
        ExitThread();
    }
    private void Log(string value)
    {
        try { lock (logFile) File.AppendAllText(logFile, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + value + Environment.NewLine, Encoding.UTF8); }
        catch (IOException) { }
    }
    protected override void ExitThreadCore()
    {
        if (closing) return;
        closing = true;
        timer.Stop();
        if (transport != null)
        {
            try { transport.WriteLine("{\"action\":\"quit\"}"); transport.Dispose(); } catch (IOException) { }
        }
        connected = false;
        ClearEntries(); WriteState(); manager.Visible = false; manager.Dispose();
        dispatch.Dispose(); timer.Dispose(); Log("Bridge stopped");
        base.ExitThreadCore();
    }
    private static string Text(Dictionary<string, object> data, string key, string fallback)
    {
        object value; return data.TryGetValue(key, out value) && value != null ? Convert.ToString(value) : fallback;
    }
    private static bool Flag(Dictionary<string, object> data, string key, bool fallback)
    {
        object value; return data.TryGetValue(key, out value) && value != null ? Convert.ToBoolean(value) : fallback;
    }
    private static string Quote(string value) { return "\"" + value.Replace("\"", "\\\"") + "\""; }
}

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        if (Array.IndexOf(args, "--stdio") < 0)
        {
            // A manual launch starts the Linux service and returns; there is no Windows watcher.
            string target = "Ubuntu";
            string configPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "config.json");
            if (File.Exists(configPath))
            {
                var config = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(configPath));
                if (config.ContainsKey("distro")) target = Convert.ToString(config["distro"]);
            }
            if (!Regex.IsMatch(target, @"^[A-Za-z0-9_.-]+$")) throw new ArgumentException("Unsupported distro name");
            ProcessStartInfo start = new ProcessStartInfo("wsl.exe", "-d " + target + " --exec systemctl --user start wsl-tray-bridge.service");
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            using (Process launcher = Process.Start(start)) launcher.WaitForExit(15000);
            return;
        }
        bool created;
        using (Mutex mutex = new Mutex(true, "Local\\WSLTrayBridge", out created))
        {
            if (!created) return;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new Bridge(args));
        }
    }
}
