#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
# DSA-6572-1: never publish images retaining the compromised eMudhra chain.
version=$(dpkg-query -W ca-certificates | awk '{print $2}')
dpkg --compare-versions "$version" ge '20250419+deb13u1'
update-ca-certificates --fresh >/dev/null
python3 - <<'PY'
import hashlib, pathlib, re, ssl
bundle = pathlib.Path('/etc/ssl/certs/ca-certificates.crt').read_text()
blocked = {'86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b',
           'd7a7a0fb5d7e2731d771e9484eebcdef71d5f0c3e0a2948782bc0eea699ef4c0'}
certs = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', bundle, re.S)
assert certs, 'Empty trust store'
assert not any(hashlib.sha256(ssl.PEM_cert_to_DER_cert(c)).hexdigest() in blocked for c in certs), 'Distrusted CA remains'
PY
install -d -m 0755 /usr/share/cibyp-vmos
dpkg-query -W > /usr/share/cibyp-vmos/packages.tsv
printf 'Verified ca-certificates=%s (DSA-6572-1)\n' "$version"
