import numpy as np

# --- Pomocné funkcie ---
def char_to_num(c):
    return ord(c) - ord('A')

def num_to_char(n):
    return chr((int(n) % 26) + ord('A'))

def mod_inv(a, m):
    """Multiplikatívny inverz a^{-1} modulo m, alebo None ak neexistuje."""
    a = a % m
    for i in range(1, m):
        if (a * i) % m == 1:
            return i
    return None

def matrix_mod_inv(matrix, modulus):
    """Inverzia matice modulo `modulus`."""
    det = int(round(np.linalg.det(matrix))) % modulus
    det_inv = mod_inv(det, modulus)
    if det_inv is None:
        raise ValueError("Matica nemá inverziu mod {}.".format(modulus))
    inv_float = np.linalg.inv(matrix)
    adjugate = np.round(inv_float * np.linalg.det(matrix)).astype(int) % modulus
    return (det_inv * adjugate) % modulus

# --- Pomocné funkcie pre trigramy ---
def trigrams(text):
    return [text[i:i+3] for i in range(0, len(text), 3)]

def trigrams_to_matrix(trigrams_list):
    return np.array([[char_to_num(c) for c in trigram] for trigram in trigrams_list]).T

# --- Funkcia na výpočet kľúča a dešifrovanie ---
def hill_decrypt(ciphertext, known_plain="DRAHYJURAJ"):
    plain_trigrams = trigrams(known_plain)
    cipher_trigrams = trigrams(ciphertext)

    # tvorba matíc z prvých 3 trigramov
    P = trigrams_to_matrix(plain_trigrams[:3])
    C = trigrams_to_matrix(cipher_trigrams[:3])

    # výpočet kľúča
    try:
        P_inv = matrix_mod_inv(P, 26)
    except ValueError:
        # ak P nie je invertovateľné, skús posun
        P = trigrams_to_matrix(plain_trigrams[1:4])
        C = trigrams_to_matrix(cipher_trigrams[1:4])
        P_inv = matrix_mod_inv(P, 26)

    K = (C.dot(P_inv)) % 26
    K_inv = matrix_mod_inv(K, 26)

    # dešifrovanie
    decrypted = ""
    for trigram in cipher_trigrams:
        vec = np.array([[char_to_num(c)] for c in trigram])
        res = (K_inv.dot(vec)) % 26
        decrypted += "".join(num_to_char(x) for x in res.flatten())

    return decrypted, K

# --- Vstupné texty ---
cipher_texts = {
    "Text 1": "NMUSMRFJGRWSWVKKDJKYTYTNSVMOJW",
    "Text 2": "PCPOVZOJYEJXJLVINLJMIAVAVEUKZLERO",
    "Text 3": "BALQTGFGYNFUHVLOIVCGPRZJUTHGWOVWCWAJGWN"
}

# --- Dešifrovanie všetkých troch ---
print("--- Dešifrovanie Hillovou šifrou (trigramy) ---\n")

for label, cipher in cipher_texts.items():
    decrypted, key_matrix = hill_decrypt(cipher)
    print(f"{label}:")
    print("Kľúčová matica K:")
    print(key_matrix)
    print("Dešifrovaný text:")
    print(decrypted)
    print("-" * 50)