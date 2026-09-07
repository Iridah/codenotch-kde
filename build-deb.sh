#!/bin/bash
# Assemble a staging tree from src/ + packaging/ + VERSION and build a .deb.
# Output: dist/codenotch_<version>_all.deb
set -euo pipefail
cd "$(dirname "$0")"

VER=$(tr -d ' \t\n\r' < VERSION)
[ -n "$VER" ] || { echo "VERSION is empty" >&2; exit 1; }

STAGE=dist/pkg
OUT="dist/codenotch_${VER}_all.deb"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/lib/codenotch" \
         "$STAGE/usr/lib/systemd/user" \
         "$STAGE/usr/share/applications"

# --- payload ---------------------------------------------------------------
install -m 0644 src/codenotch/app.py  "$STAGE/usr/lib/codenotch/app.py"
install -m 0644 src/codenotch/hook.py "$STAGE/usr/lib/codenotch/hook.py"
install -m 0644 VERSION               "$STAGE/usr/lib/codenotch/VERSION"
install -m 0755 packaging/bin/codenotch       "$STAGE/usr/bin/codenotch"
install -m 0755 packaging/bin/codenotch-hook  "$STAGE/usr/bin/codenotch-hook"
install -m 0644 packaging/systemd/codenotch.service \
        "$STAGE/usr/lib/systemd/user/codenotch.service"
install -m 0644 packaging/applications/codenotch.desktop \
        "$STAGE/usr/share/applications/codenotch.desktop"

# --- control metadata ----------------------------------------------------- #
SIZE=$(du -sk "$STAGE/usr" | cut -f1)
sed -e "s/@VERSION@/${VER}/g" -e "s/@SIZE@/${SIZE}/g" \
    packaging/debian/control.in > "$STAGE/DEBIAN/control"
install -m 0755 packaging/debian/postinst "$STAGE/DEBIAN/postinst"
install -m 0755 packaging/debian/prerm    "$STAGE/DEBIAN/prerm"

( cd "$STAGE" && find usr -type f -exec md5sum {} + > DEBIAN/md5sums )
chmod 0644 "$STAGE/DEBIAN/md5sums"

# --- build -------------------------------------------------------------------
dpkg-deb --root-owner-group --build "$STAGE" "$OUT"
echo
dpkg-deb --info "$OUT" | sed -n '1,14p'
echo "-- contents --"
dpkg-deb --contents "$OUT"
if command -v lintian >/dev/null 2>&1; then
    echo "-- lintian --"; lintian "$OUT" || true
fi
echo
echo "built: $OUT"
