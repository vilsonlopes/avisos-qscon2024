# monitor_qscon.py
# -*- coding: utf-8 -*-
import os
import time
import sqlite3
import pickle
import tempfile
import subprocess
import atexit
from pathlib import Path
from contextlib import suppress
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains
from seleniumbase import Driver

from alertaemail import send_mail

# =========================
# ======== CONFIG =========
# =========================
URL = "https://www.convocacaotemporarios.fab.mil.br/candidato/index.php"

# Perfil persistente (use uma pasta só do robô)
CHROME_USER_DATA_DIR = r"C:\workspace\chrome_selenium_profile"  # SEM profile_dir

# Cookies (opcional)
USAR_COOKIES = True
COOKIES_ARQ = Path(__file__).with_name("cookies.pkl")

# Headless (True = sem janela; False = janela visível)
HEADLESS = False

# Retry inicial (em caso de falha no start / rede lenta)
RETRIES = 3
BACKOFF_SECS = 10

# Lock file
LOCK_FILE = Path(tempfile.gettempdir()) / "qscon_monitor.lock"

# SQLite
DB_PATH = Path(__file__).with_name("qscon_monitor.db")
DDL = """
CREATE TABLE IF NOT EXISTS avisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT NOT NULL,
    texto TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aviso_chave ON avisos(chave);
"""

# =========================
# ======= FUNÇÕES =========
# =========================

def single_instance_lock():
    try:
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Lock falhou: {e}")

def release_lock():
    with suppress(Exception):
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()

def kill_orphans():
    if os.name == "nt":
        with suppress(Exception):
            subprocess.run(["taskkill", "/IM", "chromedriver.exe", "/F", "/T"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with suppress(Exception):
            subprocess.run(["taskkill", "/IM", "chrome.exe", "/F", "/T"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def db_init():
    with db_connect() as conn:
        for stmt in filter(None, DDL.split(";")):
            conn.execute(stmt)
        conn.commit()

def db_get_last_text(chave: str) -> str | None:
    with db_connect() as conn:
        cur = conn.execute("SELECT texto FROM avisos WHERE chave=? ORDER BY id DESC LIMIT 1", (chave,))
        row = cur.fetchone()
        return row[0] if row else None

def db_save_text(chave: str, texto: str):
    with db_connect() as conn:
        conn.execute("INSERT INTO avisos(chave, texto, created_at) VALUES (?, ?, ?)",
                     (chave, texto, datetime.now().isoformat(timespec="seconds")))
        conn.commit()

def safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", element)
    time.sleep(0.4)
    try:
        element.click(); return
    except ElementClickInterceptedException:
        pass
    try:
        ActionChains(driver).move_to_element_with_offset(element, 0, -10).click().perform(); return
    except Exception:
        pass
    try:
        driver.execute_script("document.querySelectorAll('footer, .footer, #footer').forEach(el=>el.style.display='none');")
        time.sleep(0.2)
        element.click(); return
    except Exception:
        driver.execute_script("arguments[0].click();", element)

def build_driver():
    # >>> Sem profile_dir; apenas user_data_dir (perfil persistente "Default" dentro da pasta)
    driver = Driver(
        uc=True,
        browser="chrome",
        headless=HEADLESS,
        user_data_dir=CHROME_USER_DATA_DIR,
        # argumentos úteis de estabilidade
        no_sandbox=True,
        disable_gpu=True,
        disable_dev_shm_usage=True,
        # detach=False é padrão; o SeleniumBase fecha junto com quit()
    )
    driver.implicitly_wait(30)
    return driver

def carregar_cookies(driver):
    if not (USAR_COOKIES and COOKIES_ARQ.exists()):
        return
    try:
        driver.get(URL)
        cookies = pickle.load(open(COOKIES_ARQ, "rb"))
        for c in cookies:
            driver.add_cookie(c)
        driver.get(URL)
        print("[INFO] Cookies restaurados.")
    except Exception as e:
        print(f"[WARN] Falha ao carregar cookies: {e}")

def salvar_cookies(driver):
    if not USAR_COOKIES:
        return
    try:
        cookies = driver.get_cookies()
        pickle.dump(cookies, open(COOKIES_ARQ, "wb"))
        print(f"[INFO] Cookies salvos em {COOKIES_ARQ}")
    except Exception as e:
        print(f"[WARN] Falha ao salvar cookies: {e}")

def fluxo(driver):
    driver.get(URL)

    qscon2024 = driver.find_element(By.ID, "convocacao-recentes")
    quadro = qscon2024.find_element(By.LINK_TEXT, "Quadro de Oficiais da Reserva de 2ª Classe Convocados (QOCON TEC) 2025/2026")
    safe_click(driver, quadro)
    time.sleep(2)

    serepbr = driver.find_element(By.ID, "accordion")
    serepbr2 = serepbr.find_element(By.LINK_TEXT, "SEREP - Brasília")
    safe_click(driver, serepbr2)
    time.sleep(2)

    brasilia = driver.find_element(By.ID, "collapse4")
    brasilia2 = brasilia.find_element(By.LINK_TEXT, "Brasília")
    safe_click(driver, brasilia2)
    time.sleep(2)

    avisos = driver.find_element(By.ID, "tableLista")
    avisos_one = avisos.find_element(By.TAG_NAME, "tr")
    texto_atual = avisos_one.text.strip()

    chave = "QSCon-Brasilia"
    ultimo = db_get_last_text(chave)

    if ultimo is None:
        db_save_text(chave, texto_atual)
        print("Inicializado: aviso salvo no banco.")
    else:
        if ultimo != texto_atual:
            send_mail("[QOCon] Novo aviso em Brasília",
                      f"Anterior:\n{ultimo}\n\nAtual:\n{texto_atual}")
            db_save_text(chave, texto_atual)
            print("Novo aviso detectado, e-mail enviado.")
        else:
            print("Sem alterações.")

def main():
    single_instance_lock()
    atexit.register(release_lock)
    atexit.register(kill_orphans)

    db_init()
    tentativas = 0
    while True:
        try:
            driver = build_driver()
            break
        except Exception as e:
            tentativas += 1
            print(f"[ERRO] Start Chrome: {e}")
            if tentativas >= RETRIES:
                raise
            time.sleep(BACKOFF_SECS)

    try:
        carregar_cookies(driver)
        fluxo(driver)
        salvar_cookies(driver)
    finally:
        with suppress(Exception):
            driver.quit()
        kill_orphans()
        release_lock()

if __name__ == "__main__":
    main()
