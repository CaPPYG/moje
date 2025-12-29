import hashlib, base64
import random
import string
import time
import os
import itertools
from multiprocessing import Pool, cpu_count

ZAZNAMY = []
MENA = []
SUBOR = "sifry/uloha5/shadow1.txt"

def spracuj_subor():
    with open(SUBOR, "r") as f:
        riadky = f.readlines()
    for riadok in riadky:
        ZAZNAMY.append(riadok.strip().split(":"))
    with open("sifry/uloha5/mena.txt", "r", encoding="utf-8") as f:
        obsah = f.read()
        global MENA
        MENA = obsah.split()

def md5_base64(text: str) -> str:
    return base64.b64encode(hashlib.md5(text.encode("utf-8")).digest()).decode("utf-8")

def name_variations(name: str):
    """Všetky malé + všetky varianty s jedným veľkým písmenom."""
    name = name.lower()
    vars = [name]
    for i in range(len(name)):
        var = name[:i] + name[i].upper() + name[i+1:]
        vars.append(var)
    return vars

# ------------------- EFEKTÍVNA ČASŤ (chunkovanie + paralelizmus) -------------------

# Globálna premenná pre workerov (naplní sa v initializer)
_RECORDS_FOR_WORKERS = None

def _init_worker(records):
    """Initializer pre Pool — nastaví globálnu premennú zdieľanú medzi workermi."""
    global _RECORDS_FOR_WORKERS
    _RECORDS_FOR_WORKERS = records

def _check_candidate(candidate: str):
    """
    Skontroluje daný candidate voči všetkým záznamom (uloženým v _RECORDS_FOR_WORKERS).
    Ak nájde zhodu, vráti tuple (login, candidate, mode) kde mode je 'pass+salt' alebo 'salt+pass'.
    Ak nenájde nič, vráti None.
    """
    # prístup k _RECORDS_FOR_WORKERS je rýchly (lokálna globálna premenná v procese)
    for rec in _RECORDS_FOR_WORKERS:
        if len(rec) < 3:
            continue
        login, salt, fingerprint = rec
        # pass + salt
        if md5_base64(candidate + salt) == fingerprint:
            return (login, candidate, "pass+salt")
        # salt + pass
        if md5_base64(salt + candidate) == fingerprint:
            return (login, candidate, "salt+pass")
    return None

def gen_all_chunk(fraction=0.1, start_offset=0):
    """
    Generuje prvú časť všetkých 6-zn. kombinácií:
      - fraction: časť priestoru (0.1 = 1/10). Hodnoty (0,1].
      - start_offset: počet kandidátov, ktoré preskočíme na začiatku (umožní resume).
    Vracia generator (iterátor) po kandidátoch (reťazcoch).
    """
    assert 0 < fraction <= 1.0
    letters = string.ascii_lowercase
    total = 26**6
    max_candidates = int(total * fraction)
    # vytvoríme product a preskočíme start_offset prvkov, potom yield-ujeme max_candidates
    gen = itertools.product(letters, repeat=6)
    # preskočíme offset
    for _ in range(start_offset):
        try:
            next(gen)
        except StopIteration:
            return
    yielded = 0
    for tup in gen:
        yield ''.join(tup)
        yielded += 1
        if yielded >= max_candidates:
            break

def run_chunk_check(fraction=0.1, start_offset=0, processes=None, out_found="sifry/uloha5/found_chunk.txt"):
    """
    Hlavná funkcia: vygeneruje candidates pre daný fraction a paralelne ich skontroluje.
    Výstup uloží do out_found (append režim).
    """
    if processes is None:
        processes = max(1, cpu_count() - 1)  # rezervujeme jeden jadro pre systém
    os.makedirs(os.path.dirname(out_found), exist_ok=True)

    # pripravíme záznamy pre workerov (filter len tých s potrebnými poliami)
    records = [rec for rec in ZAZNAMY if len(rec) >= 3]

    if not records:
        print("Žiadne platné záznamy v ZAZNAMY. Spusti spracuj_subor() najprv.")
        return

    gen = gen_all_chunk(fraction=fraction, start_offset=start_offset)

    started = time.time()
    checked = 0
    found_total = 0
    last_report = time.time()

    # otvoríme výstupný súbor a budeme doň zapisovať nálezy
    with open(out_found, "a", encoding="utf-8") as out_f:
        # Pool s initializerom, aby každý worker mal kópiu records (efektívnejšie než picklovanie pri každom volaní)
        with Pool(processes=processes, initializer=_init_worker, initargs=(records,)) as pool:
            # mapujeme kandidátov na workery po jednom (imap_unordered pre rýchlejší output)
            for result in pool.imap_unordered(_check_candidate, gen, chunksize=1000):
                checked += 1
                if result is not None:
                    login, candidate, mode = result
                    line = f"{login}: NAŠLI SME HESLO -> '{candidate}'  ({mode})"
                    print(line)
                    out_f.write(line + "\n")
                    found_total += 1
                # periodický status
                if checked % 1000000 == 0:
                    now = time.time()
                    elapsed = now - started
                    rate = checked / elapsed if elapsed > 0 else 0
                    print(f"Skontrolovaných kandidátov: {checked}  |  Nájdené: {found_total}  |  Rýchlosť: {rate:.1f} kandid./s")
                # tiež vypíšeme každý 10k kandidátov kratšie pre priebežný feedback
                if checked % 10000 == 0 and (time.time() - last_report) > 5:
                    last_report = time.time()
                    print(f"Progress: {checked} candidates checked so far...")

    total_time = time.time() - started
    print(f"Hotovo. Skontrolovaných: {checked}, Nájdené: {found_total}, Čas: {total_time:.1f}s")

# ------------------- KONIEC EFEKTÍVNEJ ČASTI -------------------


def gen_random(n, length):
    letters = string.ascii_lowercase
    for _ in range(n):
        pwd = ''.join(random.choices(letters, k=length))
        yield pwd

def overovanie_random():
    for rec in ZAZNAMY:
        if len(rec) < 3:
            continue
        login, salt, fingerprint = rec
        for candidate in gen_random(1000000, 6):
            if md5_base64(candidate + salt) == fingerprint:
                print(f"{login}: NAŠLI SME HESLO -> '{candidate}'  (pass+salt)")
                break
            if md5_base64(salt + candidate) == fingerprint:
                print(f"{login}: NAŠLI SME HESLO -> '{candidate}'  (salt+pass)")
                break

def overovanie_most_used():
    # načítaj wordlist a odfiltruj len lowercase heslá dĺžky 6 alebo 7
    with open("sifry/uloha5/most_used_passwords.txt", "r", encoding="utf-8", errors="ignore") as f:
        passwords = [p.strip() for p in f if p.strip()]
    passwords = [p for p in passwords if len(p) in (6,7) and p.isalpha() and p.islower()]

    # deduplikuj pre rýchlosť
    passwords = list(dict.fromkeys(passwords))
    counter = 0
    for rec in ZAZNAMY:
        counter += 1
        if counter % 100 == 0:
            print(f"Spracovaných záznamov: {counter}/{len(ZAZNAMY)}")
        if len(rec) < 3:
            continue
        login, salt, fingerprint = rec
        for pwd in passwords:
            if md5_base64(pwd + salt) == fingerprint:
                print(f"{login}: NAŠLI SME HESLO -> '{pwd}'  (pass+salt)")
                break
            if md5_base64(salt + pwd) == fingerprint:
                print(f"{login}: NAŠLI SME HESLO -> '{pwd}'  (salt+pass)")
                break

def gen_all():
    # kompatibilná podpätka
    letters = string.ascii_lowercase
    for tup in itertools.product(letters, repeat=6):
        yield ''.join(tup)
        
def overovanie_mien():
    for rec in ZAZNAMY:
        if len(rec) < 3:
            continue
        login, salt, fingerprint = rec
        for meno in MENA:
            for var in name_variations(meno):
                # skúsiť pass+salt
                if md5_base64(var + salt) == fingerprint:
                    print(f"{login}: NAŠLI SME HESLO -> '{var}'  (pass+salt)")
                    break
                # skúsiť salt+pass
                if md5_base64(salt + var) == fingerprint:
                    print(f"{login}: NAŠLI SME HESLO -> '{var}'  (salt+pass)")
                    break


# ------------------- PRIDAŤ: generátor pre charset (0-9a-zA-Z) a paralelné overovanie -------------------

CHARSET_62 = string.digits + string.ascii_lowercase + string.ascii_uppercase  # '0-9a-zA-Z'

def _combined_product_generator(charset, lengths_sorted):
    """Yielduje postupne kombinácie pre každú dĺžku v lengths_sorted v rastúcom poradí."""
    for L in sorted(lengths_sorted):
        for tup in itertools.product(charset, repeat=L):
            yield ''.join(tup)

def gen_charset_chunk(lengths=(4,5), fraction=0.1, start_offset=0):
    """
    Generuje kandidátov pre charset (0-9a-zA-Z) pre dĺžky v tuple lengths.
    fraction: časť priestoru (0<->1). start_offset: preskoči tento počet kandidátov.
    Vráti generator stringov.
    """
    assert 0 < fraction <= 1.0
    charset = CHARSET_62
    total = sum(len(charset)**L for L in lengths)
    max_take = int(total * fraction)
    gen_all = _combined_product_generator(charset, lengths)

    # preskočíme offset
    skipped = 0
    while skipped < start_offset:
        try:
            next(gen_all)
            skipped += 1
        except StopIteration:
            return
    taken = 0
    for cand in gen_all:
        yield cand
        taken += 1
        if taken >= max_take:
            break

def run_charset_check(lengths=(4,5), fraction=0.1, start_offset=0, processes=None, out_found="sifry/uloha5/found_4_5.txt"):
    """
    Generuje kandidátov pre charset (0-9a-zA-Z) a dĺžky v lengths, kontroluje ich paralelne.
    fraction určuje časť priestoru (0.1 = 10%), start_offset umožňuje resume.
    Používa existujúce _init_worker a _check_candidate.
    """
    if processes is None:
        processes = max(1, cpu_count() - 1)

    records = [rec for rec in ZAZNAMY if len(rec) >= 3]
    if not records:
        print("Žiadne platné záznamy v ZAZNAMY. Spusti spracuj_subor() najprv.")
        return

    gen = gen_charset_chunk(lengths=lengths, fraction=fraction, start_offset=start_offset)
    os.makedirs(os.path.dirname(out_found), exist_ok=True)

    started = time.time()
    checked = 0
    found_total = 0
    last_report = time.time()

    with open(out_found, "a", encoding="utf-8") as out_f:
        with Pool(processes=processes, initializer=_init_worker, initargs=(records,)) as pool:
            for result in pool.imap_unordered(_check_candidate, gen, chunksize=4096):
                checked += 1
                if result is not None:
                    login, candidate, mode = result
                    line = f"{login}: NAŠLI SME HESLO -> '{candidate}'  ({mode})"
                    print(line)
                    out_f.write(line + "\n")
                    found_total += 1
                if checked % 1_000_000 == 0:
                    now = time.time()
                    elapsed = now - started
                    rate = checked / elapsed if elapsed > 0 else 0
                    print(f"Skontrolovaných kandidátov: {checked}  |  Nájdené: {found_total}  |  Rýchlosť: {rate:.1f} kandid./s")
                if checked % 10000 == 0 and (time.time() - last_report) > 5:
                    last_report = time.time()
                    print(f"Progress: {checked} candidates checked so far...")

    total_time = time.time() - started
    print(f"Hotovo. Skontrolovaných: {checked}, Nájdené: {found_total}, Čas: {total_time:.1f}s")
# ------------------- KONIEC PRIDANÉHO KÓDU -------------------

# ------------------- PRIDAŤ: rýchle python optimalizácie (bytes, salt-centric, multiprocessing) -------------------

import base64
from collections import defaultdict

# CHARSET pomocné (použi podľa potreby)
CHARSET_LOWER = string.ascii_lowercase
CHARSET_62 = string.digits + string.ascii_lowercase + string.ascii_uppercase

# -> Volaj toto po spracuj_subor(), nahradí ZAZNAMY novou štruktúrou RECORDS_BYTE
RECORDS_BYTE = []  # každý záznam: (login, salt_str, salt_bytes, fingerprint_bytes)

def prepare_records_bytes():
    """
    Prekonvertuje ZAZNAMY tak, aby fingerprinty boli MD5-digests v bytes (nie base64 string).
    Výsledok sa uloží do RECORDS_BYTE.
    """
    global RECORDS_BYTE
    RECORDS_BYTE = []
    for rec in ZAZNAMY:
        if len(rec) < 3:
            continue
        login, salt, fingerprint_b64 = rec
        try:
            fp_bytes = base64.b64decode(fingerprint_b64)
        except Exception:
            # ak fingerprint nie je base64, ignoruj záznam
            continue
        salt_bytes = salt.encode("utf-8")
        RECORDS_BYTE.append((login, salt, salt_bytes, fp_bytes))
    print(f"prepare_records_bytes: pripravených {len(RECORDS_BYTE)} záznamov (bytes)")

def md5_digest_bytes(candidate_bytes: bytes, salt_bytes: bytes) -> bytes:
    """
    Vráti MD5 digest bytes pre MD5(candidate + salt) ale bez tvorenia nového candidate+salt bytes.
    """
    h = hashlib.md5()
    h.update(candidate_bytes)
    h.update(salt_bytes)
    return h.digest()

# Pomocné generator-y
def _combined_product_generator_for_charset(charset, lengths_sorted):
    """Yielduje postupne kombinácie pre každú dĺžku v lengths_sorted v rastúcom poradí."""
    for L in sorted(lengths_sorted):
        for tup in itertools.product(charset, repeat=L):
            yield ''.join(tup)

# Worker pre salt-centric processing: jeden worker spracuje jednu salt (alebo skupinu, podľa mapovania)
def _salt_worker(args):
    """
    args = (salt, salt_bytes, list_of_records_for_this_salt, lengths, charset, max_take)
    vráti (checked_count, found_lines_list)
    """
    salt, salt_bytes, recs_for_salt, lengths, charset, max_take = args
    # vytvor set fingerprintov pre tento salt (bytes) pre rýchle porovnanie
    fp_set = {fp for (_, _, _, fp) in recs_for_salt}
    found = []
    checked = 0
    # generujeme kandidátov (v požadovanom poriadku)
    gen = _combined_product_generator_for_charset(charset, lengths)
    for cand in gen:
        cand_b = cand.encode("utf-8")
        checked += 1
        # digest = md5(candidate + salt)
        digest = md5_digest_bytes(cand_b, salt_bytes)
        if digest in fp_set:
            # nájdeme všetky matching loginy pre tento digest
            for (login, _, _, fp) in recs_for_salt:
                if fp == digest:
                    line = f"{login}: NAŠLI SME HESLO -> '{cand}'  (pass+salt)"
                    found.append(line)
        if max_take is not None and checked >= max_take:
            break
    return checked, found

def run_salt_centric(lengths=(4,), charset=CHARSET_LOWER, fraction=1.0, start_offset=0, processes=None, out_found="sifry/uloha5/found_salt_centric.txt", per_salt_max=None):
    """
    Salt-centric approach:
    - pripraví mapu salt -> list(records)
    - paralelizuje cez salt-y (každý worker spracuje jednu salt)
    - lengths, charset: definujú search space (napr. lengths=(4,) a charset=CHARSET_62)
    - fraction/start_offset: kontrola priestoru pre kandidátov (len pre jednoduché použitie; per_salt_max obmedzí počet kandidátov per salt)
    - per_salt_max: ak nechceš generovať všetky kandidáty pre každú salt, nastav max (int) - vhodné pre testovanie
    """
    if processes is None:
        processes = max(1, cpu_count() - 1)

    # priprava záznamov bytes (musí byť volané predtým)
    if not RECORDS_BYTE:
        print("Spusti prepare_records_bytes() najprv.")
        return

    # skupinovanie záznamov podľa salt string (aby sme mali lokálne recs pre každý salt)
    salt_map = defaultdict(list)
    for (login, salt_str, salt_bytes, fp_bytes) in RECORDS_BYTE:
        salt_map[salt_str].append((login, salt_str, salt_bytes, fp_bytes))

    salts_items = list(salt_map.items())  # [(salt_str, [recs...]), ...]

    print(f"run_salt_centric: unique salts = {len(salts_items)}, processes = {processes}")

    # vypočítaj max_take ak fraction < 1.0 (aplikujeme rovnaký percent na kandidat pri každom salte)
    charset_len = len(charset)
    total_candidates = sum(charset_len**L for L in lengths)
    max_take_per_salt = None
    if fraction < 1.0:
        max_take_per_salt = int(total_candidates * fraction)
    if per_salt_max is not None:
        max_take_per_salt = per_salt_max

    # priprav argumenty pre workery
    tasks = []
    for salt_str, recs in salts_items:
        salt_bytes = recs[0][2]  # všetky recs pre túto salt majú rovnaké salt_bytes
        tasks.append((salt_str, salt_bytes, recs, lengths, charset, max_take_per_salt))

    started = time.time()
    total_checked = 0
    total_found = 0
    os.makedirs(os.path.dirname(out_found), exist_ok=True)

    # paralelizuj podľa saltov
    with Pool(processes=processes) as pool:
        for checked, found_lines in pool.imap_unordered(_salt_worker, tasks, chunksize=1):
            total_checked += checked
            if found_lines:
                with open(out_found, "a", encoding="utf-8") as out_f:
                    for ln in found_lines:
                        print(ln)
                        out_f.write(ln + "\n")
                        total_found += 1
            # jednoduchý status
            if total_checked % 1_000_000 == 0:
                now = time.time()
                print(f"Checked total: {total_checked}  |  Found: {total_found}  |  Elapsed: {now-started:.1f}s")

    print(f"run_salt_centric done: checked {total_checked}, found {total_found}, elapsed {time.time()-started:.1f}s")

# ------------------- KONIEC PRIDANÉHO KÓDU -------------------


if __name__ == "__main__":
    # 1️⃣ Načítanie záznamov a mien
    spracuj_subor()

    # 2️⃣ Overovanie mien (stará logika zostáva)
    #overovanie_mien()

    # 3️⃣ Príprava RECORDS_BYTE pre salt-centric overovanie
    prepare_records_bytes()

    # 4️⃣ Salt-centric overovanie pre 6-miestne lowercase heslá
    #    fraction = 0.1 -> prvá 1/10 priestoru
    #    processes = cpu_count() - 1 -> paralelizácia cez všetky jadrá okrem jedného
    run_salt_centric(
        lengths=(6,),
        charset=CHARSET_LOWER,
        fraction=0.1,
        processes=cpu_count()-1
    )

    # 5️⃣ Voliteľne: salt-centric overovanie pre 4-5 znaky 0-9a-zA-Z
    # run_salt_centric(
    #     lengths=(4,5),
    #     charset=CHARSET_62,
    #     fraction=0.01,  # 1% priestoru, vhodné pre testovanie
    #     processes=cpu_count()-1,
    #     out_found="sifry/uloha5/found_4_5.txt"
    # )
