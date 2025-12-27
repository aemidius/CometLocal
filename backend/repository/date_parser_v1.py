from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple

# Mapeo de meses en español (abreviados y completos)
SPANISH_MONTHS = {
    "ene": 1, "enero": 1,
    "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,
    "ago": 8, "agosto": 8,
    "sep": 9, "septiembre": 9,
    "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12,
}


def parse_date_from_filename(filename: str) -> Tuple[Optional[date], float]:
    """
    Parsea una fecha desde el nombre de archivo.
    
    Retorna:
        (date, confidence): fecha parseada (o None) y confianza (0..1)
    
    Patrones soportados:
        - "28-nov-25" (DD-MMM-YY)
        - "28-11-2025" (DD-MM-YYYY)
        - "2025-11-28" (YYYY-MM-DD)
        - "28/11/2025" (DD/MM/YYYY)
    """
    filename_lower = filename.lower()
    
    # Patrón 1: DD-MMM-YY (ej: "28-nov-25")
    pattern1 = r"(\d{1,2})[-/]?(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)[-/]?(\d{2,4})"
    match1 = re.search(pattern1, filename_lower)
    if match1:
        day = int(match1.group(1))
        month_str = match1.group(2)
        year_str = match1.group(3)
        
        month = SPANISH_MONTHS.get(month_str)
        if month:
            if len(year_str) == 2:
                year = 2000 + int(year_str)
                if year > datetime.now().year + 10:
                    year -= 100
            else:
                year = int(year_str)
            
            try:
                parsed_date = date(year, month, day)
                return parsed_date, 0.9  # Alta confianza si coincide con patrón conocido
            except ValueError:
                pass
    
    # Patrón 2: DD-MM-YYYY o DD/MM/YYYY (ej: "28-11-2025")
    pattern2 = r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})"
    match2 = re.search(pattern2, filename_lower)
    if match2:
        day = int(match2.group(1))
        month = int(match2.group(2))
        year = int(match2.group(3))
        
        try:
            parsed_date = date(year, month, day)
            return parsed_date, 0.85  # Buena confianza
        except ValueError:
            pass
    
    # Patrón 3: YYYY-MM-DD (ej: "2025-11-28")
    pattern3 = r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"
    match3 = re.search(pattern3, filename_lower)
    if match3:
        year = int(match3.group(1))
        month = int(match3.group(2))
        day = int(match3.group(3))
        
        try:
            parsed_date = date(year, month, day)
            return parsed_date, 0.9  # Alta confianza (formato ISO)
        except ValueError:
            pass
    
    # Patrón 4: DD-MM-YY (ej: "28-11-25")
    pattern4 = r"(\d{1,2})[-/](\d{1,2})[-/](\d{2})"
    match4 = re.search(pattern4, filename_lower)
    if match4:
        day = int(match4.group(1))
        month = int(match4.group(2))
        year_str = match4.group(3)
        year = 2000 + int(year_str)
        if year > datetime.now().year + 10:
            year -= 100
        
        try:
            parsed_date = date(year, month, day)
            return parsed_date, 0.7  # Confianza media (ambigüedad DD/MM vs MM/DD)
        except ValueError:
            pass
    
    return None, 0.0


def compute_period_from_date(d: date) -> Tuple[date, date]:
    """
    Calcula el período mensual (inicio y fin de mes) para una fecha.
    
    Retorna:
        (period_start, period_end): primer y último día del mes
    """
    period_start = date(d.year, d.month, 1)
    if d.month == 12:
        period_end = date(d.year + 1, 1, 1)
    else:
        period_end = date(d.year, d.month + 1, 1)
    
    # period_end es el primer día del mes siguiente, así que restamos 1 día
    from datetime import timedelta
    period_end = period_end - timedelta(days=1)
    
    return period_start, period_end




