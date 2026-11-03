# Key Chord Helper

This key chord helper applies when running a TeamViewer server on Ubuntu 26.04 + Wayland.

This helper detects any Ctrl+Key combinations and translates them into a valid key. There is no need to do so with Alt+Key combinations since they are properly transmitted.

## Usage

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

## Implementation details

The tv_ctrl_chord_helper.py monitors the dbus session, compute the value and sends it to a separate dbus session. The value is computed as follows: if value is between 0x1000001 and 0x100001A, substract 0x1000000 and add 0x60 to match the value of an ASCII letter.

This script require Gio and Glib libs.

In Ubuntu, install it with:
```bash
sudo apt install python3-gi
```

