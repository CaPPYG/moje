#!/usr/bin/env python3
"""
Jednoduchý skript na čítanie pcapng súboru a počítanie paketov za 1s
"""

import dpkt
import sys

# ═══════════════════════════════════════════════════════════════════════════
# KONFIGURÁCIA
# ═══════════════════════════════════════════════════════════════════════════
PCAP_FILE = r"C:\Users\patri\Desktop\tis\zadanie3\03dHulk-trim.pcapng"
START_TIME_MS = 0  # Nastav od ktorej ms chceš začať čítať (0 = od začiatku)

def count_packets_per_second(filepath, start_ms=0):
    """Načítaj pcapng a počítaj pakety za 1 sekundu"""
    try:
        with open(filepath, 'rb') as f:
            pcap = dpkt.pcapng.Reader(f)
            
            timestamps = []
            packet_count = 0
            
            # Načítaj všetky pakety
            for ts, buf in pcap:
                timestamps.append(ts)
                packet_count += 1
            
            print(f"[✓] Spolu v súbore: {packet_count} paketov")
            
            if len(timestamps) == 0:
                print("Žiadne pakety v súbore!")
                return
            
            # Časy všetkých paketov
            t_min_all = timestamps[0]
            t_max_all = timestamps[-1]
            
            # Konvertuj START_TIME_MS na sekundy
            start_time_sec = start_ms / 1000.0
            t_min = t_min_all + start_time_sec
            
            # Filtuj pakety od START_TIME_MS
            filtered_timestamps = [t for t in timestamps if t >= t_min]
            t_max = filtered_timestamps[-1] if filtered_timestamps else t_min
            
            duration = t_max - t_min
            filtered_count = len(filtered_timestamps)
            
            print(f"\nÚplný rozsah súboru:")
            print(f"  • Začiatok: {t_min_all:.6f} s")
            print(f"  • Koniec:   {t_max_all:.6f} s")
            print(f"  • Trvanie:  {t_max_all - t_min_all:.6f} s")
            
            print(f"\nAnalyzovaný rozsah (od {start_ms} ms):")
            print(f"  • Začiatok: {t_min:.6f} s ({start_ms:.2f} ms)")
            print(f"  • Koniec:   {t_max:.6f} s")
            print(f"  • Trvanie:  {duration:.6f} s")
            print(f"  • Paketov:  {filtered_count}")
            
            # Počet paketov za 1 sekundu
            avg_per_sec = filtered_count / duration if duration > 0 else 0
            print(f"\nPakety za 1 sekundu (priemerne): {avg_per_sec:.2f} pps")
            
            # Počty v každej sekunde
            print("\nRozdelelie po sekundách:")
            for sec in range(int(duration) + 1):
                count_in_sec = sum(1 for t in filtered_timestamps 
                                   if t_min + sec <= t < t_min + sec + 1)
                if count_in_sec > 0:
                    print(f"  Sekunda {sec:3d} ({t_min + sec:.2f}s): {count_in_sec:6d} paketov")
            
    except FileNotFoundError:
        print(f"❌ Súbor '{filepath}' nebol nájdený!")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Chyba: {e}")
        sys.exit(1)

if __name__ == "__main__":
    count_packets_per_second(PCAP_FILE)
