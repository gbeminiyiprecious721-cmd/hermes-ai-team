"""Product Factory worker fixes (run on the server):
 1) director.py: Claude Code / Codex count as available only when installed AND signed in.
 2) routing_policy.yaml: real Linux paths instead of the old Windows ones.
Idempotent: refuses to run twice."""
import yaml

PF = "/root/.hermes/profiles/product-factory"
p = PF + "/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "installed AND signed in" not in s, "already patched"

NEW_CLAUDE = '''def check_claude_avail() -> bool:
    """Claude Code is usable only when it is installed AND signed in (checked without consuming a model turn)."""
    try:
        result = subprocess.run(
            [CLAUDE_PATH, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )
        if result.returncode != 0:
            return False
        auth = subprocess.run(
            [CLAUDE_PATH, "auth", "status"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
        )
        try:
            return bool(json.loads(auth.stdout or "{}").get("loggedIn"))
        except ValueError:
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


'''
NEW_CODEX = '''def check_codex_avail() -> bool:
    """Codex is usable only when it is installed AND signed in (`codex login status` exits 0)."""
    try:
        result = subprocess.run(
            [CODEX_PATH, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )
        if result.returncode != 0:
            return False
        auth = subprocess.run(
            [CODEX_PATH, "login", "status"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
        )
        return auth.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

'''
a = s.index("def check_claude_avail() -> bool:")
b = s.index("def check_codex_avail() -> bool:")
s = s[:a] + NEW_CLAUDE + s[b:]
i = s.index("def check_codex_avail() -> bool:")
rest = s[i + 10:]
nxt = rest.find("\ndef ")
j = i + 10 + nxt + 1 if nxt >= 0 else len(s)
s = s[:i] + NEW_CODEX + s[j:]
if "\nimport json" not in s and not s.startswith("import json"):
    s = s.replace("import subprocess", "import json\nimport subprocess", 1)
open(p, "w", encoding="utf-8").write(s)

q = PF + "/policies/routing_policy.yaml"
y = open(q, encoding="utf-8").read()
orig = yaml.safe_load(y)
# adjust the two old Windows paths to your own (the text after "path:" in your policy) - edit these two strings first
OLD_CLAUDE = "path: C:/Users/<you>/AppData/Local/hermes/node/claude.cmd"
OLD_CODEX = "path: C:/Users/<you>/AppData/Local/hermes/bin/codex.cmd"
for old, new in [
    (OLD_CLAUDE, "path: /usr/local/bin/claude"),
    (OLD_CODEX, "path: /usr/local/bin/codex"),
    ("auth: authenticated (config file present)", 'auth: "Claude subscription sign-in (command: claude auth login)"'),
    ("auth: chatgpt_oauth (logged in via ChatGPT)", 'auth: "ChatGPT sign-in (command: codex login --device-auth)"'),
]:
    assert old in y, old
    y = y.replace(old, new, 1)
new_doc = yaml.safe_load(y)          # validate BEFORE writing (a colon+space inside an unquoted value breaks YAML)
assert new_doc["routing"] == orig["routing"]
open(q, "w", encoding="utf-8").write(y)
print("patched director.py and routing_policy.yaml")
