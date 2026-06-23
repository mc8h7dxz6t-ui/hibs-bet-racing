#!/usr/bin/env bash
# Scrape-first cache helpers — warm empty fixture bundle without API-Sports.
#
# Sourced by install_hands_off_automation.sh and hands_off_cycle.sh.
#   source /opt/hibs-bet/scripts/lib_scrape_first_cache.sh
#   scrape_first_cache_warm
set -euo pipefail

scrape_first_log() { echo "[scrape-first-cache] $*"; }
scrape_first_warn() { echo "[scrape-first-cache] WARN: $*" >&2; }

scrape_first_app_root() {
  echo "${DEPLOY_PATH:-/opt/hibs-bet}"
}

scrape_first_python() {
  local app
  app="$(scrape_first_app_root)"
  if [[ -x "${app}/.venv/bin/python3" ]]; then
    echo "${app}/.venv/bin/python3"
    return 0
  fi
  command -v python3
}

scrape_first_fixture_count() {
  local app py
  app="$(scrape_first_app_root)"
  py="$(scrape_first_python)"
  HOME="${app}" PYTHONPATH="${app}/src" HIBS_PRODUCTION=1 \
    "${py}" -c "from hibs_predictor.data_producer_slo import football_fixture_bundle_status; print(int(football_fixture_bundle_status().get('fixture_count') or 0))"
}

scrape_first_reset_rate_limits() {
  local app py
  app="$(scrape_first_app_root)"
  py="$(scrape_first_python)"
  HOME="${app}" PYTHONPATH="${app}/src" \
    "${py}" -c "from hibs_predictor.rate_limiter import RateLimiter; RateLimiter().reset_all(); print('rate_limit_state cleared')"
}

scrape_first_cache_warm() {
  local app py count
  app="$(scrape_first_app_root)"
  py="$(scrape_first_python)"
  export HOME="${app}"
  export DEPLOY_PATH="${app}"
  export PYTHONPATH="${app}/src"
  export HIBS_PRODUCTION=1

  scrape_first_log "warm fixtures (API off)"
  scrape_first_reset_rate_limits || scrape_first_warn "rate limit reset failed"

  if [[ -f "${app}/scripts/warm_football_fixtures.sh" ]]; then
    HIBS_FIXTURE_WARM_FORCE_REFRESH=1 bash "${app}/scripts/warm_football_fixtures.sh" || \
      scrape_first_warn "fixture warm failed"
  fi

  count="$(scrape_first_fixture_count 2>/dev/null || echo 0)"
  scrape_first_log "fixture_count=${count}"

  if [[ "${count}" -lt 1 ]]; then
    scrape_first_log "fetch empty — FotMob minimal seed"
    if [[ -f "${app}/scripts/seed_fotmob_minimal_bundle.py" ]]; then
      "${py}" "${app}/scripts/seed_fotmob_minimal_bundle.py" || scrape_first_warn "minimal seed failed"
    elif [[ -f "${app}/scripts/warm_low_source_scrape.sh" ]]; then
      HIBS_LOW_SOURCE_SCRAPE_FORCE=1 bash "${app}/scripts/warm_low_source_scrape.sh" || \
        scrape_first_warn "low-source scrape failed"
    fi
    count="$(scrape_first_fixture_count 2>/dev/null || echo 0)"
    scrape_first_log "fixture_count after seed=${count}"
  fi

  if [[ "${count}" -lt 1 ]]; then
    scrape_first_warn "bundle still empty — check FOOTBALL_DATA_ORG_KEY / FotMob / ESPN reachability"
    return 1
  fi
  return 0
}
