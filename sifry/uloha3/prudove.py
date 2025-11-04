#!/usr/bin/env python3
# rc4_bruteforce_simple.py
# Jednoduchý sekvenčný brute-force 100000..999999, zastaví pri prvom "plausible" hesle.
from fileinput import filename

# ---------- RC4 keygen + KSA + PRGA (matching the C code) ----------
def make_key_from_passwd(passwd: str) -> bytes:
    pb = passwd.encode('ascii') + b'\x00'
    rep = (pb * ((256 + len(pb) - 1) // len(pb)))[:256]
    return rep

def rc4_init_state(key256: bytes):
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key256[i]) & 0xff
        S[i], S[j] = S[j], S[i]
    return S, 0, 0

def rc4_keystream_byte(S, i, j):
    i = (i + 1) & 0xff
    j = (j + S[i]) & 0xff
    S[i], S[j] = S[j], S[i]
    t = (S[i] + S[j]) & 0xff
    return S[t], i, j

def rc4_decrypt_with_passwd_prefix(cipherbytes: bytes, passwd: str, prefix_len=512) -> bytes:
    """Dešifruje len(prefix) bajtov a vráti ich (pre rýchle testovanie)."""
    key256 = make_key_from_passwd(passwd)
    S, i, j = rc4_init_state(key256)
    L = min(len(cipherbytes), prefix_len)
    out = bytearray(L)
    for idx in range(L):
        k, i, j = rc4_keystream_byte(S, i, j)
        out[idx] = cipherbytes[idx] ^ k
    return bytes(out)

def rc4_decrypt_full(cipherbytes: bytes, passwd: str) -> bytes:
    key256 = make_key_from_passwd(passwd)
    S, i, j = rc4_init_state(key256)
    out = bytearray(len(cipherbytes))
    for idx, cb in enumerate(cipherbytes):
        k, i, j = rc4_keystream_byte(S, i, j)
        out[idx] = cb ^ k
    return bytes(out)

# ---------- simple heuristic ----------
def plausible_plaintext(b: bytes) -> bool:
    if len(b) == 0:
        return False
    printable = sum(1 for x in b if 32 <= x <= 126 or x in (9,10,13))
    printable_ratio = printable / len(b)
    zeros = b.count(0)
    if printable_ratio < 0.80:   # ak menej než 80% tlačiteľných znakov, väčšinou nie text
        return False
    if zeros > len(b) * 0.05:    # viac než 5% nul bajtov - veľmi podozrivé
        return False
    # musí mať aspoň jednu medzeru alebo newline (textové súbory majú)
    if (b.find(b' ') == -1) and (b.find(b'\n') == -1):
        return False
    # jednoduchý check na bežné slová
    lower = b.lower()
    for w in (b'the', b'and', b' is ', b' je ', b' a ', b' v ', b' na '):
        if w in lower:
            return True
    # ak sme tu a printable_ratio je veľmi vysoké, tiež prijmeme
    return printable_ratio > 0.92

# ---------- main loop ----------
def main():
    
    filename = r"moje\sifry\uloha3\text1_enc.txt"

    with open(filename, 'rb') as f:
        cipher = f.read()

    print(f"Loaded {filename}, {len(cipher)} bytes. Starting brute-force (100000..999999).")
    prefix_len = 512 # koľko bajtov dešifrovať pre rýchly test
    progress_step = 20000
    tried = 0
    for n in range(100000, 1000000):
        passwd = str(n) 
        tried += 1
        # test prefix quickly
        plain_pref = rc4_decrypt_with_passwd_prefix(cipher, passwd, prefix_len=prefix_len)
        if plausible_plaintext(plain_pref):
            print(f"\n>>> Candidate found: passwd = {passwd} (after {tried} tries)")
            # write full decrypted file
            fullplain = rc4_decrypt_full(cipher, passwd)
            outname = f"{filename}.decrypted_{passwd}"
            with open(outname, 'wb') as of:
                of.write(fullplain)
            print(f"Wrote decrypted file: {outname}")
            # also print preview
            try:
                preview = fullplain[:512].decode('utf-8', errors='replace')
            except:
                preview = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in fullplain[:512])
            print("Preview (first 512 bytes):\n", preview[:1000])
            return  # stop after first candidate — remove this 'return' to continue searching
        if tried % progress_step == 0:
            print(f"Tried {tried} passwords so far... latest tried: {passwd}")
    print("Finished search — no candidate passed the heuristic.")

if __name__ == "__main__":
    main()
