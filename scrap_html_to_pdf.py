import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pdfkit
from PyPDF2 import PdfMerger

# Configuración de wkhtmltopdf (¡AJUSTAR ESTA RUTA!)
WKHTMLTOPDF_PATH = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'  # Windows
# WKHTMLTOPDF_PATH = '/usr/local/bin/wkhtmltopdf'  # Linux/Mac
config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

# Configuración general
SEED_URL = "https://openapidoc.bitunix.com/doc/common/introduction.html"
BASE_DOMAIN = "https://openapidoc.bitunix.com/doc/"
OUTPUT_PDF = "bitunix_api_documentation.pdf"
TEMP_DIR = "temp_pdfs"
os.makedirs(TEMP_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def extract_urls(seed_url):
    visited = set()
    to_visit = [seed_url]
    all_urls = []
    
    while to_visit:
        url = to_visit.pop(0)
        if url in visited:
            continue
        
        try:
            print(f"\n🔍 Analizando: {url}")
            response = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")
            
            menu = soup.find("nav") or soup.find("div", class_="menu")
            menu = menu if menu else soup
            
            links = menu.find_all("a", href=True)
            print(f"📄 Enlaces encontrados: {len(links)}")
            
            for link in links:
                href = link["href"]
                absolute_url = urljoin(url, href)
                
                if (absolute_url.startswith(BASE_DOMAIN) 
                    and absolute_url.endswith(".html") 
                    and absolute_url not in all_urls):
                    
                    all_urls.append(absolute_url)
                    to_visit.append(absolute_url)
            
            visited.add(url)
        
        except Exception as e:
            print(f"🚨 Error en {url}: {str(e)}")
    
    return sorted(all_urls)

def process_html(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        
        for element in soup(["header", "footer", "nav", "script", "style"]):
            element.decompose()
        
        base_url = url.rsplit("/", 1)[0] + "/"
        for tag in soup.find_all(["img", "link"]):
            for attr in ["src", "href"]:
                if tag.get(attr):
                    tag[attr] = urljoin(base_url, tag[attr])
        
        return str(soup)
    
    except Exception as e:
        print(f"🚨 Error procesando {url}: {str(e)}")
        return None

if __name__ == "__main__":
    print("🚀 Iniciando scraping...")
    URLS = extract_urls(SEED_URL)
    
    if not URLS:
        print("🔴 No se encontraron URLs")
        exit()
    
    print(f"\n📚 URLs encontradas ({len(URLS)}):")
    
    pdf_files = []
    for idx, url in enumerate(URLS, 1):
        try:
            print(f"\n📥 Procesando ({idx}/{len(URLS)}): {url}")
            html_content = process_html(url)
            
            if html_content:
                output_path = os.path.join(TEMP_DIR, f"page_{idx}.pdf")
                pdfkit.from_string(
                    html_content,
                    output_path,
                    configuration=config,  # Configuración crítica
                    options={
                        "encoding": "UTF-8",
                        "page-size": "A4",
                        "margin-top": "15mm",
                        "enable-local-file-access": "",
                        "quiet": ""
                    }
                )
                pdf_files.append(output_path)
        
        except Exception as e:
            print(f"🚨 Error crítico: {str(e)}")

    if pdf_files:
        merger = PdfMerger()
        for pdf_file in pdf_files:
            merger.append(pdf_file)
        merger.write(OUTPUT_PDF)
        merger.close()
        
        # Limpieza
        for f in pdf_files:
            os.remove(f)
        os.rmdir(TEMP_DIR)
        print(f"\n🎉 PDF generado: {OUTPUT_PDF}")
    else:
        print("\n🔴 No se pudo generar contenido")