"""Alert delivery. Three channels, all free, none needing a third party.

  mac()      macOS notification  — at the desk, different chime per type
  imessage() iMessage to self    — the searchable log
  sms()      Gmail -> carrier    — the ring; no-ops until Mail.app has an account

send() fires whichever are enabled in config.
"""
from __future__ import annotations
import subprocess, shlex

PHONE = "+17174210932"
SMS_GATEWAY = "7174210932@tmomail.net"

SOUNDS = {"GO": "Glass", "BLOCKED": "Pop", "EXPIRY": "Sosumi",
          "ROLL": "Sosumi", "GTC": "Hero"}


def _osa(script: str) -> bool:
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True)
    return r.returncode == 0


def mac(title: str, subtitle: str, body: str, kind: str = "GO") -> bool:
    """Native macOS notification. Always available, no setup."""
    def q(s):  # AppleScript string literal
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " · ") + '"'
    return _osa(f'display notification {q(body)} with title {q(title)} '
                f'subtitle {q(subtitle)} sound name "{SOUNDS.get(kind, "Glass")}"')


def imessage(text: str, to: str = PHONE) -> bool:
    """iMessage to yourself — no ring, but a searchable thread on every device."""
    script = (
        'on run argv\n'
        '  tell application "Messages"\n'
        '    set svc to 1st account whose service type = iMessage\n'
        '    send (item 1 of argv) to participant (item 2 of argv) of svc\n'
        '  end tell\n'
        'end run'
    )
    r = subprocess.run(["osascript", "-e", script, text, to],
                       capture_output=True, text=True)
    return r.returncode == 0


def sms(text: str, to: str = SMS_GATEWAY) -> bool:
    """Gmail -> T-Mobile gateway. Arrives as a real inbound text, so it rings.
    Returns False (no-op) until Mail.app has an account configured."""
    script = (
        'on run argv\n'
        '  tell application "Mail"\n'
        '    set m to make new outgoing message with properties '
        '{subject:"", content:(item 1 of argv), visible:false}\n'
        '    tell m\n'
        '      make new to recipient at end of to recipients '
        'with properties {address:(item 2 of argv)}\n'
        '      send\n'
        '    end tell\n'
        '  end tell\n'
        'end run'
    )
    r = subprocess.run(["osascript", "-e", script, text, to],
                       capture_output=True, text=True)
    return r.returncode == 0


def sms_available() -> bool:
    r = subprocess.run(["osascript", "-e",
                        'tell application "Mail" to count of accounts'],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip().isdigit() and int(r.stdout.strip()) > 0


def send(title: str, subtitle: str, body: str, kind: str = "GO",
         channels=("mac", "imessage", "sms")) -> dict:
    """Fire an alert on every enabled channel. Returns {channel: ok}."""
    full = f"{title}\n{body}"
    out = {}
    if "mac" in channels:
        out["mac"] = mac(title, subtitle, body, kind)
    if "imessage" in channels:
        out["imessage"] = imessage(full)
    if "sms" in channels:
        out["sms"] = sms(full) if sms_available() else None
    return out
