CREATE TABLE articles (id INT PRIMARY KEY, content TEXT);
CREATE INDEX "ft_content" ON articles USING GIN (to_tsvector('simple', COALESCE(content::text, '')));
CREATE INDEX "idx_hash" ON articles USING hash (id);

CREATE OR REPLACE VIEW v_users AS SELECT * FROM users;

-- TODO: Cannot reliably convert without knowing conflict target/constraints; consider ON CONFLICT
-- INSERT INTO users (id, name) VALUES (1, 'Alice') ON DUPLICATE KEY UPDATE name = VALUES(name);

-- TODO: Unsupported MySQL-specific syntax; manual rewrite required
-- REPLACE INTO users (id, name) VALUES (1, 'Bob')

INSERT INTO logs (msg) VALUES ('error') ON CONFLICT DO NOTHING;

UPDATE users AS u SET vip = 1 FROM orders AS o WHERE u.id = o.user_id;

DELETE FROM logs WHERE ctid IN (SELECT ctid FROM logs WHERE created_at < '2020-01-01' LIMIT 1000);

SELECT 'Hello' || ' ' || 'World', STRING_AGG(name, '; ') FROM users;

SELECT NOW() + INTERVAL '1 WEEK', CAST(EXTRACT(EPOCH FROM CURRENT_TIMESTAMP) AS BIGINT);

SELECT CASE WHEN score > 60 THEN 'Pass' ELSE 'Fail' END, COALESCE(comment, 'No Comment') FROM grades;

SELECT JSON_EXTRACT_PATH(data, 'user', 'id') FROM api_logs;
