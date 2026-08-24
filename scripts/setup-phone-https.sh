#!/usr/bin/env bash
# Create a private local CA and LAN certificate for Griffin's iPhone microphone.
set -euo pipefail
cd "$(dirname "$0")/.."

OPENSSL_BIN="${OPENSSL_BIN:-$(command -v openssl || true)}"
if [ -z "$OPENSSL_BIN" ]; then
  echo "Error: OpenSSL is required to create Griffin's local HTTPS certificate." >&2
  exit 1
fi

LAN_IP="${GRIFFIN_LAN_IP:-$(ipconfig getifaddr en0 2>/dev/null || true)}"
if [ -z "$LAN_IP" ]; then
  echo "Error: Griffin could not detect the Mac's Wi-Fi address. Set GRIFFIN_LAN_IP and rerun." >&2
  exit 1
fi

TLS_DIR="$(pwd)/config/tls"
CA_KEY="$TLS_DIR/griffin-ca.key"
CA_CERT="$TLS_DIR/griffin-ca.crt"
CA_IOS_CERT="$TLS_DIR/griffin-ca.cer"
SERVER_KEY="$TLS_DIR/griffin.key"
SERVER_CERT="$TLS_DIR/griffin.crt"
CSR_FILE="$TLS_DIR/griffin.csr"
EXT_FILE="$TLS_DIR/griffin-san.cnf"
MAC_HOSTNAME="$(hostname -s 2>/dev/null || echo griffin)"

mkdir -p "$TLS_DIR"
chmod 700 "$TLS_DIR"

if [ ! -f "$CA_KEY" ] || [ ! -f "$CA_CERT" ]; then
  echo "Creating Griffin's private local certificate authority ..."
  "$OPENSSL_BIN" req -x509 -newkey rsa:2048 -sha256 -nodes \
    -keyout "$CA_KEY" \
    -out "$CA_CERT" \
    -days 3650 \
    -subj "/CN=Griffin Local CA/O=Griffin Local"
fi

printf '%s\n' \
  "basicConstraints=critical,CA:FALSE" \
  "keyUsage=critical,digitalSignature,keyEncipherment" \
  "extendedKeyUsage=serverAuth" \
  "subjectAltName=IP:${LAN_IP},IP:127.0.0.1,DNS:localhost,DNS:${MAC_HOSTNAME},DNS:${MAC_HOSTNAME}.local" \
  > "$EXT_FILE"

echo "Creating a Griffin HTTPS certificate for ${LAN_IP} ..."
"$OPENSSL_BIN" req -new -newkey rsa:2048 -sha256 -nodes \
  -keyout "$SERVER_KEY" \
  -out "$CSR_FILE" \
  -subj "/CN=${LAN_IP}/O=Griffin Local"
"$OPENSSL_BIN" x509 -req -sha256 \
  -in "$CSR_FILE" \
  -CA "$CA_CERT" \
  -CAkey "$CA_KEY" \
  -CAcreateserial \
  -out "$SERVER_CERT" \
  -days 825 \
  -extfile "$EXT_FILE"

chmod 600 "$CA_KEY" "$SERVER_KEY"
chmod 644 "$CA_CERT" "$SERVER_CERT"
"$OPENSSL_BIN" x509 -in "$CA_CERT" -outform DER -out "$CA_IOS_CERT"
chmod 644 "$CA_IOS_CERT"

echo ""
echo "Phone trust is the one manual iOS step:"
echo "  1. AirDrop this iPhone certificate: $CA_IOS_CERT"
echo "  2. Settings > General > VPN & Device Management > Downloaded Profile."
echo "     Install 'Griffin Local CA'."
echo "  3. Settings > General > About > Certificate Trust Settings."
echo "  4. Enable full trust for 'Griffin Local CA'."
echo "  5. Restart Griffin with ./scripts/dev.sh and open https://${LAN_IP}:5173"
echo ""
echo "Keep $CA_KEY private. The entire config/tls directory is gitignored."
