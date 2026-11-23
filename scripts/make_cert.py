"""내부망 HTTPS 인증서 만들기 (무료, mkcert 와 같은 방식).

1) 사내용 인증기관(CA) 을 한 번 만든다           → certs/ca.crt, certs/ca.key (키는 절대 외부 공유 금지)
   - 이름 제약(Name Constraints): 사설 IP 대역·localhost 에만 인증서를 발급할 수 있게 제한
     (키가 새어도 외부 사이트를 위장하는 데 쓸 수 없음)
2) 그 CA 로 이 서버의 인증서를 발급한다         → certs/cert.pem, certs/key.pem  (.env 의 SERVER_IPS 포함)
3) 각 PC 가 CA 를 한 번 신뢰하도록 설치 파일 생성 → certs/install_cert.bat (관리자 권한 불필요)

사용: python scripts/make_cert.py            서버 인증서만 다시 발급 (CA 는 유지 → 각 PC 재설치 불필요)
      python scripts/make_cert.py --new-ca   CA 부터 새로 만듦 (각 PC 에 다시 설치해야 함)
IP 가 바뀌면 .env 의 SERVER_IPS 를 고치고 다시 실행하세요.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # story_app/ (storybook 패키지)

import datetime
import ipaddress
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from storybook import config

D = config.CERT_DIR
D.mkdir(exist_ok=True)
CA_CRT, CA_KEY = D / "ca.crt", D / "ca.key"
NOW = datetime.datetime.now(datetime.timezone.utc)
PRIVATE_NETS = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"]


def _pem_key(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def make_ca():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AI Story Reader (LAN)"),
                      x509.NameAttribute(NameOID.COMMON_NAME, f"AI Story Reader LAN CA {NOW:%Y-%m-%d}")])
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - datetime.timedelta(days=1)).not_valid_after(NOW + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                     key_encipherment=False, data_encipherment=False, key_agreement=False,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.NameConstraints(
            permitted_subtrees=[x509.IPAddress(ipaddress.ip_network(n)) for n in PRIVATE_NETS]
            + [x509.DNSName("localhost"), x509.DNSName("local"), x509.DNSName("lan"), x509.DNSName("internal")],
            excluded_subtrees=None), critical=True)
        .add_extension(ski, critical=False)
        .sign(key, hashes.SHA256())
    )
    CA_KEY.write_bytes(_pem_key(key))
    CA_CRT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print("새 CA 생성:", CA_CRT)


def make_server_cert():
    ca_key = serialization.load_pem_private_key(CA_KEY.read_bytes(), None)
    ca = x509.load_pem_x509_certificate(CA_CRT.read_bytes())
    ips = {"127.0.0.1", *config.SERVER_IPS}
    try:
        ips.add(socket.gethostbyname(socket.gethostname()))
    except OSError:
        pass
    ips = sorted(i for i in ips if ipaddress.ip_address(i).is_private)
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ips[-1])]))
        .issuer_name(ca.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - datetime.timedelta(days=1)).not_valid_after(NOW + datetime.timedelta(days=397))
        .add_extension(x509.SubjectAlternativeName(
            [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, key_cert_sign=False, crl_sign=False,
                                     content_commitment=False, data_encipherment=False, key_agreement=True,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    (D / "key.pem").write_bytes(_pem_key(key))
    # 서버 인증서 + CA 인증서 (체인)
    (D / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM) + CA_CRT.read_bytes())
    print("서버 인증서 발급:", ips, "만료", cert.not_valid_after_utc.date())


def make_installer():
    """Windows: 현재 사용자 '신뢰할 수 있는 루트 인증 기관'에 CA 등록 (관리자 권한 불필요)."""
    lines = [f"echo {ln}" for ln in CA_CRT.read_text().strip().splitlines()]
    bat = "\r\n".join([
        "@echo off",
        "chcp 65001 >nul",
        "echo AI Story Reader - LAN HTTPS certificate install",
        'set "CRT=%TEMP%\\ai_story_lan_ca.crt"',
        "(", *lines, f') > "%CRT%"',
        'certutil -user -addstore Root "%CRT%"',
        "if errorlevel 1 (echo. & echo [FAIL] certificate was not installed. & pause & exit /b 1)",
        'del "%CRT%" >nul 2>&1',
        "echo.",
        "echo [OK] Installed. Close ALL browser windows and open https://" + (config.SERVER_IPS or ["<server-ip>"])[0] + ":8502 again.",
        "pause",
        "",
    ])
    (D / "install_cert.bat").write_text(bat, encoding="utf-8")
    print("설치 파일:", D / "install_cert.bat")


if __name__ == "__main__":
    if "--new-ca" in sys.argv or not (CA_CRT.exists() and CA_KEY.exists()):
        make_ca()
    make_server_cert()
    make_installer()
