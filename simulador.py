"""Impressora virtual RAW: porta TCP local -> captura .prn -> PDF de etiqueta.

Nenhuma comunicação com a internet. Não transmite dados de pacientes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import socket
import socketserver
import threading
import time
import uuid
import webbrowser
import re
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tspl_pdf import PrinterState, interpret, render_pdf
from previas import render_previews
from perfil import PrinterProfile, RENDERER_VERSION, dots_per_mm


HERE = Path(__file__).resolve().parent
OUT = HERE / "Saidas"
HTML = HERE / "painel.html"
LOG = HERE / "simulador.log"
CONFIG = HERE / "perfil-impressora.json"
MAX_JOB = 50 * 1024 * 1024
printer_port = 19100


class RawHandler(socketserver.BaseRequestHandler):
    def handle(self):
        chunks = []
        size = 0
        self.request.settimeout(8)
        while True:
            try:
                block = self.request.recv(65536)
            except socket.timeout:
                logging.warning("Conexão sem dados por 8 segundos; encerrando recepção")
                break
            except OSError:
                break
            if not block:
                break
            size += len(block)
            if size > MAX_JOB:
                logging.error("Trabalho excedeu o limite de 50 MB; descartado")
                return
            chunks.append(block)
        if not chunks:
            return
        raw = b"".join(chunks)
        with self.server.job_lock:
            save_job(raw, self.server.dpi, state=self.server.printer_state, profile=self.server.profile)


def save_job(raw, dpi, *, state=None, profile=None, source_id=None):
    profile = profile or PrinterProfile()
    state = state if state is not None else PrinterState()
    OUT.mkdir(parents=True, exist_ok=True)
    job_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]
    raw_path = OUT / f"{job_id}.prn"
    pdf_path = OUT / f"{job_id}.pdf"
    print_path = OUT / f"{job_id}_impressao.pdf"
    info_path = OUT / f"{job_id}.json"
    raw_path.write_bytes(raw)
    info = {
        "id": job_id, "data": dt.datetime.now().isoformat(timespec="seconds"),
        "bytes": len(raw), "paginas": 0, "pdf": None, "pdf_impressao": None,
        "raw": raw_path.name, "avisos": [], "dpi": dpi,
        "dots_por_mm": dots_per_mm(dpi), "versao_renderizador": RENDERER_VERSION,
        "perfil": profile.to_dict(), "estado_inicial": asdict(state), "origem": source_id,
    }
    try:
        conversion = interpret(raw, dpi=dpi, state=state, profile=profile)
        info["paginas"] = len(conversion.labels)
        warnings = render_pdf(conversion, pdf_path)
        info["avisos"] = sorted(set(warnings + render_pdf(conversion, print_path, show_stock=False)))
        info["tamanhos_mm"] = [list(size) for size in dict.fromkeys(
            (label.width_mm, label.height_mm) for label in conversion.labels
        )]
        info["configuracoes"] = [
            {"reference": label.reference, "shift": label.shift, "direction": label.direction,
             "mirror": label.mirror, "codepage": label.codepage} for label in conversion.labels
        ]
        if pdf_path.is_file():
            info["pdf"] = pdf_path.name
            info.update(render_previews(conversion, pdf_path, warnings=info["avisos"]))
        if print_path.is_file():
            info["pdf_impressao"] = print_path.name
        logging.info("Capturado: %s - %s bytes - %s páginas - %s avisos", job_id, len(raw), info["paginas"], len(info["avisos"]))
    except Exception as e:
        info["avisos"].append(f"Falha ao gerar prévia: {type(e).__name__}: {e}")
        logging.exception("Erro na impressão %s", job_id)
    finally:
        info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


class RawServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, handler, dpi, profile=None):
        super().__init__(address, handler)
        self.dpi = dpi
        self.profile = profile or PrinterProfile()
        self.printer_state = PrinterState()
        self.job_lock = threading.Lock()


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logging.debug("HTTP %s", fmt % args)

    def _send(self, status, mime, body, download=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, "text/html; charset=utf-8", HTML.read_bytes())
        if path == "/api/jobs":
            jobs = []
            for f in sorted(OUT.glob("*.json"), reverse=True)[:150]:
                try:
                    jobs.append(json.loads(f.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    continue
            return self._send(200, "application/json; charset=utf-8", json.dumps(jobs, ensure_ascii=False).encode())
        if path == "/api/profile":
            data = {**self.server.raw_server.profile.to_dict(), "dpi": self.server.raw_server.dpi,
                    "dots_por_mm": dots_per_mm(self.server.raw_server.dpi), "versao_renderizador": RENDERER_VERSION}
            return self._send(200, "application/json; charset=utf-8", json.dumps(data).encode())
        if path.startswith("/arquivo/"):
            name = unquote(path[len("/arquivo/"):])
            # Nunca permitir navegação de diretórios ou arquivos não relacionados.
            if not name or name != Path(name).name or not name.endswith((".pdf", ".prn", ".html", ".svg", ".png")):
                return self._send(404, "text/plain", b"Nao encontrado")
            requested = OUT / name
            if not requested.is_file():
                return self._send(404, "text/plain", b"Nao encontrado")
            mime = {".pdf": "application/pdf", ".html": "text/html; charset=utf-8",
                    ".svg": "image/svg+xml", ".png": "image/png"}.get(requested.suffix, "application/octet-stream")
            return self._send(200, mime, requested.read_bytes(), name if name.endswith(".prn") else None)
        return self._send(404, "text/plain", b"Nao encontrado")

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Envie application/json.")
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
                return self._send(403, "text/plain", b"Origem nao permitida")
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4096:
                raise ValueError("Tamanho da requisição inválido.")
            data = json.loads(self.rfile.read(length))
            raw_server = self.server.raw_server
            if path == "/api/profile":
                profile = PrinterProfile.from_dict(data)
                with raw_server.job_lock:
                    CONFIG.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
                    raw_server.profile = profile
                result = profile.to_dict()
            elif path == "/api/reprocess":
                job_id = data.get("id", "")
                if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
                    raise ValueError("Impressão inválida.")
                info = json.loads((OUT / f"{job_id}.json").read_text(encoding="utf-8"))
                raw = (OUT / f"{job_id}.prn").read_bytes()
                with raw_server.job_lock:
                    result = save_job(raw, info["dpi"], state=PrinterState(**info.get("estado_inicial", {})),
                                      profile=raw_server.profile, source_id=job_id)
            else:
                return self._send(404, "text/plain", b"Nao encontrado")
            return self._send(200, "application/json; charset=utf-8", json.dumps(result, ensure_ascii=False).encode())
        except (ValueError, OSError, TypeError, KeyError, AttributeError) as e:
            return self._send(400, "application/json; charset=utf-8", json.dumps({"erro": str(e)}, ensure_ascii=False).encode())


def main():
    parser = argparse.ArgumentParser(description="Impressora virtual TSC DA300: Windows RAW -> PDF")
    parser.add_argument("--dpi", type=int, choices=[203, 300], default=203, help="203 (layouts 8 dots/mm) ou 300 (DA300 nativa)")
    parser.add_argument("--porta", type=int, default=19100, help="mesma porta do instalador (19100)")
    parser.add_argument("--painel", type=int, default=8767, help="painel local (8767)")
    parser.add_argument("--sem-navegador", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    try:
        profile = PrinterProfile.from_dict(json.loads(CONFIG.read_text(encoding="utf-8"))) if CONFIG.is_file() else PrinterProfile()
        server = RawServer(("127.0.0.1", args.porta), RawHandler, args.dpi, profile)
        http = ThreadingHTTPServer(("127.0.0.1", args.painel), WebHandler)
        http.raw_server = server
    except OSError as e:
        print("Não consegui iniciar as portas locais. Verifique se o simulador já está aberto.")
        print(e)
        raise SystemExit(1)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=http.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{args.painel}/"
    print("=" * 62)
    print("TSC DA300 VIRTUAL - LIGADA")
    print(f"Porta de impressao: 127.0.0.1:{args.porta} (RAW TSPL)")
    print(f"Painel: {url}")
    print(f"Resolução de interpretação: {args.dpi} DPI")
    print(f"Perfil: {profile.model} - {dots_per_mm(args.dpi):g} dots/mm")
    print("Alinhamento físico: " + ("calibrado" if profile.calibrated else "não medido; veja a referência de margem no painel"))
    print(f"Arquivos PDF e PRN: {OUT}")
    print("Mantenha esta janela aberta enquanto estiver imprimindo.")
    print("Pressione Ctrl+C para encerrar.")
    print("=" * 62)
    if not args.sem_navegador:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Desligando simulador...")
    finally:
        server.shutdown()
        http.shutdown()
        server.server_close()
        http.server_close()


if __name__ == "__main__":
    main()
