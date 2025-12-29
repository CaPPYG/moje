from sympy import mod_inverse, factorint
import math
import time

def factor_small_n(n):
    print(f"  [small] Začínam faktorovať n={n}")
    for i in range(2, int(math.isqrt(n))+1):
        if n % i == 0:
            print(f"  [small] Faktory nájdené: p={i}, q={n//i}")
            return i, n // i
    print("  [small] Faktory sa nenašli")
    return None, None

def factor_large_n(n):
    print(f"  [large] Začínam faktorovať n={n} pomocou SymPy")
    factors = factorint(n)
    primes = list(factors.keys())
    if len(primes) == 2:
        print(f"  [large] Faktory nájdené: p={primes[0]}, q={primes[1]}")
        return primes[0], primes[1]
    else:
        print(f"  [large] Viac ako 2 faktory, kombinujem polovičky")
        primes.sort()
        half = len(primes)//2
        p = 1
        for f in primes[:half]:
            p *= f**factors[f]
        q = 1
        for f in primes[half:]:
            q *= f**factors[f]
        print(f"  [large] Kombinované faktory: p={p}, q={q}")
        return p, q

def rsa_decrypt(n, e, y, small):
    start = time.time()
    if small:
        p, q = factor_small_n(n)
    else:
        p, q = factor_large_n(n)
    if p is None:
        return None
    phi = (p-1)*(q-1)
    d = mod_inverse(e, phi)
    x = pow(y, d, n)
    elapsed = time.time() - start
    return x, d, p, q, elapsed

inputs_small = [
    (2164267772327, 65537, 1325266873785),
    (16812615098258879, 65537, 1990249581724467),
    (181052234309092978339, 65537, 147885702766350471578)
]

inputs_large = [
    (1327612780145399205245813, 65537, 1075593273482743198269527),
    (329897251897125970254396723194243, 65537, 22712629296843271867140518185260),
    (26845416039893360305516015851501077574841, 65537, 6820997247850432766042868007364587250604),
    (2146776870009792253322117406137065611833216495831, 65537, 604615692674313046352476676786807225671015935385)
]

def decrypt_male():
    output = "" 
    for n, e, y in inputs_small:
        print(f"\n[Malé] Spracovávam n={n}")
        result = rsa_decrypt(n, e, y, small=True)
        if result:
            x, d, p, q, elapsed = result
            out = f"n={n}\np={p}, q={q}\nd={d}\nx={x}\nTrvanie: {elapsed:.2f} sekúnd\n{'-'*60}\n"
            print(out)
            output += out
    return output 

def decrypt_velke():
    output = ""
    for n, e, y in inputs_large:
        print(f"\n[Veľké] Spracovávam n={n}")
        result = rsa_decrypt(n, e, y, small=False)
        if result:
            x, d, p, q, elapsed = result
            out = f"n={n}\np={p}, q={q}\nd={d}\nx={x}\nTrvanie: {elapsed:.2f} sekúnd\n{'-'*60}\n"
            print(out)
            output += out
    return output

if __name__ == "__main__":
    start_total = time.time()
    with open("rsa_results.txt", "w", encoding="utf-8") as f:
        f.write("=== Dešifrovanie malých úloh ===\n")
        male_results = decrypt_male()
        f.write(male_results)

        f.write("=== Dešifrovanie veľkých úloh ===\n")
        velke_results = decrypt_velke()
        f.write(velke_results)

        total_time = time.time() - start_total
        f.write(f"\nCelkový čas výpočtu: {total_time:.2f} sekúnd\n")

    print("\n✅ Výsledky boli uložené do rsa_results.txt")
