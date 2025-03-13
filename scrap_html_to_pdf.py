import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pdfkit
from PyPDF2 import PdfMerger
import re
import logging

# Configuración de logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

# Lista de URLs en el orden correcto de la documentación (referencia manual)
# Esto se utiliza como respaldo cuando no se puede extraer el orden automáticamente
REFERENCE_ORDER = [
    "https://openapidoc.bitunix.com/doc/common/introduction.html",
    "https://openapidoc.bitunix.com/doc/common/sign.html",
    # Aquí pueden agregarse más URLs en orden si se conocen
]

# Definir el orden de las secciones/directorios para organizar las páginas
SECTION_ORDER = [
    "common",
    "ErrorCode",
    "account",
    "market",
    "position",
    "tp_sl",
    "trade",
    "websocket"
]

# Definir subsecciones para directorios que contienen subdirectorios
SUBSECTION_ORDER = {
    "websocket": ["prepare", "private", "public"]
}

# Orden específico de archivos dentro de ciertos directorios (si es necesario)
SPECIFIC_FILE_ORDER = {
    "common": ["introduction.html", "sign.html"],
    "websocket/public": ["Trade Channel.html"]  # Asegura que "Trade Channel.html" sea el último
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def extract_urls_ordered(seed_url):
    """
    Extrae URLs siguiendo el orden del menú de navegación del sitio.
    """
    logger.info(f"Accediendo a la página principal: {seed_url}")
    
    try:
        # Obtenemos la página principal que contiene el menú completo
        response = requests.get(seed_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Buscar el menú de navegación principal
        menu = soup.find("nav") or soup.find("div", class_="menu")
        if not menu:
            # Intentar encontrar otros elementos que puedan contener el menú
            menu = soup.find("aside") or soup.find("div", class_="sidebar")
            if not menu:
                menu = soup  # Si no encontramos un menú específico, usamos toda la página
        
        # Buscar todos los enlaces en la estructura del menú
        ordered_urls = []
        menu_items = []
        
        # 1. Intentar encontrar elementos de lista que suelen representar menús
        menu_lists = menu.find_all(["ul", "ol"])
        if menu_lists:
            for menu_list in menu_lists:
                menu_items.extend(menu_list.find_all("li"))
        
        # 2. Si no hay elementos de lista, buscar directamente los enlaces
        if not menu_items:
            menu_items = menu.find_all("a", href=True)
        else:
            # Si tenemos elementos de lista, extraer los enlaces de cada uno
            menu_items = [item.find("a", href=True) for item in menu_items]
            # Filtrar elementos None (li sin enlaces)
            menu_items = [item for item in menu_items if item]
        
        logger.info(f"Elementos de menú encontrados: {len(menu_items)}")
        
        # Procesamos cada enlace en el orden del menú
        for item in menu_items:
            if hasattr(item, 'href') and item['href']:
                href = item['href']
                absolute_url = urljoin(seed_url, href)
                
                if (absolute_url.startswith(BASE_DOMAIN) and 
                    absolute_url.endswith(".html") and 
                    absolute_url not in ordered_urls):
                    
                    ordered_urls.append(absolute_url)
                    logger.info(f"Añadida URL del menú: {absolute_url}")
        
        # Si no encontramos URLs en el menú o son muy pocas, complementamos con crawling
        if len(ordered_urls) < 5:
            logger.warning("Pocas URLs encontradas en el menú. Realizando crawling adicional.")
            additional_urls = extract_urls_by_crawling(seed_url)
            for url in additional_urls:
                if url not in ordered_urls:
                    ordered_urls.append(url)
        
        return ordered_urls
        
    except Exception as e:
        logger.error(f"Error al extraer URLs ordenadas: {str(e)}")
        # En caso de error, recurrimos al método de crawling tradicional
        return extract_urls_by_crawling(seed_url)

def extract_urls_by_crawling(seed_url):
    """
    Método de respaldo que extrae URLs mediante crawling tradicional.
    """
    visited = set()
    to_visit = [seed_url]
    all_urls = []
    
    while to_visit:
        url = to_visit.pop(0)
        if url in visited:
            continue
        
        try:
            logger.info(f"Analizando por crawling: {url}")
            response = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")
            
            links = soup.find_all("a", href=True)
            logger.info(f"Enlaces encontrados: {len(links)}")
            
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
            logger.error(f"Error en crawling {url}: {str(e)}")
    
    # Ordenamos por la estructura de carpetas y nombres para mantener cierta lógica
    return sorted(all_urls)

def extract_code_block_content(element):
    """
    Extrae el contenido de texto de un bloque de código, 
    independientemente de cómo esté estructurado.
    """
    # Si el elemento es un pre o code directamente, obtener su texto
    if element.name in ['pre', 'code']:
        return element.get_text(strip=True)
    
    # Buscar elementos pre o code dentro del contenedor
    code_elements = element.find_all(['pre', 'code'])
    if code_elements:
        return "\n\n".join([code.get_text(strip=True) for code in code_elements])
    
    # Buscar texto dentro de divs que pueden contener código
    code_text = element.get_text(strip=True)
    return code_text

def extract_table_content(table):
    """
    Extrae el contenido de una tabla HTML y lo formatea para su inclusión en el PDF.
    """
    if not table:
        return ""
    
    rows = table.find_all('tr')
    if not rows:
        return ""
    
    table_content = []
    
    # Procesar encabezados
    headers = rows[0].find_all(['th', 'td'])
    header_row = [header.get_text(strip=True) for header in headers]
    table_content.append(" | ".join(header_row))
    table_content.append("-" * (len(" | ".join(header_row))))  # Línea separadora
    
    # Procesar filas de datos
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        row_content = [cell.get_text(strip=True) for cell in cells]
        table_content.append(" | ".join(row_content))
    
    return "\n".join(table_content)

def process_content_containers(soup):
    """
    Procesa bloques de código, tablas y otros contenedores con barras de navegación
    para que se muestren correctamente en el PDF.
    """
    # 1. Procesar bloques de código
    # Patrones comunes para identificar contenedores de código
    code_containers = []
    
    # Buscar divs con clases específicas comunes en documentación de APIs
    code_selectors = [
        "div.playground-wrapper", "div.request-example", "div.response-example",
        "div.code-block", "div.example", "div.api-example", 
        "div.tab-content", "div.tabbed-example", "div.curl-example",
        "div.language-bash", "div.language-json", "div.language-javascript",
        ".swagger-ui .opblock .opblock-section .opblock-section-header"
    ]
    
    for selector in code_selectors:
        try:
            elements = soup.select(selector)
            code_containers.extend(elements)
        except Exception:
            pass
    
    # Buscar elementos pre y code directamente
    pre_elements = soup.find_all('pre')
    code_elements = soup.find_all('code')
    code_containers.extend(pre_elements)
    code_containers.extend(code_elements)
    
    # Buscar divs que contienen navegación de pestañas (común en documentaciones de API)
    tab_containers = soup.find_all('div', class_=lambda x: x and ('tab' in x.lower() or 'example' in x.lower()))
    code_containers.extend(tab_containers)
    
    # 2. Procesar tablas y contenedores de parámetros
    table_containers = []
    
    # Buscar tablas directamente
    tables = soup.find_all('table')
    table_containers.extend(tables)
    
    # Buscar contenedores que suelen tener tablas de parámetros
    param_selectors = [
        "div.parameters", "div.params", "div.request-parameters", 
        "div.response-parameters", "div.param-container",
        ".swagger-ui .opblock .opblock-section .parameters-container",
        ".swagger-ui .opblock .opblock-section .responses-wrapper",
        "div.push-parameters", "div.request-parameters"
    ]
    
    for selector in param_selectors:
        try:
            elements = soup.select(selector)
            table_containers.extend(elements)
        except Exception:
            pass
    
    # Contenedores que pueden tener barras de navegación y que incluyen tablas
    nav_containers = soup.find_all(['div', 'section'], class_=lambda x: x and any(term in (x.lower() if x else "") for term in ['scroll', 'nav', 'slider', 'container', 'params', 'parameter']))
    table_containers.extend(nav_containers)
    
    # 3. Procesar los contenedores de código
    for container in code_containers:
        try:
            # Verificar si no es parte de un contenedor de tabla ya procesado
            if any(container in tc for tc in table_containers):
                continue
                
            # Extraer el texto del código
            code_text = extract_code_block_content(container)
            
            if code_text and len(code_text) > 10:  # Filtrar bloques muy pequeños
                # Crear un nuevo elemento pre para sustituir el contenedor
                new_pre = soup.new_tag('pre', style="white-space: pre-wrap; word-wrap: break-word; background-color: #f5f5f5; padding: 10px; border-radius: 4px; font-family: monospace;")
                new_pre.string = code_text
                
                # Reemplazar el contenedor original con el nuevo elemento pre
                container.replace_with(new_pre)
        except Exception as e:
            logger.warning(f"No se pudo procesar un bloque de código: {str(e)}")
    
    # 4. Procesar los contenedores de tablas
    for container in table_containers:
        try:
            # Buscar tablas dentro del contenedor
            tables = container.find_all('table')
            
            if tables:
                # Crear un nuevo div para almacenar todas las tablas formateadas
                new_div = soup.new_tag('div', style="margin: 15px 0;")
                
                # Por cada tabla, extraer su contenido y crear una representación texto
                for table in tables:
                    table_title = ""
                    
                    # Buscar un posible título para la tabla
                    prev_el = table.find_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'caption', 'div', 'p'])
                    if prev_el and prev_el.name not in ['div', 'p']:
                        table_title = prev_el.get_text(strip=True)
                    elif prev_el and (prev_el.has_attr('class') and any(c for c in prev_el['class'] if 'title' in c.lower())):
                        table_title = prev_el.get_text(strip=True)
                    
                    # Si encontramos un título, lo agregamos
                    if table_title:
                        title_el = soup.new_tag('h4', style="margin-bottom: 5px;")
                        title_el.string = table_title
                        new_div.append(title_el)
                    
                    # Extraer y formatear el contenido de la tabla
                    table_content = extract_table_content(table)
                    if table_content:
                        table_pre = soup.new_tag('pre', style="white-space: pre-wrap; word-wrap: break-word; background-color: #f8f8f8; padding: 10px; border-radius: 4px; font-family: monospace; margin-bottom: 15px;")
                        table_pre.string = table_content
                        new_div.append(table_pre)
                
                # Reemplazar el contenedor original con el nuevo div que contiene las tablas formateadas
                if len(new_div.contents) > 0:
                    container.replace_with(new_div)
            elif container.name == 'table':
                # El contenedor es una tabla directamente
                table_content = extract_table_content(container)
                if table_content:
                    table_pre = soup.new_tag('pre', style="white-space: pre-wrap; word-wrap: break-word; background-color: #f8f8f8; padding: 10px; border-radius: 4px; font-family: monospace;")
                    table_pre.string = table_content
                    container.replace_with(table_pre)
        except Exception as e:
            logger.warning(f"No se pudo procesar un contenedor de tabla: {str(e)}")
    
    return soup

def process_html(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Eliminar elementos de navegación y scripts
        for element in soup(["header", "footer", "nav", "script", "style"]):
            element.decompose()
        
        # Procesar los bloques de código y tablas especiales
        process_content_containers(soup)
        
        # Convertir rutas relativas a absolutas
        base_url = url.rsplit("/", 1)[0] + "/"
        for tag in soup.find_all(["img", "link"]):
            for attr in ["src", "href"]:
                if tag.get(attr):
                    tag[attr] = urljoin(base_url, tag[attr])
        
        # Mejorar la presentación general del documento
        # Agregar estilo para mejorar la legibilidad
        style_tag = soup.new_tag('style')
        style_tag.string = """
            body { font-family: Arial, sans-serif; line-height: 1.5; }
            table { border-collapse: collapse; width: 100%; margin: 15px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
            h1, h2, h3, h4, h5, h6 { margin-top: 20px; }
            pre { background-color: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; }
            code { font-family: monospace; }
        """
        soup.head.append(style_tag) if soup.head else soup.append(style_tag)
        
        return str(soup)
    
    except Exception as e:
        logger.error(f"Error procesando {url}: {str(e)}")
        return None

def convert_to_pdf(url_list):
    """
    Convierte las URLs en archivos PDF individuales y los combina.
    """
    pdf_files = []
    
    for idx, url in enumerate(url_list, 1):
        try:
            logger.info(f"Procesando ({idx}/{len(url_list)}): {url}")
            html_content = process_html(url)
            
            if html_content:
                output_path = os.path.join(TEMP_DIR, f"page_{idx}.pdf")
                
                # Obtener el nombre de la página para usarlo como encabezado
                page_name = url.split('/')[-1].replace('.html', '').replace('%20', ' ')
                
                pdfkit.from_string(
                    html_content,
                    output_path,
                    configuration=config,
                    options={
                        "encoding": "UTF-8",
                        "page-size": "A4",
                        "margin-top": "20mm",
                        "margin-right": "15mm",
                        "margin-bottom": "20mm",
                        "margin-left": "15mm",
                        "enable-local-file-access": "",
                        "quiet": "",
                        # Opciones para mejorar la legibilidad
                        "print-media-type": "",
                        "no-background": "",
                        # Agregar encabezado y pie de página
                        "header-center": page_name,
                        "header-font-size": "9",
                        "header-spacing": "5",
                        "footer-center": f"Página [page] de [topage]",
                        "footer-font-size": "8",
                        # Ajustes para mejorar la presentación de las tablas
                        "dpi": "300",
                        # Ajuste para asegurar que se muestren todos los contenidos
                        "javascript-delay": "1000",
                    }
                )
                pdf_files.append(output_path)
                logger.info(f"PDF creado: {output_path}")
        
        except Exception as e:
            logger.error(f"Error crítico al procesar {url}: {str(e)}")

    return pdf_files

def merge_pdfs(pdf_files, output_file):
    """
    Combina varios archivos PDF en uno solo.
    """
    if not pdf_files:
        logger.error("No hay archivos PDF para combinar")
        return False
    
    try:
        merger = PdfMerger()
        for pdf_file in pdf_files:
            merger.append(pdf_file)
        
        merger.write(output_file)
        merger.close()
        logger.info(f"PDF combinado creado: {output_file}")
        return True
    
    except Exception as e:
        logger.error(f"Error al combinar PDFs: {str(e)}")
        return False

def cleanup(pdf_files, temp_dir):
    """
    Limpia los archivos temporales.
    """
    try:
        for f in pdf_files:
            os.remove(f)
        os.rmdir(temp_dir)
        logger.info("Limpieza de archivos temporales completada")
    except Exception as e:
        logger.warning(f"Error durante la limpieza: {str(e)}")

def parse_navigation_structure(url):
    """
    Analiza la estructura de navegación para extraer el orden de las páginas.
    Esta función es una alternativa que intenta encontrar un índice o mapa del sitio.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Buscar elementos que suelen contener la tabla de contenidos
        toc_candidates = [
            soup.find('div', class_=lambda c: c and ('toc' in c.lower() or 'contents' in c.lower())),
            soup.find('nav', class_=lambda c: c and ('toc' in c.lower() or 'nav' in c.lower())),
            soup.find('div', id=lambda i: i and ('toc' in i.lower() or 'contents' in i.lower())),
            soup.find('div', class_=lambda c: c and ('sidebar' in c.lower() or 'menu' in c.lower()))
        ]
        
        # Filtrar candidatos None
        toc_candidates = [toc for toc in toc_candidates if toc]
        
        if toc_candidates:
            toc = toc_candidates[0]  # Tomamos el primer candidato viable
            links = toc.find_all('a', href=True)
            
            urls = []
            for link in links:
                href = link['href']
                abs_url = urljoin(url, href)
                if abs_url.startswith(BASE_DOMAIN) and abs_url.endswith('.html'):
                    urls.append(abs_url)
            
            logger.info(f"Estructura de navegación encontrada con {len(urls)} enlaces")
            return urls
        
        return []
        
    except Exception as e:
        logger.error(f"Error al analizar estructura de navegación: {str(e)}")
        return []

def order_urls_by_structure(urls):
    """
    Ordena las URLs según la estructura de secciones, subsecciones y archivos específicos definidos.
    """
    if not urls:
        return []
    
    # Dividir URLs por secciones
    sections = {}
    for section in SECTION_ORDER:
        sections[section] = []
    
    # Categoría para URLs que no pertenecen a ninguna sección conocida
    sections["other"] = []
    
    # Clasificar cada URL en su sección correspondiente
    for url in urls:
        found_section = False
        for section in SECTION_ORDER:
            if f"/{section}/" in url:
                sections[section].append(url)
                found_section = True
                break
        
        if not found_section:
            sections["other"].append(url)
    
    # Procesar subsecciones
    for section, subsections in SUBSECTION_ORDER.items():
        if section in sections and sections[section]:
            # Ordenamos las URLs de esta sección por subsecciones
            subsection_urls = {}
            for subsection in subsections:
                subsection_urls[subsection] = []
            
            # Categoría para URLs que están en la sección pero no en subsecciones conocidas
            subsection_urls["other"] = []
            
            # Clasificar las URLs de esta sección en subsecciones
            for url in sections[section]:
                found_subsection = False
                for subsection in subsections:
                    if f"/{section}/{subsection}/" in url:
                        subsection_urls[subsection].append(url)
                        found_subsection = True
                        break
                
                if not found_subsection:
                    # Si no pertenece a ninguna subsección, puede ser un archivo directamente en la sección
                    if url.split('/')[-2] == section:
                        subsection_urls["other"].append(url)
                    else:
                        # O podría estar en una subsección no definida
                        subsection_path = url.split(f"/{section}/")[1].split("/")[0]
                        if subsection_path not in subsection_urls:
                            subsection_urls[subsection_path] = []
                        subsection_urls[subsection_path].append(url)
            
            # Reordenar la sección según las subsecciones
            ordered_section_urls = []
            for subsection in subsections:
                # Para cada subsección, ordenar sus URLs según el orden específico de archivos si existe
                subsection_files = subsection_urls[subsection]
                if f"{section}/{subsection}" in SPECIFIC_FILE_ORDER:
                    specific_order = SPECIFIC_FILE_ORDER[f"{section}/{subsection}"]
                    # Primero colocamos los archivos con orden específico
                    for file_name in specific_order:
                        for url in subsection_files[:]:
                            if url.endswith(f"/{file_name}"):
                                ordered_section_urls.append(url)
                                subsection_files.remove(url)
                                break
                    
                    # Luego añadimos el resto de archivos de la subsección
                    ordered_section_urls.extend(sorted(subsection_files))
                else:
                    # Si no hay orden específico, ordenamos alfabéticamente
                    ordered_section_urls.extend(sorted(subsection_files))
            
            # Añadir URLs que están directamente en la sección (no en subsecciones)
            if "other" in subsection_urls and subsection_urls["other"]:
                # Verificar si hay un orden específico para estos archivos
                if section in SPECIFIC_FILE_ORDER:
                    specific_order = SPECIFIC_FILE_ORDER[section]
                    other_files = subsection_urls["other"]
                    
                    # Ordenar según el orden específico
                    for file_name in specific_order:
                        for url in other_files[:]:
                            if url.endswith(f"/{file_name}"):
                                ordered_section_urls.append(url)
                                other_files.remove(url)
                                break
                    
                    # Añadir el resto de archivos que no tienen orden específico
                    ordered_section_urls.extend(sorted(other_files))
                else:
                    # Sin orden específico, solo ordenamos alfabéticamente
                    ordered_section_urls.extend(sorted(subsection_urls["other"]))
            
            # Reemplazar la lista original de la sección con la ordenada
            sections[section] = ordered_section_urls
        else:
            # Si no hay URLs en esta sección o la sección no existe, continuamos
            continue
    
    # Para las secciones sin subsecciones, ordenar según el orden específico de archivos
    for section in SECTION_ORDER:
        if section not in SUBSECTION_ORDER and section in SPECIFIC_FILE_ORDER and section in sections:
            specific_order = SPECIFIC_FILE_ORDER[section]
            section_urls = sections[section]
            ordered_section_urls = []
            
            # Primero colocamos los archivos con orden específico
            for file_name in specific_order:
                for url in section_urls[:]:
                    if url.endswith(f"/{file_name}"):
                        ordered_section_urls.append(url)
                        section_urls.remove(url)
                        break
            
            # Luego añadimos el resto de archivos
            ordered_section_urls.extend(sorted(section_urls))
            sections[section] = ordered_section_urls
    
    # Reconstruir la lista final de URLs en el orden correcto
    ordered_urls = []
    for section in SECTION_ORDER:
        ordered_urls.extend(sections[section])
    
    # Añadir URLs que no pertenecen a ninguna sección conocida
    ordered_urls.extend(sorted(sections["other"]))
    
    return ordered_urls

if __name__ == "__main__":
    logger.info("🚀 Iniciando scraping de documentación API")
    
    # 1. Obtenemos todas las URLs mediante crawling
    crawled_urls = extract_urls_by_crawling(SEED_URL)
    
    if not crawled_urls:
        logger.error("No se encontraron URLs para procesar")
        exit(1)
    
    logger.info(f"Se encontraron {len(crawled_urls)} URLs mediante crawling")
    
    # 2. Ordenamos las URLs según la estructura definida
    urls = order_urls_by_structure(crawled_urls)
    
    # 3. Verificamos si tenemos URLs de referencia que deben ir al principio
    if REFERENCE_ORDER:
        # Si hay referencias manuales, aseguramos que estén al principio
        reference_urls = [url for url in REFERENCE_ORDER if url in crawled_urls]
        other_urls = [url for url in urls if url not in reference_urls]
        urls = reference_urls + other_urls
    
    logger.info(f"URLs ordenadas para procesar: {len(urls)}")
    for i, url in enumerate(urls, 1):
        logger.info(f"{i}. {url}")
    
    # Convertir a PDF
    pdf_files = convert_to_pdf(urls)
    
    # Combinar PDFs
    if merge_pdfs(pdf_files, OUTPUT_PDF):
        logger.info(f"🎉 PDF generado exitosamente: {OUTPUT_PDF}")
    else:
        logger.error("❌ No se pudo generar el PDF final")
    
    # Limpieza
    cleanup(pdf_files, TEMP_DIR)
