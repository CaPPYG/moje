from datetime import datetime
import time
import requests

URL = "https://solar.siseli.com/apis/deviceState/simple/energy/flow/v1"
PARAMS = {"deviceId": "436462865988157441", "dataSource": "2"}

HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en",
    "Host": "solar.siseli.com",
    "IOT-Time-Zone": "Europe/Bratislava",
    "IOT-Token": "E9C38618BF693D07FB372E2CB012DF45",
    "Referer": "https://solar.siseli.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 OPR/135.0.0.0",
}

last_telemetry_time = None
last_check_local = None

print("=== Spúšťam meranie intervalu aktualizácie dát ===")
print("Dopytujem server každých 15 sekúnd. Čakám na zmenu časovej pečiatky...\n")

while True:
    try:
        res = requests.get(URL, params=PARAMS, headers=HEADERS, timeout=5)

        if res.status_code == 200:
            payload = res.json()

            # Kontrola na rate limit / prázdne dáta zo strany cloudu
            if not payload.get("data") or not payload["data"].get(
                "deviceAttributeState"
            ):
                msg = payload.get("message", "Data is null / Rate limit")
                print(f"[!] Server vrátil obmedzenie ({msg}), čakám...")
            else:
                raw_time = payload["data"]["deviceAttributeState"]["time"]
                fields = payload["data"]["deviceAttributeState"]["fields"]

                # Získame hlavné metriky pre prehľad
                pv = fields.get("pvInputPower", {}).get("value", 0)
                load = int(
                    fields.get("acOutputActivePower", {}).get("value", 0) * 1000
                )
                soc = fields.get("batteryCapacity", {}).get("value", 0)

                # Parsovanie ISO času z meniča (napr. 2026-09-04T12:15:37Z)
                current_time = datetime.fromisoformat(
                    raw_time.replace("Z", "+00:00")
                )

                if last_telemetry_time is None:
                    last_telemetry_time = current_time
                    last_check_local = datetime.now()
                    print(
                        f"[POČIATOČNÝ STAV] Čas z meniča: {raw_time} | PV: {pv}W | Spotreba: {load}W | Batéria: {soc}%"
                    )
                elif current_time != last_telemetry_time:
                    # Nastal update!
                    diff_seconds = int(
                        (current_time - last_telemetry_time).total_seconds()
                    )
                    diff_minutes = round(diff_seconds / 60, 2)
                    local_now = datetime.now().strftime("%H:%M:%S")

                    print("\n" + "=" * 50)
                    print(f"🔥 NOVÝ UPDATE ZACHYTENÝ o {local_now}!")
                    print(f"Predchádzajúci čas: {last_telemetry_time}")
                    print(f"Aktuálny čas:      {current_time}")
                    print(
                        f"⏱️  REÁLNY INTERVAL: {diff_seconds} sekúnd (~{diff_minutes} minút)"
                    )
                    print(
                        f"Hodnoty: PV: {pv}W | Záťaž: {load}W | Batéria: {soc}%"
                    )
                    print("=" * 50 + "\n")

                    last_telemetry_time = current_time
                else:
                    # Dáta sú stále rovnaké
                    print(".", end="", flush=True)

        else:
            print(f"\n[!] HTTP Chyba {res.status_code}: {res.text}")

    except Exception as e:
        print(f"\n[!] Chyba spojenia: {e}")

    # Pýtame sa každých 15 sekúnd, aby sme zbytočne nepreťažili API
    time.sleep(15)