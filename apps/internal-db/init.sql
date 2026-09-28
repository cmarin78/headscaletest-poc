-- headscaletest internal-db seed schema.

CREATE TABLE IF NOT EXISTS people (
    id    SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    role  TEXT NOT NULL
);

INSERT INTO people (email, role) VALUES
    ('ada@headscaletest.example',   'engineer'),
    ('linus@headscaletest.example', 'engineer'),
    ('eve@headscaletest.example',   'untrusted');