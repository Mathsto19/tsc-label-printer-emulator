"""Conversor experimental de trabalhos RAW TSPL/TSPL2 para PDF em tamanho real.

Não é um interpretador completo do firmware TSC. Os comandos desconhecidos são
registrados como avisos, nunca apresentados como se tivessem sido impressos.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from reportlab.graphics.barcode import code128, code39, eanbc
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfdoc import PDFArray, PDFName
from reportlab.pdfgen.canvas import Canvas

from perfil import PrinterProfile, dots_per_mm


# Dimensoes de celula do manual TSPL/TSPL2 (largura x altura, em dots).
BUILTIN_CELLS = {
    "1": (8, 12), "2": (12, 20), "3": (16, 24), "4": (24, 32),
    "5": (32, 48), "6": (14, 19), "7": (21, 27), "8": (14, 25),
}


IGNORE_COMMANDS = {
    "GAP", "BLINE", "SPEED", "DENSITY", "COUNTRY",
    "OFFSET", "HOME", "FEED", "BACKFEED", "LIMITFEED", "GAPDETECT",
    "BLINEDETECT", "AUTODETECT", "SELFTEST", "REFERENCE", "DIRECTION",
    "SIZE", "CLS", "PRINT", "EOP", "BEEP", "SOUND", "DELAY", "CUT",
}
DRAW_COMMANDS = {"TEXT", "BARCODE", "BAR", "BOX", "BITMAP", "QRCODE", "CIRCLE", "REVERSE"}


@dataclass
class Label:
    width_mm: float
    height_mm: float
    dpi: int
    commands: list[tuple[str, list[str], bytes | None]] = field(default_factory=list)
    reference: tuple[int, int] = (0, 0)
    direction: int = 1
    shift: tuple[int, int] = (0, 0)
    mirror: bool = False
    codepage: str = "USA"


@dataclass
class PrinterState:
    width_mm: float = 103.0
    height_mm: float = 30.0
    reference: tuple[int, int] = (0, 0)
    direction: int = 1
    shift: tuple[int, int] = (0, 0)
    mirror: bool = False
    codepage: str = "USA"


@dataclass
class Conversion:
    labels: list[Label] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    profile: PrinterProfile = field(default_factory=PrinterProfile)


def fields(s: str) -> list[str]:
    try:
        return next(csv.reader([s], skipinitialspace=True))
    except (csv.Error, StopIteration):
        return [part.strip().strip('"') for part in s.split(",")]


def integer(value: str, default: int = 0) -> int:
    try:
        return int(float(value.strip()))
    except (ValueError, AttributeError):
        return default


def size_mm(value: str, dpi: int) -> float:
    """TSPL: dimensão sem unidade é em polegadas, com 'mm' é milímetros."""
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*(mm|inch|in|dot|dots)?\s*$", value, re.I)
    if not match:
        raise ValueError(f"Medida não reconhecida: {value!r}")
    v = float(match.group(1))
    unit = (match.group(2) or "in").lower()
    return v if unit == "mm" else (v * 25.4 if unit in ("in", "inch") else v / dots_per_mm(dpi))


def _encoding(codepage: str) -> str:
    value = codepage.upper().strip('" ')
    if value in ("UTF-8", "UTF8"):
        return "utf-8-sig"
    if value.isdigit():
        return "iso" + value if value.startswith("8859-") else "cp" + value
    if value.startswith("8859-"):
        return "iso" + value
    return "cp437"


def _lines_with_bitmaps(raw: bytes, codepage: str = "USA"):
    """Lê BITMAP como binário de comprimento exato (pode conter CR/LF)."""
    offset = 0
    binary_header = re.compile(
        rb"[ \t]*BITMAP[ \t]+(-?\d+)[ \t]*,[ \t]*(-?\d+)[ \t]*,[ \t]*(\d+)[ \t]*,[ \t]*(\d+)[ \t]*,[ \t]*(\d+)[ \t]*,",
        re.I,
    )
    while offset < len(raw):
        match = binary_header.match(raw, offset)
        if match:
            x, y, bytes_per_row, height, mode = [int(v) for v in match.groups()]
            length = bytes_per_row * height
            if length > 20_000_000:
                raise ValueError("BITMAP maior que o limite de 20 MB")
            end = match.end() + length
            if end > len(raw):
                raise ValueError("BITMAP incompleto: quantidade de bytes insuficiente")
            yield ("BITMAP", [str(x), str(y), str(bytes_per_row), str(height), str(mode)], raw[match.end():end])
            offset = end
            while offset < len(raw) and raw[offset:offset + 1] in (b"\r", b"\n"):
                offset += 1
            continue
        next_lf = raw.find(b"\n", offset)
        if next_lf < 0:
            next_lf = len(raw)
        line = raw[offset:next_lf].strip(b"\x00\r\t ")
        offset = next_lf + 1
        if not line:
            continue
        try:
            decoded = line.decode(_encoding(codepage), errors="replace")
        except LookupError:
            decoded = line.decode("ascii", errors="replace")
        parts = decoded.split(None, 1)
        command = parts[0]
        args = fields(parts[1]) if len(parts) > 1 else []
        if command.upper() == "CODEPAGE" and args:
            codepage = args[0]
        yield (command.upper(), args, None)


def interpret(raw: bytes, dpi: int = 203, max_pages: int = 200, *,
              state: PrinterState | None = None, profile: PrinterProfile | None = None) -> Conversion:
    result = Conversion(profile=profile or PrinterProfile())
    state = state if state is not None else PrinterState()
    width_mm, height_mm = state.width_mm, state.height_mm
    current: list[tuple[str, list[str], bytes | None]] = []
    reference, direction = state.reference, state.direction
    shift, mirror, codepage = state.shift, state.mirror, state.codepage
    seen_print = False
    unsupported: set[str] = set()
    try:
        commands = _lines_with_bitmaps(raw, codepage)
        for command, args, binary in commands:
            if command == "SIZE":
                try:
                    width_mm, height_mm = size_mm(args[0], dpi), size_mm(args[1], dpi)
                    if not (1 <= width_mm <= 500 and 1 <= height_mm <= 1000):
                        raise ValueError("dimensão fora de faixa")
                except (IndexError, ValueError) as e:
                    result.warnings.append(f"SIZE inválido: {e}")
            elif command == "DIRECTION":
                direction = integer(args[0], 1) if args else 1
                mirror = bool(integer(args[1])) if len(args) > 1 else False
            elif command == "REFERENCE":
                reference = (integer(args[0]), integer(args[1])) if len(args) >= 2 else (0, 0)
            elif command == "SHIFT":
                shift = ((integer(args[0]), integer(args[1])) if len(args) >= 2
                         else (shift[0], integer(args[0]))) if args else (0, 0)
            elif command == "CODEPAGE" and args:
                codepage = args[0].upper()
                try:
                    "".encode(_encoding(codepage))
                except LookupError:
                    result.warnings.append(f"CODEPAGE {codepage} não suportada; caracteres podem divergir.")
            elif command == "CLS":
                current.clear()
            elif command == "PRINT":
                seen_print = True
                sets = max(1, integer(args[0], 1)) if args else 1
                copies = max(1, integer(args[1], 1)) if len(args) > 1 else 1
                count = sets * copies
                remaining = max_pages - len(result.labels)
                if count > remaining:
                    result.warnings.append(f"PRINT solicitou {count} páginas; limite de segurança: {max_pages}")
                for _ in range(min(count, max(remaining, 0))):
                    result.labels.append(Label(width_mm, height_mm, dpi, list(current), reference,
                                               direction, shift, mirror, codepage))
            elif command in DRAW_COMMANDS:
                current.append((command, args, binary))
            elif command in IGNORE_COMMANDS:
                pass
            else:
                unsupported.add(command[:70])
    except ValueError as e:
        result.warnings.append(str(e))
    if unsupported:
        result.warnings.append("Comandos não implementados: " + ", ".join(sorted(unsupported)))
    if not seen_print:
        result.warnings.append("Nenhum comando PRINT encontrado: trabalho RAW salvo, sem PDF")
    state.width_mm, state.height_mm = width_mm, height_mm
    state.reference, state.direction = reference, direction
    state.shift, state.mirror, state.codepage = shift, mirror, codepage
    return result


@lru_cache(maxsize=1)
def _font() -> str:
    for p in (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ):
        if p.is_file():
            try:
                pdfmetrics.registerFont(TTFont("SimulatorSans", str(p)))
                return "SimulatorSans"
            except Exception:
                pass
    return "Helvetica"


@lru_cache(maxsize=1)
def _mono_font() -> str:
    for path in (Path("C:/Windows/Fonts/lucon.ttf"), Path("C:/Windows/Fonts/consola.ttf"),
                 Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
                 Path("/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf")):
        if path.is_file():
            try:
                pdfmetrics.registerFont(TTFont("SimulatorMono", str(path)))
                return "SimulatorMono"
            except Exception:
                continue
    return "Courier"


def _resident_text(args: list[str], codepage: str, errors: set[str]) -> str:
    text = args[-1].replace('\\["]', '"')
    if "\ufffd" in text:
        errors.add("Bytes incompatíveis com CODEPAGE; texto contém caracteres inválidos.")
    # Não inventar glifos que só existem na fonte do Windows. No caso reportado,
    # os acentos de TEXT com fonte residente + UTF-8 saem vazios na TTP-245C.
    if args[2].strip() in BUILTIN_CELLS and codepage in ("UTF-8", "UTF8"):
        if any(ord(ch) > 126 for ch in text):
            errors.add("Fonte residente com UTF-8: caracteres não ASCII mostrados como células vazias; confirme a fonte/codepage na TSC.")
            text = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in text)
    return text


def _draw_text(c: Canvas, args: list[str], font: str, errors: set[str], *, dpi: int = 203, codepage: str = "USA"):
    if len(args) < 7:
        errors.add("TEXT com argumentos insuficientes")
        return
    x, y = integer(args[0]), integer(args[1])
    f = args[2].strip().upper()
    rotation = integer(args[3])
    xm, ym = max(1, integer(args[4], 1)), max(1, integer(args[5], 1))
    text = _resident_text(args, codepage, errors)
    align = integer(args[6]) if len(args) >= 8 else 1
    if f in BUILTIN_CELLS:
        # Cada caractere avança exatamente a largura TSPL, inclusive I, W e espaço.
        # A fonte monoespaçada é só o desenho substituto; não define as células.
        resident_font = _mono_font()
        cell_w, cell_h = BUILTIN_CELLS[f]
        width = len(text) * cell_w * min(10, xm)
        height = cell_h * min(10, ym)
        ascent, descent = pdfmetrics.getAscentDescent(resident_font, 1)
        size = height / (ascent - descent)
        horizontal = cell_w * min(10, xm) / pdfmetrics.stringWidth("M", resident_font, size)
        shift = width / 2 if align == 2 else width if align == 3 else 0
        c.saveState()
        c.translate(x, y)
        c.rotate(rotation)
        c.translate(-shift, ascent * size)
        c.scale(horizontal, -1)
        resident_text = c.beginText()
        resident_text.setFont(resident_font, size)
        for index, character in enumerate(text):
            # O PDF arredonda larguras TTF. Ancorar cada célula evita acumular
            # esse erro ao longo de nomes e endereços extensos.
            resident_text.setTextOrigin(index * cell_w * min(10, xm) / horizontal, 0)
            resident_text.textOut(character)
        c.drawText(resident_text)
        c.restoreState()
        return
    if f == "0":
        # TSPL font 0 usa pontos, não dots nem multiplicadores de bitmap.
        size = min(250, ym) * dots_per_mm(dpi) * 25.4 / 72
        errors.add("Fonte 0: desenho substituto; a fonte CG Triumvirate da TSC não está instalada no emulador.")
    elif f.endswith((".TTF", ".FNT", ".EFT")):
        errors.add(f"Fonte {f} não fornecida ao emulador; TEXT não desenhado em uma fonte arbitrária.")
        return
    else:
        size = min(250, max(8, 12 * ym))
        errors.add(f"Fonte {f} aproximada")
    if len(args) >= 8 and args[6] in ("1", "2", "3"):
        align = integer(args[6])
    else:
        align = 1
    horizontal = xm / ym if f == "0" else 1
    width = pdfmetrics.stringWidth(text, font, size) * horizontal
    shift = (width / 2 if align == 2 else width if align == 3 else 0)
    c.saveState()
    c.translate(x, y)
    if rotation:
        c.rotate(rotation)
    c.translate(-shift, size * .85)
    c.scale(horizontal, -1)
    c.setFont(font, size)
    c.drawString(0, 0, text)
    c.restoreState()


def _draw_barcode(c: Canvas, args: list[str], font: str, errors: set[str]):
    if len(args) < 9:
        errors.add("BARCODE com argumentos insuficientes")
        return
    x, y = integer(args[0]), integer(args[1])
    kind = args[2].strip().upper()
    height = max(1, integer(args[3], 90))
    human = integer(args[4])
    rotation = integer(args[5])
    narrow = max(.5, float(integer(args[6], 2)))
    wide = max(narrow, float(integer(args[7], 2)))
    value = args[-1]
    try:
        if kind in ("128", "CODE128"):
            barcode = code128.Code128(value, barWidth=narrow, barHeight=height, quiet=False)
        elif kind in ("39", "39C", "CODE39"):
            barcode = code39.Standard39(value, barWidth=narrow, barHeight=height, ratio=wide / narrow, quiet=False, checksum=(kind == "39C"))
        elif kind in ("EAN13", "EAN-13"):
            barcode = eanbc.Ean13BarcodeWidget(value[:12])
            barcode.barWidth = narrow
            barcode.barHeight = height
            barcode.humanReadable = bool(human)
        else:
            errors.add(f"Tipo de código de barras {kind} não implementado")
            return
        c.saveState()
        c.translate(x, y)
        if rotation:
            c.rotate(rotation)
        c.translate(0, height)
        c.scale(1, -1)
        if kind in ("EAN13", "EAN-13"):
            from reportlab.graphics.shapes import Drawing
            from reportlab.graphics import renderPDF
            bounds = barcode.getBounds()
            drawing = Drawing(bounds[2], bounds[3])
            drawing.add(barcode)
            renderPDF.draw(drawing, c, 0, 0)
        else:
            barcode.drawOn(c, 0, 0)
        c.restoreState()
        if human and kind not in ("EAN13", "EAN-13"):
            # O firmware pode escolher distância/fonte próprias para o HRI.
            c.saveState()
            c.translate(x, y + height + 14)
            c.scale(1, -1)
            c.setFont(font, 11)
            c.drawString(0, 0, value)
            c.restoreState()
    except Exception as e:
        errors.add(f"Não foi possível desenhar BARCODE {kind}: {type(e).__name__}")


def _draw_bitmap(c: Canvas, args: list[str], raw: bytes | None, errors: set[str]):
    if raw is None:
        errors.add("BITMAP sem payload binário")
        return
    try:
        from PIL import Image, ImageOps
        x, y, width_bytes, height, mode = (integer(s) for s in args[:5])
        img = Image.frombytes("1", (width_bytes * 8, height), raw)
        img = ImageOps.invert(img.convert("L"))
        if mode != 0:
            errors.add(f"BITMAP modo {mode}: composição OR/XOR ainda não emulada")
        c.saveState()
        c.translate(x, y + height)
        c.scale(1, -1)
        c.drawImage(ImageReader(img), 0, 0, width=width_bytes * 8, height=height, mask="auto")
        c.restoreState()
    except Exception as e:
        errors.add(f"BITMAP não renderizado: {type(e).__name__}: {e}")


def _draw_qrcode(c: Canvas, args: list[str], errors: set[str]):
    if len(args) < 7:
        errors.add("QRCODE com argumentos insuficientes")
        return
    try:
        import qrcode
        x, y = integer(args[0]), integer(args[1])
        cell = max(1, integer(args[3], 4))
        rotation = integer(args[5])
        value = args[-1]
        obj = qrcode.QRCode(border=0, box_size=cell)
        obj.add_data(value)
        obj.make(fit=True)
        im = obj.make_image(fill_color="black", back_color="white").convert("RGB")
        c.saveState()
        c.translate(x, y)
        if rotation:
            c.rotate(rotation)
        c.translate(0, im.height)
        c.scale(1, -1)
        c.drawImage(ImageReader(im), 0, 0, im.width, im.height)
        c.restoreState()
    except ImportError:
        errors.add("QRCODE requer a dependência qrcode")
    except Exception as e:
        errors.add(f"QRCODE não renderizado: {type(e).__name__}")


def _label_regions(label: Label) -> list[tuple[float, float]]:
    # O layout IJC de 103 x 30 mm usa duas etiquetas de 50 mm e vao de 3 mm.
    # Outros formatos (inclusive 103 x 40 mm) sao uma unica etiqueta.
    if abs(label.width_mm - 103) < .01 and abs(label.height_mm - 30) < .01:
        return [(0, 50), (53, 50)]
    return [(0, label.width_mm)]


def _draw_label_stock(c: Canvas, label: Label):
    """Papel e recorte discretos, somente na versao de visualizacao."""
    mm = 72 / 25.4
    stroke = .4
    inset = stroke / 2
    c.saveState()
    c.setStrokeColorRGB(.2, .2, .2)
    c.setFillColorRGB(1, 1, 1)
    c.setLineWidth(stroke)
    for x, width in _label_regions(label):
        radius = min(1, width / 2, label.height_mm / 2) * mm
        c.roundRect(x * mm + inset, inset, width * mm - stroke,
                    label.height_mm * mm - stroke, max(0, radius - inset),
                    stroke=1, fill=1)
    c.restoreState()


def _rotated_bounds(x, y, width, height, rotation):
    angle = math.radians(rotation)
    ca, sa = math.cos(angle), math.sin(angle)
    points = [(x + px * ca - py * sa, y + px * sa + py * ca)
              for px, py in ((0, 0), (width, 0), (0, height), (width, height))]
    return min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)


def _command_bounds(name, a, binary, label, font):
    if name == "TEXT" and len(a) >= 7:
        f = a[2].strip().upper()
        xm, ym = max(1, integer(a[4], 1)), max(1, integer(a[5], 1))
        if f in BUILTIN_CELLS:
            cw, ch = BUILTIN_CELLS[f]
            width, height = len(a[-1]) * cw * min(10, xm), ch * min(10, ym)
        elif f == "0":
            height = ym * dots_per_mm(label.dpi) * 25.4 / 72
            width = pdfmetrics.stringWidth(a[-1], font, height) * xm / ym
        else:
            return None
        align = integer(a[6]) if len(a) >= 8 else 1
        dx = width / 2 if align == 2 else width if align == 3 else 0
        bounds = _rotated_bounds(0, 0, width, height, integer(a[3]))
        # Alinhamento é deslocamento ao longo do eixo local do texto.
        angle = math.radians(integer(a[3]))
        return tuple(v + (integer(a[0]) - dx * math.cos(angle) if i % 2 == 0
                          else integer(a[1]) - dx * math.sin(angle)) for i, v in enumerate(bounds))
    if name == "BARCODE" and len(a) >= 9:
        if a[2].upper() in ("128", "CODE128"):
            bar = code128.Code128(a[-1], barWidth=max(.5, integer(a[6], 2)), barHeight=max(1, integer(a[3])), quiet=False)
            return _rotated_bounds(integer(a[0]), integer(a[1]), bar.width,
                                   max(1, integer(a[3])) + (20 if integer(a[4]) else 0), integer(a[5]))
        return None
    if name in ("BAR", "BITMAP", "REVERSE") and len(a) >= 4:
        x, y, width, height = (integer(v) for v in a[:4])
        return x, y, x + width * (8 if name == "BITMAP" else 1), y + height
    if name == "BOX" and len(a) >= 5:
        return tuple(integer(v) for v in a[:4])
    return None


def _physical_bounds(bounds, label, profile):
    dpm = dots_per_mm(label.dpi)
    width, height = label.width_mm * dpm, label.height_mm * dpm
    sx, sy = label.reference
    points = []
    for x, y in ((bounds[0], bounds[1]), (bounds[2], bounds[3])):
        x, y = x + sx, y + sy
        # As prévias são orientadas para leitura em DIRECTION 1.
        if label.direction == 0:
            x, y = width - x, height - y
        if label.mirror:
            x = width - x
        points.append(((x + label.shift[0]) / dpm + profile.offset_x_mm,
                       (y + label.shift[1]) / dpm + profile.offset_y_mm))
    return min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)


def _lote_guide(label: Label) -> float | None:
    # Margem de validação tirada do lote aprovado, não um limite mecânico inferido.
    if label.dpi == 203 and abs(label.width_mm - 103) < .01 and abs(label.height_mm - 40) < .01:
        return 70 / 8
    return None


def _inspect_label(label, profile, font, page):
    issues = set()
    for name, args, binary in label.commands:
        try:
            bounds = _command_bounds(name, args, binary, label, font)
            if bounds is None:
                continue
            left, top, right, bottom = _physical_bounds(bounds, label, profile)
            prefix = f"Página {page}: {name} em X={args[0]}, Y={args[1]}"
            if left < -.001 or top < -.001 or right > min(label.width_mm, 108) + .001 or bottom > label.height_mm + .001:
                issues.add(prefix + ": caixa TSPL ultrapassa o papel/cabeça de impressão; a região excedente é recortada.")
            if not any(left >= start - .001 and right <= start + width + .001
                       for start, width in _label_regions(label)):
                issues.add(prefix + ": caixa TSPL atravessa a borda ou o vão entre etiquetas.")
            guide = _lote_guide(label)
            if guide is not None and left < guide - .001:
                issues.add(prefix + ": entra na margem de segurança do lote aprovado (X=70, 8,75 mm); risco de corte na TSC.")
        except (ValueError, IndexError, TypeError):
            issues.add(f"Página {page}: não foi possível validar os limites de {name}.")
    return issues


def _draw_guide(c, label):
    guide = _lote_guide(label)
    if guide is None:
        return
    mm = 72 / 25.4
    c.saveState()
    c.setStrokeColorRGB(.8, .18, .1)
    c.setLineWidth(.5)
    c.setDash(2, 2)
    c.line(guide * mm, 0, guide * mm, label.height_mm * mm)
    c.restoreState()


def render_pdf(conversion: Conversion, output: Path, *, show_stock: bool = True) -> list[str]:
    if not conversion.labels:
        return list(conversion.warnings)
    errors = set(conversion.warnings)
    font = _font()
    output.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(output), pagesize=(1, 1), pageCompression=1)
    # O papel ja segue SIZE; nao deixar o leitor ampliar uma etiqueta pequena
    # para preencher a janela nem sugerir ajuste ao papel na impressao.
    c.setViewerPreference("PrintScaling", "None")
    c.setTitle("TSC DA300 - impressão virtual TSPL")
    for index, label in enumerate(conversion.labels):
        w_pt = label.width_mm * 72 / 25.4
        h_pt = label.height_mm * 72 / 25.4
        dots_to_pt = 72 / (dots_per_mm(label.dpi) * 25.4)
        c.setPageSize((w_pt, h_pt))
        if show_stock:
            _draw_label_stock(c, label)
        if index == 0:
            # ReportLab nao expoe uma API de Canvas para o zoom de abertura.
            c._doc.Catalog.OpenAction = PDFArray([
                c._doc.thisPageRef(), PDFName("XYZ"), 0, h_pt, 1,
            ])
        c.saveState()
        # Cortar conteúdo fora das etiquetas, inclusive no vão de 3 mm.
        # O formato/canto físico é do papel; o TSPL não informa seu raio.
        clip = c.beginPath()
        for start, width in _label_regions(label):
            end = min(start + width, 108)
            if end > start:
                clip.rect(start * 72 / 25.4, 0, (end - start) * 72 / 25.4, h_pt)
        c.clipPath(clip, stroke=0, fill=0)
        c.translate(0, h_pt)
        c.scale(dots_to_pt, -dots_to_pt)
        dpm = dots_per_mm(label.dpi)
        c.translate(conversion.profile.offset_x_mm * dpm, conversion.profile.offset_y_mm * dpm)
        # SHIFT atua na saída física, independentemente da orientação de leitura.
        c.translate(*label.shift)
        if label.mirror:
            c.translate(label.width_mm * dpm, 0)
            c.scale(-1, 1)
        if label.direction == 0:
            c.translate(label.width_mm * dpm, label.height_mm * dpm)
            c.scale(-1, -1)
        c.setFillColorRGB(0, 0, 0)
        c.setStrokeColorRGB(0, 0, 0)
        c.translate(*label.reference)
        errors.update(_inspect_label(label, conversion.profile, font, index + 1))
        for name, a, binary in label.commands:
            try:
                if name == "TEXT":
                    _draw_text(c, a, font, errors, dpi=label.dpi, codepage=label.codepage)
                elif name == "BARCODE":
                    _draw_barcode(c, a, font, errors)
                elif name == "BITMAP":
                    _draw_bitmap(c, a, binary, errors)
                elif name == "QRCODE":
                    _draw_qrcode(c, a, errors)
                elif name == "BAR" and len(a) >= 4:
                    c.rect(integer(a[0]), integer(a[1]), integer(a[2]), integer(a[3]), fill=1, stroke=0)
                elif name == "BOX" and len(a) >= 5:
                    x, y, right, bottom, thick = (integer(v) for v in a[:5])
                    c.setLineWidth(max(1, thick))
                    c.rect(x, y, right - x, bottom - y, stroke=1, fill=0)
                elif name == "CIRCLE" and len(a) >= 4:
                    x, y, radius, thick = (integer(v) for v in a[:4])
                    c.setLineWidth(max(1, thick))
                    c.circle(x, y, radius, stroke=1, fill=0)
                elif name == "REVERSE":
                    errors.add("REVERSE ainda não emulado")
            except Exception as e:
                errors.add(f"{name} falhou: {type(e).__name__}: {str(e)[:100]}")
        c.restoreState()
        if show_stock:
            _draw_guide(c, label)
        c.showPage()
    c.save()
    return sorted(errors)


def convert(raw: bytes, output: Path, dpi: int = 203, *, show_stock: bool = True,
            profile: PrinterProfile | None = None) -> tuple[int, list[str]]:
    converted = interpret(raw, dpi=dpi, profile=profile)
    warnings = render_pdf(converted, output, show_stock=show_stock)
    return len(converted.labels), warnings
