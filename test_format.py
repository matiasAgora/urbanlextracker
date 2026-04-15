import scrapers

print("Testing empty:")
print(scrapers.procesar_salida("diario-oficial", [], "📰", "Diario Oficial", 1))

print("---")
print("Testing with items:")
print(
    scrapers.procesar_salida(
        "diario-oficial", ["DO: Item 1"], "📰", "Diario Oficial", 1
    )
)
