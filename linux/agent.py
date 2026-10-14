#!/usr/bin/env python3
"""D-Bus StatusNotifier host, transported over private wsl.exe stdio."""
import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk, GdkPixbuf

WATCH = 'org.kde.StatusNotifierWatcher'
ITEM_INTERFACES = ('org.kde.StatusNotifierItem', 'org.freedesktop.StatusNotifierItem')
PROPS = 'org.freedesktop.DBus.Properties'
MENU = 'com.canonical.dbusmenu'
DBusGMainLoop(set_as_default=True)
Gtk.init_check(None)
bus = dbus.SessionBus()
loop = GLib.MainLoop()
items = {}
proxy_process = None
owner_name = None
watcher = None

def emit(event, **values):
    try:
        print(json.dumps(dict(event=event, **values), ensure_ascii=True, separators=(',', ':')), flush=True)
    except (BrokenPipeError, OSError):
        loop.quit()

def plain(value):
    if isinstance(value, (dbus.Array, dbus.Struct, tuple, list)):
        return [plain(x) for x in value]
    if isinstance(value, (dbus.Dictionary, dict)):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (dbus.Boolean, bool)):
        return bool(value)
    if isinstance(value, (dbus.String, dbus.ObjectPath, str)):
        return str(value)
    return int(value)

def png_icon(properties, attention=False):
    prefix = 'AttentionIcon' if attention else 'Icon'
    pixmaps = properties.get(prefix + 'Pixmap', [])
    good = [p for p in pixmaps if 0 < int(p[0]) <= 512 and 0 < int(p[1]) <= 512 and len(p[2]) == int(p[0]) * int(p[1]) * 4]
    pixbuf = None
    if good:
        width, height, data = min(good, key=lambda p: abs(int(p[0]) - 64))
        width, height, data = int(width), int(height), bytes(data)
        # SNI pixmaps use network-order ARGB; GdkPixbuf takes RGBA.
        rgba = bytearray(len(data))
        rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4] = data[1::4], data[2::4], data[3::4], data[0::4]
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(rgba)), GdkPixbuf.Colorspace.RGB, True, 8, width, height, width * 4)
    if pixbuf is None:
        name = str(properties.get(prefix + 'Name', ''))
        if name:
            try:
                if os.path.isabs(name) and os.path.isfile(name):
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(name, 64, 64, True)
                else:
                    theme = Gtk.IconTheme.new()
                    custom = str(properties.get('IconThemePath', ''))
                    if custom:
                        theme.prepend_search_path(custom)
                    pixbuf = theme.load_icon(name, 64, Gtk.IconLookupFlags.FORCE_SIZE)
            except GLib.Error:
                pass
    if pixbuf is None:
        return ''
    ok, data = pixbuf.save_to_bufferv('png', [], [])
    return base64.b64encode(data).decode('ascii') if ok else ''

class Item:
    def __init__(self, service, path):
        self.service, self.path = service, path
        self.owner = service if service.startswith(':') else str(bus.get_name_owner(service))
        self.key = self.owner + path
        self.obj = bus.get_object(service, path, introspect=False)
        self.interface = ITEM_INTERFACES[0]
        self.props = {}
        self.pending = False
        self.signals = []
        self.menu_signal = None
        self.menu_path = ''
        self.last_payload = None
        for interface in ITEM_INTERFACES:
            self.signals.append(bus.add_signal_receiver(self.changed, dbus_interface=interface, path=path, bus_name=service))
        self.signals.append(bus.add_signal_receiver(self.changed, dbus_interface=PROPS, signal_name='PropertiesChanged', path=path, bus_name=service))

    def changed(self, *args):
        if not self.pending:
            self.pending = True
            GLib.timeout_add(100, self.refresh)

    def refresh(self):
        self.pending = False
        if self.key not in items:
            return False
        for interface in ITEM_INTERFACES:
            try:
                self.props = dict(dbus.Interface(self.obj, PROPS).GetAll(interface, timeout=2))
                if self.props:
                    self.interface = interface
                    break
            except dbus.DBusException:
                continue
        if not self.props:
            return False
        tip = self.props.get('ToolTip', [])
        tip_title = str(tip[2]) if len(tip) > 2 else ''
        tip_text = str(tip[3]) if len(tip) > 3 else ''
        title = str(self.props.get('Title', '') or self.props.get('Id', '') or tip_title or self.service)
        menu = str(self.props.get('Menu', ''))
        if menu and menu != '/' and menu != self.menu_path:
            if self.menu_signal:
                self.menu_signal.remove()
            self.menu_path = menu
            self.menu_signal = bus.add_signal_receiver(self.menu_changed, dbus_interface=MENU, bus_name=self.service, path=menu)
        status = str(self.props.get('Status', 'Active'))
        normal_icon = png_icon(self.props)
        attention_icon = png_icon(self.props, True) if status == 'NeedsAttention' else ''
        payload = dict(id=self.key, title=title, tooltip=tip_title + ('\n' + tip_text if tip_text else ''),
                       status=status, icon=attention_icon or normal_icon, normalIcon=normal_icon,
                       menu=bool(menu and menu != '/'), itemIsMenu=bool(self.props.get('ItemIsMenu', False)))
        if payload != self.last_payload:
            emit('item', **payload)
            self.last_payload = payload
        return False

    def menu_changed(self, *args):
        emit('menu_changed', id=self.key)

    def close(self):
        for match in self.signals:
            match.remove()
        if self.menu_signal:
            self.menu_signal.remove()

def register(service, sender=None):
    service = str(service)
    if service.startswith('/'):
        path, service = service, str(sender)
    elif '/' in service:
        service, tail = service.split('/', 1)
        path = '/' + tail
    else:
        path = '/StatusNotifierItem'
    try:
        item = Item(service, path)
        if item.key in items:
            item.close()
            return item.key
        items[item.key] = item
        GLib.idle_add(item.refresh)
        return item.key
    except (dbus.DBusException, ValueError) as exc:
        emit('warning', message='Unable to register tray item: ' + str(exc))
        return ''

def unregister(key):
    item = items.pop(key, None)
    if item:
        item.close()
        emit('remove', id=key)

class Watcher(dbus.service.Object):
    def __init__(self, name):
        super().__init__(name, '/StatusNotifierWatcher')

    @dbus.service.method(WATCH, in_signature='s', out_signature='', sender_keyword='sender')
    def RegisterStatusNotifierItem(self, service, sender=None):
        key = register(service, sender)
        if key:
            self.StatusNotifierItemRegistered(key)

    @dbus.service.method(WATCH, in_signature='s', out_signature='')
    def RegisterStatusNotifierHost(self, service):
        self.StatusNotifierHostRegistered()

    @dbus.service.method(PROPS, in_signature='ss', out_signature='v')
    def Get(self, interface, name):
        values = self.GetAll(interface)
        if name not in values:
            raise dbus.exceptions.DBusException('Unknown property', name='org.freedesktop.DBus.Error.UnknownProperty')
        return values[name]

    @dbus.service.method(PROPS, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface not in (WATCH, 'org.freedesktop.StatusNotifierWatcher'):
            return {}
        return {'RegisteredStatusNotifierItems': dbus.Array(list(items), signature='s'),
                'IsStatusNotifierHostRegistered': dbus.Boolean(True), 'ProtocolVersion': dbus.Int32(0)}

    @dbus.service.signal(WATCH, signature='s')
    def StatusNotifierItemRegistered(self, service): pass

    @dbus.service.signal(WATCH, signature='s')
    def StatusNotifierItemUnregistered(self, service): pass

    @dbus.service.signal(WATCH, signature='')
    def StatusNotifierHostRegistered(self): pass

def name_changed(name, old, new):
    if old and not new:
        for key, item in list(items.items()):
            if (str(name).startswith(':') and item.owner == str(old)) or item.service == str(name):
                unregister(key)
                if watcher:
                    watcher.StatusNotifierItemUnregistered(key)

def menu_node(node, depth=0):
    if depth > 12:
        return None
    ident, properties, children = node
    if properties.get('visible', True) is False or not bool(properties.get('visible', True)):
        return None
    result = dict(id=int(ident), label=str(properties.get('label', '')), enabled=bool(properties.get('enabled', True)),
                  separator=str(properties.get('type', '')) == 'separator',
                  toggle=str(properties.get('toggle-type', '')), checked=int(properties.get('toggle-state', 0)) == 1,
                  children=[])
    for child in list(children)[:150]:
        converted = menu_node(child, depth + 1)
        if converted:
            result['children'].append(converted)
    return result

def command(data):
    action = data.get('action')
    if action == 'quit':
        loop.quit()
        return
    if action == 'refresh':
        for item in list(items.values()):
            item.refresh()
        return
    item = items.get(data.get('id'))
    if not item:
        return
    request = data.get('request', 0)
    try:
        x, y = int(data.get('x', 0)), int(data.get('y', 0))
        if action == 'menu' and item.menu_path:
            interface = dbus.Interface(bus.get_object(item.service, item.menu_path, introspect=False), MENU)
            try:
                interface.AboutToShow(dbus.Int32(0), timeout=2)
            except dbus.DBusException:
                pass
            revision, layout = interface.GetLayout(dbus.Int32(0), dbus.Int32(-1), dbus.Array([], signature='s'), timeout=3)
            root = menu_node(layout)
            emit('menu', id=item.key, request=request, nodes=root['children'] if root else [])
        elif action == 'menu_event' and item.menu_path:
            interface = dbus.Interface(bus.get_object(item.service, item.menu_path, introspect=False), MENU)
            interface.Event(dbus.Int32(int(data['node'])), 'clicked', dbus.Int32(0, variant_level=1), dbus.UInt32(int(time.time())), timeout=3)
            emit('action_done', id=item.key, action=action, request=request)
        elif action in ('activate', 'secondary', 'context', 'scroll'):
            interface = dbus.Interface(item.obj, item.interface)
            if action == 'scroll':
                interface.Scroll(dbus.Int32(int(data.get('delta', 0))), str(data.get('orientation', 'vertical')), timeout=2)
            else:
                method = {'activate': 'Activate', 'secondary': 'SecondaryActivate', 'context': 'ContextMenu'}[action]
                getattr(interface, method)(dbus.Int32(x), dbus.Int32(y), timeout=2)
            emit('action_done', id=item.key, action=action, request=request)
    except (dbus.DBusException, ValueError, KeyError) as exc:
        emit('action_error', id=item.key, action=action, request=request, message=str(exc))
        if action == 'menu':
            emit('menu', id=item.key, request=request, nodes=[])

input_buffer = b''

def input_ready(source, condition):
    global input_buffer
    chunk = os.read(0, 65536)
    if not chunk:
        loop.quit()
        return False
    input_buffer += chunk
    while b'\n' in input_buffer:
        line, input_buffer = input_buffer.split(b'\n', 1)
        try:
            command(json.loads(line.decode('utf-8-sig')))
        except (ValueError, TypeError) as exc:
            emit('warning', message='Invalid bridge command: ' + str(exc))
    return True

def rescan():
    # Also discover items that existed before the watcher was started.
    for name in bus.list_names():
        if 'StatusNotifierItem' in name:
            register(name)
    for item in list(items.values()):
        item.refresh()
    return True

def main():
    global owner_name, watcher, proxy_process
    if not bus.name_has_owner(WATCH):
        owner_name = dbus.service.BusName(WATCH, bus, do_not_queue=True)
        watcher = Watcher(owner_name)
        watcher.StatusNotifierHostRegistered()
    else:
        obj = bus.get_object(WATCH, '/StatusNotifierWatcher')
        existing = dbus.Interface(obj, PROPS).Get(WATCH, 'RegisteredStatusNotifierItems')
        for name in existing:
            register(name)
        dbus.Interface(obj, WATCH).RegisterStatusNotifierHost(bus.get_unique_name())
        bus.add_signal_receiver(lambda name: register(name), dbus_interface=WATCH, signal_name='StatusNotifierItemRegistered')
        bus.add_signal_receiver(lambda key: unregister(str(key)), dbus_interface=WATCH, signal_name='StatusNotifierItemUnregistered')
    bus.add_signal_receiver(name_changed, dbus_interface='org.freedesktop.DBus', signal_name='NameOwnerChanged')
    legacy = Path(__file__).with_name('xembedsniproxy')
    if legacy.exists():
        env = os.environ.copy()
        env['QT_QPA_PLATFORM'] = 'xcb'
        env['QT_SCALE_FACTOR'] = '1'
        proxy_process = subprocess.Popen([str(legacy)], stdout=sys.stderr, stderr=sys.stderr, env=env)
    GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, input_ready)
    GLib.timeout_add_seconds(15, rescan)
    GLib.idle_add(rescan)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (loop.quit(), False)[1])
    emit('ready', owner=bool(watcher), legacy=bool(proxy_process), distro=os.environ.get('WSL_DISTRO_NAME', 'Ubuntu'))
    try:
        loop.run()
    finally:
        if proxy_process and proxy_process.poll() is None:
            proxy_process.terminate()
            try:
                proxy_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proxy_process.kill()

if __name__ == '__main__':
    main()
