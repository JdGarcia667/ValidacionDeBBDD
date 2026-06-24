# Datos de ejemplo

Archivos para probar la aplicación.

## Entidad "Banco" (clientes)

- `clientes.csv` — base de clientes en un solo archivo (incluye filas con errores).
- `clientes_parte1.csv` + `clientes_parte2.csv` — **la misma base dividida en dos
  archivos**, para probar la carga multi-archivo. Demuestran:
  - Concatenación de varios archivos (6 filas en total).
  - Detección de **ID duplicado entre archivos distintos** (el cliente `2001`
    aparece en ambos): aparece en la hoja *IDs Duplicados*.
  - Distinción **persona física / moral**: las morales (`2002`, `2004`) no se
    validan por CURP/género ni longitud de nombre; su fecha es de constitución.
    `2004` tiene una constitución futura → *Fecha futura en fecha de constitución*.

  En la UI: carga ambos archivos juntos en "Clientes" (selección múltiple).

  **Requisitos por nivel de cuenta**: incluyen las columnas `Nivel_cuenta` (1-4)
  y `modalidad de apertura` (presencial/remota). El Banco valida que cada cliente
  traiga los campos obligatorios de su nivel según el marco regulatorio
  (niveles 1-2 solo para físicas; 3-4 para físicas y morales). En el ejemplo,
  `2005` (nivel 2, remota) viene sin entidad federativa → aparece en la hoja
  *Requisitos por Nivel*. Una persona moral en nivel 1 o 2 se marca como
  "Nivel N no aplica a persona moral".

## Entidad "Banco" (operaciones)

- `operaciones.csv` — operaciones para probar agrupación y filtros de monto.
- `operaciones_niveles.csv` — operaciones con `nivel_cuenta` y `tipo de persona`
  para probar los **límites por nivel** (montos):
  - Abonos mensuales en UDIS por nivel (N1 750, N2 3,000, N3 10,000, N4 sin tope).
  - Efectivo en USD por tipo de persona (física $4,000; moral $0).

  En el ejemplo: `CTA1` (nivel 1) abona ~997 UDIS > 750 → hoja *Abonos sobre
  Limite (UDIS)*; `CL3` (moral) opera efectivo > $0 y `CL4` (física) > $4,000 →
  hoja *Efectivo USD sobre Limite*.
- `tasas_udis.xlsx` y `tasas_tc.xlsx` — valores de UDI y tipo de cambio (pesos
  por UDI / por dólar). Se cargan en el diálogo de operaciones; los montos en MXN
  se convierten a UDIS y USD para evaluar los límites. **Ambos** son obligatorios
  cuando la entidad valida límites por nivel.

## Entidad configurable de ejemplo

- `cooperativa_socios.csv` — socios de una cooperativa.
- Entidad **"Cooperativa de Ahorro (ejemplo)"** (en `entidades/usuario/`): valida
  por campo, sin lógica de banca. Reglas: `socio_id` único y no vacío, `nombre`
  con apellido, `rfc` formato físico, `correo` con `@`, `telefono` mínimo 10
  dígitos. Sobre los datos detecta: socio duplicado (`S001`), correo sin `@`
  (`S003`) y teléfono corto (`S004`).

## Grandes volúmenes (SQLite)

Cualquiera de estos flujos funciona también marcando **"Usar SQLite"**: los
archivos se cargan y validan por lotes. Los resultados son idénticos a la
validación en memoria (incluidos duplicados entre archivos y la agregación de
operaciones).
