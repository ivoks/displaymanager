# SPDX-License-Identifier: GPL-3.0-or-later
#
#   make              compile translations and the desktop file into build/
#   make pot          regenerate po/mullion.pot from the sources
#   make update-po    merge the template into every po/<lang>.po
#   make check        run the unit tests and validate translations
#   make install      install under $(DESTDIR)$(PREFIX), e.g.
#                     make install PREFIX=$$HOME/.local   (just for you)
#   make uninstall    remove what make install installed
#   make clean

PREFIX  ?= /usr
DESTDIR ?=
DOMAIN   = mullion
APP_ID   = io.github.ivoks.Mullion
EXT_UUID = mullion@ivoks.github.io
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' mullion/__init__.py)

DATADIR  = $(PREFIX)/share
APPDIR   = $(DATADIR)/mullion
LOCALEDIR = $(DATADIR)/locale
MANDIR   = $(DATADIR)/man
EXTDIR   = $(DATADIR)/gnome-shell/extensions/$(EXT_UUID)

LINGUAS  := $(shell grep -v '^\#' po/LINGUAS)
PY_SRC   := $(shell grep '\.py$$' po/POTFILES)
JS_SRC   := $(shell grep '\.js$$' po/POTFILES)
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
		--msgid-bugs-address=https://github.com/ivoks/mullion/issues \
		--add-comments=TRANSLATORS: \
		-o build/python.pot $(PY_SRC)
	xgettext --from-code=UTF-8 --language=JavaScript --keyword=_ \
		-o build/js.pot $(JS_SRC)
	xgettext --language=Desktop -o build/desktop.pot data/$(APP_ID).desktop.in
	msgcat --use-first -o po/$(DOMAIN).pot build/python.pot build/js.pot build/desktop.pot

update-po: pot
	for l in $(LINGUAS); do msgmerge --update --backup=none po/$$l.po po/$(DOMAIN).pot; done

check: all
	python3 -m unittest discover -s tests -t . -v
	for l in $(LINGUAS); do msgfmt --check -o /dev/null po/$$l.po; done
	if command -v desktop-file-validate >/dev/null; then \
		desktop-file-validate $(DESKTOP); fi
	if command -v gjs >/dev/null; then sh tests/check-extension.sh; fi

install: all
	install -d $(DESTDIR)$(APPDIR)/mullion $(DESTDIR)$(APPDIR)/bin $(DESTDIR)$(PREFIX)/bin
	install -m 644 mullion/*.py $(DESTDIR)$(APPDIR)/mullion/
	install -m 755 bin/mullion $(DESTDIR)$(APPDIR)/bin/
	ln -sf ../share/mullion/bin/mullion $(DESTDIR)$(PREFIX)/bin/mullion
	install -D -m 644 $(DESKTOP) $(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop
	install -D -m 644 data/icons/$(APP_ID).svg \
		$(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg
	install -D -m 644 data/icons/$(APP_ID)-symbolic.svg \
		$(DESTDIR)$(DATADIR)/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg
	install -d $(DESTDIR)$(EXTDIR)
	install -m 644 extension/$(EXT_UUID)/metadata.json extension/$(EXT_UUID)/*.js \
		$(DESTDIR)$(EXTDIR)/
	install -D -m 644 data/mullion.1 $(DESTDIR)$(MANDIR)/man1/mullion.1
	for l in $(LINGUAS); do \
		install -D -m 644 build/locale/$$l/LC_MESSAGES/$(DOMAIN).mo \
			$(DESTDIR)$(LOCALEDIR)/$$l/LC_MESSAGES/$(DOMAIN).mo; \
	done

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/mullion
	rm -rf $(DESTDIR)$(APPDIR) $(DESTDIR)$(EXTDIR)
	rm -f $(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop
	rm -f $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg
	rm -f $(DESTDIR)$(DATADIR)/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg
	rm -f $(DESTDIR)$(MANDIR)/man1/mullion.1
	for l in $(LINGUAS); do rm -f $(DESTDIR)$(LOCALEDIR)/$$l/LC_MESSAGES/$(DOMAIN).mo; done

clean:
	rm -rf build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: all pot update-po check install uninstall clean
