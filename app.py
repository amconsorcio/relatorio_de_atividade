import io
import re
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# -----------------------------------------------------------------------------
# Configuração geral
# -----------------------------------------------------------------------------

st.set_page_config(
    page_title="Relatório de Atividade",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="collapsed",
)

MAX_PHOTOS = 9
APP_PREFIX = "relatorio_atividade"

NAVY = colors.HexColor("#17343E")
TEAL = colors.HexColor("#1E716B")
TEAL_LIGHT = colors.HexColor("#E5F3EF")
ORANGE = colors.HexColor("#E9803C")
INK = colors.HexColor("#17242E")
MUTED = colors.HexColor("#6B7880")
LINE = colors.HexColor("#D9E3E0")
LIGHT = colors.HexColor("#F3F6F5")
WHITE = colors.white


# -----------------------------------------------------------------------------
# Estilos visuais da tela
# -----------------------------------------------------------------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&display=swap');

    .stApp { background: #edf2ef; color: #17242e; }
    [data-testid="stHeader"] { background: #17343e; }
    .block-container { max-width: 1100px; padding-top: 2rem; padding-bottom: 4rem; }
    h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; color: #17343e !important; }
    h1 { letter-spacing: -.04em; }
    .hero { padding: 1.2rem 0 1rem; }
    .eyebrow { color: #e9803c; font-size: .72rem; font-weight: 700; letter-spacing: .15em; text-transform: uppercase; }
    .hero p { color: #6b7880; margin-top: -.4rem; }
    .stButton > button, .stDownloadButton > button { border-radius: 9px; font-weight: 700; }
    .stDownloadButton > button { background: #e9803c; color: white; border: 0; }
    .section-card { background: white; border: 1px solid #dfe7e4; border-radius: 16px; padding: 1.3rem 1.4rem .9rem; margin: 1rem 0; box-shadow: 0 8px 22px rgba(31,63,53,.06); }
    .section-card h2 { margin-top: 0; font-size: 1.25rem; }
    .caption { color: #6b7880; font-size: .85rem; }
    .os-box { background: #e5f3ef; border: 1px solid #bfe0d6; border-radius: 10px; padding: .7rem .9rem; color: #17343e; font-weight: 700; }
    div[data-testid="stFileUploader"] { background: #f7faf9; border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Estado e funções auxiliares
# -----------------------------------------------------------------------------

def next_order_number() -> str:
    """Gera uma OS sequencial por sessão do navegador."""
    if "os_counter" not in st.session_state:
        st.session_state.os_counter = 1
    current = st.session_state.os_counter
    st.session_state.os_counter += 1
    return f"OS-{date.today().year}-{current:04d}"


def clean_filename(value: str) -> str:
    """Remove caracteres que não são adequados para nome de arquivo."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    return cleaned.strip("-") or "sem-valor"


def empty_material_row() -> dict[str, str]:
    return {
        "Código": "",
        "Descrição": "",
        "Unidade": "un",
        "Quantidade": "",
        "Observação": "",
    }


def material_editor(title: str, key: str) -> list[dict[str, str]]:
    """Exibe editor de materiais e retorna somente linhas preenchidas."""
    st.markdown(f"#### {title}")
    count = st.number_input(
        "Quantidade de linhas",
        min_value=1,
        max_value=10,
        value=3,
        step=1,
        key=f"{key}_count",
        help="Escolha quantas linhas deseja preencher.",
    )

    rows: list[dict[str, str]] = []
    headers = ["Código", "Descrição", "Unidade", "Quantidade", "Observação"]
    widths = [1.0, 2.2, 1.0, 1.0, 2.2]

    for index in range(int(count)):
        cols = st.columns(widths)
        values: dict[str, str] = {}
        for col, header in zip(cols, headers):
            with col:
                values[header] = st.text_input(
                    header,
                    key=f"{key}_{index}_{header}",
                    label_visibility="visible" if index == 0 else "collapsed",
                    placeholder=header,
                    value="un" if header == "Unidade" else "",
                )
        if any(values[name].strip() and not (name == "Unidade" and values[name].strip() == "un") for name in headers):
            rows.append(values)

    return rows


def uploaded_photo_grid(files: list, title: str) -> list:
    """Limita uploads a 9 arquivos e mostra miniaturas na tela."""
    st.markdown(f"#### {title}")
    selected = files[:MAX_PHOTOS] if files else []
    if len(files) > MAX_PHOTOS:
        st.warning(f"Apenas as primeiras {MAX_PHOTOS} fotos de {title.lower()} serão usadas.")

    if selected:
        cols = st.columns(3)
        for index, file in enumerate(selected):
            with cols[index % 3]:
                st.image(file, caption=f"{index + 1}. {file.name}", use_container_width=True)
    else:
        st.info(f"Selecione até {MAX_PHOTOS} fotos para {title.lower()}.")
    return selected


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    escaped = str(text or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped = escaped.replace("\n", "<br/>")
    return Paragraph(escaped, style)


def fit_photo(uploaded_file, max_width: float, max_height: float):
    """Cria uma imagem ReportLab em tamanho fixo, preservando a proporção."""
    try:
        raw = uploaded_file.getvalue()
        pil_image = PILImage.open(io.BytesIO(raw))
        width, height = pil_image.size
        if not width or not height:
            return None
        scale = min(max_width / width, max_height / height)
        image = Image(io.BytesIO(raw), width=width * scale, height=height * scale)
        image.hAlign = "CENTER"
        return image
    except Exception:
        return None


def photo_grid(files: list, title: str, styles: dict):
    """Monta uma grade 3x3, com placeholders para completar os 9 espaços."""
    photo_width = 57 * mm
    photo_height = 27 * mm
    cell_width = 59 * mm
    cell_height = 30 * mm
    cells = []

    for index in range(MAX_PHOTOS):
        if index < len(files):
            image = fit_photo(files[index], photo_width, photo_height)
            cell = image or paragraph("Imagem inválida", styles["Small"])
        else:
            cell = paragraph(str(index + 1), styles["Placeholder"])
        cells.append(cell)

    table = Table(
        [cells[0:3], cells[3:6], cells[6:9]],
        colWidths=[cell_width] * 3,
        rowHeights=[cell_height] * 3,
        hAlign="CENTER",
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F8F6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
            ]
        )
    )
    return [paragraph(f"{title} ({len(files)}/{MAX_PHOTOS})", styles["PhotoTitle"]), table, Spacer(1, 5 * mm)]


def fit_logo(uploaded_file, max_width: float, max_height: float):
    """Cria a imagem da logomarca preservando a proporção."""
    if not uploaded_file:
        return None
    try:
        raw = uploaded_file.getvalue()
        pil_image = PILImage.open(io.BytesIO(raw))
        width, height = pil_image.size
        if not width or not height:
            return None
        scale = min(max_width / width, max_height / height)
        logo = Image(io.BytesIO(raw), width=width * scale, height=height * scale)
        logo.hAlign = "LEFT"
        return logo
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Geração do PDF
# -----------------------------------------------------------------------------

def build_pdf(data: dict, material_groups: dict[str, list[dict[str, str]]], before: list, after: list, logo_file=None) -> bytes:
    buffer = io.BytesIO()
    page_width, page_height = A4

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=16, leading=19, textColor=NAVY, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8, leading=10, textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="Kicker", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=7, leading=8, textColor=ORANGE, tracking=1.1,
    ))
    styles.add(ParagraphStyle(
        name="Label", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=6.5, leading=8, textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="Value", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8, leading=10, textColor=INK,
    ))
    styles.add(ParagraphStyle(
        name="BodySmall", parent=styles["Normal"], fontName="Helvetica",
        fontSize=7.5, leading=10, textColor=INK,
    ))
    styles.add(ParagraphStyle(
        name="TableHeader", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=6.5, leading=8, textColor=TEAL,
    ))
    styles.add(ParagraphStyle(
        name="TableCell", parent=styles["Normal"], fontName="Helvetica",
        fontSize=7, leading=8.5, textColor=INK,
    ))
    styles.add(ParagraphStyle(
        name="Small", parent=styles["Normal"], fontName="Helvetica",
        fontSize=6, leading=7, textColor=INK,
    ))
    styles.add(ParagraphStyle(
        name="Placeholder", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8, leading=10, textColor=colors.HexColor("#A7B4B1"), alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="PhotoTitle", parent=styles["Heading3"], fontName="Helvetica-Bold",
        fontSize=9, leading=11, textColor=NAVY, spaceAfter=2,
    ))

    def draw_background(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 17 * mm, page_width - doc.rightMargin, 17 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawRightString(page_width - doc.rightMargin, 12 * mm, f"Relatório de Atividade · Página {doc.page}")
        canvas.restoreState()

    frame = Frame(12 * mm, 22 * mm, page_width - 24 * mm, page_height - 34 * mm, id="normal")
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=11 * mm,
        bottomMargin=22 * mm,
        title=f"Relatorio_{data['data_iso']}_{data['ordem']}",
        author="Relatório de Atividade",
    )
    doc.addPageTemplates([PageTemplate(id="portrait", frames=[frame], onPage=draw_background)])

    story = []

    # Cabeçalho da primeira página
    header_left = []
    logo = fit_logo(logo_file, 36 * mm, 18 * mm)
    if logo:
        header_left.append(logo)
        header_left.append(Spacer(1, 1 * mm))
    header_left += [
        paragraph("RELATÓRIO DE ATIVIDADE", styles["Kicker"]),
        paragraph(data["empresa"] or "Empresa não informada", styles["ReportTitle"]),
        paragraph("Registro de serviço em campo", styles["ReportSubtitle"]),
    ]
    header_right = [
        paragraph("ORDEM DE SERVIÇO", styles["Label"]),
        paragraph(data["ordem"], styles["Value"]),
    ]
    header = Table([[header_left, header_right]], colWidths=[140 * mm, 46 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (1, 0), (1, 0), 0.6, LINE),
        ("BACKGROUND", (1, 0), (1, 0), LIGHT),
        ("LEFTPADDING", (1, 0), (1, 0), 5),
        ("RIGHTPADDING", (1, 0), (1, 0), 5),
        ("TOPPADDING", (1, 0), (1, 0), 5),
        ("BOTTOMPADDING", (1, 0), (1, 0), 5),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story += [header, Spacer(1, 5 * mm)]

    meta_items = [
        ("Data", data["data_br"]),
        ("Município", data["municipio"]),
        ("Obra", data["obra"]),
        ("Veículo / Placa", data["veiculo"]),
        ("Equipe", data["equipe"]),
        ("Horário", f"{data['inicio'] or '—'} às {data['termino'] or '—'}"),
    ]
    meta_table = Table(
        [[paragraph(label, styles["Label"]), paragraph(value or "—", styles["Value"])] for label, value in meta_items],
        colWidths=[25 * mm, 62 * mm] * 3,
    )
    # Transformar os 6 pares em 3 colunas x 2 linhas.
    meta_data = []
    for row in range(2):
        meta_row = []
        for col in range(3):
            label, value = meta_items[row * 3 + col]
            meta_row.extend([paragraph(label, styles["Label"]), paragraph(value or "—", styles["Value"])])
        meta_data.append(meta_row)
    meta_table = Table(meta_data, colWidths=[24 * mm, 38 * mm] * 3, rowHeights=[11 * mm, 11 * mm])
    meta_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [meta_table, Spacer(1, 3 * mm)]

    address = Table([[paragraph("ENDEREÇO", styles["Label"]), paragraph(data["endereco"] or "—", styles["Value"])]], colWidths=[25 * mm, 161 * mm])
    address.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [address, Spacer(1, 3 * mm)]

    story += [paragraph("DESCRIÇÃO DO SERVIÇO", styles["Label"]), paragraph(data["descricao"] or "Nenhuma descrição informada.", styles["BodySmall"]), Spacer(1, 4 * mm)]

    def materials_table(title: str, rows: list[dict[str, str]]):
        story_rows = [[paragraph(title, styles["Value"])]]
        table_data = [[paragraph(header, styles["TableHeader"]) for header in ["Cód.", "Descrição", "Un.", "Qtd.", "Observação"]]]
        if rows:
            for row in rows:
                table_data.append([
                    paragraph(row.get("Código", "—"), styles["TableCell"]),
                    paragraph(row.get("Descrição", "—"), styles["TableCell"]),
                    paragraph(row.get("Unidade", "—"), styles["TableCell"]),
                    paragraph(row.get("Quantidade", "—"), styles["TableCell"]),
                    paragraph(row.get("Observação", "—"), styles["TableCell"]),
                ])
        else:
            table_data.append([paragraph("Nenhum material informado", styles["Small"]), "", "", "", ""])
        table = Table(table_data, colWidths=[20 * mm, 63 * mm, 17 * mm, 18 * mm, 68 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("SPAN", (0, 1), (-1, 1)) if not rows else ("BACKGROUND", (0, 0), (-1, 0), TEAL_LIGHT),
            ("BACKGROUND", (0, 0), (-1, 0), TEAL_LIGHT),
            ("GRID", (0, 0), (-1, -1), 0.35, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return [paragraph(title, styles["Value"]), table, Spacer(1, 2 * mm)]

    for title, key in [
        ("Material utilizado", "utilizado"),
        ("Material removido", "removido"),
        ("Material remanejado", "remanejado"),
    ]:
        story += materials_table(title, material_groups[key])

    # Assinaturas permanecem na primeira página.
    story += [Spacer(1, 3 * mm)]
    signature_table = Table(
        [["", ""], ["Responsável pelo serviço", "Conferência / cliente"]],
        colWidths=[88 * mm, 88 * mm],
        rowHeights=[13 * mm, 5 * mm],
    )
    signature_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (0, 0), 0.7, NAVY),
        ("LINEABOVE", (1, 0), (1, 0), 0.7, NAVY),
        ("ALIGN", (0, 1), (-1, 1), "CENTER"),
        ("TEXTCOLOR", (0, 1), (-1, 1), MUTED),
        ("FONTSIZE", (0, 1), (-1, 1), 7),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    story += [signature_table, PageBreak()]

    # Fotos: página retrato, antes em cima e depois abaixo, ambas 3x3.
    story += [paragraph("REGISTRO FOTOGRÁFICO", styles["Kicker"]), paragraph("Fotos do serviço", styles["ReportTitle"]), Spacer(1, 3 * mm)]
    story += photo_grid(before, "Fotos antes", styles)
    story += photo_grid(after, "Fotos depois", styles)

    doc.build(story)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# Interface Streamlit
# -----------------------------------------------------------------------------

if "ordem" not in st.session_state:
    st.session_state.ordem = next_order_number()

st.markdown('<div class="hero"><div class="eyebrow">Novo registro</div><h1>Relatório de atividade</h1><p>Preencha no celular e baixe um PDF pronto para compartilhar.</p></div>', unsafe_allow_html=True)

with st.form("service_form"):
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Dados do serviço")
    top_left, top_right = st.columns(2)
    with top_left:
        empresa = st.text_input("Empresa", placeholder="Nome da empresa")
        data_servico = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        municipio = st.text_input("Município", placeholder="Cidade / UF")
        endereco = st.text_input("Endereço", placeholder="Rua, número, bairro")
        veiculo = st.text_input("Veículo / Placa", placeholder="Caminhão — ABC1D23")
    with top_right:
        ordem = st.text_input(
            "Ordem de serviço",
            value=st.session_state.ordem,
            help="A numeração é sugerida automaticamente, mas você pode editar este campo.",
        )
        if ordem.strip():
            st.session_state.ordem = ordem.strip()
        obra = st.text_input("Obra", placeholder="Nome ou referência da obra")
        equipe = st.text_input("Equipe", placeholder="Nomes ou identificação da equipe")
        inicio = st.time_input("Horário de início", value=datetime.now().replace(second=0, microsecond=0).time())
        termino = st.time_input("Horário de término", value=datetime.now().replace(second=0, microsecond=0).time())
    descricao = st.text_area("Descrição do serviço", placeholder="Descreva o serviço executado, condições encontradas e resultado...", height=110)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Materiais")
    st.caption("Adicione os itens utilizados, removidos e remanejados.")
    utilizado = material_editor("Material utilizado", "utilizado")
    removido = material_editor("Material removido", "removido")
    remanejado = material_editor("Material remanejado", "remanejado")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Fotos do serviço")
    st.caption("Selecione até 9 fotos antes e até 9 fotos depois. O PDF manterá duas grades 3×3 na mesma página.")
    before_files = st.file_uploader("Fotos antes", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="before_files")
    before = uploaded_photo_grid(before_files, "Fotos antes")
    after_files = st.file_uploader("Fotos depois", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="after_files")
    after = uploaded_photo_grid(after_files, "Fotos depois")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Logomarca")
    st.caption("Opcional. A logomarca será inserida no cabeçalho do PDF.")
    logo_file = st.file_uploader(
        "Enviar logomarca",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=False,
        key="logo_file",
    )
    if logo_file:
        st.image(logo_file, caption="Prévia da logomarca", width=180)
    st.markdown('</div>', unsafe_allow_html=True)

    submitted = st.form_submit_button("Gerar relatório em PDF", type="primary", use_container_width=True)

if submitted:
    data_iso = data_servico.strftime("%Y-%m-%d")
    data_br = data_servico.strftime("%d/%m/%Y")
    report_data = {
        "empresa": empresa,
        "data_iso": data_iso,
        "data_br": data_br,
        "municipio": municipio,
        "endereco": endereco,
        "descricao": descricao,
        "obra": obra,
        "veiculo": veiculo,
        "inicio": inicio.strftime("%H:%M"),
        "termino": termino.strftime("%H:%M"),
        "equipe": equipe,
        "ordem": st.session_state.ordem,
    }
    with st.spinner("Gerando PDF..."):
        pdf_bytes = build_pdf(
            report_data,
            {"utilizado": utilizado, "removido": removido, "remanejado": remanejado},
            before,
            after,
            logo_file,
        )

    file_name = f"Relatorio_{clean_filename(data_iso)}_{clean_filename(st.session_state.ordem)}.pdf"
    st.success(f"PDF pronto: {file_name}")
    st.download_button(
        "Baixar relatório em PDF",
        data=pdf_bytes,
        file_name=file_name,
        mime="application/pdf",
        use_container_width=True,
    )

    if st.button("Criar nova ordem de serviço"):
        st.session_state.ordem = next_order_number()
        st.rerun()

st.divider()
st.caption("Dica: no Streamlit Community Cloud, mantenha este app.py e o requirements.txt no mesmo repositório do GitHub.")
