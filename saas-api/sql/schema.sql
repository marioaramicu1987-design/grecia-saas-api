-- Licențe Grecia Planner (SaaS)
-- Rulează pe o bază dedicată (ex. thassos_saas), separată de chat users din server/.

CREATE TABLE IF NOT EXISTS users (
  id               SERIAL PRIMARY KEY,
  email            VARCHAR(255) NOT NULL UNIQUE,
  is_pro           BOOLEAN      NOT NULL DEFAULT FALSE,
  bound_device_id  VARCHAR(128),
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email_pro ON users (email) WHERE is_pro = TRUE;

-- Entitlements per ghid (Kassandra etc.) — Thassos rămâne pe users.is_pro (legacy)
CREATE TABLE IF NOT EXISTS license_entitlements (
  id               SERIAL PRIMARY KEY,
  email            VARCHAR(255) NOT NULL,
  island_id        VARCHAR(32)  NOT NULL,
  bound_device_id  VARCHAR(128),
  source_order_id  VARCHAR(128),
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_license_entitlements_email_island UNIQUE (email, island_id)
);

CREATE INDEX IF NOT EXISTS idx_license_entitlements_email_island
  ON license_entitlements (email, island_id);

-- Coduri de deblocare (licență complementară: o aplicație, un dispozitiv)
CREATE TABLE IF NOT EXISTS unlock_codes (
  id               SERIAL PRIMARY KEY,
  code             VARCHAR(24)  NOT NULL UNIQUE,
  island_id        VARCHAR(32)  NOT NULL,
  note             VARCHAR(255),
  created_by       VARCHAR(255),
  bound_device_id  VARCHAR(128),
  redeemed_at      TIMESTAMPTZ,
  revoked_at       TIMESTAMPTZ,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unlock_codes_island ON unlock_codes (island_id);
