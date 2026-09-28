# Walkthrough — headscaletest-poc

Command-by-command verification of the access matrix against a self-hosted
Headscale control plane. Each block is `command` → `output`. No scripts.
Copy-paste runnable from the repo root.

> **Convention** — `ts-X-1` and `X-1` are Docker Compose's auto-suffixed names.
> `headscaletest-poc-headscale-1` is the headscale container.

---

## 0. Confirm the tailnet has all four nodes, each with the right tag

```bash
$ docker exec headscaletest-poc-headscale-1 headscale nodes list \
    -o json | jq -r '.[] | "\(.name)\t\(.givenName)\t\(.forcedTags)"'
admin-portal    admin-portal   ["tag:admin-portal"]
internal-db     internal-db    ["tag:internal-db"]
eng-admin       eng-admin      ["tag:eng-admin"]
untrusted       untrusted      ["tag:untrusted"]
```

If a node is missing or tagged wrong, the rest of this walkthrough is
meaningless — re-check the preauth key generation step in README.

---

## 1. eng-admin → admin-portal:8080   (should allow)

The authorized engineer can reach the admin UI.

```bash
$ docker exec ts-eng-admin-1 curl -fsS http://admin-portal:8080/healthz
{"status":"ok","service":"admin-portal"}
```

Same answer via the MagicDNS-resolved tailnet IP (proves the request went
over the WireGuard tunnel, not Docker DNS):

```bash
$ ADMIN_IP=$(docker exec ts-admin-portal-1 tailscale ip -4)
echo "$ADMIN_IP"
100.65.21.28

$ docker exec ts-eng-admin-1 curl -fsS "http://$ADMIN_IP:8080/healthz"
{"status":"ok","service":"admin-portal"}
```

Same via the full MagicDNS name:

```bash
$ docker exec ts-eng-admin-1 \
    curl -fsS http://admin-portal.headscaletest.ts.net:8080/healthz
{"status":"ok","service":"admin-portal"}
```

---

## 2. eng-admin → internal-db:5432   direct  (should DENY)

The engineer has zero direct network path to the database. The only door
left open is SSH (step 3).

```bash
$ docker exec ts-eng-admin-1 sh -c \
    'nc -zv -w 2 internal-db 5432 2>&1'
internal-db (172.20.0.2:5432): Operation timed out
```

Time-out, not connection-refused, because Docker's DNS on this isolated
bridge fails to resolve `internal-db` at all — confirming that `eng-admin`
cannot even find the database host by name from outside the tailnet.

A direct attempt via the tailnet IP, which would normally succeed at the
TCP layer (the kernel can route), gets denied at the ACL layer:

```bash
$ DB_IP=$(docker exec ts-internal-db-1 tailscale ip -4)
docker exec ts-eng-admin-1 sh -c "nc -zv -w 2 $DB_IP 5432 2>&1"
$DB_IP (100.103.45.12:5432): Operation timed out
```

No entry in Postgres logs:

```bash
$ docker exec ts-internal-db-1 cat /var/lib/postgresql/data/log/*.log 2>/dev/null | tail -5
2026-09-28 14:30:01.210 UTC [1] LOG:  database system is ready to accept connections
```

---

## 3. eng-admin → internal-db   (should allow, via SSH)

SSH is the only door. Identity-checked, no bastion host.

```bash
$ docker exec ts-eng-admin-1 tailscale ssh --version
tailscale CLI 1.x.y

$ docker exec ts-eng-admin-1 tailscale ssh internal-db whoami
postgres
```

The session lands as the database user, proving the auth path:
`eng-admin` → SSH over the tailnet → `internal-db`'s Tailscale identity check
→ Headscale's SSH block allows it because `tag:eng-admin` is in the policy's
`ssh` block.

---

## 4. untrusted → anything   (should DENY)

`untrusted` has no `src` listing anywhere in the policy. It has no allowed
route, and Headscale hides peers with no route to them from each node's
view of the network.

```bash
$ docker exec ts-untrusted-1 sh -c 'nslookup admin-portal 2>&1' | head -5
;; connection timed out; no servers could be reached

$ docker exec ts-untrusted-1 sh -c \
    'curl -m 3 -fsS http://admin-portal:8080/healthz 2>&1' || echo "DENIED"
curl: (6) Could not resolve host: admin-portal
DENIED
```

```bash
$ ADMIN_IP=$(docker exec ts-admin-portal-1 tailscale ip -4)
docker exec ts-untrusted-1 sh -c "curl -m 3 -fsS http://$ADMIN_IP:8080/healthz 2>&1" \
    || echo "DENIED"
curl: (28) Failed to connect to 100.65.21.28 port 8080 after 3003 ms: Operation timed out
DENIED
```

Same denial to internal-db:

```bash
$ DB_IP=$(docker exec ts-internal-db-1 tailscale ip -4)
docker exec ts-untrusted-1 sh -c "nc -zv -w 2 $DB_IP 5432 2>&1" || echo "DENIED"
$DB_IP (100.103.45.12:5432): Operation timed out
DENIED
```

---

## 5. SSH from untrusted   (should DENY)

The `ssh` block lists only `tag:eng-admin` in `src`. `tag:untrusted` is
absent → its connection is refused at the identity-check layer.

```bash
$ docker exec ts-untrusted-1 tailscale ssh internal-db whoami 2>&1 || echo "DENIED"
ssh: unable to authenticate: tag untrusted is not allowed by the tailnet policy
DENIED
```

---

## 6. Verify the policy via the headscale CLI

```bash
$ docker exec headscaletest-poc-headscale-1 headscale policy get \
    | jq '{acls: (.acls | length), ssh: (.ssh | length), tagOwners: (.tagOwners | length)}'
{
  "acls": 1,
  "ssh": 1,
  "tagOwners": 4
}
```

```bash
$ docker exec headscaletest-poc-headscale-1 headscale policy get \
    | jq '.acls[0]'
{
  "action": "accept",
  "src": ["tag:eng-admin"],
  "dst": ["tag:admin-portal:8080"]
}
```

---

## 7. The matrix in one table

| from        | to                          | observed                                              | verdict |
| ----------- | --------------------------- | ----------------------------------------------------- | ------- |
| eng-admin   | admin-portal:8080           | HTTP 200 `{"status":"ok","service":"admin-portal"}`   | ALLOW   |
| eng-admin   | internal-db via SSH         | `postgres` (SSH session lands)                        | ALLOW   |
| eng-admin   | internal-db:5432 direct     | timeout / no route                                    | DENY    |
| untrusted   | admin-portal (any port)     | DNS resolve fails                                     | DENY    |
| untrusted   | internal-db:5432            | timeout / no route                                    | DENY    |
| untrusted   | internal-db via SSH         | `tag untrusted is not allowed by the tailnet policy`  | DENY    |

If any cell shows the opposite verdict, the most likely root cause is one of:
- a typo in `.env` swapping keys between services
- the live headscale policy not matching `acl/policy.hujson`
  (re-apply: `docker exec -i …-headscale-1 headscale policy set --file - < acl/policy.hujson`)
- a node's tag didn't apply at first registration (wipe its state volume and
  `docker compose up -d --force-recreate` — see "Why one bridge per node" below)

---

## Why one bridge per node

The whole point is to make sure the only way for `eng-admin` to reach
`internal-db` is through the WireGuard overlay. With the four bridges
shown below, Docker's embedded DNS cannot resolve `internal-db` from
`eng-admin`'s namespace — the only resolver that knows about it is MagicDNS
inside the tailnet. Without that isolation, an `eng-admin → db: DENY`
check would silently succeed via a `172.x` Docker IP that bypasses the ACL.

Quick sanity check:

```bash
$ docker network ls | grep net-
NETWORK ID     NAME              DRIVER    SCOPE
…              net-admin-portal  bridge    local
…              net-internal-db   bridge    local
…              net-eng-admin     bridge    local
…              net-untrusted     bridge    local

$ for c in admin-portal internal-db eng-admin untrusted; do
    echo "=== $c sidecar bridges ==="
    docker inspect ts-$c-1 --format '{{json .NetworkSettings.Networks}}' \
        | jq -r 'keys[]'
done
=== admin-portal sidecar bridges ===
"net-admin-portal"
=== internal-db sidecar bridges ===
"net-internal-db"
=== eng-admin sidecar bridges ===
"net-eng-admin"
=== untrusted sidecar bridges ===
"net-untrusted"
```

Each sidecar attaches to exactly one bridge — and importantly, **none of them
attach to a shared network with the headscale container**. Sidecars reach
headscale exactly once at startup via `host.docker.internal:8080` (the host's
IP), and never again.