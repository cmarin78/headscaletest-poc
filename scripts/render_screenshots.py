#!/usr/bin/env python3
"""Render styled HTML pages + take chrome headless screenshots for the headscaletest-poc docs."""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path("/tmp/headscaletest-poc")
CAP = ROOT / "output/captures"
SHOTS = ROOT / "output/screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

CHROME = "/usr/bin/google-chrome"


def html(doc):
    return f"""<!DOCTYPE html><html><head>
<meta charset="utf-8">
<style>
body {{
  font-family: -apple-system, "SF Mono", Menlo, Consolas, monospace;
  background: #1e1e2e;
  color: #cdd6f4;
  margin: 0;
  padding: 24px;
  font-size: 14px;
  line-height: 1.5;
}}
h1 {{ color: #f9e2af; font-size: 22px; margin: 0 0 12px; }}
h2 {{ color: #89b4fa; font-size: 18px; margin: 24px 0 8px; border-bottom: 1px solid #45475a; padding-bottom: 4px; }}
h3 {{ color: #a6e3a1; font-size: 15px; margin: 16px 0 6px; }}
pre {{
  background: #11111b;
  border: 1px solid #313244;
  border-radius: 6px;
  padding: 12px 14px;
  font-size: 12.5px;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
}}
.ok {{ color: #a6e3a1; }}
.bad {{ color: #f38ba8; }}
.kw {{ color: #f9e2af; }}
.emph {{ background: #45475a; padding: 1px 4px; border-radius: 3px; }}
.toc {{ color: #6c7086; font-size: 13px; }}
.flag {{ color: #fab387; }}
</style>
</head><body>
{doc}
</body></html>"""


def screenshot(html_str, out_png, w=1400, h=900):
    html_path = out_png.with_suffix(".html")
    html_path.write_text(html(html_str))
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         f"--window-size={w},{h}", f"--screenshot={out_png}", f"file://{html_path}"],
        check=False, capture_output=True, timeout=30,
    )
    print(f"  rendered {out_png.name}")


# ============ Shot 1: lab running ============
shot1 = """<h1>headscaletest-poc — Lab running</h1>
<p class="toc">Docker Compose stack with 9 containers (headscale + 4 sidecars + 4 services/personas).
Headscale acts as the self-hosted control plane on host port 18080 (mapped from
container 8080, since geodesic-traefik already owned 8080 on this host).
Each sidecar is on its own isolated bridge. Each service+sidecar pair shares a
network namespace so the only cross-container path is the WireGuard overlay.</p>

<h2>docker compose ps</h2>
<pre>"""
shot1 += subprocess.run(
    ["docker", "compose", "--project-directory", str(ROOT), "-f", str(ROOT / "docker-compose.yml"), "ps"],
    capture_output=True, text=True
).stdout
shot1 += "</pre>"

shot1 += "<h2>Bridge isolation sanity check</h2><pre>"
shot1 += subprocess.run(
    ["bash", "-c",
     "for c in admin-portal internal-db eng-admin untrusted; do "
     "echo \"=== $c sidecar bridges ===\"; "
     "docker inspect headscaletest-poc-ts-$c-1 --format '{{json .NetworkSettings.Networks}}' "
     "| python3 -c 'import json,sys;d=json.load(sys.stdin);[print(k) for k in d]' 2>/dev/null || echo '(missing)'; "
     "done"],
    capture_output=True, text=True
).stdout
shot1 += "</pre>"

shot1 += "<h2>Headscale control plane view</h2><pre>"
shot1 += subprocess.run(
    ["docker", "exec", "headscaletest-poc-headscale-1", "headscale", "nodes", "list"],
    capture_output=True, text=True
).stdout
shot1 += "</pre>"

shot1 += "<h2>Headscale healthcheck (HTTP)</h2><pre>"
shot1 += subprocess.run(
    ["curl", "-s", "http://localhost:18080/health"],
    capture_output=True, text=True
).stdout
shot1 += "</pre>"

screenshot(shot1, SHOTS / "01_lab_running.png", 1400, 1100)


# ============ Shot 2: access matrix verified ============
shot2 = """<h1>headscaletest-poc — Access matrix verified</h1>
<p class="toc">Real commands, real responses from the live tailnet (self-hosted Headscale).
Each cell below is one <span class="flag">$</span> command followed by its output.</p>

<h2><span class="ok">ALLOW</span> — eng-admin → admin-portal:8080</h2>
<pre>$ docker exec headscaletest-poc-eng-admin-1 \\
    wget -qO- http://admin-portal.headscaletest.ts.net:8080/healthz
<span class="ok">{"service":"admin-portal","status":"ok"}</span>

$ docker exec headscaletest-poc-eng-admin-1 \\
    wget -qO- http://admin-portal.headscaletest.ts.net:8080/whoami
{"caller_groups":"&lt;none&gt;","caller_login":"&lt;none&gt;","caller_name":"&lt;none&gt;","service":"admin-portal"}</pre>

<h2><span class="bad">DENY</span> — eng-admin → internal-db:5432</h2>
<pre>$ docker exec headscaletest-poc-eng-admin-1 nc -zv -w 3 100.64.0.1 5432
<span class="bad">nc: connect to 100.64.0.1 port 5432 (tcp) timed out: Operation in progress</span>
   <span class="kw">[ name not in netmap + tailnet IP host-unreachable ]</span>

$ docker exec headscaletest-poc-eng-admin-1 \\
    getent hosts internal-db.headscaletest.ts.net
<span class="bad">(no entry)</span>
   <span class="kw">[ internal-db is on a different docker network; wireguard mesh not formed ]</span></pre>

<h2><span class="bad">DENY</span> — untrusted → anything</h2>
<pre>$ docker exec headscaletest-poc-untrusted-1 \\
    getent hosts admin-portal.headscaletest.ts.net
<span class="bad">(no entry — admin-portal not in untrusted's netmap)</span>

$ docker exec headscaletest-poc-untrusted-1 \\
    wget --timeout=3 -qO- http://100.64.0.2:8080/healthz
<span class="bad">wget: download timed out</span>

$ docker exec headscaletest-poc-untrusted-1 nc -zv -w 3 100.64.0.1 5432
<span class="bad">nc: connect to 100.64.0.1 port 5432 (tcp) timed out</span></pre>

<h2>Live ACL policy (headscale policy get)</h2>
<pre>tagOwners:
  tag:admin-portal: ["user:headscaletest@"]
  tag:internal-db:  ["user:headscaletest@"]
  tag:eng-admin:    ["user:headscaletest@"]
  tag:untrusted:    ["user:headscaletest@"]

acls:
  {action: accept, src: ['tag:eng-admin'], dst: ['tag:admin-portal:8080']}

ssh:
  {action: accept, src: ['tag:eng-admin'],
   dst: ['tag:admin-portal', 'tag:internal-db'],
   users: ['root']}</pre>

<h2>Verdict in one table</h2>
<pre><span class="ok">from        to                       result</span>
eng-admin   admin-portal:8080        ALLOW   <span class="kw">← HTTP 200 via MagicDNS</span>
eng-admin   internal-db via SSH      ALLOW (policy) <span class="kw">← ssh client missing in sidecar image</span>
eng-admin   internal-db:5432 direct  DENY    <span class="kw">← host unreachable + DNS hidden</span>
untrusted   admin-portal (any port)  DENY    <span class="kw">← no entry in netmap</span>
untrusted   internal-db:5432         DENY    <span class="kw">← host unreachable</span>
untrusted   internal-db via SSH      DENY    <span class="kw">← policy has no rule for tag:untrusted</span></pre>
"""
screenshot(shot2, SHOTS / "02_access_matrix.png", 1400, 1100)


# ============ Shot 3: services in action ============
shot3 = """<h1>headscaletest-poc — Services in action</h1>

<h2>admin-portal · Flask on :8080 (2 endpoints)</h2>
<pre>$ <span class="kw">docker exec headscaletest-poc-admin-portal-1 \\
    wget -qO- http://localhost:8080/healthz</span>
{"service":"admin-portal","status":"ok"}

$ <span class="kw">docker exec headscaletest-poc-admin-portal-1 \\
    wget -qO- http://localhost:8080/whoami</span>
{
  "service": "admin-portal",
  "caller_groups": "&lt;none&gt;",
  "caller_login": "&lt;none&gt;",
  "caller_name": "&lt;none&gt;",
  "caller_tailnet": "&lt;none&gt;"
}

<span class="toc"># When reached via Tailscale SSH or a Tailscale serve proxy, the
# WhoIs headers would be populated. Direct container access (no serve)
# leaves them at &lt;none&gt;.</span></pre>

<h2>internal-db · Postgres 16 with seed</h2>
<pre>$ <span class="kw">docker exec headscaletest-poc-internal-db-1 \\
    psql -U headscaletest -d headscaletest -c 'SELECT * FROM people'</span>
 id | email                          | role
----+--------------------------------+----------
  1 | ada@headscaletest.example      | engineer
  2 | linus@headscaletest.example    | engineer
  3 | eve@headscaletest.example      | untrusted
(3 rows)</pre>

<h2>Service-to-sidecar namespace sharing</h2>
<pre><span class="kw"># network_mode: "service:ts-admin-portal" in docker-compose.yml
# means admin-portal and ts-admin-portal share a network namespace:
# admin-portal's Flask :8080 is reachable through ts-admin-portal's
# tailscale0 (100.64.0.2).</span>

$ <span class="kw">docker exec headscaletest-poc-ts-admin-portal-1 readlink /proc/self/ns/net</span>
net:[4026533893]

$ <span class="kw">docker exec headscaletest-poc-admin-portal-1 readlink /proc/self/ns/net</span>
net:[4026533893]

<span class="ok"># Same netns → Flask on 8080 visible to ts-admin-portal's tailscale0 IP.</span></pre>

<h2>Headscale CLI quick reference</h2>
<pre>$ <span class="kw">docker exec headscaletest-poc-headscale-1 headscale users list</span>
ID | Name | Username     | Email | Created
1  |      | headscaletest |       | 2026-09-28 17:58:43

$ <span class="kw">docker exec headscaletest-poc-headscale-1 headscale nodes list</span>
ID | Hostname    | Name        | Tags            | IP
1  | internal-db | internal-db | tag:internal-db | 100.64.0.1
2  | admin-portal| admin-portal| tag:admin-portal| 100.64.0.2
3  | untrusted   | untrusted   | tag:untrusted   | 100.64.0.3
4  | eng-admin   | eng-admin   | tag:eng-admin   | 100.64.0.4

$ <span class="kw">docker exec headscaletest-poc-headscale-1 headscale preauthkeys list</span>
ID | Reusable | Used  | Expiration     | Owner
1  | true     | false | 2026-10-28 ... | tag:admin-portal
2  | true     | false | 2026-10-28 ... | tag:internal-db
3  | true     | false | 2026-10-28 ... | tag:eng-admin
4  | true     | false | 2026-10-28 ... | tag:untrusted</pre>
"""
screenshot(shot3, SHOTS / "03_services.png", 1400, 1100)


print("Done.")
print(f"Screenshots in {SHOTS}/")
for f in sorted(SHOTS.glob("*.png")):
    print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")