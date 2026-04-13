import sqlite3
import datetime

conn = sqlite3.connect("ult_database.db")
cur = conn.cursor()

# Agreguemos "falsas" alertas históricas de hoy para forzar el prompt a que nos de el resultado correcto
# Queremos que los scrapers piensen que hay items viejos que han leido hoy.
cur.execute(
    "INSERT INTO alerts (source, title, summary, url, category, date) VALUES ('diario-oficial', 'Ley Falsa DO (histórico)', 'test', 'http://url.com', 'normativa', 'ayer')"
)
cur.execute(
    "INSERT INTO alerts (source, title, summary, url, category, date) VALUES ('diario-oficial', 'Resolución Falsa DO (histórico)', 'test', 'http://url.com', 'normativa', 'ayer')"
)

cur.execute(
    "INSERT INTO alerts (source, title, summary, url, category, date) VALUES ('minvu', 'Decreto Falso MINVU (histórico)', 'test', 'http://url.com', 'condominio', 'ayer')"
)

conn.commit()
conn.close()
print("Test historical alerts seeded")
