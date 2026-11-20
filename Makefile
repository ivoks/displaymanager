# SPDX-License-Identifier: GPL-3.0-or-later
#
#   make              compile translations and the desktop file into build/
#   make pot          regenerate po/displaymanager.pot from the sources
#   make update-po    merge the template into every po/<lang>.po
#   make install      install under $(DESTDIR)$(PREFIX)
#   make clean

PREFIX  ?= /usr
DESTDIR ?=
DOMAIN   = displaymanager
APP_ID   = io.github.DisplayManager
EXT_UUID = displaymanager@ivoks.github.io
VERSION := $(shell dpkg-parsechangelog -S Version 2>/dev/null || echo 0)

DATADIR  = $(PREFIX)/share
APPDIR   = $(DATADIR)/displaymanager
LOCALEDIR = $(DATADIR)/locale

LINGUAS  := $(shell grep -v '^\#' po/LINGUAS)
PY_SRC   := $(shell grep '\.py$$' po/POTFILES)
MO_FILES := $(foreach l,$(LINGUAS),build/locale/$(l)/LC_MESSAGES/$(DOMAIN).mo)
DESKTOP   = build/$(APP_ID).desktop

all: $(MO_FILES) $(DESKTOP)

build/locale/%/LC_MESSAGES/$(DOMAIN).mo: po/%.po
	@mkdir -p $(dir $@)
	msgfmt --check -o $@ $<

$(DESKTOP): data/$(APP_ID).desktop.in $(wildcard po/*.po) po/LINGUAS
	@mkdir -p build
	msgfmt --desktop -d po --template $< -o $@

pot:
	@mkdir -p build
	xgettext --from-code=UTF-8 --language=Python --keyword=_ --keyword=N_ \
		--package-name=$(DOMAIN) --package-version=$(VERSION) \
		--copyright-holder="Ante Karamatic" \
		--msgid-bugs-address=https://github.com/ivoks/displaymanager/issues \
		--add-comments=TRANSLATORS: \
		-o build/python.pot $(PY_SRC)
	xgettext --language=Desktop -o build/desktop.pot data/$(APP_ID).desktop.in
	msgcat --use-first -o po/$(DOMAIN).pot build/python.pot build/desktop.pot

update-po: pot
	for l in $(LINGUAS); do msgmerge --update --backup=none po/$$l.po po/$(DOMAIN).pot; done

install: all
	install -d $(DESTDIR)$(APPDIR)/ddm $(DESTDIR)$(PREFIX)/bin
	install -m 644 ddm/*.py $(DESTDIR)$(APPDIR)/ddm/
	install -m 755 displaymanager $(DESTDIR)$(APPDIR)/
	ln -sf ../share/displaymanager/displaymanager $(DESTDIR)$(PREFIX)/bin/displaymanager
	install -D -m 644 $(DESKTOP) $(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop
	install -D -m 644 data/icons/$(APP_ID).svg \
		$(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg
	install -D -m 644 data/icons/$(APP_ID)-symbolic.svg \
		$(DESTDIR)$(DATADIR)/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg
	install -d $(DESTDIR)$(DATADIR)/gnome-shell/extensions/$(EXT_UUID)
	install -m 644 extension/$(EXT_UUID)/metadata.json extension/$(EXT_UUID)/extension.js \
		$(DESTDIR)$(DATADIR)/gnome-shell/extensions/$(EXT_UUID)/
	for l in $(LINGUAS); do \
		install -D -m 644 build/locale/$$l/LC_MESSAGES/$(DOMAIN).mo \
			$(DESTDIR)$(LOCALEDIR)/$$l/LC_MESSAGES/$(DOMAIN).mo; \
	done

clean:
	rm -rf build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: all pot update-po install clean
