"""生成内测自签代码签名证书 client/packaging/cert/cert.pfx。

为什么需要它：客户端的「发布者: 未知」要等买到公共 CA 证书才会消失，但签名链路
（signtool 调用 / Inno SignTool / 卸载器签名 / 校验闸门）可以先用自签证书走通——
`$env:AINOVEL_SIGN_DEV_CERT='1'` 即走这条。⚠️ 自签证书**不解除 SmartScreen**，
只用于内测自验与「导入根证书的机器」上看到签署者名称（见 docs/ops/client-code-signing.md）。

证书口径（与历史 cert.pfx 一致：CN 用品牌名，密码写死在 install_cert.* 与 sign_win.ps1）：
  CN=Awesome Novel (Dev)        —— 明确是内测证书，不冒充公司签发的正式证书
  EKU=Code Signing, KeyUsage=digitalSignature, CA:TRUE（自签根，直接用它签代码）
  有效期 5 年（换名/换密码须与 install_cert.bat / install_cert.ps1 / sign_win.ps1 同批改）

用法（backend venv 有 cryptography）：
  python make_dev_cert.py            # 覆盖写 cert.pfx
"""

from __future__ import annotations

import datetime
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CERT_PATH = Path(__file__).resolve().parent / "cert.pfx"
PASSWORD = b"ainovel123"  # 与 install_cert.bat / install_cert.ps1 / sign_win.ps1 同值


def main() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Awesome Novel (Dev)")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)  # 自签
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))  # 留一天余量，防目标机时钟偏慢
        .not_valid_after(now + datetime.timedelta(days=365 * 5))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=True
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    CERT_PATH.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"Awesome Novel Dev",
            key,
            cert,
            None,
            serialization.BestAvailableEncryption(PASSWORD),
        )
    )
    print(f"written: {CERT_PATH}")
    print(f"subject: {cert.subject.rfc4514_string()}")
    print(f"valid:   {cert.not_valid_before_utc} -> {cert.not_valid_after_utc}")


if __name__ == "__main__":
    main()
