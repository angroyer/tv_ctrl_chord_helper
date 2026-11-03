#!/usr/bin/env python3
"""Work around TeamViewer's Ctrl+letter keysyms on GNOME Wayland.

Run as the desktop user in the graphical session:
    /usr/bin/python3 tv_ctrl_chord_helper.py

The helper monitors Mutter's session-bus calls and injects letters through
its own remote-desktop session. It does not need /dev/uinput or a layout table.
Monitoring is asynchronous: if Ctrl is released before injection, a plain
letter can be typed. Test in a safe window before relying on this workaround.
"""

import sys
import time

try:
    from gi.repository import Gio, GLib
except ImportError as error:
    raise SystemExit(
        f"Python GObject bindings are required: {error}. "
        "On Ubuntu, install python3-gi and use /usr/bin/python3."
    ) from error

SERVICE = "org.gnome.Mutter.RemoteDesktop"
ROOT_PATH = "/org/gnome/Mutter/RemoteDesktop"
SESSION_INTERFACE = f"{SERVICE}.Session"
MATCH = (
    f"type='method_call',interface='{SESSION_INTERFACE}',"
    "member='NotifyKeyboardKeysym'"
)
CONTROL_KEYSYMS = {65507, 65508}
CONTROL_CHAR_BASE = 0x01000000
DELAY = 0.02

def ctrl_letter(keysym):
    """Return the letter encoded as a Unicode control keysym, or None."""
    if CONTROL_CHAR_BASE < keysym <= CONTROL_CHAR_BASE + 26:
        return chr(keysym - CONTROL_CHAR_BASE + ord("a") - 1)
    return None


class MutterKeyboard:
    """Own a Mutter remote-desktop session on the graphical user's bus."""

    def __init__(self):
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.connection.set_exit_on_close(False)
        self.sender = self.connection.get_unique_name()
        self.path = self._call(ROOT_PATH, SERVICE, "CreateSession").unpack()[0]
        self._call(self.path, SESSION_INTERFACE, "Start")

    def _call(self, path, interface, method, parameters=None):
        return self.connection.call_sync(
            SERVICE,
            path,
            interface,
            method,
            parameters,
            None,
            Gio.DBusCallFlags.NONE,
            5000,
            None,
        )

    def _key(self, keysym, pressed):
        self._call(
            self.path,
            SESSION_INTERFACE,
            "NotifyKeyboardKeysym",
            GLib.Variant("(ub)", (keysym, pressed)),
        )

    def tap(self, letter):
        self._key(ord(letter), True)
        try:
            time.sleep(DELAY)
        finally:
            self._key(ord(letter), False)

    def close(self):
        self._call(self.path, SESSION_INTERFACE, "Stop")


class ChordHandler:
    """Track Ctrl state independently for each remote-desktop session."""

    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.controls = {}

    def handle(self, sender, path, keysym, pressed):
        if sender == self.keyboard.sender:
            return
        source = (sender, path)
        if keysym in CONTROL_KEYSYMS:
            if pressed:
                self.controls.setdefault(source, set()).add(keysym)
            else:
                held = self.controls.get(source)
                if held is not None:
                    held.discard(keysym)
                    if not held:
                        del self.controls[source]
            return
        letter = ctrl_letter(keysym)
        if pressed and source in self.controls and letter is not None:
            print(f"Ctrl+{letter}", flush=True)
            self.keyboard.tap(letter)


class SessionMonitor:
    """Receive method calls using a dedicated session-bus monitor connection."""

    def __init__(self, handler, loop):
        self.handler = handler
        self.loop = loop
        self.error = None
        address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        flags = (
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
        )
        self.connection = Gio.DBusConnection.new_for_address_sync(
            address, flags, None, None
        )
        self.connection.set_exit_on_close(False)
        self.connection.connect("closed", self._closed)
        self.connection.add_filter(self._filter, None)
        try:
            self.connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus.Monitoring",
                "BecomeMonitor",
                GLib.Variant("(asu)", ([MATCH], 0)),
                None,
                Gio.DBusCallFlags.NONE,
                5000,
                None,
            )
        except GLib.Error:
            self.connection.close_sync(None)
            raise

    def _filter(self, _connection, message, incoming, _user_data):
        if not incoming or message.get_message_type() != Gio.DBusMessageType.METHOD_CALL:
            return message
        if (
            message.get_interface() == SESSION_INTERFACE
            and message.get_member() == "NotifyKeyboardKeysym"
        ):
            body = message.get_body()
            sender = message.get_sender()
            path = message.get_path()
            if body is not None and body.get_type_string() == "(ub)" and sender and path:
                keysym, pressed = body.unpack()
                GLib.idle_add(self._dispatch, sender, path, keysym, pressed)
            else:
                print("Ignoring malformed NotifyKeyboardKeysym call", file=sys.stderr)
        # A monitor must not respond to messages addressed to other clients.
        return None

    def _dispatch(self, sender, path, keysym, pressed):
        try:
            self.handler.handle(sender, path, keysym, pressed)
        except (GLib.Error, OSError, RuntimeError) as error:
            self.error = error
            self.loop.quit()
        return GLib.SOURCE_REMOVE

    def _closed(self, _connection, _remote_peer_vanished, error):
        self.error = RuntimeError(f"D-Bus monitor connection closed: {error}")
        self.loop.quit()

    def close(self):
        if not self.connection.is_closed():
            self.connection.close_sync(None)


def run():
    keyboard = MutterKeyboard()
    try:
        loop = GLib.MainLoop()
        monitor = SessionMonitor(ChordHandler(keyboard), loop)
        try:
            print("watching Ctrl chords on the GNOME session bus", flush=True)
            loop.run()
            if monitor.error is not None:
                raise monitor.error
            raise RuntimeError("D-Bus monitor stopped unexpectedly")
        except KeyboardInterrupt:
            pass
        finally:
            monitor.close()
    finally:
        keyboard.close()
    return 0


def main():
    if len(sys.argv) != 1:
        print(f"Usage: {sys.argv[0]}", file=sys.stderr)
        return 2
    try:
        return run()
    except (GLib.Error, OSError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
