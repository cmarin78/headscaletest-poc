"""admin-portal — minimal Flask app to prove tag-based access control.

The whole app is one endpoint. The POC's purpose is to validate that *who can
reach this endpoint at all* is controlled by the tagOwners + acls + ssh
blocks in acl/policy.hujson, not by anything in this code.
"""
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "admin-portal"})


@app.get("/whoami")
def whoami():
    # When reached via `tailscale serve`, these headers carry the caller identity.
    return jsonify(
        {
            "service": "admin-portal",
            "caller_login":    request.headers.get("Tailscale-User-Login",   "<none>"),
            "caller_name":     request.headers.get("Tailscale-User-Name",    "<none>"),
            "caller_groups":   request.headers.get("Tailscale-User-Groups",  "<none>"),
            "caller_tailnet":  request.headers.get("Tailscale-Tailnet",      "<none>"),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)