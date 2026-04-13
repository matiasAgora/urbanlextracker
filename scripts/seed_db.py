import database
import scrapers
import sqlite3

print("Paso 1: Rastreando todo para poblar la DB con los links estáticos actuales...")
scrapers.run_all_scrapers()

print("Paso 2: Marcando todos los links insertados como de hace 15 días...")
conn = sqlite3.connect('ult_database.db')
conn.execute("UPDATE alerts SET created_at = datetime('now', '-15 days')")
conn.execute("DELETE FROM scrape_history")
conn.commit()
conn.close()

print("Precarga y calibración completada con éxito. Ya no aparecerán como novedades del día.")
