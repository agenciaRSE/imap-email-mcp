"""Offline checks: python test_imap_mcp.py"""
import email
from email.policy import default as default_policy

import imap_mcp as im

assert im.imap_date("2026-11-04") == "04-Nov-2026"
assert im.quote('a "b" \\c') == '"a \\"b\\" \\\\c"'
assert im.decode("=?utf-8?q?Caf=C3=A9?=") == "Café"
assert im.html_to_text("<style>x{}</style><p>Hola&nbsp;<b>Diego</b></p><br>Adiós") == "Hola\xa0Diego\n\nAdiós"

orig = email.message_from_bytes(
    b"From: a@x.com\r\nSubject: Hola\r\nMessage-ID: <1@x.com>\r\nReferences: <0@x.com>\r\n\r\nbody",
    policy=default_policy)
msg = im.build_message("you@example.com", "a@x.com", "Re: Hola", "Gracias, ñ", reply_to_msg=orig)
assert msg["In-Reply-To"] == "<1@x.com>"
assert msg["References"] == "<0@x.com> <1@x.com>"
assert msg["Message-ID"].endswith("@example.com>")
assert "ñ" in msg.get_content()

# protocol
box = None
r = im.handle(box, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
assert r["result"]["protocolVersion"] == "2025-06-18"
assert im.handle(box, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
names = [t["name"] for t in im.handle(box, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]]
assert names == ["list_folders", "search_emails", "read_email", "create_draft", "send_email",
                 "move_email", "mark_spam", "not_spam", "trash_email", "mark_email"]

# special folders: SPECIAL-USE flag first, then name (Junk preferred over spam)
class FakeList:
    def __init__(self, lines): self.lines = lines
    def list(self): return "OK", [l.encode() for l in self.lines]
b = im.Mailbox({})
fake = FakeList([r'(\HasNoChildren) "." INBOX.spam', r'(\HasNoChildren) "." INBOX.Junk',
                 r'(\HasNoChildren) "." INBOX.Trash', r'(\HasNoChildren \Sent) "." "INBOX.Enviados"'])
assert b.special(fake, "Junk") == "INBOX.Junk"
assert b.special(fake, "Trash") == "INBOX.Trash"
assert b.special(fake, "Sent") == "INBOX.Enviados"
assert b.special(fake, "Drafts") == "INBOX.Drafts"
try:
    im.Mailbox({}).set_flags(1)
    raise SystemExit("mark_email accepted no flags")
except ValueError:
    pass
r = im.handle(box, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}})
assert r["result"]["isError"]
assert im.handle(box, {"jsonrpc": "2.0", "id": 4, "method": "foo"})["error"]["code"] == -32601

# security
import time
for bad in ("a\r\nb", "x\n", "\0"):
    try:
        im.quote(bad)
        raise SystemExit(f"quote accepted {bad!r}")
    except ValueError:
        pass
for bad in ("1:*", "1 BODY[]", 0, -1, True, 1.5):
    try:
        im.check_uid(bad)
        raise SystemExit(f"check_uid accepted {bad!r}")
    except ValueError:
        pass
assert im.check_uid(42) == "42"
t0 = time.time()
im.html_to_text("<script " * 20000)
assert time.time() - t0 < 1, "html_to_text is slow on unclosed tags"
assert im.html_to_text("a<script>x</script>b<SCRIPT>y</Script>c<style>z") == "abc"
try:
    im.Mailbox({}).send(body="x", reply_to_uid=1)
    raise SystemExit("send_email accepted a reply without 'to'")
except ValueError:
    pass
print("OK")

# setup helpers
import json, os, tempfile
cfg = {"user": "you@example.com", "imap_host": "mail.example.com", "smtp_host": "mail.example.com",
       "imap_port": 993, "smtp_port": 465}
assert im.server_env(cfg) == {"MAIL_USER": "you@example.com"}
assert im.server_env({**cfg, "imap_host": "x.host", "smtp_host": "x.host"})["IMAP_HOST"] == "x.host"
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "claude_desktop_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {"other": {"command": "x"}}, "keep": 1}, f)
    im.add_to_desktop(path, "mail-example", cfg)
    data = json.load(open(path, encoding="utf-8"))
    assert data["keep"] == 1 and "other" in data["mcpServers"]
    assert data["mcpServers"]["mail-example"]["env"] == {"MAIL_USER": "you@example.com"}
    assert os.path.exists(path + ".bak")
    os.remove(path); os.remove(path + ".bak")
    im.add_to_desktop(path, "mail-example", cfg)  # no config file yet
    assert "mail-example" in json.load(open(path, encoding="utf-8"))["mcpServers"]
assert "server name" in im.test_login({**cfg, "imap_host": "nonexistent.invalid"}, "x")
print("OK setup")
