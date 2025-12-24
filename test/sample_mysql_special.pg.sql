/* MySQL special-syntax regression sample for mysql2pgsql */ /* Notes: */ /* 1) This file intentionally mixes DDL + DML + MySQL-only constructs. */ /* 2) Some statements are expected to emit -- TODO / -- ERROR depending on sqlglot support. */ /* 1) DDL: table options, unsigned, auto_increment, charset/collate, inline indexes, FULLTEXT */ CREATE TABLE "users" ("id" BIGINT NOT NULL GENERATED AS IDENTITY, "username" VARCHAR(255) NOT NULL, "email" VARCHAR(255) NOT NULL, "status" ENUM('active', 'disabled', 'pending') NOT NULL DEFAULT 'pending', "meta" JSON NULL, "created_at" TIMESTAMPTZ NULL DEFAULT CURRENT_TIMESTAMP, "updated_at" TIMESTAMPTZ NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY ("id"), CONSTRAINT "uniq_email" UNIQUE ("email"));
-- TODO: column "updated_at" used MySQL 'ON UPDATE CURRENT_TIMESTAMP'; implement via trigger in PostgreSQL
CREATE INDEX "idx_username" ON "users" ("username");
CREATE INDEX "idx_compound" ON "users" ("username", "created_at");
CREATE INDEX "ft_username" ON "users" USING GIN (to_tsvector('simple', COALESCE("username"::text, '')));

/* 2) DDL: generated column, check constraint (MySQL 8+), index prefix length */ CREATE TABLE "orders" ("id" DECIMAL(20, 0) NOT NULL GENERATED AS IDENTITY, "user_id" BIGINT NOT NULL, "order_no" VARCHAR(64) NOT NULL, "payload" JSON NOT NULL, "amount_cents" INT NOT NULL, "amount" DECIMAL(10, 2) GENERATED ALWAYS AS (CAST("amount_cents" AS DOUBLE PRECISION) / NULLIF(100, 0)) STORED, "note" TEXT, PRIMARY KEY ("id"), CONSTRAINT "chk_amount_nonneg" CHECK ("amount_cents" >= 0));
CREATE INDEX "idx_order_no_prefix" ON "orders" ("ORDER_NO"(16));

ALTER TABLE "orders" ADD CONSTRAINT "fk_orders_user" FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE CASCADE /* 3) DDL: foreign key + named constraint + on delete cascade */;

/* 4) MySQL-specific INSERT forms */ INSERT INTO "users" ("username", "email", "status") VALUES ('alice', 'alice@example.com', 'active'), ('bob', 'bob@example.com', 'pending') ON CONFLICT DO NOTHING;

-- TODO: Cannot reliably convert without knowing conflict target/constraints; consider ON CONFLICT
-- INSERT INTO `users` (`username`, `email`, `status`) VALUES ('alice2', 'alice@example.com', 'active') ON DUPLICATE KEY UPDATE `username` = VALUES(`username`), `updated_at` = CURRENT_TIMESTAMP();

-- TODO: Unsupported MySQL-specific syntax; manual rewrite required
-- REPLACE INTO `users` (`id`, `username`, `email`, `status`) VALUES
--   (1, 'alice_replaced', 'alice@example.com', 'active')

/* 5) Query syntax differences: backticks, LIMIT offset,count, IF/IFNULL, DATE_FORMAT */ SELECT "id", COALESCE(JSON_EXTRACT_PATH_TEXT("meta", 'country'), 'unknown') AS country, CASE WHEN "status" = 'active' THEN 1 ELSE 0 END AS is_active, TO_CHAR("created_at", 'YYYY-MM-DD') AS day FROM "users" WHERE "email" LIKE '%@example.com' ORDER BY "created_at" DESC NULLS LAST LIMIT 20 OFFSET 10;

/* 6) MySQL REGEXP and JSON operators */ SELECT "id" FROM "users" WHERE "email" ~ '^[a-z]+';

SELECT JSON_EXTRACT_PATH("payload", 'items', '0', 'sku') AS sku FROM "orders" LIMIT 5;

/* 7) MySQL comment edge cases */ SELECT 1;

/* end-of-line comment */;

/* inline */ SELECT 2;
