import string
from collections import Counter, defaultdict


with open('moje/sifry/uloha1/text1_enc.txt', 'r') as f:
    ciphertext = f.read()


sk_frequencies = {
    'A': 0.110, 'B': 0.020, 'C': 0.025, 'D': 0.036, 'E': 0.095, 'F': 0.002,
    'G': 0.001, 'H': 0.021, 'I': 0.085, 'J': 0.025, 'K': 0.045, 'L': 0.035,
    'M': 0.035, 'N': 0.060, 'O': 0.090, 'P': 0.030, 'Q': 0.001, 'R': 0.050,
    'S': 0.050, 'T': 0.060, 'U': 0.035, 'V': 0.045, 'W': 0.001, 'X': 0.001,
    'Y': 0.020, 'Z': 0.030
}

en_frequencies = {
    'A': 0.0817, 'B': 0.0149, 'C': 0.0278, 'D': 0.0425, 'E': 0.1270,
    'F': 0.0223, 'G': 0.0202, 'H': 0.0609, 'I': 0.0697, 'J': 0.0015,
    'K': 0.0077, 'L': 0.0403, 'M': 0.0241, 'N': 0.0675, 'O': 0.0751,
    'P': 0.0193, 'Q': 0.0010, 'R': 0.0599, 'S': 0.0633, 'T': 0.0906,
    'U': 0.0276, 'V': 0.0098, 'W': 0.0236, 'X': 0.0015, 'Y': 0.0197,
    'Z': 0.0007
}

sk_ic = 0.0620
en_ic = 0.0667

# Výpočet Index of Coincidence
def index_of_coincidence(text):
    N = len(text)
    freqs = Counter(text)
    ic = sum(f * (f-1) for f in freqs.values()) / (N * (N-1))
    return ic

# Odhad dĺžky hesla pomocou Friedmanovej metódy
def friedman_estimate_length(text):
    ic = index_of_coincidence(text)
    if ic == 0:
        return 1
    return round(0.027 * len(text) / ((len(text)-1) * ic - 0.038 * len(text) + 0.065))


def kasiski_test(text):
    # Zachovanie len veľkých písmen (A-Z)
    text = ''.join([c for c in text if 'A' <= c <= 'Z'])
    
    n = len(text)
    distances = []

    # Hľadanie opakujúcich sa trigramov
    for i in range(n - 2):
        trigram = text[i:i+3]
        for j in range(i+1, n - 2):
            if text[j:j+3] == trigram:
                distances.append((j - i, trigram))
    
    return distances   

def guess_key_length(distances):
    factors = []

    for d, _ in distances:
        for i in range(3, 26):  # heslo má dĺžku 15–25, takže skúšame len tento rozsah
            if d % i == 0:
                factors.append(i)
    
    factor_counts = Counter(factors)
    most_common = factor_counts.most_common(5)  # top 5 najpravdepodobnejších dĺžok hesla
    return most_common

def test_key_lengths(text, start_len=1, end_len=10):
    """
    Nájde dve dĺžky kľúča, ktoré majú priemerný IC najbližšie k SK a EN.
    """
    text = ''.join([c for c in text if 'A' <= c <= 'Z'])
    
    if not text:
        print("Text neobsahuje žiadne veľké písmená A-Z!")
        return None, None

    ic_list = []
    for key_len in range(start_len, end_len + 1):
        groups = [''.join(text[i::key_len]) for i in range(key_len)]
        avg_ic = sum(index_of_coincidence(g) for g in groups) / key_len
        ic_list.append((key_len, avg_ic))
        print(f"Dĺžka kľúča {key_len}: IC = {avg_ic:.4f}")

    # Najbližšie k SK
    best_sk = min(ic_list, key=lambda x: abs(x[1] - sk_ic))[0]
    # Najbližšie k EN
    best_en = min(ic_list, key=lambda x: abs(x[1] - en_ic))[0]

    return best_sk, best_en


def chi_squared_stat(observed, expected):
    return sum((observed.get(chr(i + 65), 0) - expected[chr(i + 65)]) ** 2 / expected[chr(i + 65)] for i in range(26))

def get_key_for_length(text, key_length, freqs_reference):
    text = ''.join([c for c in text if 'A' <= c <= 'Z'])
    key = ""

    for i in range(key_length):
        group = text[i::key_length]
        best_shift = None
        lowest_chi = float('inf')

        for shift in range(26):
            shifted = ''.join(chr((ord(c) - 65 - shift) % 26 + 65) for c in group)
            freqs = Counter(shifted)
            total = len(shifted)
            if total == 0:
                continue
            observed = {c: freqs.get(c, 0) / total for c in freqs_reference}
            chi = sum((observed[c] - freqs_reference[c]) ** 2 / freqs_reference[c] for c in freqs_reference)

            if chi < lowest_chi:
                lowest_chi = chi
                best_shift = shift

        key += chr(65 + (best_shift or 0))

    return key


def vigenere_decrypt(text, key):
    text = ''.join([c for c in text if 'A' <= c <= 'Z'])
    key = key.upper()
    plaintext = ''
    for i, c in enumerate(text):
        k = key[i % len(key)]
        p = (ord(c) - ord(k)) % 26
        plaintext += chr(p + 65)
    return plaintext

def brute_force_decrypt(text, start_len, end_len):
    for kluc in range(start_len, end_len + 1):
        key = get_key_for_length(text, kluc)
        decrypted_text = vigenere_decrypt(text, key)
        print(f"\nDešifrovaný text s dĺžkou kľúča {kluc}:")
        print(decrypted_text + "\n")










distances = kasiski_test(ciphertext)
for d, trigram in distances:
    print(f"{d} ({trigram})")

#dlzky hesla
estimated_length = friedman_estimate_length(ciphertext)
#print(f"Odhadovaná dĺžka hesla: {estimated_length}")

key_length_estimates = guess_key_length(distances)
#print("Pravdepodobné dĺžky hesla:", key_length_estimates)

best_sk, best_en = test_key_lengths(ciphertext, start_len=14, end_len=26)

print(f"Najlepšia dĺžka kľúča pre SK: {best_sk}")
print(f"Najlepšia dĺžka kľúča pre EN: {best_en}")

keySK = get_key_for_length(ciphertext, best_sk, sk_frequencies)
print("Odhadnutý kľúč pre SK:", keySK)

keyEN = get_key_for_length(ciphertext, best_en, en_frequencies)
print("Odhadnutý kľúč pre EN:", keyEN)

plaintextSK = vigenere_decrypt(ciphertext, keySK)
print("\nDešifrovaný text pre SK:")
print(plaintextSK)

plaintextEN = vigenere_decrypt(ciphertext, keyEN)
print("\nDešifrovaný text pre EN:")
print(plaintextEN)

#vysledok = over_zmysel_textu(plaintext)
#print(vysledok)




    





