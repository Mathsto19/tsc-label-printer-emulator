"""Valida o ZIP real, mudando de pasta e sem Python/venv do computador."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which('powershell.exe')


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class PortablePackageTests(unittest.TestCase):
    def test_zip_moved_without_system_python_receives_print(self):
        package = max((ROOT / "Pacotes").glob("*.zip"), key=lambda p: p.stat().st_mtime)
        with tempfile.TemporaryDirectory(prefix=".teste portatil acento ç ", dir=ROOT) as temp:
            # Confere o destino antes da limpeza recursiva feita por TemporaryDirectory.
            self.assertEqual(Path(temp).resolve().parent, ROOT)
            with zipfile.ZipFile(package) as archive:
                names = archive.namelist()
                self.assertFalse(any(part in {".venv", "Saidas", ".pacote-cache"}
                                     for name in names for part in Path(name).parts))
                self.assertFalse(any(name.endswith("simulador.log") for name in names))
                archive.extractall(temp)
            folder, = Path(temp).iterdir()
            python = folder / "runtime" / "python.exe"
            self.assertTrue(python.is_file())
            self.assertTrue((folder / "instaladores" / "qz-tray-2.3.0-x86_64.exe").is_file())
            # A .venv de outro computador esta deliberadamente inutilizavel.
            (folder / ".venv").mkdir()
            (folder / ".venv" / "pyvenv.cfg").write_text("home = C:\\PythonQueNaoExiste\n")
            env = os.environ.copy()
            env.update(PATH=str(Path(env["SYSTEMROOT"]) / "System32"),
                       PYTHONHOME=r"C:\PythonQueNaoExiste", PYTHONPATH=r"C:\PythonQueNaoExiste",
                       TSC_TEST_PACKAGE=str(folder))
            validator = subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 ". (Join-Path $env:TSC_TEST_PACKAGE 'ambiente_python.ps1'); Get-SimulatorPython"],
                env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(validator.returncode, 0, validator.stdout + validator.stderr)
            raw_port, http_port = free_port(), free_port()
            while http_port == raw_port:
                http_port = free_port()
            process = subprocess.Popen(
                [str(python), str(folder / "simulador.py"), "--sem-navegador",
                 "--porta", str(raw_port), "--painel", str(http_port)],
                env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                url = f"http://127.0.0.1:{http_port}"
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with urllib.request.urlopen(url + "/api/jobs", timeout=1) as response:
                            self.assertEqual(json.load(response), [])
                        break
                    except OSError:
                        if process.poll() is not None:
                            self.fail(process.stdout.read().decode(errors="replace"))
                        if time.monotonic() > deadline:
                            self.fail("O painel nao iniciou no prazo.")
                        time.sleep(0.2)
                raw = (folder / "exemplo_teste.prn").read_bytes()
                with socket.create_connection(("127.0.0.1", raw_port), timeout=3) as connection:
                    connection.sendall(raw)
                deadline = time.monotonic() + 30
                while True:
                    with urllib.request.urlopen(url + "/api/jobs", timeout=3) as response:
                        jobs = json.load(response)
                    if jobs:
                        break
                    if time.monotonic() > deadline:
                        self.fail("O trabalho nao gerou captura e previa.")
                    time.sleep(0.2)
                output = folder / "Saidas"
                captured, = output.glob("*.prn")
                self.assertEqual(captured.read_bytes(), raw)
                self.assertTrue(any(p.read_bytes().startswith(b"%PDF-") for p in output.glob("*.pdf")))
                self.assertTrue(list(output.glob("*.png")))
                self.assertTrue(list(output.glob("*.svg")))
                self.assertTrue(list(output.glob("*.html")))
                self.assertTrue((folder / "simulador.log").is_file())
            finally:
                process.terminate()
                process.communicate(timeout=10)

    def test_missing_runtime_fails_before_opening_qz(self):
        with tempfile.TemporaryDirectory(prefix=".teste sem runtime ", dir=ROOT) as temp:
            self.assertEqual(Path(temp).resolve().parent, ROOT)
            for name in ("iniciar_simulador.ps1", "ambiente_python.ps1"):
                shutil.copy2(ROOT / name, Path(temp) / name)
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 str(Path(temp) / "iniciar_simulador.ps1")],
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Extraia o ZIP completo", result.stdout)
            self.assertNotIn("Verificando QZ", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
