import json
import os
from pathlib import Path
import sys
os.environ['GDK_BACKEND'] = 'x11'
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
name = dbus.service.BusName('org.kde.StatusNotifierItem.BridgeTest', bus)
log = Path(os.environ.get('WSL_TRAY_TEST_LOG', 'fixture-results.jsonl'))
log.write_text('')
def record(event):
    with log.open('a') as output:
        output.write(json.dumps({'event': event}) + '\n')

class TestItem(dbus.service.Object):
    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        data = bytes([255, 42, 160, 80]) * (32 * 32)
        return {'Id':'bridge-test', 'Title':'Bridge integration test', 'Status':'Active', 'Category':'ApplicationStatus',
                'IconPixmap':dbus.Array([dbus.Struct((32,32,dbus.ByteArray(data)),signature='iiay')],signature='(iiay)'),
                'Menu':dbus.ObjectPath('/BridgeTestMenu'), 'ItemIsMenu':False}

    @dbus.service.method('org.kde.StatusNotifierItem', in_signature='ii', out_signature='')
    def Activate(self, x, y): record('activate')

    @dbus.service.method('org.kde.StatusNotifierItem', in_signature='ii', out_signature='')
    def ContextMenu(self, x, y): record('context')

class TestMenu(dbus.service.Object):
    @dbus.service.method('com.canonical.dbusmenu', in_signature='i', out_signature='b')
    def AboutToShow(self, ident): return False

    @dbus.service.method('com.canonical.dbusmenu', in_signature='iias', out_signature='u(ia{sv}av)')
    def GetLayout(self, root, depth, props):
        def node(ident, values, children=(), variant=0):
            return dbus.Struct((ident, dbus.Dictionary(values,signature='sv'), dbus.Array(children,signature='v')),signature='ia{sv}av', variant_level=variant)
        children=[node(1,{'label':'Test action','enabled':dbus.Boolean(True)},variant=1),
                  node(2,{'label':'Checked option','toggle-type':'checkmark','toggle-state':dbus.Int32(1)},variant=1)]
        record('menu')
        return dbus.UInt32(1),node(0,{},children)

    @dbus.service.method('com.canonical.dbusmenu', in_signature='isvu', out_signature='')
    def Event(self, ident, event, data, timestamp): record('menu_click_' + str(ident))

item = TestItem(name, '/BridgeTest')
menu = TestMenu(name, '/BridgeTestMenu')
registered = False
def register():
    global registered
    if registered:
        return False
    try:
        watcher = dbus.Interface(bus.get_object('org.kde.StatusNotifierWatcher','/StatusNotifierWatcher'),'org.kde.StatusNotifierWatcher')
        watcher.RegisterStatusNotifierItem('/BridgeTest')
        registered = True
        record('registered')
        return False
    except dbus.DBusException:
        return True
Gtk.init([])
legacy = Gtk.StatusIcon.new_from_icon_name('utilities-terminal')
legacy.set_title('Bridge legacy X11 test')
legacy.set_tooltip_text('Bridge legacy X11 test')
legacy.set_visible(True)
legacy.connect('activate', lambda *args: record('legacy_activate'))
GLib.timeout_add(500, register)
GLib.timeout_add_seconds(55, lambda: (Gtk.main_quit(),False)[1])
Gtk.main()
