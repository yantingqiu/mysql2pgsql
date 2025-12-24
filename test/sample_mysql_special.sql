-- MySQL special-syntax regression sample for mysql2pgsql
-- Notes:
-- 1) This file intentionally mixes DDL + DML + MySQL-only constructs.
-- 2) Some statements are expected to emit -- TODO / -- ERROR depending on sqlglot support.

/* 1) DDL: table options, unsigned, auto_increment, charset/collate, inline indexes, FULLTEXT */
CREATE TABLE `users` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) NOT NULL,
  `status` enum('active','disabled','pending') NOT NULL DEFAULT 'pending',
  `meta` json NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_email` (`email`),
  KEY `idx_username` (`username`),
  KEY `idx_compound` (`username`, `created_at`),
  FULLTEXT KEY `ft_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

/* 2) DDL: generated column, check constraint (MySQL 8+), index prefix length */
CREATE TABLE `orders` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int unsigned NOT NULL,
  `order_no` varchar(64) NOT NULL,
  `payload` json NOT NULL,
  `amount_cents` int NOT NULL,
  `amount` decimal(10,2) GENERATED ALWAYS AS (`amount_cents` / 100) STORED,
  `note` text,
  PRIMARY KEY (`id`),
  KEY `idx_order_no_prefix` (`order_no`(16)),
  CONSTRAINT `chk_amount_nonneg` CHECK (`amount_cents` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

/* 3) DDL: foreign key + named constraint + on delete cascade */
ALTER TABLE `orders`
  ADD CONSTRAINT `fk_orders_user`
  FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
  ON DELETE CASCADE;

/* 4) MySQL-specific INSERT forms */
INSERT IGNORE INTO `users` (`username`, `email`, `status`) VALUES
  ('alice', 'alice@example.com', 'active'),
  ('bob', 'bob@example.com', 'pending');

INSERT INTO `users` (`username`, `email`, `status`) VALUES ('alice2', 'alice@example.com', 'active')
ON DUPLICATE KEY UPDATE
  `username` = VALUES(`username`),
  `updated_at` = CURRENT_TIMESTAMP;

REPLACE INTO `users` (`id`, `username`, `email`, `status`) VALUES
  (1, 'alice_replaced', 'alice@example.com', 'active');

/* 5) Query syntax differences: backticks, LIMIT offset,count, IF/IFNULL, DATE_FORMAT */
SELECT
  `id`,
  IFNULL(`meta`->>'$.country', 'unknown') AS country,
  IF(`status` = 'active', 1, 0) AS is_active,
  DATE_FORMAT(`created_at`, '%Y-%m-%d') AS day
FROM `users`
WHERE `email` LIKE '%@example.com'
ORDER BY `created_at` DESC
LIMIT 10, 20;

/* 6) MySQL REGEXP and JSON operators */
SELECT `id` FROM `users` WHERE `email` REGEXP '^[a-z]+';
SELECT JSON_EXTRACT(`payload`, '$.items[0].sku') AS sku FROM `orders` LIMIT 5;

/* 7) MySQL comment edge cases */
SELECT 1; -- end-of-line comment
SELECT /* inline */ 2;
