#!/usr/bin/env python3
"""Re-inject Ctrl+letter chords that TeamViewer sends as control characters.

On Wayland, TeamViewer sends Ctrl+A as NotifyKeyboardKeysym(0x01000001)
while Control_L is held. In the observed session, no corresponding letter
reaches the focused Wayland window. This helper watches Mutter RemoteDesktop
calls from all senders on the session bus. While Control is held, it injects
the matching physical key through a uinput keyboard.

Run as the desktop user with access to /dev/uinput:
    /usr/bin/python3 tv_ctrl_chord_helper.py

The compositor's Wayland keymap determines the keycodes. If a letter has no
unmodified keycode common to every layout group, it is not injected. This
asynchronous workaround cannot guarantee that Ctrl is still held when the
injected key arrives.
"""

import fcntl
import os
import re
import struct
import subprocess
import sys
import time

try:
    import gi

    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk
except (ImportError, ValueError) as error:
    raise SystemExit(
        f"GTK 3 Python bindings are required: {error}. "
        "On Ubuntu, install python3-gi and gir1.2-gtk-3.0 and use /usr/bin/python3."
    ) from error

EV_SYN = 0x00
EV_KEY = 0x01
SYN_REPORT = 0

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_SETUP = 0x405C5503
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502

CONTROL_KEYSYMS = {65507, 65508}  # Control_L, Control_R
CONTROL_CHAR_BASE = 0x01000000  # Unicode keysym base for control characters

MATCH = (
    "type='method_call',interface='org.gnome.Mutter.RemoteDesktop.Session',"
    "member='NotifyKeyboardKeysym'"
)

UINT32_RE = re.compile(r"UINT32 (\d+);")
BOOL_RE = re.compile(r"BOOLEAN (true|false);")

DELAY = 0.02
XKB_KEYCODE_OFFSET = 8
MAX_XKB_KEYCODE = 255


def build_key_map(keymap):
    """Map ASCII letters to unmodified evdev keys valid in every XKB group."""
    groups = set()
    for keycode in range(XKB_KEYCODE_OFFSET + 1, MAX_XKB_KEYCODE + 1):
        found, entries, _ = keymap.get_entries_for_keycode(keycode)
        if found:
            groups.update(entry.group for entry in entries)
    if not groups:
        raise RuntimeError("The Wayland compositor did not provide a keyboard keymap")

    result = {}
    for value in range(ord("a"), ord("z") + 1):
        found, entries = keymap.get_entries_for_keyval(value)
        if not found:
            continue
        by_group = {group: set() for group in groups}
        for entry in entries:
            if (
                entry.group in by_group
                and entry.level == 0
                and XKB_KEYCODE_OFFSET < entry.keycode <= MAX_XKB_KEYCODE
            ):
                by_group[entry.group].add(entry.keycode - XKB_KEYCODE_OFFSET)
        common = set.intersection(*by_group.values())
        if common:
            result[chr(value)] = min(common)
    return result


class WaylandKeyMap:
    """Read the compositor's keymap and refresh it when it changes."""

    def __init__(self):
        Gdk.set_allowed_backends("wayland")
        initialized, _ = Gdk.init_check([])
        if not initialized:
            raise RuntimeError("Cannot connect to the graphical user's Wayland display")
        self.display = Gdk.Display.get_default()
        if self.display is None:
            raise RuntimeError("Cannot obtain the Wayland display")
        self.keymap = Gdk.Keymap.get_for_display(self.display)
        if self.keymap is None:
            raise RuntimeError("Cannot obtain the Wayland keyboard keymap")
        self.changed = True
        self.codes = {}
        self.keymap.connect("keys-changed", self._keys_changed)

    def _keys_changed(self, _keymap):
        self.changed = True

    def get(self, letter):
        # A round trip dispatches pending keymap changes before lookup.
        self.display.sync()
        if self.changed:
            self.codes = build_key_map(self.keymap)
            self.changed = False
        return self.codes.get(letter)


def ctrl_letter(keysym):
    """Return the letter for a control-character keysym (Ctrl+letter), or None."""
    if CONTROL_CHAR_BASE < keysym <= CONTROL_CHAR_BASE + 26:
        code = keysym - CONTROL_CHAR_BASE
    else:
        return None
    return chr(code + 0x60)


def iter_keysyms(lines):
    """Yield (keysym, pressed) for each NotifyKeyboardKeysym message in busctl output."""
    keysym = None
    for raw in lines:
        line = raw.strip()
        if line.startswith("Type="):
            keysym = None
            continue
        match = UINT32_RE.search(line)
        if match:
            keysym = int(match.group(1))
            continue
        match = BOOL_RE.search(line)
        if match and keysym is not None:
            yield keysym, match.group(1) == "true"
            keysym = None


class VirtualKeyboard:
    """Minimal uinput keyboard that stays open for the lifetime of the helper."""

    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
            # Support keymap changes without replacing the virtual device.
            for code in range(1, MAX_XKB_KEYCODE - XKB_KEYCODE_OFFSET + 1):
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            name = b"tv-ctrl-chord-helper"
            setup = struct.pack("HHHH", 0x03, 0x1234, 0x5679, 1)
            setup += name.ljust(80, b"\0") + struct.pack("I", 0)
            fcntl.ioctl(self.fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        # Let the compositor register the new device before the first event.
        time.sleep(2)

    def _emit(self, ev_type, code, value):
        os.write(self.fd, struct.pack("llHHi", 0, 0, ev_type, code, value))

    def tap(self, code):
        self._emit(EV_KEY, code, 1)
        self._emit(EV_SYN, SYN_REPORT, 0)
        time.sleep(DELAY)
        self._emit(EV_KEY, code, 0)
        self._emit(EV_SYN, SYN_REPORT, 0)

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)


def run():
    keymap = WaylandKeyMap()
    # Validate that a keymap is available before creating an input device.
    keymap.get("a")
    keyboard = VirtualKeyboard()
    ctrl_down = False

    proc = None
    try:
        proc = subprocess.Popen(
            ["stdbuf", "-oL", "busctl", "--user", "monitor", f"--match={MATCH}"],
            stdout=subprocess.PIPE,
            text=True,
        )
        print("watching Ctrl chords using the Wayland keymap", flush=True)
        for keysym, pressed in iter_keysyms(proc.stdout):
            if keysym in CONTROL_KEYSYMS:
                ctrl_down = pressed
                continue
            if not (pressed and ctrl_down):
                continue
            letter = ctrl_letter(keysym)
            if letter is None:
                continue
            code = keymap.get(letter)
            if code is None:
                print(
                    f"Cannot safely map Ctrl+{letter} in all keyboard layout groups; skipping",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            print(f"Ctrl+{letter}", flush=True)
            keyboard.tap(code)
        status = proc.wait()
        if status != 0:
            raise RuntimeError(f"busctl monitor exited with status {status}")
        raise RuntimeError("busctl monitor stopped unexpectedly")
    except KeyboardInterrupt:
        pass
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
            proc.wait()
        keyboard.close()
    return 0


def main():
    if len(sys.argv) != 1:
        print(f"Usage: {sys.argv[0]}", file=sys.stderr)
        return 2
    try:
        return run()
    except (OSError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
