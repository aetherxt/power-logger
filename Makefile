VENV = venv
PYTHON = $(VENV)/bin/python
BINDIR = $(HOME)/.local/bin

.PHONY: install service run record web clean

install: $(VENV)
	@mkdir -p $(BINDIR)
	@rm -f $(BINDIR)/termpower
	@printf '#!/bin/sh\nset -eu\nexec %s/$(VENV)/bin/python %s/termpower.py "$$@"\n' "$(CURDIR)" "$(CURDIR)" > $(BINDIR)/termpower
	@chmod +x $(BINDIR)/termpower
	@echo "Installed termpower -> $(BINDIR)/termpower"
	@echo "Ensure $$HOME/.local/bin is in your PATH."

$(VENV):
	python -m venv $(VENV)
	$(VENV)/bin/pip install rich psutil flask
	@echo "Venv created at $(VENV)"

service: $(VENV)
	@mkdir -p $(HOME)/.config/systemd/user
	@sed 's|@CURDIR@|$(CURDIR)|g' power-logger.service.template > $(HOME)/.config/systemd/user/power-logger.service
	@echo "Service unit installed at ~/.config/systemd/user/power-logger.service"
	@echo "Run: systemctl --user daemon-reload"
	@echo "     systemctl --user enable --now power-logger"

run:
	$(PYTHON) termpower.py

record:
	$(PYTHON) record.py

web:
	$(PYTHON) web/app.py

clean:
	-systemctl --user disable --now power-logger 2>/dev/null
	-rm -f $(HOME)/.config/systemd/user/power-logger.service
	-systemctl --user daemon-reload 2>/dev/null
	rm -f $(BINDIR)/termpower
	rm -rf $(VENV)
	@echo "Removed venv, termpower, and systemd service"
