-- Atomic market steam / drift across feeds (multi-pod safe).
-- KEYS[1] = hash key runner:{runner_id}
-- ARGV[1] = feed name (pinnacle|singbet|betfair|matchbook)
-- ARGV[2] = current decimal odds
-- ARGV[3] = unix ts (seconds)
-- ARGV[4] = steam threshold pct (e.g. 8)
-- ARGV[5] = drift threshold pct (e.g. 12)
-- Returns JSON: {direction, change_pct, drift_delta, gate, prev_odds, odds_now}

local key = KEYS[1]
local feed = ARGV[1]
local odds = tonumber(ARGV[2])
local ts = tonumber(ARGV[3])
local steam_thr = tonumber(ARGV[4]) or 8
local drift_thr = tonumber(ARGV[5]) or 12

if odds == nil or odds <= 1 then
  return cjson.encode({err='invalid_odds'})
end

local prev = redis.call('HGET', key, feed)
local prev_ts = tonumber(redis.call('HGET', key, feed .. ':ts') or '0')
redis.call('HSET', key, feed, tostring(odds), feed .. ':ts', tostring(ts))
redis.call('EXPIRE', key, 86400)

if prev == false or prev == nil then
  return cjson.encode({direction='unknown', gate='proceed', odds_now=odds, prev_odds=nil})
end

local prev_odds = tonumber(prev)
if prev_odds == nil or prev_odds <= 1 then
  return cjson.encode({direction='unknown', gate='proceed', odds_now=odds, prev_odds=prev})
end

local change_pct = ((odds - prev_odds) / prev_odds) * 100
local direction = 'flat'
if change_pct <= -steam_thr then
  direction = 'steam'
elseif change_pct >= drift_thr then
  direction = 'drift'
end

local gate = 'proceed'
if direction == 'steam' then
  gate = 'scale_up'
elseif direction == 'drift' then
  gate = 'abort'
end

return cjson.encode({
  direction=direction,
  change_pct=change_pct,
  drift_delta=odds - prev_odds,
  gate=gate,
  prev_odds=prev_odds,
  odds_now=odds,
  feed=feed,
  age_sec=math.max(0, ts - prev_ts)
})
