"""Let Claude Code write files INSIDE the Product Factory project folder only (run on the server).
Before: claude -p ... --max-turns 1 --permission-mode dontAsk   (no tools allowed -> every file write denied -> error_max_turns)
After : more turns, only the file tools exist (no shell, no web), and Read/Write/Edit are allowed only under the project folder (./**).
Idempotent and validated (py_compile) before the file is replaced."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "allowedTools" not in s, "already patched"

a = s.index("def invoke_claude_code(")
b = s.index("def ", a + 10)
fn = s[a:b]

old_flags = '''             "--output-format", "json",
             "--max-turns", "1",
             "--permission-mode", "dontAsk",
             "--no-session-persistence"],'''
new_flags = '''             "--output-format", "json",
             "--max-turns", "10",
             "--permission-mode", "dontAsk",
             "--no-session-persistence",
             # Claude Code may only use file tools, and only inside this project folder (cwd). No shell, no web.
             "--tools", "Read,Write,Edit,Glob,Grep",
             "--allowedTools", "Read(./**)", "Write(./**)", "Edit(./**)", "Glob", "Grep"],'''
assert fn.count(old_flags) == 1, fn.count(old_flags)
fn2 = fn.replace(old_flags, new_flags, 1)
assert fn2.count("timeout=180,") == 1
fn2 = fn2.replace("timeout=180,", "timeout=600,", 1)
t = s[:a] + fn2 + s[b:]

shutil.copy(p, "/root/backups/manual-changes/director.py.before-claude-tools-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(t)
py_compile.compile(tmp, doraise=True)          # must compile before it replaces the live file
shutil.move(tmp, p)
print("patched invoke_claude_code: max-turns 10, tools limited to Read/Write/Edit/Glob/Grep, writes scoped to the project folder, timeout 600 s")
