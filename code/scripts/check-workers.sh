#!/bin/bash
# Shows which Product Factory workers are usable right now (installed AND signed in). Uses no model quota.
export PATH=$PATH:/usr/local/bin:/root/.local/bin
echo "Claude Code sign-in:"; claude auth status 2>&1 | grep -E "loggedIn|email|subscription" | head -3
echo "Codex sign-in:"; codex login status 2>&1 | head -2
echo; echo "Product Factory view:"
HERMES_HOME=/root/.hermes/profiles/product-factory /usr/local/lib/hermes-agent/venv/bin/python /root/.hermes/scripts/check-workers.py 2>&1 | tail -6
