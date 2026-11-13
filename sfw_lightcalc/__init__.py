"""sfw_lightcalc: calcolo illuminotecnico dei locali (illuminamento, uniformità, UGR, mappe isolux)."""
from .ies import Photometry, lambertian, parse_ies_text, read_ies
from .room import RoomResult, design_room

__all__ = ["Photometry", "lambertian", "parse_ies_text", "read_ies", "RoomResult", "design_room"]
__version__ = "0.1.0"
