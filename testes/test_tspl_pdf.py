import tempfile
import json
import socket
import threading
import time
import urllib.request
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

import simulador
import pymupdf
from perfil import PrinterProfile, dots_per_mm
from tspl_pdf import PrinterState, _draw_text, convert, interpret, render_pdf, size_mm
from previas import render_previews
from PIL import Image


class TestesDeConversao(unittest.TestCase):
    def test_texto_e_codigo_de_barras_permanecem_vetoriais(self):
        raw = b'SIZE 50 mm,30 mm\nCLS\nTEXT 20,20,"2",0,1,1,"TESTE 123"\nBARCODE 20,50,"128",60,0,0,2,2,"123456"\nPRINT 1\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vetor.pdf"
            convert(raw, path, dpi=203)
            page = PdfReader(path).pages[0]
            self.assertTrue(page["/Resources"]["/Font"])
            self.assertNotIn("/XObject", page["/Resources"])

    def test_transparencia_real_e_etiquetas_individuais(self):
        raw = b'SIZE 103 mm,30 mm\nCLS\nPRINT 1\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "etiquetas.pdf"
            convert(raw, path, dpi=203)
            result = render_previews(interpret(raw, dpi=203), path)
            with Image.open(Path(tmp) / result["previas"][0]["png"]) as im:
                self.assertEqual(im.mode, "RGBA")
                self.assertEqual(im.getpixel((0, 0))[3], 0)
                self.assertEqual(im.getpixel((im.width // 2, im.height // 2))[3], 0)
                self.assertEqual(im.getpixel((im.width // 4, im.height // 2)), (255,255,255,255))
            pages = PdfReader(Path(tmp) / result["pdf_individuais"]).pages
            self.assertEqual(len(pages), 2)
            for page in pages:
                self.assertAlmostEqual(float(page.mediabox.width) * 25.4 / 72, 50, places=3)
                self.assertAlmostEqual(float(page.mediabox.height) * 25.4 / 72, 30, places=3)
            self.assertEqual(len(result["previas"][0]["etiquetas"]), 2)
            viewer = (Path(tmp) / result["visualizacao"]).read_text(encoding="utf-8")
            self.assertNotIn("{{", viewer)
            self.assertIn("data:image/svg+xml;base64,", viewer)

    def test_texto_rotacionado_preserva_ancora_e_multiplicadores(self):
        from unittest.mock import MagicMock
        canvas = MagicMock()
        errors = set()
        _draw_text(canvas, ["25", "60", "2", "90", "2", "3", "AB"], "Helvetica", errors)
        self.assertFalse(errors)
        canvas.translate.assert_any_call(25, 60)
        canvas.rotate.assert_called_once_with(90)
        canvas.drawImage.assert_not_called()
        canvas.drawText.assert_called_once()
        text = canvas.beginText.return_value
        self.assertEqual([call.args[0] for call in text.textOut.call_args_list], ["A", "B"])
        self.assertNotEqual(text.setFont.call_args[0][0], "Helvetica")

    def test_pdf_para_impressao_nao_inclui_papel_ou_recorte(self):
        raw = b'SIZE 103 mm,30 mm\nCLS\nPRINT 1\n'
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp) / "preview.pdf"
            clean = Path(tmp) / "clean.pdf"
            convert(raw, preview, dpi=203)
            convert(raw, clean, dpi=203, show_stock=False)
            preview_page = PdfReader(preview).pages[0]
            clean_page = PdfReader(clean).pages[0]
            self.assertIn(b" c\n", preview_page.get_contents().get_data())
            self.assertNotIn(b" c\n", clean_page.get_contents().get_data())
            # Caminhos retangulares de clipping são necessários também no PDF limpo.
            self.assertIn(b"W* n", clean_page.get_contents().get_data())
            self.assertEqual(clean_page.mediabox, preview_page.mediabox)

    def test_medidas_tspl(self):
        self.assertAlmostEqual(size_mm("103 mm", 203), 103)
        self.assertAlmostEqual(size_mm("4", 203), 101.6)

    def test_duas_etiquetas_na_mesma_pagina(self):
        raw = (Path(__file__).parents[1] / "exemplo_teste.prn").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "impresso.pdf"
            pages, warnings = convert(raw, pdf, dpi=203)
            self.assertEqual(pages, 1)
            self.assertEqual(warnings, [])
            reader = PdfReader(pdf)
            self.assertEqual(len(reader.pages), 1)
            self.assertAlmostEqual(float(reader.pages[0].mediabox.width), 103 * 72 / 25.4, places=3)
            self.assertAlmostEqual(float(reader.pages[0].mediabox.height), 30 * 72 / 25.4, places=3)

    def test_trabalhos_multiplas_paginas(self):
        raw = b'SIZE 50 mm,25 mm\nCLS\nTEXT 10,10,"2",0,1,1,"TESTE"\nPRINT 2,2\n'
        p = interpret(raw, dpi=203)
        self.assertEqual(len(p.labels), 4)
        self.assertFalse(p.warnings)

    def test_pdf_abre_em_100_porcento_e_imprime_sem_ajuste(self):
        raw = b'SIZE 50 mm,30 mm\nCLS\nBAR 0,0,400,240\nPRINT 1\n'
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "tamanho-real.pdf"
            convert(raw, pdf, dpi=203)
            reader = PdfReader(pdf)
            catalog = reader.trailer["/Root"]
            self.assertEqual(catalog["/ViewerPreferences"]["/PrintScaling"], "/None")
            destination = catalog["/OpenAction"]
            self.assertEqual(destination[1], "/XYZ")
            self.assertEqual(float(destination[4]), 1)
            self.assertEqual(destination[0].get_object(), reader.pages[0])
            self.assertAlmostEqual(float(reader.pages[0].mediabox.width) * 25.4 / 72, 50, places=3)
            self.assertAlmostEqual(float(reader.pages[0].mediabox.height) * 25.4 / 72, 30, places=3)

    def test_bitmap_binario_com_lf_dentro(self):
        # O byte 0x0a e parte da imagem; nao e delimitador de linha.
        raw = b'SIZE 30 mm,20 mm\nCLS\nBITMAP 0,0,1,2,0,\x0a\x80\r\nPRINT 1\n'
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "bitmap.pdf"
            pages, warnings = convert(raw, pdf, dpi=203)
            self.assertEqual(pages, 1)
            self.assertEqual(warnings, [])
            self.assertGreater(pdf.stat().st_size, 500)

    def test_formatos_ijc_preservam_papel_sem_somar_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            for width, height in [(103, 30), (103, 40), (88, 38), (80, 45), (100, 60)]:
                with self.subTest(width=width, height=height):
                    pdf = Path(tmp) / f"{width}x{height}.pdf"
                    raw = f'SIZE {width} mm,{height} mm\nGAP 3 mm,0 mm\nCLS\nPRINT 1\n'.encode()
                    convert(raw, pdf, dpi=203)
                    page = PdfReader(pdf).pages[0]
                    self.assertAlmostEqual(float(page.mediabox.width) * 25.4 / 72, width, places=3)
                    self.assertAlmostEqual(float(page.mediabox.height) * 25.4 / 72, height, places=3)

    def test_comando_desconhecido_gera_aviso(self):
        p = interpret(b'CLS\nPUTBMP 10,10,"LOGO.BMP"\nPRINT 1\n')
        self.assertEqual(len(p.labels), 1)
        self.assertTrue(any("PUTBMP" in x for x in p.warnings))

    def test_sem_print_nao_cria_pdf(self):
        raw = b'CLS\nTEXT 1,2,"2",0,1,1,"X"\n'
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "sem.pdf"
            pages, warnings = convert(raw, pdf)
            self.assertEqual(pages, 0)
            self.assertFalse(pdf.exists())
            self.assertTrue(any("PRINT" in x for x in warnings))

    def test_recebimento_pela_porta_tcp_gera_arquivos(self):
        raw = (Path(__file__).parents[1] / "exemplo_teste.prn").read_bytes()
        with tempfile.TemporaryDirectory() as tmp, patch.object(simulador, "OUT", Path(tmp)):
            with simulador.RawServer(("127.0.0.1", 0), simulador.RawHandler, dpi=203) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                with socket.create_connection(server.server_address, timeout=5) as sock:
                    sock.sendall(raw)
                    sock.shutdown(socket.SHUT_WR)
                for _ in range(40):
                    if list(Path(tmp).glob("*.json")):
                        break
                    time.sleep(.05)
                server.shutdown()
                thread.join(timeout=2)
            self.assertEqual(len(list(Path(tmp).glob("*.prn"))), 1)
            self.assertEqual(len(list(Path(tmp).glob("*.pdf"))), 3)
            self.assertEqual(len(list(Path(tmp).glob("*.json"))), 1)
            info = json.loads(next(Path(tmp).glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(info["tamanhos_mm"], [[103, 30]])
            self.assertTrue((Path(tmp) / info["pdf_impressao"]).is_file())

    def test_larguras_reais_das_celulas_nao_dependem_das_letras(self):
        raw = b'SIZE 103 mm,30 mm\nCLS\nTEXT 40,20,"3",0,1,1,"IIII"\nTEXT 40,60,"3",0,1,1,"WWWW"\nPRINT 1\n'
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "metricas.pdf"
            convert(raw, pdf)
            with pymupdf.open(pdf) as doc:
                lines = [line for block in doc[0].get_text("rawdict")["blocks"] for line in block.get("lines", [])]
                for line in lines:
                    chars = line["spans"][0]["chars"]
                    self.assertEqual(len(chars), 4)
                    for left, right in zip(chars, chars[1:]):
                        self.assertAlmostEqual(right["origin"][0] - left["origin"][0], 2 * 72 / 25.4, places=3)
                self.assertAlmostEqual(lines[0]["bbox"][2] - lines[0]["bbox"][0], lines[1]["bbox"][2] - lines[1]["bbox"][0], places=3)

    def test_shift_reference_direction_e_espelho_afetam_o_pdf(self):
        raw = b'SIZE 50 mm,30 mm\nDIRECTION 1\nSHIFT 16,24\nREFERENCE 8,8\nCLS\nBAR 40,40,16,16\nPRINT 1\nDIRECTION 0,1\nPRINT 1\n'
        parsed = interpret(raw)
        self.assertEqual(parsed.labels[0].shift, (16, 24))
        self.assertTrue(parsed.labels[1].mirror)
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "posicoes.pdf"
            render_pdf(parsed, pdf, show_stock=False)
            with pymupdf.open(pdf) as doc:
                first, second = [page.get_drawings()[0]["rect"] for page in doc]
                mm = 72 / 25.4
                self.assertAlmostEqual(first.x0, 8 * mm, places=3)
                self.assertAlmostEqual(first.y0, 9 * mm, places=3)
                self.assertAlmostEqual(second.x0, first.x0, places=3)
                self.assertAlmostEqual(second.y0, 25 * mm, places=3)

    def test_configuracoes_persistem_e_cls_nao_remove_shift(self):
        state = PrinterState()
        interpret(b'SHIFT -20,5\nREFERENCE 8,9\nDIRECTION 0,1\nCODEPAGE 1252\nCLS\nPRINT 1\n', state=state)
        second = interpret(b'CLS\nTEXT 50,20,"2",0,1,1,"TESTE"\nPRINT 1\n', state=state)
        label = second.labels[0]
        self.assertEqual(label.shift, (-20, 5))
        self.assertEqual(label.reference, (8, 9))
        self.assertEqual(label.direction, 0)
        self.assertTrue(label.mirror)
        self.assertEqual(label.codepage, "1252")
        reset = interpret(b'SHIFT 0,0\nCLS\nPRINT 1\n', state=state)
        self.assertEqual(reset.labels[0].shift, (0, 0))

    def test_codepage_obedecida_e_utf8_residente_nao_ganha_glifos_do_windows(self):
        raw = 'CODEPAGE 1252\nCLS\nTEXT 80,20,"3",0,1,1,"SÃO"\nPRINT 1\n'.encode("cp1252")
        self.assertEqual(interpret(raw).labels[0].commands[0][1][-1], "SÃO")
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "utf8.pdf"
            raw = 'CODEPAGE UTF-8\nCLS\nTEXT 80,20,"3",0,1,1,"SÃO"\nPRINT 1\n'.encode("utf-8")
            _, warnings = convert(raw, pdf)
            self.assertTrue(any("células vazias" in warning for warning in warnings))
            self.assertEqual(PdfReader(pdf).pages[0].extract_text().strip(), "S O")

    def test_etiqueta_reportada_alerta_margem_e_acentos_e_corrigida_passa(self):
        original = 'SIZE 103 mm,40 mm\nDIRECTION 1\nSHIFT 0,0\nREFERENCE 0,0\nCODEPAGE UTF-8\nCLS\nTEXT 24,24,"3",0,1,1,"CÓDIGO: 6327"\nTEXT 24,64,"3",0,1,1,"INSTITUIÇÃO: ASSOCIACAO CASA FONTE DA VIDA"\nPRINT 1\n'
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "original.pdf"
            _, warnings = convert(original.encode("utf-8"), old)
            self.assertTrue(any("margem de segurança" in warning for warning in warnings))
            self.assertTrue(any("UTF-8" in warning for warning in warnings))
            fixed = original.replace("TEXT 24,", "TEXT 70,").replace("CÓDIGO", "CODIGO").replace("INSTITUIÇÃO", "INSTITUICAO")
            _, warnings = convert(fixed.encode("utf-8"), Path(tmp) / "corrigida.pdf")
            self.assertEqual(warnings, [])
            result = render_previews(interpret(original.encode("utf-8")), old, warnings=["Teste <corte>"])
            viewer = (Path(tmp) / result["visualizacao"]).read_text(encoding="utf-8")
            self.assertIn("não medido", viewer)
            self.assertIn("Teste &lt;corte&gt;", viewer)
            self.assertNotIn("{{", viewer)

    def test_recorte_real_no_vao_e_aviso_de_corte_fora_do_papel(self):
        raw = b'SIZE 103 mm,30 mm\nCLS\nBAR -8,0,840,300\nPRINT 1\n'
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "cortado.pdf"
            _, warnings = convert(raw, pdf)
            self.assertTrue(any("caixa TSPL ultrapassa" in warning for warning in warnings))
            with pymupdf.open(pdf) as doc:
                pix = doc[0].get_pixmap(dpi=203, alpha=True)
                gap_x = round(51.5 * 203 / 25.4)
                self.assertEqual(pix.pixel(gap_x, pix.height // 2)[3], 0)
                self.assertGreater(pix.pixel(100, pix.height // 2)[3], 0)

    def test_calibracao_aplica_desvio_sem_alterar_comandos(self):
        raw = b'SIZE 50 mm,30 mm\nCLS\nBAR 40,40,16,16\nPRINT 1\n'
        parsed = interpret(raw, profile=PrinterProfile(offset_x_mm=-2, offset_y_mm=1, calibrated=True))
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "calibrado.pdf"
            render_pdf(parsed, pdf, show_stock=False)
            with pymupdf.open(pdf) as doc:
                rect = doc[0].get_drawings()[0]["rect"]
                self.assertAlmostEqual(rect.x0, 3 * 72 / 25.4, places=3)
                self.assertAlmostEqual(rect.y0, 6 * 72 / 25.4, places=3)
        self.assertEqual(parsed.labels[0].commands[0][1][0], "40")
        self.assertEqual(dots_per_mm(203), 8)
        self.assertEqual(dots_per_mm(300), 12)
        for invalid in (float("nan"), 30, True, "1"):
            with self.assertRaises(ValueError):
                PrinterProfile.from_dict({"offset_x_mm": invalid})

    def test_reprocessamento_http_preserva_captura_e_grava_novo_perfil(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(simulador, "OUT", Path(tmp)), patch.object(simulador, "CONFIG", Path(tmp) / "perfil.json"):
            raw = b'SIZE 103 mm,40 mm\nCLS\nTEXT 24,24,"3",0,1,1,"CODIGO: 6327"\nPRINT 1\n'
            first = simulador.save_job(raw, 203)
            old_json = (Path(tmp) / f'{first["id"]}.json').read_bytes()
            server = simulador.RawServer(("127.0.0.1", 0), simulador.RawHandler, dpi=203)
            http = simulador.ThreadingHTTPServer(("127.0.0.1", 0), simulador.WebHandler)
            http.raw_server = server
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            def post(path, data):
                request = urllib.request.Request(f'http://127.0.0.1:{http.server_port}{path}', data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=15) as response:
                    return json.load(response)
            try:
                profile = post("/api/profile", {"offset_x_mm": -2, "offset_y_mm": 0, "calibrated": True})
                self.assertEqual(profile["offset_x_mm"], -2)
                self.assertTrue(simulador.CONFIG.is_file())
                second = post("/api/reprocess", {"id": first["id"]})
                self.assertNotEqual(first["id"], second["id"])
                self.assertEqual(second["perfil"]["offset_x_mm"], -2)
                self.assertEqual(second["versao_renderizador"], 2)
                self.assertEqual((Path(tmp) / second["raw"]).read_bytes(), raw)
                self.assertEqual((Path(tmp) / f'{first["id"]}.json').read_bytes(), old_json)
            finally:
                http.shutdown()
                thread.join(timeout=2)
                http.server_close()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
