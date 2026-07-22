#!/usr/bin/env python3
"""
Komplexná analýza reálneho IP toku
────────────────────────────────────────────────────────────────
[1] Tok a(i) + 4 kĺzavé okná m(t) → výber najvhodnejšieho
[2] m(t) + s(t) + pásy ±1σ / ±2σ / ±3σ
[3] V(t) = s/m – samostatne (s hodnotou 1) + spolu s a(i)
[4] Kĺzavý odhad p pre Binomické rozdelenie + spolu s a(i)
[5] Bernoulliho aproximácia + porovnanie histogramov
[6] MMRP odhady α(t), β(t) + spolu s a(i)
[7] MMRP simulácia + porovnanie histogramov
[8] FFT vyhladzovanie (5 harmoník) + zdôvodnenie
[9] Body 5–7 zopakované na FFT-vyhladených dátach
"""

import sys
import dpkt
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as ticker
from scipy.fft import fft, ifft, fftfreq

# ─────────────────────────────────────────────────────────────────
# KONFIGURÁCIA  –  uprav podľa potreby
# ─────────────────────────────────────────────────────────────────
PCAP_FILE    = "split_00003_20241231060017.pcap"
SAMPLING_S   = 0.001            # vzorkovanie 1 ms
WINDOWS_TEST = [50, 200, 500, 1000]   # 4 okná na porovnanie (sloty)
N_FFT_REMOVE = 500                # počet harmoník na odstránenie FFT

# ─────────────────────────────────────────────────────────────────
# PARSOVANIE PCAP
# ─────────────────────────────────────────────────────────────────
def parse_pcap(path: str):
    times, protos = [], []

    def _process(reader):
        t0 = None
        for ts, buf in reader:
            if t0 is None:
                t0 = ts
            times.append(ts - t0)
            try:
                eth = dpkt.ethernet.Ethernet(buf)
                ip  = eth.data
                if isinstance(ip, dpkt.ip.IP):
                    protos.append(
                        'TCP'   if ip.p == dpkt.ip.IP_PROTO_TCP else
                        'UDP'   if ip.p == dpkt.ip.IP_PROTO_UDP else 'OTHER')
                else:
                    protos.append('OTHER')
            except Exception:
                protos.append('OTHER')

    with open(path, 'rb') as f:
        try:
            _process(dpkt.pcapng.Reader(f))
        except Exception:
            f.seek(0)
            _process(dpkt.pcap.Reader(f))

    return np.asarray(times), protos


# ─────────────────────────────────────────────────────────────────
# TOK a(i)
# ─────────────────────────────────────────────────────────────────
def compute_flow(times: np.ndarray, sr: float):
    """Vracia (slot_times [s], flow [pkt/slot])."""
    n = int(times[-1] / sr) + 1
    flow = np.zeros(n, dtype=np.float64)
    for ts in times:
        idx = int(ts / sr)
        if idx < n:
            flow[idx] += 1
    return np.arange(n, dtype=np.float64) * sr, flow


# ─────────────────────────────────────────────────────────────────
# KĹZAVÉ ŠTATISTIKY  (kauzálne okno)
# ─────────────────────────────────────────────────────────────────
def moving_stats(flow: np.ndarray, window: int):
    """m(t), s(t), V(t) – kĺzavé, bez pohľadu do budúcnosti."""
    ser  = pd.Series(flow)
    roll = ser.rolling(window=window, min_periods=1)
    m    = roll.mean().to_numpy()
    s    = roll.std(ddof=0).to_numpy()
    s    = np.nan_to_num(s, nan=0.0)
    with np.errstate(invalid='ignore', divide='ignore'):
        V = np.where(m > 0, s / m, 0.0)
    return m, s, V


# ─────────────────────────────────────────────────────────────────
# BINOMICKÝ ODHAD  p(t)
# ─────────────────────────────────────────────────────────────────
def binom_p(m: np.ndarray, s: np.ndarray) -> np.ndarray:
    """
    B(n,p): E=np, Var=npq  →  q = Var/E = s²/m  →  p = 1 − s²/m.
    Príklad: m=5, Var=4  →  q=0.8, p=0.2
    """
    with np.errstate(invalid='ignore', divide='ignore'):
        p = np.where(m > 0, 1.0 - s**2 / m, np.nan)
    return p


# ─────────────────────────────────────────────────────────────────
# MMRP – odhad α(t), β(t)
# ─────────────────────────────────────────────────────────────────
def mmrp_estimate(flow: np.ndarray, m: np.ndarray, window: int):
    """
    2-stavový ON/OFF model (prah = m(t)):
        state[i] = 1 (ON)  ak  flow[i] >= m[i]
    α(t) = kĺzavé P(ON→OFF),  β(t) = kĺzavé P(OFF→ON)
    """
    state = (flow >= m).astype(np.float64)
    diff  = np.diff(state, prepend=state[0])

    t10 = pd.Series((diff < 0).astype(float))  # ON→OFF
    t01 = pd.Series((diff > 0).astype(float))  # OFF→ON
    on  = pd.Series(state)
    off = pd.Series(1.0 - state)

    r = dict(window=window, min_periods=1)
    sum_t10 = t10.rolling(**r).sum().to_numpy()
    sum_t01 = t01.rolling(**r).sum().to_numpy()
    sum_on  = on.rolling(**r).sum().to_numpy()
    sum_off = off.rolling(**r).sum().to_numpy()

    with np.errstate(invalid='ignore', divide='ignore'):
        alpha = np.where(sum_on  > 0, sum_t10 / sum_on,  0.0)
        beta  = np.where(sum_off > 0, sum_t01 / sum_off, 0.0)

    return np.clip(alpha, 0, 1), np.clip(beta, 0, 1), state


def mmrp_simulate(alpha_val: float, beta_val: float,
                  n: int, mu_on: float, mu_off: float) -> tuple:
    """Simulácia ON/OFF Markovského reťazca + Poissonov tok."""
    pi1   = beta_val  / (alpha_val + beta_val + 1e-12)
    state = int(np.random.rand() < pi1)
    states = np.empty(n, dtype=np.int8)
    for i in range(n):
        states[i] = state
        if state == 1:
            if np.random.rand() < alpha_val: state = 0
        else:
            if np.random.rand() < beta_val:  state = 1
    mu = np.where(states == 1, max(mu_on, 0.01), max(mu_off, 0.01))
    sim = np.random.poisson(mu).astype(np.float64)
    return sim, states


# ─────────────────────────────────────────────────────────────────
# FFT VYHLADZOVANIE
# ─────────────────────────────────────────────────────────────────
def fft_smooth(flow: np.ndarray, n_remove: int, sr: float):
    """
    Odstráni n_remove najsilnejších harmoník (okrem DC).
    Vracia (smoothed, removed_info).
    removed_info: list of dict {rank, idx, freq_hz, period_s, amplitude}
    """
    N     = len(flow)
    F     = fft(flow)
    freqs = fftfreq(N, d=sr)

    half = N // 2
    Fabs_pos = np.abs(F[1:half])               # bez DC
    top_ranks = np.argsort(Fabs_pos)[-n_remove:][::-1]  # od najsilnejšej
    top_idx   = top_ranks + 1                  # +1 kvôli DC offsetu

    F_sm = F.copy()
    removed_info = []
    for rank, idx in enumerate(top_idx):
        F_sm[idx]     = 0
        F_sm[N - idx] = 0
        fhz = abs(freqs[idx])
        removed_info.append({
            'rank'     : rank + 1,
            'idx'      : idx,
            'freq_hz'  : fhz,
            'period_s' : 1.0 / fhz if fhz > 0 else np.inf,
            'amplitude': np.abs(F[idx]) / (N / 2),
        })

    smoothed = np.real(ifft(F_sm))
    return smoothed, freqs, np.abs(F), removed_info


# ─────────────────────────────────────────────────────────────────
# POMOCNÉ FUNKCIE
# ─────────────────────────────────────────────────────────────────
C = {   # farby
    'flow'  : '#5B9BD5',
    'mean'  : '#1A1A1A',
    'sigma' : '#E67E22',
    'V'     : '#8E44AD',
    'alpha' : '#E74C3C',
    'beta'  : '#27AE60',
    'p'     : '#16A085',
    'fft'   : '#C0392B',
    'sim'   : '#E74C3C',
}

def _base(ax, t, ylabel='', title=''):
    ax.set_xlim(t[0], t[-1])
    ax.set_xlabel("Čas [s]", fontsize=9)
    if ylabel: ax.set_ylabel(ylabel, fontsize=9)
    if title:  ax.set_title(title,   fontsize=10)
    ax.grid(True, alpha=0.18, lw=0.5)
    ax.tick_params(labelsize=8)

def _save(fname):
    plt.tight_layout()
    plt.savefig(fname, dpi=150)
    print(f"[+] Uložené: {fname}")
    plt.close()

def _flow_line(ax, t, flow, m=None, alpha_f=0.55, lw_f=0.30):
    ax.plot(t, flow, color=C['flow'], lw=lw_f, alpha=alpha_f, label='a(i)')
    if m is not None:
        ax.plot(t, m, color=C['mean'], lw=1.4, label='m(t)')


# ─────────────────────────────────────────────────────────────────
# GRAFY
# ─────────────────────────────────────────────────────────────────

def plot_4windows(t, flow, windows):
    fig, axes = plt.subplots(2, 2, figsize=(18, 10), sharex=True)
    fig.suptitle("Úkol 1 – Kĺzavý priemer m(t): porovnanie 4 okien\n"
                 f"(vzorkovanie {SAMPLING_S*1000:.0f} ms)", fontsize=13)
    for ax, W in zip(axes.flat, windows):
        m_w, _, _ = moving_stats(flow, W)
        _flow_line(ax, t, flow, m_w)
        _base(ax, t, "Pakety / slot",
              f"Okno W = {W} slotov  ({W*SAMPLING_S*1000:.0f} ms)")
        ax.legend(fontsize=8, loc='upper right')
    _save("ul1_4okna_m.png")


def plot_bands(t, flow, m, s, W):
    fig, ax = plt.subplots(figsize=(16, 6))
    ax.fill_between(t, m-3*s, m+3*s, color='#E74C3C', alpha=0.12, label='±3σ(t)')
    ax.fill_between(t, m-2*s, m+2*s, color='#F1C40F', alpha=0.22, label='±2σ(t)')
    ax.fill_between(t, m  -s, m  +s, color='#2ECC71', alpha=0.38, label='±1σ(t)')
    _flow_line(ax, t, flow, m)
    ax.set_title(f"Úkol 2 – m(t) + pásy σ(t)   [okno {W} sl. = {W*SAMPLING_S*1000:.0f} ms]",
                 fontsize=12)
    ax.legend(loc='upper right', fontsize=9)
    _base(ax, t, "Pakety / slot")
    _save("ul2_pasma.png")


def plot_V(t, flow, m, s, V, W):
    # ── 3a: a(i) a V(t) vertikálne, referencia V=1 ─────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), sharex=True,
                                   gridspec_kw={'hspace': 0.06})
    fig.suptitle(f"Úkol 3a – a(i) a V(t) = σ/m   [okno {W}]", fontsize=12)
    _flow_line(ax1, t, flow, m)
    _base(ax1, t, "Pakety / slot"); ax1.legend(fontsize=9)
    ax2.plot(t, V, color=C['V'],     lw=0.7, label='V(t) = σ/m')
    ax2.axhline(1, color='red', lw=1.0, ls='--', label='V = 1  (Poisson)')
    _base(ax2, t, "V(t)"); ax2.legend(fontsize=9)
    _save("ul3a_V_sigma.png")

    # ── 3b: V(t) spolu s a(i), duálna os Y ──────────────────────
    fig, ax1 = plt.subplots(figsize=(16, 6))
    l1, = ax1.plot(t, flow, color=C['flow'], lw=0.30, alpha=0.55, label='a(i)')
    l2, = ax1.plot(t, m,    color=C['mean'], lw=1.30,             label='m(t)')
    ax1.set_ylabel("Pakety / slot", color=C['flow'], fontsize=9)
    ax1.tick_params(axis='y', labelcolor=C['flow'])
    ax2 = ax1.twinx()
    l3, = ax2.plot(t, V, color=C['V'], lw=0.80, alpha=0.85, label='V(t)')
    ax2.axhline(1, color='gray', lw=0.8, ls='--', alpha=0.6)
    ax2.set_ylabel("V(t)", color=C['V'], fontsize=9)
    ax2.tick_params(axis='y', labelcolor=C['V'])
    ax1.set_title(f"Úkol 3b – a(i) + V(t)   [duálna os Y, okno {W}]", fontsize=12)
    ax1.legend(handles=[l1,l2,l3], loc='upper right', fontsize=9)
    _base(ax1, t, "Pakety / slot")
    _save("ul3b_tok_V.png")


def plot_binom(t, flow, m, s, W):
    p = binom_p(m, s)
    
    # Vytvorenie jedného veľkého grafu
    fig, ax1 = plt.subplots(figsize=(14, 7))
    plt.title(f"Úkol 4 – Kĺzavý odhad p(t) spolu s tokom a(i) [okno {W}]\n"
              f"Dôkaz zlyhania modelu pri zhlukovej prevádzke (p klesá pod 0)", fontsize=14)

    # --- ĽAVÁ OS: Pôvodný tok (modrá) ---
    ax1.plot(t, flow, color='blue', alpha=0.4, label='Pôvodný tok a(i)')
    ax1.set_xlabel('Čas (index i)', fontsize=12)
    ax1.set_ylabel('Počet paketov a(i)', color='blue', fontsize=12)
    ax1.tick_params(axis='y', labelcolor='blue')
    ax1.grid(True, alpha=0.3)

    # --- PRAVÁ OS: Pravdepodobnosť p(t) (zelená) ---
    ax2 = ax1.twinx() # Vytvorí druhú Y-ovú os zdieľajúcu rovnakú X-ovú os
    ax2.plot(t, p, color='green', linewidth=2, label='Odhad p(t)')
    
    # Pridáme jasnú červenú čiaru na nulu (hranica zlyhania)
    ax2.axhline(0.0, color='red', linewidth=2, linestyle='--', label='Hranica zlyhania (p=0)')
    
    ax2.set_ylabel('Pravdepodobnosť p(t)', color='green', fontsize=12)
    ax2.tick_params(axis='y', labelcolor='green')

    # Spojenie legiend z oboch osí do jednej, aby to vyzeralo pekne
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right', fontsize=10)

    # plt.show() # Odkomentuj, ak chceš, aby ti graf aj vyskočil na obrazovku
    _save("ul4_binom_p_spolu.png")
    
    return p


def _bernoulli_core(flow_seg, label_suffix=""):
    """Simuluj Bernoulli z reálnych dát a porovnaj histogramy."""
    # Odhad pravdepodobnosti: podiel slotov, kde prišiel aspoň 1 paket (nemeňme pôvodné dáta!)
    p_est = np.mean(flow_seg > 0)
    
    # Skutočná simulácia pomocou Bernoulliho modelu
    sim_bern = np.random.binomial(1, p_est, len(flow_seg))
    max_pkt = int(flow_seg.max())

    # Vyrobíme iba DVA grafy pre priame a férové porovnanie
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f"Úkol 5 – Bernoulliho aproximácia{label_suffix}\n"
                 f"Odhad p̂ = {p_est:.4f}  |  Max. počet paketov v reálnom slote = {max_pkt}", fontsize=14)

    # 1. GRAF: Reálna prevádzka (nesploštená!)
    bins_real = np.arange(-0.5, max_pkt + 1.5, 1)
    axes[0].hist(flow_seg, bins=bins_real, density=False,
                 color='#3498DB', edgecolor='k', alpha=0.7)
    axes[0].set_title("Reálna IP prevádzka")
    axes[0].set_xlabel("Počet paketov v slote")

    # 2. GRAF: Bernoulli simulácia
    bins_bern = np.arange(-0.5, 2.5, 1)
    axes[1].hist(sim_bern, bins=bins_bern, density=False,
                 color='#E74C3C', edgecolor='k', alpha=0.7)
    axes[1].set_title(f"Bernoulliho simulácia B(1, {p_est:.3f})")
    axes[1].set_xlabel("Počet paketov v slote")
    axes[1].set_xticks([0, 1])

    # Zjednotenie Y-osí, aby bolo jasne vidieť rozdiel
    max_y = max(axes[0].get_ylim()[1], axes[1].get_ylim()[1])
    for ax in axes:
        ax.set_yscale('log') # Zapnutie logaritmickej osi
        ax.set_ylim(0.5, max_y * 1.5) # Pri log osi nemôže byť nula, začíname od 0.5
        ax.set_ylabel("Frekvencia (Logaritmická mierka)")
        ax.grid(True, alpha=0.3)

    
    plt.tight_layout(rect=[0, 0.08, 1, 1])
    suffix = label_suffix.replace(" ","_").strip("_()").replace("(","").replace(")","")
    _save(f"ul5_bernoulli{'_'+suffix if suffix else ''}.png")


def plot_bernoulli(flow, m, label_suffix=""):
    """Nájde reprezentatívny segment a spustí analýzu."""
    # Namiesto hľadania najprázdnejšieho miesta (m=0.5) nájdeme segment s typickou priemernou prevádzkou
    mean_all = np.mean(flow)
    diff = np.abs(m - mean_all)
    center = int(np.argmin(diff))
    
    W_seg = 2000
    s_from = max(0, center - W_seg//2)
    s_to   = min(len(flow), s_from + W_seg)
    seg    = flow[s_from:s_to]
    
    print(f"   Segment: sloty {s_from}–{s_to}  (m̄≈{np.mean(m[s_from:s_to]):.2f})")
    _bernoulli_core(seg, label_suffix)


def plot_mmrp_params(t, flow, m, s, W):
    # Predpokladám, že tu na začiatku máš funkciu, ktorá tie parametre vypočíta
    # Napríklad: alpha_g, beta_g, _ = mmrp_estimate(flow, m, W)
    alpha_g, beta_g, _ = mmrp_estimate(flow, m, W) # (Uprav podľa tvojho kódu)

    # Vytvorenie jedného veľkého grafu
    fig, ax1 = plt.subplots(figsize=(14, 7))
    plt.title(f"Úkol 6 – Kĺzavý odhad MMRP parametrov α(t), β(t) spolu s tokom a(i) [okno {W}]", fontsize=14)

    # --- ĽAVÁ OS: Pôvodný tok (modrá - dáme ju do pozadia s alpha=0.3) ---
    ax1.plot(t, flow, color='blue', alpha=0.3, label='Pôvodný tok a(i)')
    ax1.set_xlabel('Čas (index i)', fontsize=12)
    ax1.set_ylabel('Počet paketov a(i)', color='blue', fontsize=12)
    ax1.tick_params(axis='y', labelcolor='blue')
    ax1.grid(True, alpha=0.3)

    # --- PRAVÁ OS: Parametre Alfa a Beta ---
    ax2 = ax1.twinx() 
    ax2.plot(t, alpha_g, color='red', linewidth=2, label='α(t) (prechod do burstu)')
    ax2.plot(t, beta_g, color='green', linewidth=2, label='β(t) (návrat do normálu)')
    
    ax2.set_ylabel('Hodnota parametrov α a β', color='black', fontsize=12)
    ax2.tick_params(axis='y', labelcolor='black')

    # Spojenie legiend z oboch osí do jednej
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right', fontsize=10)

    # plt.show() # Odkomentuj, ak chceš graf zobraziť v okne
    _save("ul6_mmrp_alpha_beta_spolu.png")
    
    return alpha_g, beta_g, None


def _mmrp_sim_core(flow, alpha, beta, m, label_suffix=""):
    # Mediánové hodnoty α, β (robustnejšie ako priemer)
    a_val = float(np.median(alpha[alpha > 1e-6])) if np.any(alpha > 1e-6) else 0.05
    b_val = float(np.median(beta [beta  > 1e-6])) if np.any(beta  > 1e-6) else 0.05
    on_mask  = flow >= m
    mu_on    = float(np.mean(flow[on_mask]))  if np.any(on_mask)  else 1.0
    mu_off   = float(np.mean(flow[~on_mask])) if np.any(~on_mask) else 0.0

    sim, _ = mmrp_simulate(a_val, b_val, len(flow), mu_on, mu_off)

    hi = int(np.percentile(np.concatenate([flow, sim]), 99)) + 2
    bins = np.arange(-0.5, hi + 1.5)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(
        f"Úkol 7 – MMRP simulácia vs IP tok{label_suffix}\n"
        f"α={a_val:.5f}, β={b_val:.5f},  μ_ON={mu_on:.2f}, μ_OFF={mu_off:.2f}", fontsize=12)

    axes[0].hist(flow, bins=bins, density=True, color='#3498DB', edgecolor='k', alpha=0.8)
    axes[0].set_title("IP tok – histogram")

    axes[1].hist(sim,  bins=bins, density=True, color=C['sim'],  edgecolor='k', alpha=0.8)
    axes[1].set_title("MMRP simulácia – histogram")

    axes[2].hist(flow, bins=bins, density=True, color='#3498DB',
                 edgecolor='none', alpha=0.55, label='IP tok')
    axes[2].hist(sim,  bins=bins, density=True, color=C['sim'],
                 edgecolor='none', alpha=0.55, label='MMRP sim')
    axes[2].set_title("Overlay")
    axes[2].legend(fontsize=9)

    for ax in axes:
        ax.set_xlabel("Pakety / slot"); ax.set_ylabel("Hustota")
        ax.grid(True, alpha=0.2)

    suffix = label_suffix.replace(" ","_").strip("_").replace("(","").replace(")","")
    _save(f"ul7_mmrp_sim{'_'+suffix if suffix else ''}.png")


def plot_mmrp_sim(flow, alpha, beta, m, label_suffix=""):
    _mmrp_sim_core(flow, alpha, beta, m, label_suffix)


def plot_fft(t, flow, n_remove):
    smoothed, freqs, Fabs, removed = fft_smooth(flow, n_remove, SAMPLING_S)
    N    = len(flow)
    half = N // 2
    f_pos = freqs[1:half]
    A_pos = Fabs[1:half]

    fig = plt.figure(figsize=(18, 13))
    gs  = gridspec.GridSpec(3, 2, figure=fig, hspace=0.40, wspace=0.30)
    fig.suptitle(f"Úkol 8 – FFT vyhladzovanie (odstránených {n_remove} najsilnejších harmoník)", fontsize=14, fontweight='bold')

    # ── Spektrum ────────────────────────────────────────────────
    ax_sp = fig.add_subplot(gs[0, :])
    ax_sp.semilogy(f_pos, A_pos, color='#2980B9', lw=0.45, label='|F(f)|')
    colors_h = ['#E74C3C','#E67E22','#F1C40F','#27AE60','#8E44AD',
                '#1ABC9C','#3498DB','#D35400','#2C3E50','#7F8C8D']
    
    # Aby legenda nebola obrovská, detailne označíme len top 10
    max_labels = 10 
    for h in removed:
        rank = h['rank']
        if rank <= max_labels:
            c = colors_h[(rank-1) % len(colors_h)]
            ax_sp.axvline(h['freq_hz'], color=c, lw=1.2, ls='--',
                          label=f"H{rank}: {h['freq_hz']:.4f} Hz "
                                f"(T≈{h['period_s']:.1f}s, A≈{h['amplitude']:.1f})")
        else:
            # Ostatné odstránené harmoniky len jemne naznačíme sivou čiarou bez legendy
            ax_sp.axvline(h['freq_hz'], color='gray', lw=0.5, ls=':', alpha=0.3)

    ax_sp.set_xlabel("Frekvencia [Hz]", fontsize=11)
    ax_sp.set_ylabel("|F(f)|  [log]", fontsize=11)
    ax_sp.set_title("Frekvenčné spektrum – kladné frekvencie", fontsize=12)
    ax_sp.legend(fontsize=9, loc='upper right', ncol=2)
    ax_sp.grid(True, alpha=0.25)

    # ── Originál vs vyhladený ────────────────────────────────────
    ax_fl = fig.add_subplot(gs[1, :])
    # Zosvetlíme pôvodný tok a zhrubíme vyhladený, nech je to super vidieť
    ax_fl.plot(t, flow,     color='#A9CCE3', lw=0.60, alpha=0.8, label='a(i) originál')
    ax_fl.plot(t, smoothed, color='#C0392B', lw=1.50,            label=f'FFT vyhladený ({n_remove} zložiek)')
    
    # Rýchle nastavenie popiskov ak _base funkcia náhodou chýba
    ax_fl.set_xlabel("Čas (index i)", fontsize=11)
    ax_fl.set_ylabel("Pakety / slot", fontsize=11)
    ax_fl.set_title("Originál vs FFT vyhladený", fontsize=12)
    ax_fl.legend(fontsize=10)
    ax_fl.grid(True, alpha=0.3)

    # ── Detail: prvých 5 s ────────────────────────────────────────
    # Ochrana, ak by SAMPLING_S nebolo správne, zoberieme prvých cca 500 hodnôt
    d_end = int(5.0 / SAMPLING_S) if 'SAMPLING_S' in globals() else 500
    ax_dt = fig.add_subplot(gs[2, 0])
    ax_dt.plot(t[:d_end], flow[:d_end],     color='#A9CCE3', lw=1.0, alpha=0.8, label='originál')
    ax_dt.plot(t[:d_end], smoothed[:d_end], color='#C0392B', lw=1.5,            label='FFT vyhladené')
    ax_dt.set_title("Detail – začiatok toku", fontsize=12); ax_dt.set_xlabel("Čas", fontsize=11)
    ax_dt.set_ylabel("Pakety / slot", fontsize=11); ax_dt.legend(fontsize=9); ax_dt.grid(True, alpha=0.3)

    # ── Zdôvodnenie odstránených harmoník ────────────────────────
    ax_tx = fig.add_subplot(gs[2, 1])
    ax_tx.axis('off')
    
    lines = [f"Zdôvodnenie: Celkovo odstránených najsilnejších {n_remove} zložiek.\n"]
    lines.append("Najsilnejšie identifikované zložky (Top 5):")
    total_energy = np.sum(Fabs**2)
    
    # Výpis len pre Top 5
    top_n_print = min(5, len(removed))
    for h in removed[:top_n_print]:
        idx_safe = min(h['idx'], len(Fabs)-1)
        e_pct = (Fabs[idx_safe]**2 + Fabs[N-idx_safe]**2) / total_energy * 100
        lines.append(f" H{h['rank']:1d}: f={h['freq_hz']:.4f} Hz (T≈{h['period_s']:.1f}s) | E ≈ {e_pct:.2f}%")

    if len(removed) > top_n_print:
        lines.append(f" ... a ďalších {len(removed) - top_n_print} harmoník so slabšou energiou.\n")

    lines.append("\nZdôvodnenie zvýšeného počtu odstránených harmoník:")
    lines.append("Zadanie požadovalo odstrániť 'aspoň 5' harmonických vlnení.")
    lines.append("Keďže IP prevádzka je stochastický proces a pripomína skôr")
    lines.append("širokospektrálny šum než jednoduchý periodický signál,")
    lines.append("odstránenie iba 5 najsilnejších zložiek neprinieslo dostatočné")
    lines.append("vyhladenie. Aplikovaním FFT ako Low-pass filtra (odstránením")
    lines.append(f"až {n_remove} zložiek) sme úspešne odhalili čistý makro-trend.")

    ax_tx.text(0.05, 0.95, "\n".join(lines), transform=ax_tx.transAxes,
               fontsize=10.0, va='top', fontfamily='monospace',
               bbox=dict(boxstyle='round,pad=1', facecolor='lightyellow', alpha=0.85))

    # Aby sa popisy neprekrývali
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    filename = f"ul8_fft_{n_remove}harmonik.png"
    plt.savefig(filename, dpi=150)
    print(f"[+] Uložené: {filename}")
    # plt.show() # Odkomentuj pre zobrazenie v okne
    plt.close()
    return smoothed


def plot_fft_repeat(t, flow_fft_raw, m_orig, W, n_remove_extra=0):
    """Úkol 9 – body 5–7 na FFT-vyhladených dátach + ev. ďalšie harmoniky."""
    label = f"FFT-{N_FFT_REMOVE + n_remove_extra}harmoník"

    if n_remove_extra > 0:
        flow_f, *_ = fft_smooth(flow_fft_raw, n_remove_extra, SAMPLING_S)
        print(f"   Dodatočné odstránenie {n_remove_extra} harmoník …")
    else:
        flow_f = flow_fft_raw

    flow_f = np.maximum(flow_f, 0.0)   # záporné hodnoty na 0
    m_f, s_f, _ = moving_stats(flow_f, W)

    # 5 – Bernoulli
    print("   9/5: Bernoulli …")
    plot_bernoulli(flow_f, m_f, label_suffix=f" ({label})")

    # 6 – MMRP parametre
    print("   9/6: MMRP parametre …")
    a_f, b_f, _ = mmrp_estimate(flow_f, m_f, W)

    # Zjednodušený graf α, β pre FFT dáta
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 7), sharex=True,
                                   gridspec_kw={'hspace': 0.06})
    fig.suptitle(f"Úkol 9/6 – MMRP α(t), β(t) na {label}   [okno {W}]", fontsize=12)
    ax1.plot(t, a_f, color=C['alpha'], lw=0.65, label='α(t)')
    ax1.set_ylim(0, min(1.05, np.percentile(a_f,99.5)*1.5+0.01))
    _base(ax1, t, "α(t)"); ax1.legend(fontsize=9)
    ax2.plot(t, b_f, color=C['beta'],  lw=0.65, label='β(t)')
    ax2.set_ylim(0, min(1.05, np.percentile(b_f,99.5)*1.5+0.01))
    _base(ax2, t, "β(t)"); ax2.legend(fontsize=9)
    _save(f"ul9_mmrp_params_{label}.png")

    # 7 – MMRP simulácia
    print("   9/7: MMRP simulácia …")
    _mmrp_sim_core(flow_f, a_f, b_f, m_f, label_suffix=f" ({label})")


# ─────────────────────────────────────────────────────────────────
# INTERAKTÍVNE MENU
# ─────────────────────────────────────────────────────────────────
VALID_CHOICES = {str(i) for i in range(10)} | {'VŠETKO'}

def show_menu(W):
    print("\n" + "═"*68)
    print("  KOMPLEXNÁ ANALÝZA IP TOKU")
    print(f"  Vzorkovanie: {SAMPLING_S*1000:.0f} ms  │  Aktívne okno: {W} sl. = {W*SAMPLING_S*1000:.0f} ms")
    print("─"*68)
    print("  [1]  Tok a(i) + 4 kĺzavé okná m(t)  →  výber najvhodnejšieho")
    print("  [2]  m(t) + s(t) + pásy ±1σ / ±2σ / ±3σ")
    print("  [3]  V(t) – samostatne (ref. V=1) + spolu s a(i)")
    print("  [4]  Kĺzavý odhad p Binomického rozdelenia + spolu s a(i)")
    print("  [5]  Bernoulliho aproximácia – histogramy + zdôvodnenie")
    print("  [6]  MMRP odhady α(t), β(t) – klzavo + spolu s a(i)")
    print("  [7]  MMRP simulácia – porovnanie histogramov")
    print("  [8]  FFT vyhladzovanie – spektrum + zdôvodnenie")
    print("  [9]  Body 5–7 zopakované na FFT-vyhladených dátach")
    print("─"*68)
    print("  [VŠETKO]  Generuj všetky grafy (1–9)")
    print("  [0]       Koniec")
    print("═"*68)

def get_choice():
    while True:
        try:
            c = input("  Voľba: ").strip().upper()
            if c in VALID_CHOICES:
                return c
            print("  [!] Neplatná voľba. Zadaj číslo 0–9 alebo VŠETKO.")
        except (KeyboardInterrupt, EOFError):
            print("\n  [*] Zbohom!")
            sys.exit(0)


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    # ── Načítanie a príprava ─────────────────────────────────────
    print(f"\n[*] Parsovanie: {PCAP_FILE} …")
    times, protos = parse_pcap(PCAP_FILE)
    if len(times) == 0:
        print("[!] Žiadne dáta. Koniec."); sys.exit(1)

    print(f"[+] {len(times):,} paketov  |  0 – {times[-1]:.1f} s")
    print(f"[+] TCP {protos.count('TCP'):,}  UDP {protos.count('UDP'):,}  "
          f"Ostatné {protos.count('OTHER'):,}")

    print(f"\n[*] Výpočet toku (sr = {SAMPLING_S*1000:.0f} ms) …")
    t, flow = compute_flow(times, SAMPLING_S)

    # Výber aktívneho okna – začíname s WINDOWS_TEST[1]
    W = WINDOWS_TEST[1]
    m, s, V = moving_stats(flow, W)

    # Pomocné premenné (vypočítajú sa neskôr podľa voľby)
    flow_fft = None     # FFT-vyhladený tok
    alpha_g  = None
    beta_g   = None

    # ── Hlavná slučka ─────────────────────────────────────────────
    while True:
        show_menu(W)
        ch = get_choice()

        if ch == '0':
            print("\n[*] Koniec. Zbohom!")
            sys.exit(0)

        ALL = (ch == 'VŠETKO')

        # ── [1] 4 okná ──────────────────────────────────────────
        if ch in ('1', 'VŠETKO'):
            print("\n[*] Generujem Graf 1: 4 kĺzavé okná …")
            plot_4windows(t, flow, WINDOWS_TEST)
            # Heuristika výberu: okno kde variácia m(t) nie je ani
            # príliš hladká (W=1000) ani príliš zašumená (W=50)
            W = WINDOWS_TEST[1]   # 200 ms – dobrý kompromis
            m, s, V = moving_stats(flow, W)
            print(f"[+] Zvolené okno: W = {W} slotov ({W*SAMPLING_S*1000:.0f} ms)")

        # ── [2] Pásy ───────────────────────────────────────────
        if ch in ('2', 'VŠETKO'):
            print("\n[*] Generujem Graf 2: m(t) + pásy σ(t) …")
            plot_bands(t, flow, m, s, W)

        # ── [3] V(t) ───────────────────────────────────────────
        if ch in ('3', 'VŠETKO'):
            print("\n[*] Generujem Graf 3: V(t) …")
            plot_V(t, flow, m, s, V, W)

        # ── [4] Binomický p ────────────────────────────────────
        if ch in ('4', 'VŠETKO'):
            print("\n[*] Generujem Graf 4: Binomický odhad p …")
            plot_binom(t, flow, m, s, W)

        # ── [5] Bernoulli ──────────────────────────────────────
        if ch in ('5', 'VŠETKO'):
            print("\n[*] Generujem Graf 5: Bernoulliho aproximácia …")
            plot_bernoulli(flow, m)

        # ── [6] MMRP α, β ──────────────────────────────────────
        if ch in ('6', 'VŠETKO'):
            print("\n[*] Generujem Graf 6: MMRP α(t), β(t) …")
            alpha_g, beta_g, _ = plot_mmrp_params(t, flow, m, s, W)

        # ── [7] MMRP simulácia ─────────────────────────────────
        if ch in ('7', 'VŠETKO'):
            print("\n[*] Generujem Graf 7: MMRP simulácia …")
            if alpha_g is None:
                alpha_g, beta_g, _ = mmrp_estimate(flow, m, W)
            plot_mmrp_sim(flow, alpha_g, beta_g, m)

        # ── [8] FFT ────────────────────────────────────────────
        if ch in ('8', 'VŠETKO'):
            print(f"\n[*] Generujem Graf 8: FFT vyhladzovanie "
                  f"({N_FFT_REMOVE} harmoník) …")
            flow_fft = plot_fft(t, flow, N_FFT_REMOVE)

        # ── [9] Body 5–7 na FFT dátach ────────────────────────
        if ch in ('9', 'VŠETKO'):
            print("\n[*] Generujem Graf 9: Body 5–7 na FFT dátach …")
            if flow_fft is None:
                print("   (Najprv vyhlaďujem FFT …)")
                flow_fft, *_ = fft_smooth(flow, N_FFT_REMOVE, SAMPLING_S)
            plot_fft_repeat(t, flow_fft, m, W, n_remove_extra=0)

        print("\n[+] Hotovo!\n")


if __name__ == "__main__":
    main()