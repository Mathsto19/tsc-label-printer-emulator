"""Perfil físico separado do TSPL: nunca deduz um deslocamento a partir de uma foto."""

from dataclasses import asdict, dataclass
import math


RENDERER_VERSION = 2


def dots_per_mm(dpi: int) -> float:
    # Resoluções nominais TSC: 203 dpi = 8 dots/mm; 300 dpi = 12 dots/mm.
    return {203: 8.0, 300: 12.0}.get(dpi, dpi / 25.4)


@dataclass(frozen=True)
class PrinterProfile:
    model: str = "TSC TTP-245C"
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    calibrated: bool = False

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Perfil deve ser um objeto JSON.")
        offsets = []
        for key in ("offset_x_mm", "offset_y_mm"):
            value = values.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or abs(value) > 25.4:
                raise ValueError("Deslocamentos devem ser números entre -25,4 e 25,4 mm.")
            offsets.append(float(value))
        calibrated = values.get("calibrated", False)
        if not isinstance(calibrated, bool):
            raise ValueError("Estado de calibração inválido.")
        return cls(offset_x_mm=offsets[0], offset_y_mm=offsets[1], calibrated=calibrated)
