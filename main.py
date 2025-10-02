import time
import sqlite3
from pathlib import Path
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains
from seleniumbase import Driver

from alertaemail import send_mail

url = "https://www.convocacaotemporarios.fab.mil.br/candidato/index.php"

# === SQLite básico ===
DB_PATH = Path(__file__).with_name("qscon_monitor.db")
DDL = """
CREATE TABLE IF NOT EXISTS avisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT NOT NULL,         -- ex.: 'QSCon-Brasilia'
    texto TEXT NOT NULL,         -- último aviso visto
    created_at TEXT NOT NULL     -- quando foi salvo
);
CREATE INDEX IF NOT EXISTS idx_aviso_chave ON avisos(chave);
"""

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
        cur = conn.execute(
            "SELECT texto FROM avisos WHERE chave=? ORDER BY id DESC LIMIT 1",
            (chave,),
        )
        row = cur.fetchone()
        return row[0] if row else None

def db_save_text(chave: str, texto: str):
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO avisos(chave, texto, created_at) VALUES (?, ?, ?)",
            (chave, texto, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()

# === helper mínimo para cliques sem interceptação ===
def safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", element)
    time.sleep(0.4)
    try:
        element.click()
        return
    except ElementClickInterceptedException:
        pass
    try:
        ActionChains(driver).move_to_element_with_offset(element, 0, -10).click().perform()
        return
    except Exception:
        pass
    try:
        driver.execute_script("""
            document.querySelectorAll('.copyright, footer, .footer, #footer')
                    .forEach(el => el.style.setProperty('display','none','important'));
        """)
        time.sleep(0.2)
        element.click()
        return
    except Exception:
        driver.execute_script("arguments[0].click();", element)

# === SeleniumBase Driver ===
driver = Driver(
    uc=True,
    browser="chrome",
    headless=False,      # mantenha visível enquanto estabiliza
    # headless2=False,
    # incognito=True,
    # no_sandbox=True,
    # do_not_track=True,
    # block_images=False,
    # page_load_strategy="normal",
)
driver.implicitly_wait(80)

# === fluxo original com SeleniumBase ===
db_init()  # inicializa o banco

driver.get(url)

qscon2024 = driver.find_element(By.ID, "convocacao-recentes")

# (ajuste o texto do link se for outro quadro)
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
avisos_todo = avisos.find_element(By.TAG_NAME, "tbody")
avisos_one = avisos_todo.find_element(By.TAG_NAME, "tr")

texto_atual = avisos_one.text.strip()
chave = "QSCon-Brasilia"  # identificador lógico da “fonte”

ultimo = db_get_last_text(chave)

if ultimo is None:
    # primeira execução: grava, não notifica
    db_save_text(chave, texto_atual)
    print("Inicializado: aviso salvo no banco.")
else:
    if ultimo != texto_atual:
        # mudou -> envia e-mail e atualiza banco
        send_mail("[QOCon] Novo aviso em Brasília", f"Anterior:\n{ultimo}\n\nAtual:\n{texto_atual}")
        db_save_text(chave, texto_atual)
        print("Novo aviso detectado, e-mail enviado e banco atualizado.")
    else:
        print("Sem alterações.")

driver.quit()
