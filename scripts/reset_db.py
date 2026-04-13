import database
conn = database.get_connection()
conn.execute("DELETE FROM alerts")
conn.execute("DELETE FROM scrape_history")
conn.commit()
conn.close()
print("Base de datos limpia.")
