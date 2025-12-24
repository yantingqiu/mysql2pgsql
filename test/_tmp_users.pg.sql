CREATE TABLE "users" ("id" INT(11) NOT NULL GENERATED AS IDENTITY, "username" VARCHAR(255) NOT NULL, "email" VARCHAR(255) NOT NULL, "created_at" TIMESTAMPTZ NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY ("id"), CONSTRAINT "uniq_email" UNIQUE ("email"));
CREATE INDEX "idx_username" ON "users" ("username");
CREATE INDEX "idx_compound" ON "users" ("username", "created_at");
