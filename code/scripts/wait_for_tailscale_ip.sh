#!/bin/bash
# Waits until the tailscale0 interface has an IPv4 address, up to 60s.
for i in $(seq 1 30); do
  if /usr/bin/tailscale ip -4 >/dev/null 2>&1; then
    exit 0
  fi
  sleep 2
done
echo "tailscale IP not available after 60s" >&2
exit 1
