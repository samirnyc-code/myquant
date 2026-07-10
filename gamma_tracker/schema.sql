-- MentorQ gamma-level tracker
-- One row per (date, level). Morning fields = captured before RTH from the
-- Backtest panel. Evening fields = filled after the cash close.
--
-- Usage:
--   sqlite3 gamma.db < schema.sql          # create the DB
--   .import --csv --skip 1 daily_log.csv daily_levels   # load a CSV of rows

CREATE TABLE IF NOT EXISTS daily_levels (
    date                 TEXT NOT NULL,          -- YYYY-MM-DD
    level_name           TEXT NOT NULL,          -- '1D Max', 'Call Res.', 'Put Support', ...
    level_price          REAL,

    -- ---- captured in the morning, from the panel ----
    regime_label         TEXT,                   -- if MentorQ ever exposes which regime today is
    regime_hold_rate_pct REAL,                   -- e.g. 89.07
    positive_outcomes    INTEGER,                -- e.g. 348  (the count they display)
    broke_at_close_pct   REAL,                   -- e.g. 10.9
    comeback_rate_pct    REAL,                   -- e.g. 43
    avg_move_intraday    REAL,                   -- 'Broke During Day' avg move, points
    worst_move_intraday  REAL,                   -- 'Broke During Day' worst, points
    median_close_beyond  REAL,                   -- 'Broke At Close' median, points
    avg_close_beyond     REAL,                   -- 'Broke At Close' avg close, points
    worst_close_beyond   REAL,                   -- 'Broke At Close' worst, points

    -- ---- captured after the close ----
    session_high         REAL,
    session_low          REAL,
    session_close        REAL,
    touched              INTEGER,                -- 0/1  did price reach the level intraday
    broke_intraday       INTEGER,                -- 0/1  did it pierce through
    max_excursion_beyond REAL,                   -- how far past the level, points (0 if not broken)
    closed_beyond        INTEGER,                -- 0/1  closed on the far side
    dist_beyond_at_close REAL,                   -- signed distance past level at close
    held                 INTEGER,                -- 0/1  MentorQ's 'positive outcome' (closed inside)
    notes                TEXT,

    PRIMARY KEY (date, level_name)
);

-- Reconstruct the never-reached / comeback / broke split from the panel's
-- four headline numbers, per the decomposition:
--   N               = positive_outcomes / hold_rate
--   closed_beyond   = N * broke_at_close_pct
--   comeback_days   = closed_beyond * cr/(1-cr)      where cr = comeback_rate
--   broke_intraday  = comeback_days + closed_beyond
--   never_reached   = N - broke_intraday
-- These are ESTIMATES from the vendor's aggregates; your logged columns above
-- are the ground truth you accumulate to check them.
CREATE VIEW IF NOT EXISTS v_decomposition AS
SELECT
    date,
    level_name,
    ROUND(positive_outcomes / (regime_hold_rate_pct/100.0))                              AS est_total_days,
    ROUND(positive_outcomes / (regime_hold_rate_pct/100.0) * (broke_at_close_pct/100.0)) AS est_closed_beyond,
    ROUND(positive_outcomes / (regime_hold_rate_pct/100.0) * (broke_at_close_pct/100.0)
          * (comeback_rate_pct/100.0) / (1 - comeback_rate_pct/100.0))                    AS est_comeback_days,
    ROUND(positive_outcomes / (regime_hold_rate_pct/100.0)
          - positive_outcomes / (regime_hold_rate_pct/100.0) * (broke_at_close_pct/100.0)
            * (1 + comeback_rate_pct/100.0/(1 - comeback_rate_pct/100.0)))                AS est_never_reached
FROM daily_levels
WHERE regime_hold_rate_pct IS NOT NULL
  AND broke_at_close_pct   IS NOT NULL
  AND comeback_rate_pct    IS NOT NULL;
