"""Route the new 'AI Career Coach' Telegram forum topic (thread_id 423, created
via the Bot API in the existing Hermes supergroup) to the data-science-career-coach
profile (run on the server). Targeted string insert, matching the existing
gateway.profile_routes entries exactly in structure/indentation.
"""
import shutil
import time

p = "/root/.hermes/config.yaml"
s = open(p, encoding="utf-8").read()
assert "telegram-pf-group-career-coach" not in s, "already routed"

anchor = """    - name: telegram-pf-group-scribe
      platform: telegram
      chat_id: '-1004391218809'
      thread_id: '206'
      profile: scribe
      enabled: true
"""
assert s.count(anchor) == 1, "anchor not found or not unique"

new_route = """    - name: telegram-pf-group-career-coach
      platform: telegram
      chat_id: '-1004391218809'
      thread_id: '423'
      profile: data-science-career-coach
      enabled: true
"""
s = s.replace(anchor, anchor + new_route, 1)

shutil.copy(p, "/root/backups/manual-changes/config.yaml.before-career-coach-telegram-route-" + time.strftime("%Y%m%d-%H%M%S"))
open(p, "w", encoding="utf-8").write(s)
print("patched: telegram-pf-group-career-coach route added (thread 423 -> data-science-career-coach)")
