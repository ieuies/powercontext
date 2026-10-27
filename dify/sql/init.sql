-- 酒馆老板的记性：seekdb 初始化脚本
-- 用法：mysql -h127.0.0.1 -P2881 -uroot < sql/init.sql

CREATE DATABASE IF NOT EXISTS tavern DEFAULT CHARSET utf8mb4;
USE tavern;

CREATE TABLE IF NOT EXISTS players (
  player_id  VARCHAR(64)  NOT NULL PRIMARY KEY,
  name       VARCHAR(64)  NULL,
  created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
) DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS memories (
  id         BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  player_id  VARCHAR(64)  NOT NULL,
  kind       VARCHAR(16)  NOT NULL,
  content    TEXT         NOT NULL,
  session_id VARCHAR(64)  NOT NULL,
  created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_player (player_id),
  FULLTEXT INDEX ft_memory_content (content) WITH PARSER ik
) DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS turns (
  id              BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
  player_id       VARCHAR(64) NOT NULL,
  session_id      VARCHAR(64) NOT NULL,
  user_message    TEXT        NOT NULL,
  assistant_reply TEXT        NOT NULL,
  created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_player (player_id)
) DEFAULT CHARSET = utf8mb4;
