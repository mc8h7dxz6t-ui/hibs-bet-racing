# Institutional++ portfolio — plug / demo / run
# Sports (hibs-racing) targets are unchanged; inst++ targets are prefixed or grouped below.

.PHONY: help install plug buyer-pack demo-ready demo demo-all demo-phase2 demo-gold \
        demo-gold-up demo-gold-down demo-gold-reset smoke rigorous chaos proof \
        verify-portfolio test instpp-test workflow-up workflow-down stack-up redis-up

PYTHON ?= python3
DEMO_DIR ?= ./data/demo/portfolio
GOLD_DIR ?= ./data/demo/spend_gold
COMPOSE ?= docker compose -f docker-compose.instpp.yml

help:
	@echo "Institutional++ (inst++) — plug / demo / run"
	@echo ""
	@echo "  make plug              one-shot: install + preflight + demo-all + verify (offline)"
	@echo "  make buyer-pack        full evidence pack → PORTFOLIO_MANIFEST.json"
	@echo "  make install           pip install -e \".[dev,instpp]\""
	@echo "  make demo-ready        preflight: deps, CLIs, imports"
	@echo "  make demo-all          all 12 SKU demos → $(DEMO_DIR)/"
	@echo "  make verify-portfolio  offline verify-bundle 12/12 after demo-all"
	@echo "  make demo-phase2       drift-gate + webhook-replay + spend-guard only"
	@echo "  make demo-gold         canonical spend-plane walkthrough"
	@echo "  make demo-gold-reset   wipe spend-gold wallet after drift lockout"
	@echo "  make demo-gold-up      seed data + Proof Console UI (http://127.0.0.1:8790)"
	@echo "  make demo-gold-down    stop workflow UI"
	@echo "  make spend-gateway     OpenAI-compat spend gateway (mock upstream)"
	@echo "  make stack-up          docker: workflow UI (+ optional redis profile)"
	@echo "  make smoke             unit + integration smoke (134+ tests)"
	@echo "  make rigorous          12/12 rigorous E2E → docs/test_logs/"
	@echo "  make proof             smoke + rigorous + verify-portfolio"
	@echo "  make chaos             chaos + integration drills"
	@echo "  make test              full pytest suite"
	@echo ""
	@echo "Quick start:  make plug"
	@echo "Diligence:    make proof"
	@echo "Docs:         docs/RUN_DEMO.md"

install:
	$(PYTHON) -m pip install -e ".[dev,instpp]"

plug: install demo-ready
	SKIP_LIVE=1 $(MAKE) demo-all
	$(MAKE) verify-portfolio

buyer-pack:
	./scripts/instpp_buyer_pack.sh

demo-ready:
	./scripts/demo_ready.sh

demo demo-all:
	SKIP_LIVE=$${SKIP_LIVE:-0} ./scripts/demo_portfolio_all.sh $(if $(CLEAN),--clean,)

verify-portfolio:
	./scripts/verify_portfolio.sh

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

stack-up:
	$(COMPOSE) up -d inst-workflow

redis-up:
	$(COMPOSE) --profile redis up -d

workflow-up: demo-gold-up

workflow-down: demo-gold-down

smoke:
	./scripts/instpp_smoke_test.sh

rigorous:
	./scripts/instpp_rigorous_test.sh

proof: smoke rigorous verify-portfolio

chaos:
	./scripts/chaos_instpp.sh

test instpp-test:
	$(PYTHON) -m pytest
