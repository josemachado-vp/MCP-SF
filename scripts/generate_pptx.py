"""
Genera la presentación ejecutiva de SF Assistant MCP para directores.
Paleta: azul oscuro (#1A3C6E), gris (#4A5568 / #E2E8F0), blanco (#FFFFFF).
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
from pptx.oxml.ns import qn
from lxml import etree
import copy

# ── Paleta ──────────────────────────────────────────────────────────────────
DARK_BLUE  = RGBColor(0x1A, 0x3C, 0x6E)
MID_BLUE   = RGBColor(0x2A, 0x5A, 0x9F)
LIGHT_BLUE = RGBColor(0xD6, 0xE4, 0xF7)
DARK_GREY  = RGBColor(0x4A, 0x55, 0x68)
MID_GREY   = RGBColor(0x71, 0x80, 0x96)
LIGHT_GREY = RGBColor(0xE2, 0xE8, 0xF0)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
ACCENT     = RGBColor(0xF0, 0x8C, 0x00)   # ámbar para énfasis puntual

prs = Presentation()
prs.slide_width  = Inches(13.33)
prs.slide_height = Inches(7.5)

BLANK = prs.slide_layouts[6]   # completamente en blanco


# ── Helpers ──────────────────────────────────────────────────────────────────

def bg(slide, color: RGBColor):
    """Fondo sólido para una diapositiva."""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color


def box(slide, left, top, width, height,
        bg_color=None, border_color=None, border_pt=0):
    """Caja rectangular (sin texto)."""
    from pptx.util import Pt as Pt2
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    fill = shape.fill
    if bg_color:
        fill.solid()
        fill.fore_color.rgb = bg_color
    else:
        fill.background()
    line = shape.line
    if border_color and border_pt:
        line.color.rgb = border_color
        line.width = Pt2(border_pt)
    else:
        line.fill.background()
    return shape


def txt(slide, text, left, top, width, height,
        font_size=18, bold=False, color=WHITE,
        align=PP_ALIGN.LEFT, wrap=True, italic=False):
    """Cuadro de texto."""
    txBox = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = "Calibri"
    return txBox


def txt_lines(slide, lines, left, top, width, height,
              font_size=16, color=WHITE, line_spacing_pt=6,
              bold_first=False):
    """
    Cuadro de texto con múltiples párrafos.
    lines: list of str  (o list of (str, bold:bool))
    """
    from pptx.util import Pt as Pt2
    from pptx.oxml.ns import qn
    txBox = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    tf = txBox.text_frame
    tf.word_wrap = True

    for i, line in enumerate(lines):
        if isinstance(line, tuple):
            text_val, is_bold = line
        else:
            text_val = line
            is_bold = bold_first and i == 0

        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.space_before = Pt2(line_spacing_pt)
        run = p.add_run()
        run.text = text_val
        run.font.size = Pt2(font_size)
        run.font.bold = is_bold
        run.font.color.rgb = color
        run.font.name = "Calibri"
    return txBox


def accent_bar(slide, top=0.0, height=0.07, color=ACCENT):
    """Barra horizontal de acento."""
    box(slide, 0, top, 13.33, height, bg_color=color)


def side_stripe(slide, color=DARK_BLUE, width=0.35):
    """Franja vertical izquierda."""
    box(slide, 0, 0, width, 7.5, bg_color=color)


# ════════════════════════════════════════════════════════════════════════════
# SLIDE 1 — Portada
# ════════════════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(BLANK)
bg(slide, DARK_BLUE)

# Franja inferior gris
box(slide, 0, 6.0, 13.33, 1.5, bg_color=DARK_GREY)

# Barra de acento ámbar
accent_bar(slide, top=5.85, height=0.12)

# Título principal
txt(slide, "SF Assistant MCP",
    left=0.8, top=1.4, width=11.0, height=1.4,
    font_size=52, bold=True, color=WHITE, align=PP_ALIGN.LEFT)

# Subtítulo
txt(slide, "El copiloto inteligente para consultoría SuccessFactors",
    left=0.8, top=2.95, width=10.0, height=0.8,
    font_size=22, bold=False, color=LIGHT_GREY, align=PP_ALIGN.LEFT)

# Tagline en franja inferior
txt(slide, "Seguridad. Eficiencia. El consultor que piensa, no que ejecuta.",
    left=0.8, top=6.1, width=11.5, height=0.7,
    font_size=16, bold=False, color=LIGHT_GREY, align=PP_ALIGN.LEFT)


# ════════════════════════════════════════════════════════════════════════════
# SLIDE 2 — El problema (storytelling)
# ════════════════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(BLANK)
bg(slide, WHITE)
side_stripe(slide, color=DARK_BLUE)
accent_bar(slide, top=0.0, height=0.07, color=DARK_BLUE)

# Título
txt(slide, "¿Cómo trabaja un consultor SF hoy?",
    left=0.7, top=0.2, width=12.0, height=0.7,
    font_size=26, bold=True, color=DARK_BLUE)

# Cita / escena
box(slide, 0.7, 1.05, 11.9, 2.1, bg_color=LIGHT_GREY)
txt(slide,
    "\"Son las 11 de la noche. El cutover es en 48 horas. Tiene Provisioning en una "
    "pestaña, un Excel con 4,000 registros en otra y Postman en una tercera. "
    "Revisa campo por campo. Son las 2am cuando termina — y todavía no está seguro "
    "de que no se le escapó algo.\"",
    left=1.0, top=1.15, width=11.4, height=1.8,
    font_size=15, bold=False, color=DARK_GREY, italic=True)

# Tres columnas de dolor
col_data = [
    ("⏱  Tiempo perdido",
     "30–40% del tiempo de un proyecto\nse va en tareas mecánicas:\nqueries, comparaciones, documentación."),
    ("⚠  Riesgo humano",
     "Revisar miles de registros a mano\nno es auditoría — es una apuesta.\nUn campo mal mapeado cuesta horas."),
    ("💸  Costo invisible",
     "Cada hora de un senior en tareas\nrepetitivas es una hora que no\nse dedica al cliente ni al diseño."),
]
for i, (title, body) in enumerate(col_data):
    x = 0.7 + i * 4.2
    box(slide, x, 3.35, 3.9, 3.4, bg_color=DARK_BLUE)
    txt(slide, title, x + 0.2, 3.5, 3.5, 0.6,
        font_size=14, bold=True, color=ACCENT)
    txt(slide, body, x + 0.2, 4.15, 3.5, 2.4,
        font_size=13, bold=False, color=WHITE)


# ════════════════════════════════════════════════════════════════════════════
# SLIDE 3 — Seguridad primero (PII)
# ════════════════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(BLANK)
bg(slide, DARK_BLUE)
accent_bar(slide, top=0.0, height=0.07, color=ACCENT)

txt(slide, "Primero lo que importa: seguridad",
    left=0.7, top=0.15, width=12.0, height=0.7,
    font_size=26, bold=True, color=WHITE)

txt(slide,
    "SuccessFactors almacena SSNs, salarios, datos de salud y estructuras "
    "organizacionales completas. Antes de hablar de productividad — ¿qué tan "
    "seguro es el acceso?",
    left=0.7, top=0.95, width=12.0, height=0.65,
    font_size=14, color=LIGHT_GREY)

# Escenario de riesgo
box(slide, 0.7, 1.75, 11.9, 1.0, bg_color=RGBColor(0x7B, 0x1D, 0x1D))
txt(slide,
    "⚠  Sin protección: \"dame los empleados de México con información personal\" "
    "→ SSNs de 5,000 empleados en el chat. Un screenshot. Una brecha.",
    left=0.9, top=1.82, width=11.4, height=0.8,
    font_size=13, bold=False, color=WHITE)

# Grid de controles de seguridad: 2 filas × 3 columnas
controls = [
    ("🔐  Autenticación OIDC",    "Flujo SAP estándar de 2 pasos via IAS.\nSin contraseñas en texto plano."),
    ("🛡  Protección PII",         "Clasificación en 4 niveles.\nSSNs y cuentas bancarias: bloqueados."),
    ("🏢  Aislamiento multi-tenant","Cada cliente en su propio espacio.\nImposible cruzar credenciales."),
    ("✏  Escritura segura",        "dry_run por defecto.\nLa escritura real requiere confirmación."),
    ("🔍  Auditorías read-only",    "Diagnostica sin modificar.\nCero riesgo de alterar producción."),
    ("⚡  Rate limiting",           "Máx. 5 requests concurrentes.\nProtege la instancia del cliente."),
]
for i, (title, body) in enumerate(controls):
    row, col = divmod(i, 3)
    x = 0.55 + col * 4.25
    y = 2.95 + row * 2.1
    box(slide, x, y, 4.0, 1.9, bg_color=MID_BLUE)
    txt(slide, title, x + 0.18, y + 0.12, 3.65, 0.55,
        font_size=13, bold=True, color=ACCENT)
    txt(slide, body, x + 0.18, y + 0.65, 3.65, 1.15,
        font_size=12, color=WHITE)


# ════════════════════════════════════════════════════════════════════════════
# SLIDE 4 — Capacidades (50 herramientas agrupadas)
# ════════════════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(BLANK)
bg(slide, WHITE)
side_stripe(slide, color=DARK_BLUE)
accent_bar(slide, top=0.0, height=0.07, color=DARK_BLUE)

txt(slide, "50 herramientas. Un solo flujo de trabajo.",
    left=0.7, top=0.18, width=12.0, height=0.7,
    font_size=26, bold=True, color=DARK_BLUE)

txt(slide, "Se usan conversacionalmente — como hablarle a un colega que conoce la API de SF de memoria.",
    left=0.7, top=0.95, width=12.0, height=0.45,
    font_size=14, color=DARK_GREY)

categories = [
    ("Discovery",        "Explora entidades, campos\ny picklists en segundos"),
    ("Business Rules",   "Del requerimiento al test case\nen lenguaje natural"),
    ("Empleados",        "Búsqueda, perfiles, organigramas\ne historial de empleo"),
    ("Comparación",      "DEV vs QA vs PROD —\nqué difiere, exactamente"),
    ("Auditoría",        "Detecta anomalías y diagnostica\nsin tocar la instancia"),
    ("Migración",        "Valida, ordena, reconcilia\ny genera archivos de purge"),
    ("Documentación",    "Specs, checklists y diccionarios\ngenerados, no escritos"),
    ("Go-Live",          "Validación sistemática antes\nde cruzar el punto de no retorno"),
]

cols = 4
for i, (cat, desc) in enumerate(categories):
    row, col = divmod(i, cols)
    x = 0.6 + col * 3.15
    y = 1.6 + row * 2.6
    box(slide, x, y, 3.0, 2.4,
        bg_color=DARK_BLUE if row == 0 else LIGHT_GREY)
    txt_color = WHITE if row == 0 else DARK_BLUE
    desc_color = LIGHT_GREY if row == 0 else DARK_GREY
    txt(slide, cat, x + 0.15, y + 0.12, 2.7, 0.55,
        font_size=14, bold=True, color=txt_color)
    txt(slide, desc, x + 0.15, y + 0.7, 2.7, 1.5,
        font_size=12, color=desc_color)


# ════════════════════════════════════════════════════════════════════════════
# SLIDE 5 — Antes vs Después
# ════════════════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(BLANK)
bg(slide, WHITE)
side_stripe(slide, color=DARK_BLUE)
accent_bar(slide, top=0.0, height=0.07, color=DARK_BLUE)

txt(slide, "El tiempo recuperado — en números concretos",
    left=0.7, top=0.18, width=12.0, height=0.7,
    font_size=26, bold=True, color=DARK_BLUE)

# Encabezados de columna
box(slide, 0.65, 1.05, 4.5, 0.55, bg_color=DARK_GREY)
txt(slide, "Tarea", 0.75, 1.1, 4.3, 0.45,
    font_size=14, bold=True, color=WHITE, align=PP_ALIGN.LEFT)

box(slide, 5.3, 1.05, 3.3, 0.55, bg_color=DARK_GREY)
txt(slide, "Antes", 5.4, 1.1, 3.1, 0.45,
    font_size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

box(slide, 8.75, 1.05, 3.85, 0.55, bg_color=DARK_BLUE)
txt(slide, "Con MCP", 8.85, 1.1, 3.65, 0.45,
    font_size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

rows_data = [
    ("Explorar metadatos de una entidad",       "2 horas",        "2 minutos"),
    ("Especificación de business rule",          "Medio día",      "15 minutos"),
    ("Comparar entornos antes del cutover",      "1 día completo", "10 minutos"),
    ("Validar archivo de migración (5,000 reg.)", "3–4 horas",     "5 minutos"),
    ("Generar documentación funcional",          "1–2 días",       "Inmediato"),
    ("Checklist de go-live",                     "4 horas",        "Automatizado"),
]

for i, (task, before, after) in enumerate(rows_data):
    y = 1.75 + i * 0.82
    row_bg = LIGHT_GREY if i % 2 == 0 else WHITE
    box(slide, 0.65, y, 4.5, 0.72, bg_color=row_bg)
    txt(slide, task,   0.78, y + 0.08, 4.2, 0.58, font_size=13, color=DARK_GREY)

    box(slide, 5.3, y, 3.3, 0.72, bg_color=row_bg)
    txt(slide, before, 5.3, y + 0.08, 3.3, 0.58,
        font_size=13, bold=False, color=MID_GREY, align=PP_ALIGN.CENTER)

    box(slide, 8.75, y, 3.85, 0.72, bg_color=LIGHT_BLUE)
    txt(slide, after,  8.75, y + 0.08, 3.85, 0.58,
        font_size=13, bold=True, color=DARK_BLUE, align=PP_ALIGN.CENTER)

# Nota al pie
txt(slide,
    "* Estimados basados en flujos de trabajo típicos de proyectos de implementación SF.",
    left=0.7, top=6.9, width=12.0, height=0.4,
    font_size=10, color=MID_GREY, italic=True)


# ════════════════════════════════════════════════════════════════════════════
# SLIDE 6 — El cambio de rol
# ════════════════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(BLANK)
bg(slide, DARK_BLUE)
accent_bar(slide, top=0.0, height=0.07, color=ACCENT)

txt(slide, "El consultor que piensa, no que ejecuta",
    left=0.7, top=0.15, width=12.0, height=0.75,
    font_size=28, bold=True, color=WHITE)

# Dos columnas: Antes / Después
box(slide, 0.6, 1.1, 5.8, 5.6, bg_color=DARK_GREY)
box(slide, 6.9, 1.1, 5.8, 5.6, bg_color=MID_BLUE)

txt(slide, "Antes",  0.6,  1.1, 5.8, 0.6, font_size=18, bold=True,
    color=LIGHT_GREY, align=PP_ALIGN.CENTER)
txt(slide, "Con MCP", 6.9, 1.1, 5.8, 0.6, font_size=18, bold=True,
    color=ACCENT, align=PP_ALIGN.CENTER)

before_items = [
    "Construye queries OData manualmente",
    "Compara entornos copiando y pegando",
    "Escribe specs desde cero",
    "Valida datos registro por registro",
    "Documenta lo que ya hizo (tarde, incompleto)",
    "Llega al go-live sin certeza total",
]
after_items = [
    "Pregunta en lenguaje natural",
    "Obtiene diferencias en segundos",
    "Revisa y valida lo generado",
    "Validación automática contra metadatos reales",
    "Documentación generada al instante desde la instancia",
    "Go-live con validación sistemática",
]

for i, item in enumerate(before_items):
    txt(slide, f"✗  {item}", 0.8, 1.85 + i * 0.72, 5.3, 0.65,
        font_size=13, color=LIGHT_GREY)

for i, item in enumerate(after_items):
    txt(slide, f"✓  {item}", 7.1, 1.85 + i * 0.72, 5.3, 0.65,
        font_size=13, color=WHITE)


# ════════════════════════════════════════════════════════════════════════════
# SLIDE 7 — Para quién es y próximos pasos
# ════════════════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(BLANK)
bg(slide, WHITE)
side_stripe(slide, color=DARK_BLUE)
accent_bar(slide, top=0.0, height=0.07, color=DARK_BLUE)

txt(slide, "¿Para quién es SF Assistant MCP?",
    left=0.7, top=0.18, width=12.0, height=0.65,
    font_size=26, bold=True, color=DARK_BLUE)

audiences = [
    ("Consultores SF",
     "Reducen trabajo manual sin sacrificar calidad. "
     "Más tiempo para diseñar, menos para ejecutar."),
    ("Leads técnicos",
     "Comparan entornos, validan migraciones y preparan "
     "go-lives con datos reales — no con intuición."),
    ("Equipos de soporte",
     "Diagnostican incidentes con datos precisos, "
     "en modo lectura, sin riesgo de alterar la instancia."),
    ("Firmas de consultoría",
     "Escalan capacidad de delivery sin escalar "
     "proporcionalmente el headcount."),
]

for i, (role, desc) in enumerate(audiences):
    row, col = divmod(i, 2)
    x = 0.65 + col * 6.35
    y = 1.05 + row * 2.55
    box(slide, x, y, 6.1, 2.3, bg_color=LIGHT_GREY)
    box(slide, x, y, 0.18, 2.3, bg_color=DARK_BLUE)
    txt(slide, role, x + 0.35, y + 0.15, 5.6, 0.55,
        font_size=16, bold=True, color=DARK_BLUE)
    txt(slide, desc, x + 0.35, y + 0.75, 5.6, 1.35,
        font_size=13, color=DARK_GREY)

# Cierre
box(slide, 0.65, 6.05, 12.1, 1.1, bg_color=DARK_BLUE)
txt(slide,
    "SF Assistant MCP no es una herramienta más. Es el cambio de paradigma "
    "que le devuelve al consultor el tiempo para ser consultor.",
    left=0.9, top=6.15, width=11.7, height=0.85,
    font_size=14, bold=False, color=WHITE, align=PP_ALIGN.CENTER)


# ════════════════════════════════════════════════════════════════════════════
# Guardar
# ════════════════════════════════════════════════════════════════════════════
output = "docs/SF_Assistant_MCP_Ejecutivo.pptx"
prs.save(output)
print(f"Presentación guardada en: {output}")
