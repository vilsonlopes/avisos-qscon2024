
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager

from alertaemail import send_mail

url = "https://www.convocacaotemporarios.fab.mil.br/candidato/index.php"

# Configurações iniciais
option = Options()
option.headless = False   # Deixar true em produção
driver = webdriver.Firefox(options=option)
driver.implicitly_wait(80)  # seconds
driver.get(url)
# driver.maximize_window()

patterns = """06/03/2024 CUMPRIMENTO DE DECISÃO JUDICIAL - BRUNA DURÃES GOMES"""

qscon2024 = driver.find_element(By.ID, "convocacao-recentes")

quadro = qscon2024.find_element(By.LINK_TEXT, "Quadro de Sargentos da Reserva de 2ª Classe Convocados (QSCon 2024)")

quadro.click()

time.sleep(2)

serepbr = driver.find_element(By.ID, "accordion")

serepbr2 = serepbr.find_element(By.LINK_TEXT, "SEREP - Brasília")

serepbr2.click()

time.sleep(2)

brasilia = driver.find_element(By.ID, "collapse4")

brasilia2 = brasilia.find_element(By.LINK_TEXT, "Brasília")

brasilia2.click()

time.sleep(2)

avisos = driver.find_element(By.ID, "tableLista")

avisos_todo = avisos.find_element(By.TAG_NAME, "tbody")

avisos_one = avisos_todo.find_element(By.TAG_NAME, "tr")

# print(avisos_one.text)

if patterns != avisos_one.text:
    send_mail()
else:
    print('Sem alterações')

driver.close()
