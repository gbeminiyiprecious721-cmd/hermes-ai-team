"""Set tts.provider: neutts for the coach profile only (run on the server).
Free, local, on-device TTS - the owner's explicit choice over the paid OpenAI option.
"""
import shutil
import time

p = "/root/.hermes/profiles/data-science-career-coach/config.yaml"
s = open(p, encoding="utf-8").read()
assert "tts:" not in s, "tts section already present"

old = "model:\n  provider: openai-codex\n  default: gpt-5.6-terra\n"
new = old + "tts:\n  provider: neutts\n"
assert s.count(old) == 1, "anchor not found or not unique"
s = s.replace(old, new, 1)

shutil.copy(p, "/root/backups/manual-changes/data-science-career-coach.config.yaml.before-tts-" + time.strftime("%Y%m%d-%H%M%S"))
open(p, "w", encoding="utf-8").write(s)
print("patched: tts.provider = neutts for data-science-career-coach")
