# Validación de BBDD

Aplicación de escritorio (Flet) para validar bases de datos de **clientes** y **operaciones**, con validaciones que dependen de la **entidad financiera** seleccionada. Incluye la entidad **Banco** (tu lógica real) y permite **crear entidades nuevas** con su propio catálogo de reglas, sin programar.

## Idea central

Una entidad expone una interfaz común (`entidades/base.py: ValidadorEntidad`) y devuelve siempre el mismo formato que ya usaba tu pipeline: `dict {categoria: DataFrame}`. Así, el mismo reporte (`core/report_generator.py`) sirve para cualquier entidad.

Hay dos implementaciones de esa interfaz:

- **Banco** (`entidades/banco.py`): **envuelve tu código real** (`core/validator.py` y `core/validator_operaciones.py`) sin reimplementarlo. No es configuración: es tu lógica probada.
- **Entidad configurable** (`entidades/configurable.py`): motor de reglas para las entidades que creas desde la UI; se guardan como JSON en `entidades/usuario/`.

## Estructura

```
main.py                     Punto de entrada (ft.run)
core/                       TU CÓDIGO REAL (traído del repo, casi intacto)
  validator.py              Validaciones de clientes
  validator_operaciones.py  Validaciones de operaciones (agrupación + FX + umbrales)
  conversor.py              ConversorMoneda (UDIS / Dólares vía merge_asof)
  report_generator.py       Genera el Excel multi-hoja
  utils.py                  Normalización, estados MX, constantes
  io_utils.py               Lectura de CSV/Excel (preserva fechas dd/mm/yyyy)
entidades/                  Framework de entidades
  base.py                   Interfaz ValidadorEntidad
  banco.py                  Banco = envoltorio de tu core real
  configurable.py           Motor de reglas (entidades de usuario)
  reglas.py                 Catálogo de 19 reglas (no_vacío, curp, rfc, rango, ...)
  modelo.py                 Dataclasses de configuración + (de)serialización JSON
  mapeo.py                  Auto-mapeo campo→columna (sin dependencias)
  registro.py               Carga/guarda/lista entidades (builtin + JSON)
  usuario/                  Entidades creadas por ti (.json)
ui/
  app.py                    Pantalla principal y constructor de entidades
  dialogo_operaciones.py    Config de operaciones (moneda, agrupación, filtros, tasas)
datos_ejemplo/              clientes.csv, operaciones.csv (con errores de muestra)
```

## Flujo de uso

1. Elige la **entidad** (Banco u otra creada por ti).
2. Carga **clientes** y/o **operaciones** (CSV o Excel).
3. Revisa el **mapeo** de columnas (se auto-sugiere).
4. **Validar**:
   - Clientes: si la entidad lo pide y no mapeaste *tipo de persona*, se pregunta (físicas/morales).
   - Operaciones: si la entidad lo pide (Banco), se abre la config de moneda, agrupación, filtros de monto y, si aplica, los archivos de tasas UDIS / tipo de cambio.
5. Revisa los hallazgos por hoja y **exporta** el Excel.

> Operaciones del Banco: no se validan campo por campo. Se **agrupan** (cuenta/tipo/mes/instrumento), se suman los montos (con conversión por fecha real si eliges UDIS o Dólares) y se marcan los grupos que **exceden los umbrales** que definas (`>`, `<`, `>=`, `<=`). Sin filtros no hay hallazgos de operaciones.

## Crear una entidad nueva

Botón **Nueva entidad** → nombre + descripción → agrega campos (cliente y/u operación), y para cada campo marca las reglas del catálogo (con sus parámetros). Se guarda en `entidades/usuario/<nombre>.json` y aparece en el selector.

## Requisitos

```
pip install -r requirements.txt
python main.py
```

`fuzzywuzzy` es opcional (solo lo usa `core/mapper.py` del proyecto original); la UI usa `entidades/mapeo.py`, que no tiene dependencias externas.

## Nota de compatibilidad

`core/validator.py` traía una comparación `dtype == 'datetime64[ns]'` que en **pandas ≥ 3** falla (las fechas quedan en `datetime64[us]`) y se saltaba en silencio las hojas de fechas (Menores de 18, Fechas Futuras, Edades Irrealistas). Se reemplazó por `pd.api.types.is_datetime64_any_dtype(...)` (mismo comportamiento, marcado con comentario). Es el único cambio respecto a tu código.
