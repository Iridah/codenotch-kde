VERSION := $(shell tr -d ' \t\n\r' < VERSION)
DEB     := dist/codenotch_$(VERSION)_all.deb
PREFIX  := /usr

.PHONY: help deb run dump lint clean install-local uninstall-local release

help:
	@echo "codenotch-kde $(VERSION)"
	@echo "  make deb              build dist/codenotch_$(VERSION)_all.deb"
	@echo "  make run              run the overlay from src/ (dev)"
	@echo "  make dump             print the raw /usage response"
	@echo "  make lint             byte-compile + pyflakes (if present)"
	@echo "  make install-local    copy src+packaging into $(PREFIX) (sudo)"
	@echo "  make uninstall-local  remove the above (sudo)"
	@echo "  make clean            remove dist/ and __pycache__"

deb:
	./build-deb.sh

run:
	python3 src/codenotch/app.py

dump:
	python3 src/codenotch/app.py --dump

lint:
	python3 -m py_compile src/codenotch/app.py src/codenotch/hook.py
	@command -v pyflakes >/dev/null 2>&1 && pyflakes src/codenotch/*.py || \
		echo "(pyflakes not installed, skipped)"

install-local:
	install -m 0644 -D src/codenotch/app.py  $(DESTDIR)$(PREFIX)/lib/codenotch/app.py
	install -m 0644 -D src/codenotch/hook.py $(DESTDIR)$(PREFIX)/lib/codenotch/hook.py
	install -m 0644 -D VERSION               $(DESTDIR)$(PREFIX)/lib/codenotch/VERSION
	install -m 0755 -D packaging/bin/codenotch       $(DESTDIR)$(PREFIX)/bin/codenotch
	install -m 0755 -D packaging/bin/codenotch-hook  $(DESTDIR)$(PREFIX)/bin/codenotch-hook
	install -m 0644 -D packaging/systemd/codenotch.service \
		$(DESTDIR)$(PREFIX)/lib/systemd/user/codenotch.service
	install -m 0644 -D packaging/applications/codenotch.desktop \
		$(DESTDIR)$(PREFIX)/share/applications/codenotch.desktop
	@echo "installed. then: systemctl --user daemon-reload && systemctl --user restart codenotch"

uninstall-local:
	rm -rf $(DESTDIR)$(PREFIX)/lib/codenotch
	rm -f  $(DESTDIR)$(PREFIX)/bin/codenotch $(DESTDIR)$(PREFIX)/bin/codenotch-hook
	rm -f  $(DESTDIR)$(PREFIX)/lib/systemd/user/codenotch.service
	rm -f  $(DESTDIR)$(PREFIX)/share/applications/codenotch.desktop

release:
	@grep -q '"$(VERSION)"' src/codenotch/app.py || \
		{ echo "app.py __version__ != VERSION ($(VERSION))"; exit 1; }
	@grep -q '\[$(VERSION)\]' CHANGELOG.md || \
		{ echo "CHANGELOG.md has no [$(VERSION)] section"; exit 1; }
	@echo "version $(VERSION) looks consistent; tag with: git tag -a v$(VERSION) -m v$(VERSION)"

clean:
	rm -rf dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
