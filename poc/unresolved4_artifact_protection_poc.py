#!/usr/bin/env python3
"""
PoC for unresolved item #4:
Model/artifact protection level (encryption vs signing).

We simulate a "model.onnx" blob and measure:
- sha256 hashing cost (dominant for signing workflows)
- Ed25519 sign/verify on the hash
- AES-256-GCM encrypt/decrypt cost
- tamper detection behavior (signature verify fails / AESGCM decrypt fails)

NOTE: This does not solve key management (DPAPI/TPM/etc). It only demonstrates mechanics/overhead.
"""

from __future__ import annotations

import hashlib
import secrets
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def ms(dt_s: float) -> float:
    return dt_s * 1000.0


def bench_sha256(data: bytes) -> tuple[bytes, float]:
    t0 = time.perf_counter()
    h = hashlib.sha256(data).digest()
    t1 = time.perf_counter()
    return h, ms(t1 - t0)


def bench_ed25519(hash32: bytes) -> tuple[bytes, float, float]:
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()

    t0 = time.perf_counter()
    sig = sk.sign(hash32)
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    pk.verify(sig, hash32)
    t3 = time.perf_counter()

    return sig, ms(t1 - t0), ms(t3 - t2)


def bench_aesgcm(data: bytes, aad: bytes = b"") -> tuple[bytes, bytes, float, float]:
    key = AESGCM.generate_key(bit_length=256)
    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)  # 96-bit nonce

    t0 = time.perf_counter()
    ct = aes.encrypt(nonce, data, aad)
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    pt = aes.decrypt(nonce, ct, aad)
    t3 = time.perf_counter()

    assert pt == data
    return nonce, ct, ms(t1 - t0), ms(t3 - t2)


def tamper_one_byte(b: bytes) -> bytes:
    ba = bytearray(b)
    i = len(ba) // 2
    ba[i] ^= 0x01
    return bytes(ba)


def main() -> None:
    size_mb = 14
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    print(f"artifact_size_bytes={len(data)} (~{size_mb}MB)")

    h, t_hash = bench_sha256(data)
    print(f"sha256_ms={t_hash:.2f}")

    sig, t_sign, t_verify = bench_ed25519(h)
    print(f"ed25519_sign_ms={t_sign:.4f} (hash-signed, not whole file)")
    print(f"ed25519_verify_ms={t_verify:.4f} (hash-verified)")
    print(f"sig_len_bytes={len(sig)}")

    aad = b"artifact:model.onnx;version:1"
    nonce, ct, t_enc, t_dec = bench_aesgcm(data, aad=aad)
    print(f"aesgcm_encrypt_ms={t_enc:.2f}")
    print(f"aesgcm_decrypt_ms={t_dec:.2f}")
    print(f"nonce_len_bytes={len(nonce)} ct_len_bytes={len(ct)} (includes GCM tag)")

    # Tamper behavior: signature path
    h_tampered, _ = bench_sha256(tamper_one_byte(data))
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    sig_ok = sk.sign(h)
    try:
        pk.verify(sig_ok, h_tampered)
        print("tamper_signature_verify=UNEXPECTED_OK")
    except Exception:
        print("tamper_signature_verify=FAIL_OK")

    # Tamper behavior: AES-GCM path
    key = AESGCM.generate_key(bit_length=256)
    aes = AESGCM(key)
    nonce2 = secrets.token_bytes(12)
    ct2 = aes.encrypt(nonce2, data, aad)
    try:
        aes.decrypt(nonce2, tamper_one_byte(ct2), aad)
        print("tamper_aesgcm_decrypt=UNEXPECTED_OK")
    except Exception:
        print("tamper_aesgcm_decrypt=FAIL_OK")


if __name__ == "__main__":
    main()

