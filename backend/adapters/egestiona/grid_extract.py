"""
Extractor robusto de grid DHTMLX de eGestiona.

Centraliza la lógica de extracción del grid para evitar duplicación
y garantizar que se extraen correctamente los campos tipo_doc, elemento, empresa, etc.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def extract_dhtmlx_grid(frame: Any) -> Dict[str, Any]:
    """
    Extrae el grid DHTMLX de eGestiona de forma robusta.
    
    Args:
        frame: Playwright frame que contiene el grid
    
    Returns:
        Dict con:
        - headers: List[str] - Nombres de columnas detectados
        - rows: List[Dict] - Filas con keys canónicas (tipo_doc, elemento, empresa, etc.)
        - raw_rows_preview: List[List[str]] - Primeras 3 filas como arrays de strings (para debug)
        - mapping_debug: Dict[str, int] - Mapeo header -> índice
        - warnings: List[str] - Advertencias si hay problemas
    """
    extracted = frame.evaluate(
        """() => {
  function norm(s){ return (s||'').replace(/\\s+/g,' ').trim(); }
  
  function headersFromHdrTable(hdr){
    // Intentar obtener headers de la segunda fila (tr:nth-of-type(2))
    const cells = Array.from(hdr.querySelectorAll('tr:nth-of-type(2) td'));
    if(cells.length){
      return cells.map(td => {
        const span = td.querySelector('.hdrcell span');
        return span ? norm(span.innerText) : norm(td.innerText);
      });
    }
    // Fallback: buscar directamente en .hdrcell span
    return Array.from(hdr.querySelectorAll('.hdrcell span')).map(s => norm(s.innerText));
  }
  
  function scoreHdr(hdr){
    const hs = headersFromHdrTable(hdr);
    const nonEmpty = hs.filter(Boolean).length;
    return nonEmpty * 100 + norm(hdr.innerText).length;
  }
  
  function extractRowsFromObjTable(tbl, headers){
    const trs = Array.from(tbl.querySelectorAll('tbody tr'));
    const rows = [];
    for(const tr of trs){
      const tds = Array.from(tr.querySelectorAll('td'));
      if(!tds.length) continue; // Ignorar filas sin celdas
      
      const cells = tds.map(td => norm(td.innerText));
      
      // Ignorar filas completamente vacías (todas las celdas vacías)
      if(!cells.some(x => x)) continue;
      
      // Mapear celdas a headers
      const mapped = {};
      for(let i=0; i<cells.length; i++){
        const header = (i < headers.length && headers[i]) ? headers[i] : `col_${i+1}`;
        const value = cells[i] || '';
        mapped[header] = value;
      }
      
      // Añadir raw_cells para debug
      mapped._raw_cells = cells;
      mapped._td_count = tds.length;
      
      rows.push(mapped);
    }
    return rows;
  }
  
  // Buscar todas las tablas header y data
  const hdrTables = Array.from(document.querySelectorAll('table.hdr'));
  const objTables = Array.from(document.querySelectorAll('table.obj.row20px'));
  
  if(!hdrTables.length || !objTables.length){
    return {
      headers: [],
      rows: [],
      raw_rows_preview: [],
      mapping_debug: {},
      warnings: ['No se encontraron tablas hdr u obj']
    };
  }
  
  // Seleccionar el mejor header (más columnas no vacías)
  hdrTables.sort((a,b) => scoreHdr(b) - scoreHdr(a));
  const bestHdr = hdrTables[0];
  const headers = headersFromHdrTable(bestHdr);
  
  // Seleccionar la mejor tabla de datos (más filas con contenido)
  let bestObj = null;
  let bestRows = [];
  for(const t of objTables){
    const rs = extractRowsFromObjTable(t, headers);
    if(rs.length > bestRows.length){
      bestObj = t;
      bestRows = rs;
    } else if(rs.length === bestRows.length && rs.length > 0){
      // Tie-breaker: más texto total
      const tText = norm(t.innerText).length;
      const bestText = bestObj ? norm(bestObj.innerText).length : 0;
      if(tText > bestText){
        bestObj = t;
        bestRows = rs;
      }
    }
  }
  
  // Crear mapping debug
  const mapping_debug = {};
  headers.forEach((h, i) => {
    if(h) mapping_debug[h] = i;
  });
  
  // Preview de primeras 3 filas
  const raw_rows_preview = bestRows.slice(0, 3).map(r => r._raw_cells || []);
  
  // Warnings
  const warnings = [];
  if(headers.length < 5){
    warnings.push(`Solo se detectaron ${headers.length} headers (esperado >= 5)`);
  }
  
  // Verificar que hay filas con contenido real
  const rowsWithContent = bestRows.filter(r => {
    const tipoDoc = r['Tipo Documento'] || r['tipo_doc'] || r['Tipo'] || '';
    const elemento = r['Elemento'] || r['elemento'] || '';
    return tipoDoc || elemento;
  });
  
  if(rowsWithContent.length === 0 && bestRows.length > 0){
    warnings.push(`Se encontraron ${bestRows.length} filas pero todas tienen tipo_doc y elemento vacíos`);
  }
  
  return {
    headers,
    rows: bestRows,
    raw_rows_preview,
    mapping_debug,
    warnings,
    debug: {
      hdr_tables: hdrTables.length,
      obj_tables: objTables.length,
      total_rows: bestRows.length,
      rows_with_content: rowsWithContent.length
    }
  };
}"""
    )
    
    return extracted


def canonicalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Canonicaliza una fila del grid a campos estándar.
    
    Args:
        row: Fila cruda del grid con keys del header
    
    Returns:
        Fila con keys canónicas:
        - tipo_doc: str | None
        - elemento: str | None
        - empresa: str | None
        - estado: str | None
        - origen: str | None
        - fecha_solicitud: str | None
        - inicio: str | None
        - fin: str | None
    """
    # Mapeo de posibles nombres de columnas a keys canónicas
    tipo_doc = (
        row.get("Tipo Documento") or 
        row.get("tipo_doc") or 
        row.get("Tipo") or 
        row.get("TipoDoc") or
        None
    )
    
    elemento = (
        row.get("Elemento") or 
        row.get("elemento") or
        None
    )
    
    empresa = (
        row.get("Empresa") or 
        row.get("empresa") or
        None
    )
    
    estado = (
        row.get("Estado") or 
        row.get("estado") or
        None
    )
    
    origen = (
        row.get("Origen") or 
        row.get("origen") or
        None
    )
    
    fecha_solicitud = (
        row.get("Fecha Solicitud") or 
        row.get("fecha_solicitud") or 
        row.get("FechaSolicitud") or
        None
    )
    
    inicio = (
        row.get("Inicio") or 
        row.get("inicio") or 
        row.get("Fecha Inicio") or
        row.get("FechaInicio") or
        None
    )
    
    fin = (
        row.get("Fin") or 
        row.get("fin") or 
        row.get("Fecha Fin") or
        row.get("FechaFin") or
        None
    )
    
    # Normalizar: convertir strings vacíos a None
    def clean_value(v):
        if v is None:
            return None
        v_str = str(v).strip()
        return v_str if v_str else None
    
    return {
        "tipo_doc": clean_value(tipo_doc),
        "elemento": clean_value(elemento),
        "empresa": clean_value(empresa),
        "estado": clean_value(estado),
        "origen": clean_value(origen),
        "fecha_solicitud": clean_value(fecha_solicitud),
        "inicio": clean_value(inicio),
        "fin": clean_value(fin),
        # Mantener raw_data para debug
        "_raw_row": row
    }



























