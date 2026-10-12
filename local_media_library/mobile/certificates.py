"""Local certificates, no public CA/ACME calls. CA signing key is never persisted."""
import csv
import datetime as dt
import ipaddress
import os
from pathlib import Path
import secrets
import ssl
import subprocess

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def restrict_directory(directory: Path):
    if directory.is_symlink():
        raise ValueError('unsafe certificate directory')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'nt':
        flags = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], check=True,
                                capture_output=True, text=True, creationflags=flags)
        sid = next(csv.reader(result.stdout.splitlines()))[1]
        if not sid.startswith('S-1-'):
            raise RuntimeError('cannot identify local account')
        subprocess.run(['icacls', str(directory), '/inheritance:r', '/grant:r',
                        f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], check=True,
                       capture_output=True, creationflags=flags)
    else:
        directory.chmod(0o700)


def ensure_certificate(directory: Path, address: str):
    ip = ipaddress.IPv4Address(address)
    restrict_directory(directory)
    leaf_file, key_file, ca_file = (directory / n for n in ('server.pem', 'server-key.pem', 'LocalMediaLibrary.cer'))
    for f in (leaf_file, key_file, ca_file):
        if f.is_symlink():
            raise ValueError('unsafe certificate file')
    now = dt.datetime.now(dt.timezone.utc)
    try:
        leaf = x509.load_pem_x509_certificate(leaf_file.read_bytes())
        ca = x509.load_der_x509_certificate(ca_file.read_bytes())
        names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        reusable = (ip in names.get_values_for_type(x509.IPAddress) and
                    leaf.not_valid_after_utc > now + dt.timedelta(days=1) and key_file.is_file())
    except (OSError, ValueError, x509.ExtensionNotFound):
        reusable = False
    if not reusable:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Local Media Library ' + secrets.token_hex(4))])
        ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
              .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=400))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
              .sign(ca_key, hashes.SHA256()))
        leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, address)]))
                .issuer_name(ca_name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=397))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip)]), critical=False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
                .sign(ca_key, hashes.SHA256()))
        # Only local management files. No CA private key is written.
        for path, data in ((key_file, leaf_key.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
                           (leaf_file, leaf.public_bytes(serialization.Encoding.PEM)),
                           (ca_file, ca.public_bytes(serialization.Encoding.DER))):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'wb') as out:
                out.write(data)
            if os.name != 'nt':
                path.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(leaf_file, key_file)
    return context, ca_file, ca.fingerprint(hashes.SHA256()).hex().upper()
