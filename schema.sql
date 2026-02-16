-- Normalized schema for Traders Union bot (PostgreSQL)

CREATE TABLE IF NOT EXISTS modlog_config (
  guild_id BIGINT PRIMARY KEY,
  channel_id BIGINT
);

CREATE TABLE IF NOT EXISTS audit_log_config (
  guild_id BIGINT PRIMARY KEY,
  channel_id BIGINT
);

CREATE TABLE IF NOT EXISTS welcome_config (
  guild_id BIGINT PRIMARY KEY,
  channel_id BIGINT
);

CREATE TABLE IF NOT EXISTS news_config (
  guild_id BIGINT PRIMARY KEY,
  news_channel_id BIGINT,
  reminder_channel_id BIGINT
);

CREATE TABLE IF NOT EXISTS session_alert_config (
  guild_id BIGINT PRIMARY KEY,
  channel_id BIGINT,
  session_role_id BIGINT,
  news_role_id BIGINT,
  last_asia_date TEXT,
  last_london_date TEXT
);

CREATE TABLE IF NOT EXISTS antilink_config (
  guild_id BIGINT PRIMARY KEY,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  punishment TEXT NOT NULL DEFAULT 'mute',
  duration_minutes INTEGER NOT NULL DEFAULT 60
);

CREATE TABLE IF NOT EXISTS antispam_config (
  guild_id BIGINT PRIMARY KEY,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  punishment TEXT NOT NULL DEFAULT 'mute',
  duration_minutes INTEGER NOT NULL DEFAULT 60,
  limit_count INTEGER NOT NULL DEFAULT 4
);

CREATE TABLE IF NOT EXISTS automod_caps_config (
  guild_id BIGINT PRIMARY KEY,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  punishment TEXT NOT NULL DEFAULT 'mute',
  duration_minutes INTEGER NOT NULL DEFAULT 10,
  ratio NUMERIC NOT NULL DEFAULT 0.5,
  min_len INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS automod_emoji_config (
  guild_id BIGINT PRIMARY KEY,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  punishment TEXT NOT NULL DEFAULT 'mute',
  limit_count INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS automod_bypass_role (
  guild_id BIGINT PRIMARY KEY,
  role_id BIGINT
);

CREATE TABLE IF NOT EXISTS afk_status (
  guild_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  reason TEXT NOT NULL,
  PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS ban_limits (
  guild_id BIGINT NOT NULL,
  admin_id BIGINT NOT NULL,
  day_key TEXT NOT NULL,
  count INTEGER NOT NULL,
  PRIMARY KEY (guild_id, admin_id, day_key)
);

CREATE TABLE IF NOT EXISTS attendance_config (
  guild_id BIGINT PRIMARY KEY,
  channel_id BIGINT,
  log_channel_id BIGINT,
  attendance_message_id BIGINT
);

CREATE TABLE IF NOT EXISTS attendance_batches (
  guild_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  batch_name TEXT NOT NULL,
  PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS attendance_records (
  guild_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  date_key TEXT NOT NULL,
  user_id BIGINT NOT NULL,
  status TEXT NOT NULL,
  time_label TEXT,
  username TEXT,
  PRIMARY KEY (guild_id, role_id, date_key, user_id)
);

CREATE TABLE IF NOT EXISTS union_points (
  guild_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  points INTEGER NOT NULL DEFAULT 0,
  name TEXT,
  username TEXT,
  last_updated TEXT,
  PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS union_logs (
  guild_id BIGINT NOT NULL,
  timestamp TEXT NOT NULL,
  manager_id BIGINT NOT NULL,
  manager_name TEXT NOT NULL,
  action TEXT NOT NULL,
  target_id BIGINT NOT NULL,
  target_name TEXT NOT NULL,
  points INTEGER NOT NULL,
  reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS union_managers (
  guild_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS union_leaderboard_config (
  guild_id BIGINT PRIMARY KEY,
  channel_id BIGINT,
  message_id BIGINT
);

CREATE TABLE IF NOT EXISTS union_log_channel (
  guild_id BIGINT PRIMARY KEY,
  channel_id BIGINT
);

CREATE TABLE IF NOT EXISTS giveaways (
  guild_id BIGINT NOT NULL,
  message_id BIGINT NOT NULL,
  channel_id BIGINT NOT NULL,
  prize TEXT NOT NULL,
  winners INTEGER NOT NULL,
  ends_at TEXT NOT NULL,
  required_role_id BIGINT,
  min_join_seconds INTEGER NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TEXT,
  ended_at TEXT,
  winner_ids TEXT,
  PRIMARY KEY (guild_id, message_id)
);

CREATE TABLE IF NOT EXISTS announcements (
  id SERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  channel_id BIGINT NOT NULL,
  run_at TEXT NOT NULL,
  content TEXT NOT NULL,
  sent BOOLEAN NOT NULL DEFAULT FALSE,
  sent_at TEXT
);

CREATE TABLE IF NOT EXISTS tickets_config (
  guild_id BIGINT PRIMARY KEY,
  panel_channel_id BIGINT,
  log_channel_id BIGINT,
  category_id BIGINT,
  auto_close_hours INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ticket_staff_roles (
  guild_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS ticket_reasons (
  guild_id BIGINT NOT NULL,
  reason TEXT NOT NULL,
  PRIMARY KEY (guild_id, reason)
);

CREATE TABLE IF NOT EXISTS tickets (
  guild_id BIGINT NOT NULL,
  channel_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  created_at TEXT NOT NULL,
  last_activity TEXT NOT NULL,
  reason TEXT,
  PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS sent_news (
  guild_id BIGINT NOT NULL,
  event_id TEXT NOT NULL,
  alert_sent BOOLEAN NOT NULL DEFAULT FALSE,
  reminder_sent BOOLEAN NOT NULL DEFAULT FALSE,
  msg_id BIGINT,
  actual TEXT,
  PRIMARY KEY (guild_id, event_id)
);

CREATE TABLE IF NOT EXISTS news_cache (
  event_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  country TEXT NOT NULL,
  date_utc TEXT NOT NULL,
  impact TEXT NOT NULL,
  forecast TEXT,
  actual TEXT,
  previous TEXT,
  fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snipe_cache (
  guild_id BIGINT NOT NULL,
  channel_id BIGINT NOT NULL,
  message_id BIGINT NOT NULL,
  author_id BIGINT,
  author_name TEXT,
  content TEXT,
  attachments TEXT,
  stickers TEXT,
  created_at TEXT,
  deleted_at TEXT,
  reply_to_message_id BIGINT,
  reply_to_author_id BIGINT
);
