"""Push notifications via ntfy — the coach's line to your phone.

Install the ntfy app on the phone, subscribe to the topic shown in the app's
Vitals tab, and every push lands on the wrist too (watch mirrors phone
notifications). No accounts, no keys; the topic name is the secret.
"""
import urllib.request


def push(settings, title, message, priority='default'):
    """Send a push. Returns True if dispatched, False if not configured."""
    topic = (settings or {}).get('ntfy_topic', '').strip()
    server = ((settings or {}).get('ntfy_server') or 'https://ntfy.sh').rstrip('/')
    if not topic:
        return False
    req = urllib.request.Request(
        f"{server}/{topic}",
        data=message.encode('utf-8'),
        headers={'Title': title.encode('utf-8').decode('latin-1', 'replace'),
                 'Priority': priority},
        method='POST',
    )
    urllib.request.urlopen(req, timeout=10)
    return True
