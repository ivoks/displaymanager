# Commands

## Checks

```sh
make check            # unittest (no hardware), msgfmt --check, desktop-file-validate,
                      # tests/check-extension.sh (if gjs is installed)
make clean            # remove build/ and __pycache__ before committing
```

Run the CLI from the checkout with `./bin/mullion …`; read-only commands are
safe on the live monitor (`status`, `state`, `cross left --check`, `detect`).

## Translations

```sh
make update-po        # regenerate po/mullion.pot (Python, JS, desktop) and merge into po/*.po
msgattrib --untranslated --no-wrap po/hr.po | grep '^msgid'
msgattrib --only-fuzzy   --no-wrap po/hr.po | grep -A1 '^msgid'
```

- New source files with strings go in `po/POTFILES`.
- msgmerge's fuzzy guesses are usually wrong (it once offered
  "Slika u slici" — picture in picture — for "Picture & Sound", and a
  string with `{input}` for one with `{name}`). Replace them, removing the
  `#, fuzzy` flag and `#|` lines, then:
  `msgattrib --no-obsolete po/hr.po -o po/hr.po && msgcat po/hr.po -o po/hr.po && msgfmt --check --statistics -o /dev/null po/hr.po`
- Croatian (`hr`) is the user's language and the only translation; write it
  and mention the new terms so they can review them.
- `tests/test_translations.py` fails if a translation's `{placeholders}`
  differ from the original.

## Packaging

`scripts/build-deb.sh <repo> [outdir]` (this skill) — or by hand:

```sh
mkdir -p /tmp/b/mullion && git ls-files -co --exclude-standard -z | xargs -0 cp --parents -t /tmp/b/mullion/
(cd /tmp/b/mullion && dpkg-buildpackage -us -uc -b) && lintian --fail-on error,warning /tmp/b/mullion_*_all.deb
```

The Makefile is the single install path (`make install [PREFIX=…] [DESTDIR=…]`,
`make uninstall`); `debian/rules` just lets debhelper call it, and
`dh_auto_test` runs `make check`. New installed files go in the Makefile's
`install` and `uninstall` targets. The user installs test builds with
`sudo dpkg -i …` (same version) and needs a log out/in for extension changes.

## CI

`.github/workflows/ci.yml`: Ubuntu 26.04 container → `make check` →
`tests/check-extension.sh` → `dpkg-buildpackage` → lintian (warnings fail) →
upload the .deb. Replay it locally with `scripts/ci-replay.sh <repo>` (needs
docker; the user is in the docker group). Scratch directories under `/tmp/claude-*`
aren't visible to the docker daemon, so the script works in `<repo>/build/ci`.

Watch the run after pushing:

```sh
sha=$(git rev-parse HEAD)
curl -s "https://api.github.com/repos/ivoks/mullion/actions/runs?per_page=1&head_sha=$sha" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['workflow_runs'][0]; print(r['status'], r['conclusion'], r['html_url'])"
```

## Releases (only when asked)

1. Bump `mullion/__init__.py`, add a `debian/changelog` entry
   (`dch` style, `resolute`, maintainer Ante Karamatic <ivoks@ubuntu.com>),
   and update the man page header (`data/mullion.1`, `.TH … "mullion X.Y.Z"`).
   `tests/test_release.py` checks all three agree.
2. Commit "Release X.Y.Z", `git tag -a vX.Y.Z -m "Mullion X.Y.Z …"`, push
   `main` and the tag, wait for CI.
3. Build assets from the tag: `git archive --prefix=mullion-X.Y.Z/ -o
   mullion-X.Y.Z.tar.gz vX.Y.Z`, build the .deb from that tree, write
   `SHA256SUMS` and `RELEASE_NOTES.md` into `~/Projekti/mullion-X.Y.Z-release/`.
4. The user publishes the GitHub release (no token here) — give them the
   web link and a `gh release create` command; afterwards verify the
   assets through the public API and check their checksums.
