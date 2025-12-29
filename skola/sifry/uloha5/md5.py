import hashlib, base64
import string
import itertools


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


def overovanie_mien():
    total_attempts = 0
    found_total = 0
    for rec in ZAZNAMY:
        if len(rec) < 3:
            continue
        login, salt, fingerprint = rec
        for meno in MENA:
            for var in name_variations(meno):
                total_attempts += 1
                if md5_base64(var + salt) == fingerprint:
                    print(f"{login}: NAŠLI SME HESLO -> '{var}'  (pass+salt)  | Pokusov: {total_attempts}")
                    found_total += 1
                    break
    print(f"Hotovo. Celkový počet pokusov: {total_attempts}, Nájdených hesiel: {found_total}")


def generate_combinations(length: int = 4, chars: str = string.ascii_letters + string.digits):            
    total = len(chars) ** length
    print(f"Generujem všetky kombinácie: charset={len(chars)}, length={length}, celkom={total}")
    with open("sifry/uloha5/4miestne.txt", "w", encoding="utf-8") as out:
        for tup in itertools.product(chars, repeat=length):
            out.write(''.join(tup) + '\n')
    print(f"Hotovo. Zapísané kombinácie do súboru.")

def overovanie_4miestnych():
    total_attempts = 0
    found_total = 0
    with open("sifry/uloha5/najdene4miestne.txt", "a", encoding="utf-8") as g:
        with open("sifry/uloha5/4miestne.txt", "r", encoding="utf-8") as f:
            kombinacie = f.read().splitlines()
        for rec in ZAZNAMY:
            if len(rec) < 3:
                continue
            login, salt, fingerprint = rec
            for komb in kombinacie:
                total_attempts += 1
                if total_attempts % 100_000_000 == 0:
                    print(f"Pokusov: {total_attempts}")
                if md5_base64(komb + salt) == fingerprint:
                    print(f"{login}: NAŠLI SME HESLO -> '{komb}'  (pass+salt)  | Pokusov: {total_attempts}")
                    g.write(f"{login}: NAŠLI SME HESLO -> '{komb}'  (pass+salt)  | Pokusov: {total_attempts}\n")
                    found_total += 1
                    break
        print(f"Hotovo. Celkový počet pokusov: {total_attempts}, Nájdených hesiel: {found_total}")
    



if __name__ == "__main__":
    spracuj_subor()
    overovanie_mien()
    #overovanie_4miestnych()
    
