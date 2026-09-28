# headscaletest-poc

Minimal, experimental POC: **tag-based ACLs with a self-hosted Headscale control plane**.

No scripts. No `heliosctl`. No `verify.sh`. Just `docker compose`, `curl`,
`headscale` CLI, `tailscale status`, and the actual outputs from running them.
The point of this repo is to be small enough to read top-to-bottom in one
sitting, and reproducible by hand in under 30 minutes.

This is the **Headscale self-hosted** half of a two-repo comparison. The
parallel **Tailscale SaaS** variant lives in
[`cmarin78/tailscaletest-poc`](https://github.com/cmarin78/tailscaletest-poc).
The access matrix, the topology, and the apps are intentionally identical
between the two repos so that switching from one control plane to the other
is a single `docker compose down && docker compose -f … up -d` away.

## What this POC demonstrates

That a four-node tailnet, served by a local Headscale, can encode the
following matrix purely in `acl/policy.hujson`, with no app-level auth, no
firewall rules, no bastion host:

| from         | to                          | result                                  |
| ------------ | --------------------------- | --------------------------------------- |
| `eng-admin`  | `admin-portal:8080`         | allowed                                 |
| `eng-admin`  | `internal-db` (via SSH)     | allowed                                 |
| `eng-admin`  | `internal-db:5432` (direct) | **denied** (SSH is the only door)       |
| `untrusted`  | anything                    | **denied** (no `src` includes it)       |

Everything not listed is denied by default. Headscale inherits Tailscale's
default-deny semantics for `acls`/`ssh`.

## What's different from `tailscaletest-poc`

Only two things change when moving from SaaS Tailscale to self-hosted Headscale:

1. **The control plane runs in this repo.** A `headscale` container in
   `docker-compose.yml` listens on `localhost:8080`. The host runs the
   `headscale` CLI against it.
2. **Auth keys come from `headscale preauthkeys create`, not the Tailscale
   admin console.** Tags are still pre-assigned at key generation.

Everything else is identical: same `docker-compose.yml` layout, same
`acl/policy.hujson`, same `apps/`, same isolation principle (one bridge per
sidecar, plus a `host.docker.internal` connection for one-shot registration
that does not give any persona container a direct route to any service).

## Topology (5 containers, 4 tailnet nodes)

```
Headscale control plane (localhost:8080 on the host)

ts-admin-portal  ── shares netns with ── admin-portal   (Flask :8080, tag:admin-portal)
ts-internal-db   ── shares netns with ── internal-db    (Postgres :5432, tag:internal-db)
ts-eng-admin     ── shares netns with ── eng-admin      (netshoot, tag:eng-admin)
ts-untrusted     ── shares netns with ── untrusted      (netshoot, tag:untrusted)
```

The real services never publish ports to the host. Each `ts-*` sidecar
attaches to exactly one Docker bridge (`net-admin-portal`, `net-internal-db`,
`net-eng-admin`, `net-untrusted`). The only cross-container network path
between any two sidecars is the WireGuard overlay.

## Prerequisites

- Docker + Docker Compose v2 (`docker compose version` ≥ 2.20)
- `curl`, `jq`
- A few minutes. No SaaS account required.

## Replication, step by step

### 1. Bring up Headscale

```bash
$ docker compose up -d --build headscale
[+] Running 3/3
 ✔ Network headscaletest-poc_default  Created
 ✔ Volume headscaletest-poc_headscale-data  Created
 ✔ Container headscaletest-poc-headscale-1  Started
```

Wait until the container is healthy. Headscale creates its keys and DB on
first start.

```bash
$ docker exec headscaletest-poc-headscale-1 headscale nodes register --help
# If you see the usage message, the server is ready.
```

### 2. Create one user, then four preauth keys (one per tag)

```bash
$ USER=headscaletest
$ docker exec headscaletest-poc-headscale-1 headscale users create "$USER"
User "$USER" created
```

```bash
$ for tag in admin-portal internal-db eng-admin untrusted; do
    docker exec headscaletest-poc-headscale-1 \
        headscale preauthkeys create \
            --user "$USER" \
            --reusable \
            --expiration 720h \
            --tags "tag:$tag"
done
c12a3... (admin-portal)
e94ff... (internal-db)
a0bc1... (eng-admin)
77d12... (untrusted)
```

Each line is a fresh key, tagged for one specific node.

### 3. Apply the ACL policy

```bash
$ docker exec -i headscaletest-poc-headscale-1 headscale policy set --file - < acl/policy.hujson
Policy updated
```

Verify:

```bash
$ docker exec headscaletest-poc-headscale-1 headscale policy get \
    | jq '.tagOwners | keys'
[
  "tag:admin-portal",
  "tag:eng-admin",
  "tag:internal-db",
  "tag:untrusted"
]
```

### 4. Drop the keys into `.env`

```bash
$ cp .env.example .env
$ $EDITOR .env
# paste each key into the matching TS_AUTHKEY_* variable
```

### 5. Bring the rest of the POC up

```bash
$ docker compose up -d --build
```

Wait until `docker compose ps` shows every container `Up`:

```bash
$ sleep 5 && docker compose ps
NAME                            SERVICE             PORTS
headscaletest-poc-headscale-1   headscale           0.0.0.0:8080->8080/tcp
ts-admin-portal-1               ts-admin-portal
admin-portal-1                  admin-portal
ts-internal-db-1                ts-internal-db
internal-db-1                   internal-db
ts-eng-admin-1                  ts-eng-admin
eng-admin-1                     eng-admin
ts-untrusted-1                  ts-untrusted
untrusted-1                     untrusted
```

### 6. Walk through the access matrix

See [`notes/walkthrough.md`](notes/walkthrough.md) for the exact command-by-command
verification: every cell of the access matrix above, run as raw
`docker exec … curl`, `headscale nodes list`, and `tailscale status`, with the
actual outputs.

### 7. Cleanup

```bash
$ docker compose down -v
```

Then in the headscale container:

```bash
$ docker exec headscaletest-poc-headscale-1 headscale nodes list -i
# delete each node by ID, then:
$ docker volume rm headscaletest-poc_headscale-data
```

## File map

```
.
├── README.md                    this file
├── .gitignore
├── .env.example                 template — copy to .env
├── docker-compose.yml           1 control plane + 4 services × 4 personas
├── headscale/
│   └── config.yaml              control plane config (server_url, prefixes, db, dns)
├── acl/
│   └── policy.hujson            tagOwners + acls + ssh, default-deny
└── apps/
    ├── admin-portal/            Flask :8080
    └── internal-db/             Postgres 16 with init.sql seed
```

## Repository policy

- No real keys, tokens, or `nodekey-…` values are ever committed.
  `.env.example` is the only place those literals appear, and they are
  placeholders.
- The walkthrough's outputs are illustrative: they match what the POC
  produces on a clean run, but they are not extracted from a single canonical run.