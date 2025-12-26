CometLocal — Data Layout (v1)

Este directorio contiene datos locales (sin DB) usados por el executor y futuros módulos.

Estructura canónica (H7.5):

- `data/documents/`:
  - `companies/<company_id>/workers/<worker_id>/{contracts,training,medical,other}/`
  - `companies/<company_id>/company_docs/{insurance,prevention_plan,other}/`
  - `meta.json` (futuro; opcional)
- `data/refs/`:
  - `documents.json` — índice `file_ref -> metadata + path + sha256`
  - `secrets.json` — referencias a credenciales (NO valores)
- `data/runs/`:
  - Runs auditable (trace + evidence) (ver H4/H7)
- `data/tmp/uploads/`:
  - Copias efímeras para uploads (no tocar el documento original)

Notas:
- Local-only, sin autenticación.
- No OCR / no inspección de contenido en H7.5.





