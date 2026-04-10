PYTHON := /root/bot/.venv/bin/python
SERVICE := telegram-openai-bot
UNIT_SRC := /root/bot/deploy/systemd/$(SERVICE).service
UNIT_DST := /etc/systemd/system/$(SERVICE).service

.PHONY: help install check compile run service-install service-restart service-status logs

help:
	@printf '%s\n' \
		'make install          Install Python dependencies in .venv' \
		'make check            Validate .env configuration' \
		'make compile          Compile the package to catch syntax errors' \
		'make run              Run the bot in the current shell' \
		'make service-install  Install/update the systemd unit and start it' \
		'make service-restart  Restart the systemd service' \
		'make service-status   Show systemd service status' \
		'make logs             Follow service logs'

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

check:
	$(PYTHON) -m telegram_openai_bot --check-config

compile:
	$(PYTHON) -m compileall telegram_openai_bot

run:
	$(PYTHON) -m telegram_openai_bot

service-install:
	cp $(UNIT_SRC) $(UNIT_DST)
	systemctl daemon-reload
	systemctl enable --now $(SERVICE)

service-restart:
	systemctl restart $(SERVICE)

service-status:
	systemctl status --no-pager --full $(SERVICE)

logs:
	journalctl -u $(SERVICE) -f
