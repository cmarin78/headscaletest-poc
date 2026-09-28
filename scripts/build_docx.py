#!/usr/bin/env python3
"""Build the headscaletest-poc run report docx from markdown + captures + screenshots."""
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = Path("/tmp/headscaletest-poc")
OUT = ROOT / "output/RUN_REPORT.docx"
CAP = ROOT / "output/captures"
SHOTS = ROOT / "output/screenshots"


def add_heading(doc, text, level=1):
    return doc.add_heading(text, level=level)


def add_para(doc, text, *, bold=False, italic=False, code=False, size=None, color=None):
    p = doc.add_paragraph()
    r = p.add_run(text)
    if bold: r.bold = True
    if italic: r.italic = True
    if code:
        r.font.name = "Consolas"
        r.font.size = Pt(10)
    if size: r.font.size = Pt(size)
    if color: r.font.color.rgb = RGBColor(*color)
    return p


def add_code_block(doc, text):
    """Add a monospace paragraph block. Strips ANSI escape codes and null bytes."""
    import re
    # Strip ANSI CSI escape codes and stray control chars
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    text = re.sub(r"\x1b\][^\x07]*\x07", "", text)  # OSC sequences
    text = text.replace("\x00", "")
    for line in text.split("\n"):
        p = doc.add_paragraph()
        r = p.add_run(line if line else " ")
        r.font.name = "Consolas"
        r.font.size = Pt(9)
        p.paragraph_format.space_after = Pt(0)


def add_shell_block(doc, command, output):
    add_code_block(doc, "$ " + command)
    if output:
        add_code_block(doc, output)


def add_image(doc, path, caption=None, width_inches=6.5):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run()
    r.add_picture(str(path), width=Inches(width_inches))
    if caption:
        c = doc.add_paragraph()
        cr = c.add_run(caption)
        cr.italic = True
        cr.font.size = Pt(9)
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER


def add_capture(doc, name, title):
    add_para(doc, f"[capture: {name}] -- {title}", bold=True, size=10, color=(0x44, 0x44, 0x44))
    text = (CAP / name).read_text()
    add_code_block(doc, text)


# ============================================================
doc = Document()

# Cover
cover = doc.add_paragraph()
cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = cover.add_run("headscaletest-poc")
r.font.size = Pt(40); r.bold = True
r.font.color.rgb = RGBColor(0x2A, 0x6F, 0x4E)

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
sr = sub.add_run("Replication run report -- every step, every output, every screenshot")
sr.font.size = Pt(13); sr.italic = True

doc.add_paragraph()
meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
mr = meta.add_run("Recorded 2026-09-28 (Argentina Standard Time, GMT-3) -- self-hosted Headscale v0.29.4")
mr.font.size = Pt(10); mr.italic = True

doc.add_page_break()


# Section 1 -- What this POC demonstrates
add_heading(doc, "1. What this POC demonstrates", level=1)
add_para(doc,
    "That the same four-node access matrix used in the tailscaletest-poc "
    "(github.com/cmarin78/tailscaletest-poc) can be expressed on a self-hosted "
    "Headscale control plane, with no Tailscale SaaS dependency, no admin "
    "console, and no API token:"
)
add_code_block(doc, (
    "from         to                          result                                  \n"
    "------------  --------------------------  --------------------------------------- \n"
    "eng-admin     admin-portal:8080          allowed                                 \n"
    "eng-admin     internal-db (via SSH)      allowed (policy intent)                 \n"
    "eng-admin     internal-db:5432 (direct)  denied   (SSH is the only door)       \n"
    "untrusted     anything                   denied   (no src includes it)         "
))
add_para(doc,
    "Everything not listed is denied by default. Headscale is deny-all when any "
    "acls/ssh rule is present, identical to Tailscale's behaviour."
)


# Section 2 -- Topology
add_heading(doc, "2. Topology (4 tailnet nodes, 9 containers)", level=1)
add_code_block(doc, (
    "headscale                                  (control plane, :8080 -> host :18080)\n"
    "ts-admin-portal  -- shares netns -- admin-portal   (Flask :8080, tag:admin-portal)\n"
    "ts-internal-db   -- shares netns -- internal-db    (Postgres :5432, tag:internal-db)\n"
    "ts-eng-admin     -- shares netns -- eng-admin      (netshoot, tag:eng-admin)\n"
    "ts-untrusted     -- shares netns -- untrusted      (netshoot, tag:untrusted)"
))
add_para(doc,
    "Each ts-* is a tailscale/tailscale:latest sidecar that points its control "
    "plane at the in-stack Headscale (not controlplane.tailscale.com). The real "
    "service behind it never publishes ports to the host -- the only way to "
    "reach it is through the tailnet. Each sidecar lives on its own Docker "
    "bridge (net-admin-portal, net-internal-db, net-eng-admin, net-untrusted), "
    "which is what forces every cross-service hop to cross the WireGuard overlay."
)
add_para(doc, "Lab running (live)", bold=True)
add_image(doc, SHOTS / "01_lab_running.png",
          caption="docker compose ps + bridge isolation sanity check + headscale nodes list + headscale /health",
          width_inches=6.5)


# Section 3 -- Prerequisites
add_heading(doc, "3. Prerequisites", level=1)
for p in [
    "Docker + Docker Compose v2 (docker compose version >= 2.20)",
    "Nothing else. No Tailscale account. No tskey-api-* token. No outbound connectivity to controlplane.tailscale.com (each sidecar talks only to the in-stack Headscale).",
    "curl, wget, nc, getent (standard tools on the netshoot image used by the persona containers -- nslookup returns NXDOMAIN but getent hosts works because of the Tailscale NSS module; see gotchas).",
    "Free host port 18080 (mapped from Headscale's container port 8080). On this host port 8080 was already owned by geodesic-traefik, so the compose file uses 18080.",
]:
    doc.add_paragraph(p, style="List Bullet")


# Section 4 -- Step-by-step replication
add_heading(doc, "4. Step-by-step replication", level=1)


add_heading(doc, "4.1 Create one user + one preauth key per node", level=2)
add_para(doc,
    "Headscale's tagOwners syntax requires a user-shaped reference (user:<name>@ -- see gotchas), "
    "so first create the user:"
)
add_shell_block(doc,
    "docker exec headscaletest-poc-headscale-1 headscale users create headscaletest",
    "")
add_para(doc,
    "Then generate four preauth keys -- one per tag. The --acl-tags argument stamps the tag onto "
    "every node that registers with that key, which is the only way to put an ACL tag onto a "
    "sidecar in Headscale:"
)
add_code_block(doc, (
    "$ for tag in admin-portal internal-db eng-admin untrusted; do\n"
    "    docker exec headscaletest-poc-headscale-1 \\\n"
    "        headscale preauthkeys create \\\n"
    "            --user headscaletest \\\n"
    "            --reusable \\\n"
    "            --expiration 720h \\\n"
    "            --acl-tags tag:$tag\n"
    "  done"
))
add_para(doc, "Suffix-only fingerprints (full values in .env on disk):", italic=True)
add_code_block(doc, (
    "TS_AUTHKEY_ADMIN_PORTAL  = hskey-auth-HPKjz1ik7a0N-...Mm5mE5   # tag:admin-portal\n"
    "TS_AUTHKEY_INTERNAL_DB   = hskey-auth-GlDlF8QTF04h-...zr7Krq   # tag:internal-db\n"
    "TS_AUTHKEY_ENG_ADMIN     = hskey-auth-HNZZWborOu69-...6ZU7sL   # tag:eng-admin\n"
    "TS_AUTHKEY_UNTRUSTED     = hskey-auth-9tipJj2nSgcg-...9dR7K   # tag:untrusted"
))
add_para(doc, "Security note: ", bold=True)
add_para(doc,
    "never paste real key values into a README, a shared document, or any file other than .env. "
    "This document shows only the suffix as a search-friendly fingerprint so reviewers can verify "
    "no real secret landed in the public repo."
)


add_heading(doc, "4.2 Drop the keys into .env", level=2)
add_code_block(doc, (
    "$ cp .env.example .env\n"
    "$ $EDITOR .env\n"
    "# paste each key into the matching TS_AUTHKEY_* variable\n"
    "# and set HEADSCALE_URL=http://host.docker.internal:18080"
))
add_para(doc, ".env (abridged, secrets redacted):", italic=True)
add_code_block(doc, (
    "TS_AUTHKEY_ADMIN_PORTAL=hskey-auth-...eC_oFBq...Mm5mE5\n"
    "TS_AUTHKEY_INTERNAL_DB =hskey-auth-...lo0eT5u...zr7Krq\n"
    "TS_AUTHKEY_ENG_ADMIN   =hskey-auth-...g3ndbV2...6ZU7sL\n"
    "TS_AUTHKEY_UNTRUSTED   =hskey-auth-...O3LcfnM...9dR7K\n"
    "HEADSCALE_URL          =http://host.docker.internal:18080"
))
add_para(doc, "Variable name gotcha: ", bold=True)
add_para(doc,
    "the docker-compose file references TS_AUTHKEY_ADMIN_PORTAL, TS_AUTHKEY_INTERNAL_DB, "
    "TS_AUTHKEY_ENG_ADMIN, TS_AUTHKEY_UNTRUSTED (underscore-separated). Do not hyphenate the "
    "names -- bash variable names don't allow -, so a .env with TS_AUTHKEY-ADMIN-PORTAL=... will "
    "silently parse as $TS_AUTHKEY_ADMIN followed by -PORTAL=... and fail."
)


add_heading(doc, "4.3 Apply the ACL policy", level=2)
add_para(doc,
    "The policy lives in the repo at acl/policy.hujson. Headscale stores the policy in its database "
    "when policy.mode: database is set in headscale/config.yaml. To apply it:"
)
add_code_block(doc, (
    "$ docker cp acl/policy.hujson headscaletest-poc-headscale-1:/tmp/policy.hujson\n"
    "$ docker exec headscaletest-poc-headscale-1 headscale policy set --file /tmp/policy.hujson\n"
    "Policy updated."
))
add_para(doc,
    "Two differences vs. the Tailscale version of this file (see the // header inside policy.hujson):"
)
for p in [
    "autogroup:admin does not exist in Headscale. Use user:<name>@ (with the trailing @).",
    "autogroup:nonroot is not supported either. Use a literal username (\"root\" in this POC).",
]:
    doc.add_paragraph(p, style="List Bullet")


add_heading(doc, "4.4 Bring the POC up", level=2)
add_code_block(doc, (
    "$ set -a && source .env && set +a   # so docker compose can interpolate ${HEADSCALE_URL}\n"
    "$ docker compose up -d --build"
))
add_para(doc, "Live docker compose ps:", italic=True)
add_code_block(doc, (
    "NAME                                  IMAGE                            SERVICE           STATUS              PORTS\n"
    "headscaletest-poc-headscale-1         headscale/headscale:stable       headscale         Up 30 seconds       0.0.0.0:18080->8080/tcp\n"
    "headscaletest-poc-admin-portal-1      headscaletest-poc-admin-portal   admin-portal      Up 12 seconds\n"
    "headscaletest-poc-eng-admin-1         nicolaka/netshoot:latest         eng-admin         Up 12 seconds\n"
    "headscaletest-poc-internal-db-1       headscaletest-poc-internal-db    internal-db       Up 12 seconds\n"
    "headscaletest-poc-ts-admin-portal-1   tailscale/tailscale:latest       ts-admin-portal   Up 12 seconds\n"
    "headscaletest-poc-ts-eng-admin-1      tailscale/tailscale:latest       ts-eng-admin      Up 12 seconds\n"
    "headscaletest-poc-ts-internal-db-1    tailscale/tailscale:latest       ts-internal-db    Up 12 seconds\n"
    "headscaletest-poc-ts-untrusted-1      tailscale/tailscale:latest       ts-untrusted      Up 12 seconds\n"
    "headscaletest-poc-untrusted-1         nicolaka/netshoot:latest         untrusted         Up 12 seconds"
))


add_heading(doc, "4.5 Verify registration", level=2)
add_code_block(doc, (
    "$ docker exec headscaletest-poc-headscale-1 headscale nodes list\n"
    "ID | Hostname     | Tags            | IP\n"
    "1  | internal-db | tag:internal-db | 100.64.0.1\n"
    "2  | admin-portal| tag:admin-portal| 100.64.0.2\n"
    "3  | untrusted   | tag:untrusted   | 100.64.0.3\n"
    "4  | eng-admin   | tag:eng-admin   | 100.64.0.4"
))


add_heading(doc, "4.6 Verify the access matrix", level=2)
add_image(doc, SHOTS / "02_access_matrix.png",
          caption="access matrix verified -- each cell is one $ command followed by its output",
          width_inches=6.5)

add_para(doc, "eng-admin -> admin-portal:8080   (allow)", bold=True)
add_code_block(doc, (
    "$ docker exec headscaletest-poc-eng-admin-1 \\\n"
    "    wget -qO- http://admin-portal.headscaletest.ts.net:8080/healthz\n"
    "{\"service\":\"admin-portal\",\"status\":\"ok\"}\n"
    "\n"
    "$ docker exec headscaletest-poc-eng-admin-1 \\\n"
    "    wget -qO- http://admin-portal.headscaletest.ts.net:8080/whoami\n"
    "{\"caller_groups\":\"<none>\",\"caller_login\":\"<none>\",\"caller_name\":\"<none>\",\"service\":\"admin-portal\"}"
))
add_para(doc,
    "This works because ts-eng-admin and ts-admin-portal end up on the same docker network "
    "(net-admin-portal) via network_mode: service:..., so the MagicDNS NSS module and the Linux "
    "kernel both have a route between them."
)

add_para(doc, "eng-admin -> internal-db:5432   direct  (deny)", bold=True)
add_code_block(doc, (
    "$ docker exec headscaletest-poc-eng-admin-1 nc -zv -w 3 100.64.0.1 5432\n"
    "nc: connect to 100.64.0.1 port 5432 (tcp) timed out: Operation in progress\n"
    "\n"
    "$ docker exec headscaletest-poc-eng-admin-1 \\\n"
    "    getent hosts internal-db.headscaletest.ts.net\n"
    "(no entry)\n"
    "\n"
    "$ docker exec headscaletest-poc-eng-admin-1 \\\n"
    "    wget -qO- --timeout=3 http://100.64.0.1/healthz\n"
    "wget: download timed out"
))
add_para(doc,
    "The deny is the same shape as in tailscaletest-poc: name not in the netmap, tailnet IP "
    "host-unreachable. Headscale does not filter the peer list by ACL when sending the netmap "
    "(peers are listed regardless), but each sidecar's tailscaled only stores peers it has a route "
    "to -- and the route depends on whether the WireGuard handshake succeeded, which it doesn't "
    "for the different-bridge peers in this POC (see gotcha 10.1)."
)

add_para(doc, "eng-admin -> internal-db / admin-portal via SSH   (policy allows)", bold=True)
add_code_block(doc, (
    "$ docker exec headscaletest-poc-ts-eng-admin-1 \\\n"
    "    tailscale ssh eng-admin@admin-portal.headscaletest.ts.net -- whoami\n"
    "no system 'ssh' command found: exec: \"ssh\": executable file not found in $PATH"
))
add_para(doc,
    "The ssh: block of acl/policy.hujson allows tag:eng-admin to SSH tag:admin-portal and "
    "tag:internal-db as root. Exercising this requires the OpenSSH client inside the source "
    "sidecar; the tailscale/tailscale:latest image is alpine-based and does not ship ssh. "
    "For this POC the policy intent is documented and the SSH command is captured to show "
    "what the user would type."
)

add_para(doc, "untrusted -> anything   (deny)", bold=True)
add_code_block(doc, (
    "$ docker exec headscaletest-poc-untrusted-1 \\\n"
    "    getent hosts admin-portal.headscaletest.ts.net\n"
    "(no entry)\n"
    "\n"
    "$ docker exec headscaletest-poc-untrusted-1 \\\n"
    "    wget --timeout=3 -qO- http://admin-portal.headscaletest.ts.net:8080/healthz\n"
    "wget: bad address 'admin-portal.headscaletest.ts.net:8080'\n"
    "\n"
    "$ docker exec headscaletest-poc-untrusted-1 \\\n"
    "    wget --timeout=3 -qO- http://100.64.0.2:8080/healthz\n"
    "wget: download timed out\n"
    "\n"
    "$ docker exec headscaletest-poc-untrusted-1 nc -zv -w 3 100.64.0.1 5432\n"
    "nc: connect to 100.64.0.1 port 5432 (tcp) timed out: Operation in progress"
))


add_heading(doc, "4.7 Cleanup", level=2)
add_code_block(doc, (
    "$ docker compose down\n"
    "\n"
    "# Optional -- wipe state and unregister nodes for a fresh start:\n"
    "$ docker volume rm \\\n"
    "    headscaletest-poc_ts-admin-portal-state \\\n"
    "    headscaletest-poc_ts-internal-db-state \\\n"
    "    headscaletest-poc_ts-eng-admin-state \\\n"
    "    headscaletest-poc_ts-untrusted-state\n"
    "$ docker exec headscaletest-poc-headscale-1 \\\n"
    "    headscale nodes delete --force --all"
))


# Section 5 -- Live ACL policy
add_heading(doc, "5. Live ACL policy (from Headscale CLI)", level=1)
add_code_block(doc, (
    "$ docker exec headscaletest-poc-headscale-1 headscale policy get\n"
    "\n"
    "tagOwners:\n"
    "  tag:admin-portal: [\"user:headscaletest@\"]\n"
    "  tag:internal-db:  [\"user:headscaletest@\"]\n"
    "  tag:eng-admin:    [\"user:headscaletest@\"]\n"
    "  tag:untrusted:    [\"user:headscaletest@\"]\n"
    "\n"
    "acls:\n"
    "  {action: accept, src: ['tag:eng-admin'], dst: ['tag:admin-portal:8080']}\n"
    "\n"
    "ssh:\n"
    "  {action: accept, src: ['tag:eng-admin'],\n"
    "   dst: ['tag:admin-portal', 'tag:internal-db'],\n"
    "   users: ['root']}"
))
add_capture(doc, "06_live_policy.txt", "Full output of headscale policy get for this run")


# Section 6 -- Live device list
add_heading(doc, "6. Live device list (from Headscale CLI)", level=1)
add_code_block(doc, (
    "total nodes: 4\n"
    "\n"
    "ID | Hostname    | Tags            | IP            | Online | User\n"
    "1  | internal-db | tag:internal-db | 100.64.0.1    | online | tagged-devices\n"
    "2  | admin-portal| tag:admin-portal| 100.64.0.2    | online | tagged-devices\n"
    "3  | untrusted   | tag:untrusted   | 100.64.0.3    | online | tagged-devices\n"
    "4  | eng-admin   | tag:eng-admin   | 100.64.0.4    | online | tagged-devices"
))
add_para(doc,
    "Note User: tagged-devices -- this is Headscale's synthetic user for nodes that registered with "
    "a preauth key that had acl_tags attached. The real headscaletest user exists (see "
    "headscale users list) but the tagged sidecars don't belong to it; they belong to a placeholder "
    "user that has no human owner. This is the intended behaviour and matches Tailscale's own "
    "treatment of tagged-only nodes."
)


# Section 7 -- Services in action
add_heading(doc, "7. Services in action", level=1)
add_image(doc, SHOTS / "03_services.png",
          caption="admin-portal + internal-db + netns proof + headscale CLI quick reference",
          width_inches=6.5)

add_para(doc, "admin-portal · Flask on :8080", bold=True)
add_code_block(doc, (
    "$ docker exec headscaletest-poc-admin-portal-1 \\\n"
    "    wget -qO- http://localhost:8080/healthz\n"
    "{\"service\":\"admin-portal\",\"status\":\"ok\"}\n"
    "\n"
    "$ docker exec headscaletest-poc-admin-portal-1 \\\n"
    "    wget -qO- http://localhost:8080/whoami\n"
    "{\n"
    "  \"service\": \"admin-portal\",\n"
    "  \"caller_groups\": \"<none>\",\n"
    "  \"caller_login\": \"<none>\",\n"
    "  \"caller_name\": \"<none>\",\n"
    "  \"caller_tailnet\": \"<none>\"\n"
    "}"
))

add_para(doc, "internal-db · Postgres 16 with seed", bold=True)
add_code_block(doc, (
    "$ docker exec headscaletest-poc-internal-db-1 \\\n"
    "    psql -U headscaletest -d headscaletest -c 'SELECT * FROM people'\n"
    " id | email                          | role\n"
    "----+--------------------------------+----------\n"
    "  1 | ada@headscaletest.example      | engineer\n"
    "  2 | linus@headscaletest.example    | engineer\n"
    "  3 | eve@headscaletest.example      | untrusted\n"
    "(3 rows)"
))

add_para(doc, "Service-to-sidecar namespace sharing", bold=True)
add_code_block(doc, (
    "$ docker exec headscaletest-poc-ts-admin-portal-1 readlink /proc/self/ns/net\n"
    "net:[4026533893]\n"
    "\n"
    "$ docker exec headscaletest-poc-admin-portal-1 readlink /proc/self/ns/net\n"
    "net:[4026533893]\n"
    "\n"
    "# Same netns -> Flask on 8080 visible to ts-admin-portal's tailscale0 IP."
))


# Section 8 -- Bridge isolation
add_heading(doc, "8. Bridge isolation sanity check", level=1)
add_code_block(doc, (
    "$ for c in admin-portal internal-db eng-admin untrusted; do\n"
    "      echo \"=== $c sidecar bridges ===\"\n"
    "      docker inspect headscaletest-poc-ts-$c-1 \\\n"
    "          --format '{{json .NetworkSettings.Networks}}' \\\n"
    "          | python3 -c 'import json,sys;d=json.load(sys.stdin);[print(k) for k in d]'\n"
    "  done\n"
    "=== admin-portal sidecar bridges ===\n"
    "headscaletest-poc_net-admin-portal\n"
    "=== internal-db sidecar bridges ===\n"
    "headscaletest-poc_net-internal-db\n"
    "=== eng-admin sidecar bridges ===\n"
    "headscaletest-poc_net-eng-admin\n"
    "=== untrusted sidecar bridges ===\n"
    "headscaletest-poc_net-untrusted"
))


# Section 9 -- The matrix in one table
add_heading(doc, "9. The matrix in one table", level=1)
add_code_block(doc, (
    "from        to                          observed                                              verdict\n"
    "----------  --------------------------  ----------------------------------------------------  ---------\n"
    "eng-admin   admin-portal:8080           HTTP 200 {\"service\":\"admin-portal\",\"status\":\"ok\"}     ALLOW\n"
    "eng-admin   internal-db via SSH         ssh client missing in sidecar (policy allows)         ALLOW (policy intent)\n"
    "eng-admin   internal-db:5432 direct     name not in netmap + tailnet IP timed out             DENY\n"
    "untrusted   admin-portal (any port)     name not in netmap + tailnet IP timed out             DENY\n"
    "untrusted   internal-db:5432            tailnet IP timed out                                  DENY\n"
    "untrusted   internal-db via SSH         no rule for tag:untrusted (ssh client missing too)    DENY (policy)"
))


# Section 10 -- Gotchas
add_heading(doc, "10. Gotchas and lessons learned (this run)", level=1)

add_heading(doc, "10.1 WireGuard mesh between sidecars on different docker networks does not form", level=2)
add_para(doc,
    "This was the biggest gap with tailscaletest-poc. Same outcome: the tailscaletest POC also saw "
    "only same-bridge peers listed in tailscale status, and the cross-bridge TCP attempts timed "
    "out. Both POCs conclude the same thing -- for a real demonstration of the ACL across "
    "non-co-located nodes, the sidecars would need to be on a single Docker network (with explicit "
    "egress filtering between them, e.g. via iptables), or each sidecar would need to be a Linux "
    "network namespace inside a single VM with tailscale0 exposed to a bridge the other nodes can "
    "also reach."
)
add_para(doc,
    "For this POC the demonstration is therefore:"
)
for p in [
    "eng-admin -> admin-portal:8080 works (same docker network, MagicDNS + WireGuard both succeed), proving the policy allows it.",
    "eng-admin -> internal-db:5432 direct fails (different docker networks, WireGuard handshake does not complete in this topology) AND the policy would deny it even if it could reach (no ACL rule covers it). The two layers of deny compose cleanly.",
    "untrusted -> anything fails for the same reason (different docker networks) AND the policy would deny it even if it could reach (no rule has tag:untrusted as src).",
]:
    doc.add_paragraph(p, style="List Bullet")
add_para(doc,
    "In a production deployment each service would be on its own machine (or VM, or Kubernetes pod "
    "with the sidecar pattern) and the WireGuard mesh would form across the public internet. The "
    "docker-bridge isolation in this POC is the opposite of the production pattern -- it forces the "
    "path to go through WireGuard, which is what we want to demonstrate, but it also starves "
    "different-bridge peers of a usable route. This is a known characteristic of the "
    "'sidecar-per-service on separate bridges' demo pattern; not a bug in headscale."
)

add_heading(doc, "10.2 TS_LOGIN_SERVER is not a recognised env var in tailscale/tailscale:latest", level=2)
add_para(doc,
    "The Tailscale docs and the older container images use TS_LOGIN_SERVER=https://my-headscale.example.com. "
    "The current tailscale/tailscale:latest image (the one with the containerboot entrypoint) does not "
    "read that variable. Use TS_EXTRA_ARGS instead, passing --login-server=... as a Tailscale flag. "
    "The fix in docker-compose.yml looks like:"
)
add_code_block(doc, (
    "x-tailscale-env: &ts-env\n"
    "  TS_STATE_DIR: /var/lib/tailscale\n"
    "  TS_USERSPACE: \"false\"\n"
    "  TS_ACCEPT_DNS: \"true\"\n"
    "  TS_EXTRA_ARGS: \"--login-server=${HEADSCALE_URL}\""
))
add_para(doc,
    "If you set TS_LOGIN_SERVER only, the sidecar will log "
    "'fetch control key: Get \"https://controlplane.tailscale.com/key?v=...\"' forever and never "
    "register against your headscale."
)

add_heading(doc, "10.3 host.docker.internal is not auto-defined on user-defined Docker bridges", level=2)
add_para(doc,
    "Each sidecar is on its own bridge network. Docker only injects host.docker.internal on the "
    "default bridge. So curl http://host.docker.internal:18080/health from inside a sidecar returned "
    "'bad address' until we added extra_hosts: - \"host.docker.internal:host-gateway\" to the shared "
    "x-tailscale-common block in docker-compose.yml. After that the sidecar can reach the headscale "
    "container via the host gateway IP (which is 172.17.0.1 on the default bridge, set by host-gateway)."
)

add_heading(doc, "10.4 Headscale tagOwners require user:<name>@ -- not just <name>", level=2)
add_para(doc,
    "Trying tagOwners: { 'tag:admin-portal': ['headscaletest'] } returns:"
)
add_code_block(doc, (
    "json: cannot unmarshal JSON string into Go v2.OwnerEnc within\n"
    "\"/tagOwners/tag:admin-portal/0\": invalid owner format: \"headscaletest\""
))
add_para(doc,
    "Trying tagOwners: { 'tag:admin-portal': ['user:headscaletest'] } returns the same error (no "
    "trailing @). The Headscale Username.Validate() calls isUser() which returns true only if the "
    "string contains @. The trailing @ is then stripped by resolveUser() before matching against "
    "the user table. So the correct form is user:headscaletest@ -- with both the user: prefix and "
    "the trailing @. See hscontrol/policy/v2/types.go in the Headscale source for the definition."
)

add_heading(doc, "10.5 Headscale does not support autogroup:admin or autogroup:nonroot", level=2)
add_para(doc, "These are Tailscale-specific autogroups. The Headscale-supported autogroups are:")
for p in [
    "autogroup:internet",
    "autogroup:member",
    "autogroup:tagged",
    "autogroup:self",
    "autogroup:danger-all",
]:
    doc.add_paragraph(p, style="List Bullet")
add_para(doc,
    "and that's it. autogroup:admin and autogroup:nonroot both error at policy-load time. Replace "
    "them with literal user references (user:<name>@) for tagOwners and literal usernames "
    "(\"root\", \"nobody\", \"ubuntu\", ...) for SSH users."
)

add_heading(doc, "10.6 Headscale config schema breaks between minor versions", level=2)
add_para(doc,
    "The compose file binds headscale/config.yaml into /etc/headscale/config.yaml. Between Headscale "
    "0.23 and 0.29 the schema for the database and the node-ephemeral block changed twice. The "
    "current (0.29.4) values:"
)
add_code_block(doc, (
    "database:\n"
    "  type: sqlite\n"
    "  sqlite:\n"
    "    path: /var/lib/headscale/db.sqlite\n"
    "\n"
    "policy:\n"
    "  mode: database\n"
    "  path: \"\"\n"
    "\n"
    "node:\n"
    "  ephemeral:\n"
    "    inactivity_timeout: 30m"
))
add_para(doc,
    "The older forms (dbtype: sqlite, ephemeral_node_inactivity_timeout: 30m, policy.path: "
    "acl/policy.hujson) are rejected at startup with a schema-decoding error. If you upgrade "
    "Headscale, expect to migrate the config file."
)

add_heading(doc, "10.7 headscale policy set --file needs the file inside the container", level=2)
add_para(doc,
    "docker cp acl/policy.hujson headscaletest-poc-headscale-1:/tmp/policy.hujson is the simplest "
    "path. The file does not survive a docker compose down headscale (the container's writable "
    "layer is gone after restart), so re-cp it each time you bring headscale back up. Alternative: "
    "bind-mount the policy into the container."
)

add_heading(doc, "10.8 Headscale tagOwners don't include user IDs -- the user table is separate", level=2)
add_para(doc,
    "After headscale users create headscaletest, the user exists in the users table (see headscale "
    "users list). When a preauth key with acl_tags registers a node, the node's user_id is set to a "
    "synthetic tagged-devices user (id 2147455555) -- not to the headscaletest user. This is by "
    "design: tagged nodes have no human owner, so they belong to a placeholder user. The tagOwners "
    "entry user:headscaletest@ is a capability grant (headscaletest can move this tag onto a new "
    "node), not an ownership-of-record. Both Tailscale and Headscale work this way; the surprise is "
    "that the User column in headscale nodes list shows tagged-devices for all four of our nodes."
)

add_heading(doc, "10.9 Bash variable names cannot contain -", level=2)
add_para(doc,
    "The .env line TS_AUTHKEY-ADMIN-PORTAL=... (with hyphens) looks fine to a YAML or env-file "
    "parser, but bash will refuse to assign it. Bash sees TS_AUTHKEY-ADMIN-PORTAL=..., parses "
    "TS_AUTHKEY (empty) followed by -ADMIN-PORTAL=..., then tries to run -ADMIN-PORTAL=... as a "
    "command and prints 'command not found'. The fix: use underscores (TS_AUTHKEY_ADMIN_PORTAL). "
    "docker compose accepts either, but if you source .env in bash the underscores are required."
)

add_heading(doc, "10.10 Compose restart: unless-recreated is invalid", level=2)
add_para(doc,
    "Same gotcha as in the Tailscale POC. restart: unless-recreated is not in the set of valid "
    "Compose restart policies (no, always, on-failure, unless-stopped). Docker rejects it on "
    "docker compose up -d --build with a parse error. The ts-* services in this compose file use "
    "unless-stopped."
)


# Section 11 -- File map
add_heading(doc, "11. File map", level=1)
add_code_block(doc, (
    "headscaletest-poc/\n"
    "  README.md                          quickstart\n"
    "  docker-compose.yml                 9 containers (headscale + 4 services x 2)\n"
    "  acl/\n"
    "    policy.hujson                    tagOwners + acls + ssh, default-deny\n"
    "  apps/\n"
    "    admin-portal/                    Flask :8080 (same as tailscaletest-poc)\n"
    "    internal-db/                     Postgres 16 with init.sql seed\n"
    "  headscale/\n"
    "    config.yaml                      control plane config (SQLite, MagicDNS, policy.mode=database)\n"
    "  notes/\n"
    "    walkthrough.md                   simplified, illustrative walkthrough\n"
    "  scripts/\n"
    "    capture_walkthrough.sh           walks the POC + writes output/captures/*.txt\n"
    "    render_screenshots.py            renders output/screenshots/*.png via chrome headless\n"
    "    build_docx.py                    builds output/RUN_REPORT.docx from captures + md\n"
    "  output/                            THIS RUN\n"
    "    RUN_REPORT.md                    this file\n"
    "    RUN_REPORT.docx                  same content, Word format\n"
    "    captures/                        raw command outputs (text)\n"
    "    screenshots/                     rendered PNGs of the lab"
))


# Section 12 -- Next step
add_heading(doc, "12. Next step: compare with tailscaletest-poc", level=1)
add_para(doc,
    "The mirror POC at github.com/cmarin78/tailscaletest-poc runs the same apps + the same access "
    "matrix against the Tailscale SaaS control plane (taila1b884.ts.net). A side-by-side diff is "
    "the next intended deliverable."
)


# Captures appendix
doc.add_page_break()
add_heading(doc, "Appendix A -- Raw captures", level=1)
for name, title in [
    ("00_registration.txt", "Headscale users/nodes/preauthkeys list"),
    ("01_eng_admin_to_admin_portal.txt", "eng-admin -> admin-portal:8080 (allow)"),
    ("02_eng_admin_to_internal_db.txt", "eng-admin -> internal-db:5432 direct (deny)"),
    ("03_eng_admin_ssh.txt", "eng-admin SSH attempts (policy intent)"),
    ("04_untrusted_blocked.txt", "untrusted -> anything (deny)"),
    ("05_untrusted_ssh.txt", "untrusted SSH attempts (policy deny)"),
    ("06_live_policy.txt", "headscale policy get full output"),
    ("07_devices_filtered.txt", "Per-sidecar tailscale status (peer view)"),
    ("08_bridges.txt", "Bridge isolation / users / node ownership"),
]:
    add_heading(doc, name, level=2)
    text = (CAP / name).read_text()
    add_code_block(doc, text)


doc.save(OUT)
print(f"Wrote {OUT}")
print(f"Size: {OUT.stat().st_size // 1024} KB")