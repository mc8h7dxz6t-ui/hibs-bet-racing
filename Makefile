# Institutional++ portfolio — plug / demo / run
# Sports (hibs-racing) targets are unchanged; inst++ targets are prefixed or grouped below.

.PHONY: help install demo-ready demo demo-all demo-phase2 demo-gold demo-gold-up demo-gold-down demo-gold-reset \
        smoke rigorous chaos test instpp-test workflow-up workflow-down

PYTHON ?= python3
DEMO_DIR ?= ./data/demo/portfolio
GOLD_DIR ?= ./data/demo/spend_gold

help:
	@echo "Institutional++ (inst++) — plug / demo / run"
	@echo ""
	@echo "  make install          pip install -e \".[dev,instpp]\""
	@echo "  make demo-ready       preflight: deps, CLIs, quick sanity"
	@echo "  make demo-all         all 11 SKU demos → $(DEMO_DIR)/"
	@echo "  make demo-phase2      drift-gate + webhook-replay + spend-guard only"
	@echo "  make demo-gold        canonical spend-plane walkthrough (11 steps, CLI)"
	@echo "  make demo-gold-reset  wipe spend-gold wallet after drift lockout"
	@echo "  make demo-gold-up     prep portfolio data + start workflow UI (optional)"
	@echo "  make demo-gold-down   stop workflow UI"
	@echo "  make smoke            unit + integration smoke (113+ tests)"
	@echo "  make rigorous         11/11 rigorous E2E → docs/test_logs/"
	@echo "  make chaos            chaos + integration drills"
	@echo "  make test             full pytest suite"
	@echo ""
	@echo "Quick start:  make install && make demo-ready && make demo-all"
	@echo "Docs:         docs/RUN_DEMO.md"

install:
	$(PYTHON) -m pip install -e ".[dev,instpp]"

demo-ready:
	./scripts/demo_ready.sh

demo demo-all:
	SKIP_LIVE=$${SKIP_LIVE:-0} ./scripts/demo_portfolio_all.sh $(if $(CLEAN),--clean,)

demo-phase2:
	./scripts/demo_phase2_all.sh

demo-gold:
	./scripts/demo_gold.sh

demo-gold-reset:
	rm -f "$(GOLD_DIR)/spend_wallet.sqlite" "$(GOLD_DIR)/spend_guard.sqlite" \
		"$(GOLD_DIR)/spend_guard_bundle.tar"
	@echo "[OK] spend-gold state reset — rerun: make demo-gold"

demo-gold-up:
	./scripts/demo_gold_up.sh

demo-gold-down:
	./scripts/demo_gold_down.sh

spend-gateway:
	SPEND_GUARD_MOCK_UPSTREAM=1 spend-guard serve --mock-upstream

workflow-up: demo-gold-up

workflow-down: demo-gold-down

smoke:
	./scripts/instpp_smoke_test.sh

rigorous:
	./scripts/instpp_rigorous_test.sh

chaos:
	./scripts/chaos_instpp.sh

test instpp-test:
	$(PYTHON) -m pytest
