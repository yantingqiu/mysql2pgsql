CREATE TABLE articles (
  id INT PRIMARY KEY,
  content TEXT,
  FULLTEXT KEY ft_content (content),
  KEY idx_hash (id) USING HASH
);

CREATE OR REPLACE DEFINER=`admin`@`%` VIEW v_users AS SELECT * FROM users;

INSERT INTO users (id, name) VALUES (1, 'Alice') 
ON DUPLICATE KEY UPDATE name = VALUES(name);

REPLACE INTO users (id, name) VALUES (1, 'Bob');

INSERT IGNORE INTO logs (msg) VALUES ('error');

UPDATE users u JOIN orders o ON u.id = o.user_id SET u.vip = 1;

DELETE FROM logs WHERE created_at < '2020-01-01' LIMIT 1000;

SELECT CONCAT("Hello", " ", "World"), GROUP_CONCAT(name SEPARATOR '; ') FROM users;

SELECT DATE_ADD(NOW(), INTERVAL 1 WEEK), UNIX_TIMESTAMP();

SELECT IF(score > 60, 'Pass', 'Fail'), IFNULL(comment, 'No Comment') FROM grades;

SELECT JSON_EXTRACT(data, '$.user.id') FROM api_logs;
