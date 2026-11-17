"""Previas vetoriais e PNG com transparencia real fora das etiquetas."""

from __future__ import annotations

import base64
import html
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pymupdf

from tspl_pdf import Conversion, _label_regions, _lote_guide
from perfil import dots_per_mm


def _svg(page, width_mm, height_mm, clip=None):
    root = ET.fromstring(page.get_svg_image(text_as_path=True))
    box = clip or page.rect
    root.set("viewBox", f"{box.x0} {box.y0} {box.width} {box.height}")
    root.set("width", f"{width_mm}mm")
    root.set("height", f"{height_mm}mm")
    return ET.tostring(root, encoding="unicode")


def _image(svg):
    data = base64.b64encode(svg.encode()).decode("ascii")
    width = float(ET.fromstring(svg).get("width").removesuffix("mm"))
    return f'<img data-mm="{width}" style="width:{width}mm" alt="Etiqueta branca com contorno e fundo transparente" src="data:image/svg+xml;base64,' + data + '">'


def render_previews(conversion: Conversion, pdf_path: Path, *, warnings=None):
    if not conversion.labels:
        return {}
    groups = []
    individual_pdf = pdf_path.with_stem(pdf_path.stem + "_individuais")
    blocks = []
    mm = 72 / 25.4
    with pymupdf.open(str(pdf_path)) as doc, pymupdf.open() as individuals:
        for index, (page, label) in enumerate(zip(doc, conversion.labels), 1):
            prefix = pdf_path.with_name(f"{pdf_path.stem}_p{index}")
            svg = _svg(page, label.width_mm, label.height_mm)
            svg_path = prefix.with_suffix(".svg")
            svg_path.write_text(svg, encoding="utf-8")
            # Limita a memoria para rolos de dimensoes maiores.
            area = label.width_mm * label.height_mm / 25.4 ** 2
            dpi = max(36, min(600, int(math.sqrt(20_000_000 / area))))
            png_path = prefix.with_suffix(".png")
            page.get_pixmap(dpi=dpi, alpha=True).save(str(png_path))
            labels = []
            single_blocks = []
            for column, (x, width) in enumerate(_label_regions(label), 1):
                clip = pymupdf.Rect(x * mm, 0, (x + width) * mm, page.rect.height)
                single_svg = _svg(page, width, label.height_mm, clip)
                stem = prefix.with_name(f"{prefix.stem}_e{column}")
                single_svg_path = stem.with_suffix(".svg")
                single_png_path = stem.with_suffix(".png")
                single_svg_path.write_text(single_svg, encoding="utf-8")
                page.get_pixmap(dpi=dpi, alpha=True, clip=clip).save(str(single_png_path))
                target = individuals.new_page(width=clip.width, height=clip.height)
                target.show_pdf_page(target.rect, doc, index - 1, clip=clip)
                labels.append({"svg": single_svg_path.name, "png": single_png_path.name})
                single_blocks.append('<figure>' + _image(single_svg) + f'<figcaption>Etiqueta {column} · {width:g} × {label.height_mm:g} mm · <a download href="{single_png_path.name}">PNG</a> <a download href="{single_svg_path.name}">SVG</a></figcaption></figure>')
            groups.append({"svg": svg_path.name, "png": png_path.name, "etiquetas": labels})
            blocks.append(f'<section><h2>Faixa {index} · {label.width_mm:g} × {label.height_mm:g} mm</h2><div class="pair">' + _image(svg) + '</div><div class="single">' + ''.join(single_blocks) + '</div></section>')
        individuals.save(str(individual_pdf), deflate=True)
    viewer = pdf_path.with_suffix(".html")
    template = Path(__file__).with_name("previa.html").read_text(encoding="utf-8")
    template = template.replace("{{ETIQUETAS}}", ''.join(blocks))
    template = template.replace("{{PDF}}", html.escape(pdf_path.name, quote=True))
    template = template.replace("{{PDF_INDIVIDUAIS}}", html.escape(individual_pdf.name, quote=True))
    profile = conversion.profile
    status = (f"Alinhamento calibrado: X={profile.offset_x_mm:g} mm, Y={profile.offset_y_mm:g} mm."
              if profile.calibrated else "Alinhamento físico não medido: a prévia não confirma a posição mecânica da impressora.")
    fidelity = '<div class="fidelity"><strong>' + html.escape(profile.model + " · " + status) + '</strong><p>'
    fidelity += html.escape(f"{dots_per_mm(conversion.labels[0].dpi):g} dots/mm. Células das fontes TSPL com largura fixa; desenho dos glifos substituto. Orientação de leitura: DIRECTION 1.") + '</p>'
    if any(_lote_guide(label) is not None for label in conversion.labels):
        fidelity += '<p>A linha vermelha marca X=70 (8,75 mm), referência do lote aprovado. É uma margem de segurança, não uma medição do limite mecânico.</p>'
    problems = warnings if warnings is not None else conversion.warnings
    if problems:
        fidelity += '<ul class="warning">' + ''.join('<li>' + html.escape(item) + '</li>' for item in problems) + '</ul>'
    fidelity += '</div>'
    template = template.replace("{{FIDELIDADE}}", fidelity)
    viewer.write_text(template, encoding="utf-8")
    return {"visualizacao": viewer.name, "pdf_individuais": individual_pdf.name, "previas": groups}
