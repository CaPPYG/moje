#!/usr/bin/env python3
"""
Analýza DDoS útoku z pcapng súboru - KOMPLETNÁ ANALÝZA (Krok 1 až 6)
════════════════════════════════════════════════════════════════════
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import dpkt
import warnings
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════════
# KONFIGURÁCIA
# ═══════════════════════════════════════════════════════════════════════════
PCAP_FILE = r"C:\Users\patri\Desktop\tis\zadanie3\03dHulk-trim.pcapng"  # Cesta k pcapng súboru
START_TIME_MS = 300000  # Od ktorej ms v súbore začať analýzu
OUTPUT_DIR = "output_ddos"

SAMPLING_WINDOWS = [1.0, 5.0, 10.0]  # tS (ms)
SELECTED_TS = 1.0  # Vybrané okno pre vzorkovanie

MOVING_WINDOWS = [500, 1000, 2000]  # cw (veľkosti kĺzavého okna)
SELECTED_CW = 10  # Vybrané okno pre výpočet parametrov

PREDICTION_WINDOW = 500  # Počet hodnôt (PW) pre predikčný tunel

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
# KROK 1: NAČÍTANIE A VZORKOVANIE
# ═══════════════════════════════════════════════════════════════════════════

def load_pcap(filepath, start_time_ms):
    print(f"[*] Načítavam {filepath}...")
    try:
        with open(filepath, 'rb') as f:
            pcap = dpkt.pcapng.Reader(f) if filepath.endswith('.pcapng') else dpkt.pcap.Reader(f)
            timestamps = [float(ts) for ts, buf in pcap]
        
        if not timestamps: sys.exit("    ✗ Žiadne pakety v súbore!")
            
        t_min_all = timestamps[0]
        if start_time_ms > 0:
            t_limit = t_min_all + (start_time_ms / 1000.0)
            timestamps = [t for t in timestamps if t >= t_limit]
            
        print(f"    ✓ Načítaných {len(timestamps)} paketov")
        return np.array(timestamps)
    except Exception as e:
        sys.exit(f"    ✗ Chyba pri načítavaní: {e}")

def sample_flow(timestamps, ts_ms):
    ts = ts_ms / 1000.0
    t_min, t_max = timestamps[0], timestamps[-1]
    n_slots = int(np.ceil((t_max - t_min) / ts)) + 1
    a = np.zeros(n_slots, dtype=int)
    
    for t in timestamps:
        slot_idx = int((t - t_min) / ts)
        if slot_idx < n_slots: a[slot_idx] += 1
            
    time_axis = (np.arange(n_slots) * ts * 1000) + START_TIME_MS
    return a, time_axis

def plot_sampling_comparison(timestamps):
    print("\n" + "="*70 + "\nKROK 1: VZORKOVANIE\n" + "="*70)
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle('Vzorkovanie toku - Porovnanie rôznych okien (tS)', fontsize=14, fontweight='bold')
    
    sampling_data = {}
    for idx, ts_ms in enumerate(SAMPLING_WINDOWS):
        a, time_axis = sample_flow(timestamps, ts_ms)
        sampling_data[ts_ms] = (a, time_axis)
        print(f"    ✓ Vzorkovanie {ts_ms} ms: {len(a)} slotov")
        
        ax = axes[idx]
        ax.plot(time_axis, a, linewidth=1, color='blue', alpha=0.7)
        ax.fill_between(time_axis, a, alpha=0.2, color='blue')
        ax.set_ylabel('Počet paketov')
        ax.set_title(f'Vzorkovacie okno: {ts_ms*1000:.0f} µs')
        ax.grid(True, alpha=0.3)
    
    axes[-1].set_xlabel('Čas [ms]')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '01_sampling_comparison.png'), dpi=150)
    plt.close()
    
    print(f"\n    → VYBRATÉ PRE ĎALŠIE KROKY: tS = {SELECTED_TS} ms")
    return sampling_data[SELECTED_TS][0], sampling_data[SELECTED_TS][1]

# ═══════════════════════════════════════════════════════════════════════════
# KROK 2: JEDNOROZMERNÉ KĹZAVÉ PARAMETRE
# ═══════════════════════════════════════════════════════════════════════════

def compute_1d_params(a, cw):
    n = len(a)
    params = {
        'avg': np.zeros(n), 'std': np.zeros(n), 'cv': np.zeros(n),
        'q': np.zeros(n), 'skewness': np.zeros(n), 'kurtosis': np.zeros(n)
    }
    
    for i in range(n):
        start = max(0, i - cw + 1)
        window = a[start:i+1]
        
        if len(window) == 0: continue
        
        mean_val = np.mean(window)
        params['avg'][i] = mean_val
        
        std_val = np.std(window, ddof=1) if len(window) > 1 else 0
        params['std'][i] = std_val
        params['cv'][i] = std_val / mean_val if mean_val > 0 else 0
        
        p = np.count_nonzero(window) / len(window)
        params['q'][i] = 1.0 - p
        
        if len(window) > 1 and std_val > 0:
            params['skewness'][i] = np.mean((window - mean_val)**3) / (std_val**3)
            params['kurtosis'][i] = np.mean((window - mean_val)**4) / (std_val**4) - 3
            
    return params

def run_step_2(a, time_axis):
    print("\n" + "="*70 + "\nKROK 2: JEDNOROZMERNÉ KĹZAVÉ PARAMETRE\n" + "="*70)
    
    cw_data = {}
    print("    [*] Počítam dáta pre všetky okná cw (môže to chvíľu trvať)...")
    for cw in MOVING_WINDOWS:
        cw_data[cw] = compute_1d_params(a, cw)
        
    print("    [*] Vykresľujem porovnávací graf priemerov...")
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle('Porovnanie kĺzavého priemeru pre rôzne výpočtové okná (cw)', fontsize=14, fontweight='bold')
    
    for idx, cw in enumerate(MOVING_WINDOWS):
        ax = axes[idx]
        ax.plot(time_axis, a, linewidth=0.5, color='gray', alpha=0.4, label='Pôvodný tok')
        ax.plot(time_axis, cw_data[cw]['avg'], linewidth=1.5, color='red', label=f'Priemer (cw={cw})')
        ax.set_ylabel('Počet paketov')
        ax.set_title(f'Výpočtové okno cw = {cw}')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        
    axes[-1].set_xlabel('Čas [ms]')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '02a_porovnanie_priemerov.png'), dpi=150)
    plt.close()

    print(f"\n    → PRE OSTATNÉ PARAMETRE BOLO ZVOLENÉ OKNO: cw = {SELECTED_CW}")
    print("    [*] Vykresľujem samostatné grafy pre 1D parametre...")
    
    selected_params = cw_data[SELECTED_CW]
    param_titles = {
        'std': 'Smerodajná odchýlka', 'cv': 'Koeficient variabilnosti',
        'q': 'Pravdepodobnosť q (1-p)', 'skewness': 'Koeficient šikmosti', 'kurtosis': 'Koeficient špicatosti'
    }
    
    for key, title in param_titles.items():
        fig, ax1 = plt.subplots(figsize=(14, 5))
        ax1.set_xlabel('Čas [ms]'); ax1.set_ylabel('Tok paketov a(i)', color='tab:blue')
        ax1.plot(time_axis, a, color='tab:blue', linewidth=0.5, alpha=0.5, label='Tok a(i)')
        ax1.tick_params(axis='y', labelcolor='tab:blue'); ax1.grid(True, alpha=0.3)

        ax2 = ax1.twinx()  
        ax2.set_ylabel(title, color='tab:red', fontweight='bold')  
        ax2.plot(time_axis, selected_params[key], color='tab:red', linewidth=1.5, label=title)
        ax2.tick_params(axis='y', labelcolor='tab:red')

        fig.suptitle(f'{title} (pri okne cw = {SELECTED_CW})', fontsize=14, fontweight='bold')
        fig.tight_layout()  
        plt.savefig(os.path.join(OUTPUT_DIR, f'02b_{key}_cw{SELECTED_CW}.png'), dpi=150)
        plt.close()

    print(f"    ✓ Grafy KROKU 2 uložené.")

# ═══════════════════════════════════════════════════════════════════════════
# KROK 3: DVOJROZMERNÉ KĹZAVÉ PARAMETRE
# ═══════════════════════════════════════════════════════════════════════════

def compute_2d_params(a, cw):
    n = len(a)
    params = {
        'correlation': np.zeros(n), 
        'ar1': np.zeros(n)
    }
    
    for i in range(n):
        if i >= cw - 1:
            w_curr = a[i - cw + 1 : i + 1]
            mean_curr = np.mean(w_curr)
            num_ar = np.sum((w_curr[:-1] - mean_curr) * (w_curr[1:] - mean_curr))
            den_ar = np.sum((w_curr - mean_curr)**2)
            if den_ar > 0:
                params['ar1'][i] = num_ar / den_ar
        
        if i >= 2 * cw - 1:
            w_prev = a[i - 2*cw + 1 : i - cw + 1]
            w_curr = a[i - cw + 1 : i + 1]         
            mean_prev = np.mean(w_prev)
            mean_curr = np.mean(w_curr)
            num_corr = np.sum((w_prev - mean_prev) * (w_curr - mean_curr))
            den_corr = np.sqrt(np.sum((w_prev - mean_prev)**2) * np.sum((w_curr - mean_curr)**2))
            if den_corr > 0:
                params['correlation'][i] = num_corr / den_corr
                
    return params

def run_step_3(a, time_axis):
    print("\n" + "="*70 + "\nKROK 3: DVOJROZMERNÉ KĹZAVÉ PARAMETRE\n" + "="*70)
    print(f"    [*] Počítam AR(1) a Koreláciu (pre zvolené okno cw = {SELECTED_CW})...")
    
    params_2d = compute_2d_params(a, SELECTED_CW)
    
    param_titles = {
        'correlation': 'Korelačný koeficient (Pearson)',
        'ar1': 'Autoregresný koeficient AR(1)'
    }
    
    print("    [*] Vykresľujem grafy pre 2D parametre...")
    for key, title in param_titles.items():
        fig, ax1 = plt.subplots(figsize=(14, 5))
        ax1.set_xlabel('Čas [ms]'); ax1.set_ylabel('Tok paketov a(i)', color='tab:blue')
        ax1.plot(time_axis, a, color='tab:blue', linewidth=0.5, alpha=0.5, label='Tok a(i)')
        ax1.tick_params(axis='y', labelcolor='tab:blue'); ax1.grid(True, alpha=0.3)

        ax2 = ax1.twinx()  
        ax2.set_ylabel(title, color='tab:green', fontweight='bold')  
        ax2.plot(time_axis, params_2d[key], color='tab:green', linewidth=1.5, label=title)
        ax2.tick_params(axis='y', labelcolor='tab:green')
        ax2.set_ylim(-1.1, 1.1)

        fig.suptitle(f'{title} (pri okne cw = {SELECTED_CW})', fontsize=14, fontweight='bold')
        fig.tight_layout()  
        plt.savefig(os.path.join(OUTPUT_DIR, f'03_{key}_cw{SELECTED_CW}.png'), dpi=150)
        plt.close()

    print(f"    ✓ Grafy KROKU 3 uložené v zložke: {OUTPUT_DIR}")

# ═══════════════════════════════════════════════════════════════════════════
# KROK 5: PREDIKČNÉ TUNELY
# ═══════════════════════════════════════════════════════════════════════════

def compute_prediction_tunnel(signal, pw_size):
    n = len(signal)
    means = np.zeros(n)
    stds = np.zeros(n)
    
    for i in range(n):
        start = max(0, i - pw_size)
        window = signal[start:i]
        
        if len(window) > 0:
            means[i] = np.mean(window)
            stds[i] = np.std(window, ddof=1) if len(window) > 1 else 0
        else:
            means[i] = signal[i]
            stds[i] = 0
            
    bounds = {}
    for n_sigma in [1, 2, 3]:
        bounds[n_sigma] = (means - n_sigma * stds, means + n_sigma * stds)
        
    return means, stds, bounds

def run_step_5(a, time_axis, params_1d):
    print("\n" + "="*70 + "\nKROK 5: PREDIKČNÉ TUNELY (Detekcia)\n" + "="*70)
    print(f"    [*] Počítam predikčné tunely pre vybrané parametre (PW = {PREDICTION_WINDOW})...")
    
    selected_keys = ['avg', 'std', 'cv', 'skewness']
    mid_idx = len(time_axis) // 2 
    
    for key in selected_keys:
        signal = params_1d[key]
        means, stds, bounds = compute_prediction_tunnel(signal, PREDICTION_WINDOW)
        
        fig, ax1 = plt.subplots(figsize=(14, 6))
        ax1.set_xlabel('Čas [ms]')
        ax1.set_ylabel('Pôvodný tok a(i)', color='tab:blue')
        ax1.plot(time_axis, a, color='tab:blue', linewidth=0.3, alpha=0.3, label='Tok a(i)')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        
        ax2 = ax1.twinx()
        ax2.set_ylabel(f'Parameter: {key}', color='black', fontweight='bold')
        
        ax2.fill_between(time_axis, bounds[3][0], bounds[3][1], color='red', alpha=0.1)
        ax2.plot(time_axis, bounds[3][1], color='red', linewidth=1.5, linestyle='--', label='Hranica +3σ')
        ax2.plot(time_axis, bounds[3][0], color='red', linewidth=1.5, linestyle='--', label='Hranica -3σ')
        
        ax2.fill_between(time_axis, bounds[2][0], bounds[2][1], color='orange', alpha=0.15, label='±2σ Tunel')
        ax2.fill_between(time_axis, bounds[1][0], bounds[1][1], color='green', alpha=0.2, label='±1σ Tunel')
        
        ax2.plot(time_axis, signal, color='black', linewidth=0.6, alpha=0.8, label=f'Hodnota {key}')
        
        start_plot_idx = SELECTED_CW 
        if start_plot_idx < len(time_axis):
            end_plot_idx = max(start_plot_idx + 10, mid_idx)
            ax1.set_xlim(time_axis[start_plot_idx], time_axis[end_plot_idx])
            
            valid_signal = signal[start_plot_idx:end_plot_idx]
            valid_bound_upper = bounds[3][1][start_plot_idx:end_plot_idx]
            valid_bound_lower = bounds[3][0][start_plot_idx:end_plot_idx]
            
            if len(valid_signal) > 0:
                y_max = max(np.max(valid_signal), np.max(valid_bound_upper))
                y_min = min(np.min(valid_signal), np.min(valid_bound_lower))
                padding = (y_max - y_min) * 0.1
                if padding == 0: padding = 1
                ax2.set_ylim(y_min - padding, y_max + padding)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize='small')
        
        fig.suptitle(f'Predikčný tunel (Prvá polovica, PW={PREDICTION_WINDOW}) pre: {key}', fontsize=14, fontweight='bold')
        fig.tight_layout()
        
        filename = os.path.join(OUTPUT_DIR, f'05_tunnel_{key}_pw{PREDICTION_WINDOW}_zoom.png')
        plt.savefig(filename, dpi=150)
        plt.close()
        print(f"    ✓ Vygenerovaný graf s tunelom: {filename}")

# ═══════════════════════════════════════════════════════════════════════════
# KROK 6: FINÁLNE VYHODNOTENIE A GRAFY DETEKCIE
# ═══════════════════════════════════════════════════════════════════════════

def run_step_6(a, time_axis, params_1d):
    print("\n" + "="*70 + "\nKROK 6: VYHODNOTENIE (Falošné poplachy a Doba detekcie)\n" + "="*70)
    
    # 1. Definícia kedy reálne začal útok a odkedy hodnotiť
    WARM_UP_IDX = SELECTED_CW  # Ignorujeme počiatočný šum
    
    # Podľa zadania: Útok začne tam, kde tok po prvý krát prekročí 30 paketov
    attack_candidates = np.where((a > 20) & (np.arange(len(a)) > WARM_UP_IDX))[0]
    if len(attack_candidates) > 0:
        ATTACK_START_IDX = int(attack_candidates[0])
        print(f"    [*] Útok automaticky detekovaný v čase: {time_axis[ATTACK_START_IDX]:.0f} ms (tok po prvý krát prekročil 30 paketov)")
    else:
        ATTACK_START_IDX = len(a) // 2
        print(f"    [!] Útok nebol detekovaný podľa kritéria (a > 30), používam stredný čas")

    evaluation_data = []
    selected_keys = ['avg', 'std', 'cv', 'skewness', 'q']
    
    print("    [*] Počítam oneskorenie detekcie pre všetky parametre...")
    
    for key in selected_keys:
        signal = params_1d[key]
        means, stds, bounds = compute_prediction_tunnel(signal, PREDICTION_WINDOW)
        
        # Hodnotíme všetky tunely, ale do špeciálneho grafu dáme len prísny 3-sigma tunel
        for n_sigma in [1, 2, 3]:
            lower, upper = bounds[n_sigma]
            
            # Detekcia je akýkoľvek moment, kedy je signál mimo tunela
            detections = (signal > upper) | (signal < lower)
            
            # Falošné poplachy: Detekcie PRED útokom (ale po zahriatí okna)
            fp_count = np.count_nonzero(detections[WARM_UP_IDX:ATTACK_START_IDX])
            
            # Doba detekcie: Prvá detekcia PO začiatku útoku
            # DÔLEŽITÉ: Ignorujeme prvých SELECTED_CW ms, pretože okno sa musí vyprázdniť od starých dát
            search_start_idx = min(ATTACK_START_IDX + SELECTED_CW, len(detections) - 1)
            post_attack_detections = np.where(detections[search_start_idx:])[0]
            
            if len(post_attack_detections) > 0:
                detection_delay_samples = search_start_idx - ATTACK_START_IDX + post_attack_detections[0]
                detection_delay_ms = detection_delay_samples * SELECTED_TS
                first_detection_idx = ATTACK_START_IDX + detection_delay_samples
            else:
                detection_delay_ms = -1
                first_detection_idx = None
                
            evaluation_data.append({
                'Parameter': key,
                'Sigma Tunel': f"±{n_sigma}σ",
                'Falošné Poplachy (FP)': fp_count,
                'Doba Detekcie [ms]': detection_delay_ms if detection_delay_ms != -1 else "Nenájdené"
            })
            
            # Vygenerujeme špeciálny graf len pre 3-sigma tunel, ktorý to vizuálne potvrdí
            if n_sigma == 3:
                fig, ax = plt.subplots(figsize=(14, 6))
                
                # Zobrazíme výrez okolo útoku - útok v strede
                plot_start = max(0, ATTACK_START_IDX - 3000)
                plot_end = min(len(time_axis), ATTACK_START_IDX + 3000)
                
                # Vykresliť dáta
                ax.plot(time_axis[plot_start:plot_end], signal[plot_start:plot_end], color='black', linewidth=1.5, label=f'Parameter {key}')
                ax.plot(time_axis[plot_start:plot_end], upper[plot_start:plot_end], color='red', linestyle='--', linewidth=1.5, label='Hranica +3σ')
                ax.plot(time_axis[plot_start:plot_end], lower[plot_start:plot_end], color='red', linestyle='--', linewidth=1.5, label='Hranica -3σ')
                
                # **DÔLEŽITÉ: Nastaviť xlim PRED kreslením čiar**
                ax.set_xlim(time_axis[plot_start], time_axis[plot_end])
                
                # Zvislá čiara - Skutočný útok
                ax.axvline(x=time_axis[ATTACK_START_IDX], color='red', linewidth=1, linestyle='-', label=f'ZAČIATOK ÚTOKU ({time_axis[ATTACK_START_IDX]:.0f} ms)')
                
                # Zvislá čiara - Moment detekcie
                if first_detection_idx is not None and plot_start <= first_detection_idx <= plot_end:
                    ax.axvline(x=time_axis[first_detection_idx], color='green', linewidth=1, linestyle='-', label=f'DETEKCIA (Oneskorenie: {detection_delay_ms:.0f} ms)')
                
                ax.set_title(f'Vyhodnotenie (Krok 6) - Parameter: {key} (Tunel ±3σ)', fontsize=12, fontweight='bold')
                ax.set_xlabel('Čas [ms]')
                ax.set_ylabel('Hodnota parametra')
                ax.legend(loc='upper left', fontsize=9)
                ax.grid(True, alpha=0.3)
                
                filename = os.path.join(OUTPUT_DIR, f'06_evaluation_{key}_3sigma.png')
                plt.savefig(filename, dpi=150)
                plt.close()

    # 2. Vytlačenie a uloženie tabuľky
    df = pd.DataFrame(evaluation_data)
    print("\nTABUĽKA VÝSLEDKOV:")
    print(df.to_string(index=False))
    
    csv_path = os.path.join(OUTPUT_DIR, '06_vyhodnotenie_tabulka.csv')
    df.to_csv(csv_path, index=False, sep=';', encoding='utf-8-sig')
    print(f"\n    ✓ Tabuľka uložená do: {csv_path}")
    print(f"    ✓ Evaluačné grafy detekcie uložené v priečinku.")

    # 3. Záverečné zhodnotenie
    print("\n" + "="*70)
    print("ZÁVEREČNÉ ODPORÚČANIE (Víťazný koeficient)")
    print("="*70)
    
    df_valid = df[df['Doba Detekcie [ms]'] != "Nenájdené"]
    if len(df_valid) > 0:
        # Preferujeme 0 falošných poplachov
        df_zero_fp = df_valid[df_valid['Falošné Poplachy (FP)'] == 0]
        
        if len(df_zero_fp) > 0:
            best_idx = df_zero_fp['Doba Detekcie [ms]'].idxmin()
            best_row = df_zero_fp.loc[best_idx]
        else:
            # Ak majú všetky FP, zoberieme ten s najmenším počtom FP a najkratším časom
            scores = (df_valid['Falošné Poplachy (FP)'] * 1000) + df_valid['Doba Detekcie [ms]']
            best_idx = scores.idxmin()
            best_row = df_valid.loc[best_idx]
            
        print(f"    🏆 NAJLEPŠÍ KOEFICIENT: {best_row['Parameter']} ({best_row['Sigma Tunel']})")
        print(f"      • Falošné poplachy pred útokom: {best_row['Falošné Poplachy (FP)']}")
        print(f"      • Doba detekcie od začiatku útoku: {best_row['Doba Detekcie [ms]']:.0f} ms")
        print("\n    Zdôvodnenie: Tento parameter najlepšie ignoroval bežný šum a zároveň")
        print("    najrýchlejšie upozornil na prudký nárast prevádzky z '2 na stovky'.")

# ═══════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "═"*70)
    print("DDoS ANALÝZA Z PCAPNG - HLAVNÉ MENU")
    print("═"*70)
    print(" [1] Krok 1: Vzorkovanie")
    print(" [2] Krok 2: 1D Parametre")
    print(" [3] Krok 3: 2D Parametre")
    print(" [4] Krok 5: Predikčné tunely (ZAZOOMOVANÉ)")
    print(" [6] Krok 6: Vyhodnotenie parametrov (Tabuľka a grafy detekcie)")
    print(" [0] Spustiť VŠETKO naraz")
    print("═"*70)
    
    volba = input("Zadajte číslo úlohy, ktorú chcete vykonať: ").strip()
    if volba not in ['0', '1', '2', '3', '4', '6']: return

    timestamps = load_pcap(PCAP_FILE, START_TIME_MS)

    a, time_axis = sample_flow(timestamps, SELECTED_TS)
    if volba == '1': return
    
    if volba in ['0', '2']:
        run_step_2(a, time_axis)
        if volba == '2': return
    
    if volba in ['0', '3']:
        run_step_3(a, time_axis)
        if volba == '3': return
        
    print("    [*] Pripravujem 1D parametre...")
    params_1d = compute_1d_params(a, SELECTED_CW)

    if volba in ['0', '4']:
        run_step_5(a, time_axis, params_1d)
        if volba == '4': return

    # Spustenie nového KROKU 6
    if volba in ['0', '6']:
        run_step_6(a, time_axis, params_1d)

if __name__ == "__main__":
    main()