"""Loaded automatically by Python (only for the hermes-gateway service, via PYTHONPATH in its systemd drop-in).
Hides one harmless, high-volume warning from hermes_cli.auth: when a background task on the multiplexed gateway asks the Nous provider
for a routing override without a profile scope, Hermes logs a warning and uses default routing, which is exactly what we want because
no NOUS_INFERENCE_BASE_URL / HERMES_PORTAL_BASE_URL override is set. If an override is ever set, the filter switches itself off."""
import logging
import os


class _QuietNousScope(logging.Filter):
    def filter(self, record):
        try:
            if any(os.environ.get(k) for k in ("NOUS_INFERENCE_BASE_URL", "HERMES_PORTAL_BASE_URL", "NOUS_PORTAL_BASE_URL")):
                return True
            msg = record.getMessage()
            return not (msg.startswith("nous: ") and "no profile secret scope on a multiplexed call" in msg)
        except Exception:
            return True


logging.getLogger("hermes_cli.auth").addFilter(_QuietNousScope())
