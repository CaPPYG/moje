import os
import re
import socket
import subprocess

SERVER_IP = "35.209.172.238"


def clean_domain(domain_raw):
    """
    Vyčistí doménu od http://, https://, lomiek a medzier.
    """
    if not domain_raw:
        return ""
    d = domain_raw.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].split(":")[0]
    return d


def resolve_domain_ips(domain):
    """
    Zistí IP adresy pre zadanú doménu cez DNS.
    """
    ips = []
    try:
        answers = socket.getaddrinfo(domain, 80, socket.AF_INET, socket.SOCK_STREAM)
        for a in answers:
            ip = a[4][0]
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


def check_dns_status(domain):
    """
    Skontroluje, či doména (a www varianta) ukazuje na IP tohto servera.
    """
    clean_d = clean_domain(domain)
    if not clean_d:
        return {
            "configured": False,
            "domain": "",
            "server_ip": SERVER_IP,
            "message": "Doména nie je nastavená."
        }

    # Zistiť root doménu a www
    root_d = clean_d[4:] if clean_d.startswith("www.") else clean_d
    www_d = f"www.{root_d}"

    root_ips = resolve_domain_ips(root_d)
    www_ips = resolve_domain_ips(www_d)

    is_pointing = SERVER_IP in root_ips
    is_www_pointing = SERVER_IP in www_ips

    # Zistiť, či existuje a funguje SSL certifikát
    ssl_active = False
    if is_pointing:
        try:
            import ssl
            ctx = ssl.create_default_context()
            with socket.create_connection((root_d, 443), timeout=3) as s:
                with ctx.wrap_socket(s, server_hostname=root_d) as ss:
                    ssl_active = True
        except Exception:
            ssl_active = os.path.exists(f"/etc/letsencrypt/live/{root_d}/fullchain.pem")

    return {
        "configured": True,
        "domain": root_d,
        "www_domain": www_d,
        "server_ip": SERVER_IP,
        "root_ips": root_ips,
        "www_ips": www_ips,
        "is_pointing": is_pointing,
        "is_www_pointing": is_www_pointing,
        "ssl_active": ssl_active,
        "ready_for_ssl": is_pointing
    }


def setup_nginx_for_domain(domain):
    """
    Vytvorí Nginx server blok pre zadanú doménu a presmeruje na CloakHub (port 5100).
    """
    clean_d = clean_domain(domain)
    if not clean_d:
        return False, "Neplatná doména."

    root_d = clean_d[4:] if clean_d.startswith("www.") else clean_d
    conf_name = f"cloakhub_{root_d}.conf"
    available_path = f"/etc/nginx/sites-available/{conf_name}"
    enabled_path = f"/etc/nginx/sites-enabled/{conf_name}"

    nginx_config = f"""# CloakHub Custom Domain - {root_d}
server {{
    listen 80;
    listen [::]:80;
    server_name {root_d} www.{root_d};

    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}

    location / {{
        proxy_pass http://127.0.0.1:5100;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }}
}}
"""

    try:
        # 1. Zápis do dočasného súboru
        temp_path = f"/tmp/{conf_name}"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(nginx_config)

        # 2. Presun do /etc/nginx/sites-available/ s právami roota
        subprocess.run(["sudo", "mv", temp_path, available_path], check=True)
        subprocess.run(["sudo", "chmod", "644", available_path], check=True)

        # 3. Symlink do sites-enabled ak ešte neexistuje
        if not os.path.exists(enabled_path):
            subprocess.run(["sudo", "ln", "-s", available_path, enabled_path], check=True)

        # 4. Test a reload Nginx
        test_res = subprocess.run(["sudo", "nginx", "-t"], capture_output=True, text=True)
        if test_res.returncode != 0:
            return False, f"Nginx syntax error: {test_res.stderr}"

        subprocess.run(["sudo", "systemctl", "reload", "nginx"], check=True)
        return True, "Nginx konfigurácia úspešne aplikovaná!"
    except Exception as e:
        return False, str(e)


def issue_certbot_ssl(domain, email=None):
    """
    Spustí Certbot pre danú doménu a www subdoménu.
    """
    clean_d = clean_domain(domain)
    if not clean_d:
        return False, "Neplatná doména."

    root_d = clean_d[4:] if clean_d.startswith("www.") else clean_d

    # Najprv sa uistiť, že Nginx je nakonfigurovaný
    ok, msg = setup_nginx_for_domain(root_d)
    if not ok:
        return False, f"Chyba pri príprave Nginx: {msg}"

    # Zistiť, či aj www subdoména smeruje na tento server
    www_ips = resolve_domain_ips(f"www.{root_d}")
    has_www = SERVER_IP in www_ips

    # Zostaviť certbot príkaz
    cmd = [
        "sudo", "certbot", "--nginx",
        "-d", root_d,
    ]
    if has_www:
        cmd.extend(["-d", f"www.{root_d}"])

    cmd.extend([
        "--non-interactive",
        "--agree-tos",
        "--redirect"
    ])
    if email:
        cmd.extend(["-m", email])
    else:
        cmd.append("--register-unsafely-without-email")

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            return True, "SSL certifikát bol úspešne vygenerovaný a HTTPS je aktívne!"
        else:
            return False, f"Certbot chyba: {res.stderr or res.stdout}"
    except subprocess.TimeoutExpired:
        return False, "Certbot vypršal (timeout 120s)."
    except Exception as e:
        return False, str(e)
