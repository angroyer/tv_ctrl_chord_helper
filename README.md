# Key Chord Helper

This key chord helper applies when running a TeamViewer server on Ubuntu 26.04 + Wayland.

This helper detects any Ctrl+Key combinations and translates them into a valid shortcut. There is no need to do so with Alt+Key combinations since they are properly transmitted.

## Usage

Before running this script, it is necessary to add your linux user to the "input" group:
```bash
sudo usermod -aG input $USER
```
Log out and log back in.

Then run the script:
```bash
python3 tv_ctrl_chord_helper.py
```
It will print any Ctrl+Key chords that have been detected and converted.

## Current Status

You can monitor how TeamViewer injects the Ctrl+Key combination:
```bash
$ busctl --user monitor --match="type='method_call',interface='org.gnome.Mutter.RemoteDesktop.Session',member='NotifyKeyboardKeysym'"
```

For example, when pressing Ctrl, then A, then releasing A, then Ctrl, you will see:
```bash
Type=method_call  Endian=l  Flags=0  Version=1  Cookie=14853  Timestamp="Mon 2026-11-02 11:53:31.885792 UTC"
Sender=:1.204  Destination=org.gnome.Mutter.RemoteDesktop  Path=/org/gnome/Mutter/RemoteDesktop/Session/u4  Interface=org.gnome.Mutter.RemoteDesktop.Session  Member=NotifyKeyboardKeysym
UniqueName=:1.204
MESSAGE "ub" {
        UINT32 65507;
        BOOLEAN true;
};

Type=method_call  Endian=l  Flags=0  Version=1  Cookie=14854  Timestamp="Mon 2026-11-02 11:53:31.886001 UTC"
Sender=:1.204  Destination=org.gnome.Mutter.RemoteDesktop  Path=/org/gnome/Mutter/RemoteDesktop/Session/u4  Interface=org.gnome.Mutter.RemoteDesktop.Session  Member=NotifyKeyboardKeysym
UniqueName=:1.204
MESSAGE "ub" {
        UINT32 16777217;
        BOOLEAN true;
};

Type=method_call  Endian=l  Flags=0  Version=1  Cookie=14855  Timestamp="Mon 2026-11-02 11:53:31.886406 UTC"
Sender=:1.204  Destination=org.gnome.Mutter.RemoteDesktop  Path=/org/gnome/Mutter/RemoteDesktop/Session/u4  Interface=org.gnome.Mutter.RemoteDesktop.Session  Member=NotifyKeyboardKeysym
UniqueName=:1.204
MESSAGE "ub" {
        UINT32 16777217;
        BOOLEAN false;
};

Type=method_call  Endian=l  Flags=0  Version=1  Cookie=14856  Timestamp="Mon 2026-11-02 11:53:31.886541 UTC"
Sender=:1.204  Destination=org.gnome.Mutter.RemoteDesktop  Path=/org/gnome/Mutter/RemoteDesktop/Session/u4  Interface=org.gnome.Mutter.RemoteDesktop.Session  Member=NotifyKeyboardKeysym
UniqueName=:1.204
MESSAGE "ub" {
        UINT32 65507;
        BOOLEAN false;
};
```

You can notice the 'Ctrl+a' combination is sent as value 16777217 (0x1000001) whereas Wayland expects the letter 'a' to be sent as value 97 (0x61).

It would the same for letter b, that is sent as 16777218 (0x1000002) whereas Wayland expects the letter 'b' to be sent as value 98 (0x62).

To solve this issue, the tv_ctrl_chord_helper.py reads the `busctl` command output and translates into a `uinput` event. The value is computed as follows: if value is between 0x1000001 and 0x100001A, substract 0x1000000 and add 0x60 and send as a uinput event.

## Implementation details

This script does not require any specific additional python libs. It would have been possible to use dbus_next and evdev libs to reduce the amount of code but this requires installing additional libs.

This script reads your Ubuntu keyboard map in order to apply it before sending a uinput event.
