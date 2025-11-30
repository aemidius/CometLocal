import traceback
from playwright.sync_api import sync_playwright

print("➡ Inicio del script test_playwright.py")

def main():
    print("➡ Entrando en main()")
    try:
        with sync_playwright() as p:
            print("➡ sync_playwright() iniciado correctamente")
            browser = p.chromium.launch(headless=False)
            print("➡ Navegador Chromium lanzado")
            page = browser.new_page()
            print("➡ Nueva pestaña creada")
            page.goto("https://www.google.com")
            print("➡ Navegando a https://www.google.com")
            input("✅ Navegador debería estar abierto. Pulsa ENTER para cerrarlo...")
            browser.close()
            print("➡ Navegador cerrado correctamente")
    except Exception as e:
        print("❌ ERROR durante la ejecución:")
        print(e)
        traceback.print_exc()
    finally:
        input("⌨ Pulsa ENTER para salir del script...")

if __name__ == "__main__":
    print("➡ Bloque __main__ ejecutado")
    main()
