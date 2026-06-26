import logging
import pandas as pd
import re
from datetime import datetime, date

from core.utils import (
    normalizar_texto,
    ESTADOS_MEXICANOS_NORM,
    TELEFONO_MIN_DIGITOS,
    DIRECCION_MIN_SEPARADORES,
    YEAR_CORTE_SIGLO,
)
from core.paises import es_mexico, es_pais_valido

logger = logging.getLogger(__name__)

# Partes del domicilio cuando viene dividido en columnas. 'numero_interior' es
# opcional; el resto son obligatorias si el domicilio se valida por columnas.
DIRECCION_PARTES_REQUERIDAS = [
    "calle_avenida_via", "numero_exterior", "colonia_urbanizacion",
    "alcaldia_municipio", "ciudad_poblacion", "entidad_federativa_estado",
    "codigo_postal", "pais",
]
DIRECCION_PARTES = DIRECCION_PARTES_REQUERIDAS + ["numero_interior"]

# Más de 5 dígitos iguales consecutivos en un teléfono (6 o más).
TELEFONO_REPETIDOS_RE = re.compile(r"(\d)\1{5}")


class Validator:
    """Realiza todas las validaciones sobre un DataFrame de clientes."""

    COLUMNAS_BASE = ['id_cliente', 'nombre', 'estatus_cliente', 'tipo de persona', 'CURP']

    # Variantes de texto que se reconocen como México
    _VARIANTES_MEXICO = {'MEXICO', 'MEXICANA', 'MEX', 'MX'}

    def __init__(self, df: pd.DataFrame, mapeo: dict, tipo_persona_default: str | None = None):
        self.df = df
        self.mapeo = mapeo
        self.tipo_persona_default = tipo_persona_default

        self.real_columns = {normalizar_texto(c): c for c in self.df.columns}
        self.col_mapping = {}
        for campo, col_mapeada in self.mapeo.items():
            if col_mapeada:
                col_norm = normalizar_texto(col_mapeada)
                self.col_mapping[campo] = self.real_columns.get(col_norm)
            else:
                self.col_mapping[campo] = None

        self.col_id = self.col_mapping.get('id_cliente')
        self.tiene_id = self.col_id is not None

        self.columnas_criticas = [
            'id_cliente', 'nombre', 'fecha_nacimiento', 'fecha_inicio_relacion',
            'Dirección', 'genero', 'Actividad_especifica', 'Correo electronico'
        ]

        self.columnas_fecha = [
            'fecha_nacimiento', 'fecha_inicio_relacion', 'fecha_termino_relacion', 'fecha_riesgo'
        ]

    # ------------------------------------------------------------------
    # Métodos auxiliares
    # ------------------------------------------------------------------
    def _get_valor(self, row, campo):
        col = self.col_mapping.get(campo)
        if col and col in self.df.columns:
            return row[col]
        return None

    def _obtener_columnas_base(self) -> dict:
        """Devuelve un dict con los nombres reales de las columnas base que existen."""
        base = {}
        for campo in self.COLUMNAS_BASE:
            real = self.col_mapping.get(campo)
            if real and real in self.df.columns:
                base[campo] = real
        return base

    def _es_mexicano(self, texto) -> bool:
        """Determina si un texto (país o nacionalidad) se refiere a México.

        Reconoce México por el catálogo de países (México/MX/MEX/484) y la
        nacionalidad por adjetivo (Mexicana/Mexicano)."""
        if pd.isna(texto) or texto == '':
            return False
        return es_mexico(texto) or normalizar_texto(str(texto)).upper() in self._VARIANTES_MEXICO

    def _normalizar_entidad(self, entidad) -> str:
        if pd.isna(entidad) or entidad == '':
            return ''
        return normalizar_texto(str(entidad)).upper()

    # ------------------------------------------------------------------
    # Tipo de persona (física / moral)
    # ------------------------------------------------------------------
    def _es_moral_row(self, row) -> bool:
        """True si la fila es persona moral.

        Si no hay valor de 'tipo de persona' se usa el default; si tampoco hay
        default, se asume FÍSICA (no moral), para no dejar pasar validaciones.
        """
        valor = self._get_valor(row, 'tipo de persona')
        if valor is None or pd.isna(valor) or str(valor).strip() == '':
            valor = self.tipo_persona_default
        return bool(valor) and 'moral' in str(valor).lower()

    def _serie_es_moral(self) -> pd.Series:
        """Serie booleana (alineada al índice del df): True = persona moral.

        Mismo criterio que _es_moral_row pero vectorizado para las validaciones
        que operan sobre todo el DataFrame. Desconocido -> física (False).
        """
        default_moral = (bool(self.tipo_persona_default)
                         and 'moral' in self.tipo_persona_default.lower())
        col = self.col_mapping.get('tipo de persona')
        if not col or col not in self.df.columns:
            return pd.Series(default_moral, index=self.df.index)
        serie = self.df[col]
        es_moral = serie.astype(str).str.lower().str.contains('moral', na=False)
        if default_moral:
            vacias = serie.isna() | serie.astype(str).str.strip().str.lower().isin(
                ['', 'nan', 'none', 'null'])
            es_moral = es_moral | vacias
        return es_moral

    def _etiqueta_fecha_nac(self, index, es_moral) -> pd.Series:
        """Nombre legible del campo de nacimiento por fila: 'fecha de constitución'
        para persona moral y 'fecha_nacimiento' para física. Se usa en las hojas
        vectorizadas, donde una misma hoja mezcla filas de ambos tipos."""
        return es_moral.loc[index].map(
            lambda m: 'fecha de constitución' if m else 'fecha_nacimiento')

    # ------------------------------------------------------------------
    # Conversión de fechas
    # ------------------------------------------------------------------
    def _convertir_fecha_dia_mes(self, valor):
        if pd.isna(valor):
            return pd.NaT
        try:
            str_valor = str(valor).strip()
            numeros = re.findall(r'\d+', str_valor)
            if len(numeros) >= 3:
                dia = int(numeros[0])
                mes = int(numeros[1])
                año = int(numeros[2])
                if año < 100:
                    año += 2000 if año <= YEAR_CORTE_SIGLO else 1900
                if 1 <= mes <= 12 and 1 <= dia <= 31 and 1900 <= año <= 2100:
                    return pd.Timestamp(year=año, month=mes, day=dia)
        except (ValueError, TypeError):
            pass
        return pd.NaT

    def _estandarizar_fechas(self):
        for campo in self.columnas_fecha:
            col = self.col_mapping.get(campo)
            if col and col in self.df.columns:
                self.df[col] = self.df[col].apply(self._convertir_fecha_dia_mes)

    # ------------------------------------------------------------------
    # Validaciones por fila (devuelven string de error o None)
    # ------------------------------------------------------------------
    def _validar_id_cliente(self, row):
        valor = self._get_valor(row, 'id_cliente')
        if pd.isna(valor) or valor == '':
            return "ID de cliente vacío"
        return None

    def _validar_nombre_completo(self, row):
        valor = self._get_valor(row, 'nombre')
        if pd.isna(valor) or valor == '':
            return "Nombre vacío"
        # Caso 1: el nombre viene dividido en columnas (nombre + apellidos). Se
        # exige el nombre y al menos uno de los apellidos (paterno o materno).
        # Las personas morales no tienen apellidos (razón social).
        if self.col_mapping.get('apellido_paterno') or self.col_mapping.get('apellido_materno'):
            if self._es_moral_row(row):
                return None
            ap = self._get_valor(row, 'apellido_paterno')
            am = self._get_valor(row, 'apellido_materno')
            ap_ok = not (pd.isna(ap) or str(ap).strip() == '')
            am_ok = not (pd.isna(am) or str(am).strip() == '')
            if not (ap_ok or am_ok):
                return "Falta al menos un apellido (paterno o materno)"
            return None
        # Caso 2: nombre en una sola columna. El requisito de "nombre + apellido"
        # (al menos un espacio) aplica solo a persona física; una razón social de
        # persona moral puede ser una sola palabra.
        if self._es_moral_row(row):
            return None
        if valor.count(' ') < 1:
            return "Nombre incompleto (debe tener al menos un espacio)"
        return None


    def _validar_fecha_nacimiento(self, row):
        col = self.col_mapping.get('fecha_nacimiento')
        if not col or col not in self.df.columns:
            return None
        valor = row[col]
        es_moral = self._es_moral_row(row)
        etiqueta = "Fecha de constitución" if es_moral else "Fecha de nacimiento"
        if pd.isna(valor) or valor == '':
            return f"{etiqueta} vacía"
        try:
            fecha = pd.to_datetime(valor, errors='coerce')
            if pd.isna(fecha):
                return "Fecha inválida"
            # Los límites de edad (18-120 años) aplican solo a persona física.
            # Para persona moral la fecha es de constitución: basta con que sea
            # válida y no futura (la futura la detecta la sección 'Fechas Futuras').
            if es_moral:
                return None
            hoy = date.today()
            edad = hoy.year - fecha.year - ((hoy.month, hoy.day) < (fecha.month, fecha.day))
            if edad < 18:
                return f"Edad {edad} años menor a 18"
            elif edad > 110:
                return f"Edad {edad} años mayor a 110"
        except (ValueError, TypeError):
            return "Fecha no procesable"
        return None

    def _validar_genero(self, row):
        # Las personas morales no tienen género.
        if self._es_moral_row(row):
            return None
        valor = self._get_valor(row, 'genero')
        if pd.isna(valor) or valor == '':
            return "Género vacío"
        return None

    def _validar_tipo_persona(self, row):
        valor = self._get_valor(row, 'tipo de persona')
        if valor is None and self.tipo_persona_default:
            return None
        if pd.isna(valor) or valor == '':
            return "Tipo de persona vacío"
        return None

    def _validar_estatus_cliente(self, row):
        valor = self._get_valor(row, 'estatus_cliente')
        if pd.isna(valor) or valor == '':
            return "Estatus vacío"
        return None

    def _validar_fechas_relacion(self, row):
        fecha_inicio = self._get_valor(row, 'fecha_inicio_relacion')
        fecha_termino = self._get_valor(row, 'fecha_termino_relacion')
        estatus = self._get_valor(row, 'estatus_cliente')

        if pd.isna(fecha_inicio) or fecha_inicio == '':
            return "Fecha inicio relación vacía"
        try:
            f_ini = pd.to_datetime(fecha_inicio, errors='coerce')
            if pd.isna(f_ini):
                return "Fecha inicio inválida"
        except (ValueError, TypeError):
            return "Fecha inicio inválida"

        if not (pd.isna(fecha_termino) or fecha_termino == ''):
            try:
                f_ter = pd.to_datetime(fecha_termino, errors='coerce')
                if pd.isna(f_ter):
                    return "Fecha término inválida"
                if f_ter < f_ini:
                    return "Fecha término anterior a fecha inicio"
            except (ValueError, TypeError):
                return "Fecha término inválida"

        if estatus and isinstance(estatus, str) and 'activo' in estatus.lower():
            if not (pd.isna(fecha_termino) or fecha_termino == ''):
                return "Cliente activo con fecha de término"
        return None

    def _validar_grado_riesgo(self, row):
        valor = self._get_valor(row, 'grado_riesgo')
        if pd.isna(valor) or valor == '':
            return "Grado de riesgo vacío"
        return None

    def _validar_fecha_riesgo(self, row):
        valor = self._get_valor(row, 'fecha_riesgo')
        if pd.isna(valor) or valor == '':
            return "Fecha de riesgo vacía"
        try:
            if pd.isna(pd.to_datetime(valor, errors='coerce')):
                return "Fecha de riesgo inválida"
        except (ValueError, TypeError):
            return "Fecha de riesgo inválida"
        return None

    def _validar_pep(self, row):
        valor = self._get_valor(row, 'PEP')
        if pd.isna(valor) or valor == '':
            return "PEP vacío"
        return None

    def _validar_nacionalidad(self, row):
        valor = self._get_valor(row, 'Nacionalidad')
        if pd.isna(valor) or valor == '':
            return "Nacionalidad vacía"
        return None

    def _validar_pais_nacimiento(self, row):
        valor = self._get_valor(row, 'Pais_nacimiento')
        if pd.isna(valor) or valor == '':
            return "País de nacimiento vacío"
        if not es_pais_valido(valor):
            return f"País de nacimiento '{valor}' no reconocido"
        return None

    def _validar_entidad_federativa(self, row):
        # Esta validacion no aplica para extranjeros (Bancos): si el país de
        # nacimiento está informado y no es México, no se valida la entidad.
        pais = self._get_valor(row, 'Pais_nacimiento')
        if not (pd.isna(pais) or str(pais).strip() == '') and not self._es_mexicano(pais):
            return None
        entidad = self._get_valor(row, 'entidad_federativa')
        if pd.isna(entidad) or entidad == '':
            return "Entidad federativa vacía"
        if self._es_mexicano(pais):
            entidad_norm = normalizar_texto(str(entidad)).upper()
            if entidad_norm not in ESTADOS_MEXICANOS_NORM:
                return f"Entidad '{entidad}' no válida para México"
        return None

    def _validar_actividades(self, row):
        act_gen = self._get_valor(row, 'Actividad_generica')
        act_esp = self._get_valor(row, 'Actividad_especifica')
        if (pd.isna(act_gen) or act_gen == '') and (pd.isna(act_esp) or act_esp == ''):
            return "Ambas actividades vacías"
        return None

    def _validate_telefono_row(self, row):
        valor = self._get_valor(row, 'Teléfono')
        if pd.isna(valor) or str(valor).strip() == '':
            return None
        telefono_limpio = re.sub(r'\D', '', str(valor))
        if telefono_limpio in ('', 'nan'):
            return None
        errores = []
        if len(telefono_limpio) != TELEFONO_MIN_DIGITOS:
            errores.append(f"Longitud {len(telefono_limpio)}, se esperan {TELEFONO_MIN_DIGITOS}")
        if TELEFONO_REPETIDOS_RE.search(telefono_limpio):
            errores.append("Más de 5 dígitos iguales consecutivos")
        return "; ".join(errores) if errores else None

    def _validar_correo(self, row):
        valor = self._get_valor(row, 'Correo electronico')
        if pd.isna(valor) or valor == '':
            return "Correo vacío"
        if '@' not in str(valor):
            return "Correo sin @"
        return None

    def _validate_curp_row(self, row):
        col_curp = self.col_mapping.get('CURP')
        if not col_curp or col_curp not in self.df.columns:
            return "Columna CURP no encontrada"
        curp = str(row[col_curp]).strip().upper()
        if curp in ['NAN', '', 'NONE', 'NULL']:
            return "CURP faltante"
        errors = []
        if len(curp) != 18:
            errors.append(f"Longitud incorrecta: {len(curp)} caracteres")
        if not re.match(r'^[A-Z0-9]+$', curp):
            errors.append("Caracteres no permitidos")
        if errors:
            return "; ".join(errors)
        # Validación por estructura (18): 4 letras + 6 números + género (pos 11) +
        # 5 letras + 2 números.
        if not re.match(r'^[A-Z]{4}', curp):
            errors.append("Primeros 4 caracteres no son letras")
        if not re.match(r'^[0-9]{6}$', curp[4:10]):
            errors.append("Caracteres 5-10 no son números")
        if not re.match(r'^[A-Z]{5}$', curp[11:16]):
            errors.append("Caracteres 12-16 no son letras")
        if not re.match(r'^[0-9]{2}$', curp[16:18]):
            errors.append("Últimos 2 caracteres no son números")
        col_genero = self.col_mapping.get('genero')
        if col_genero and col_genero in self.df.columns:
            gender_data = str(row[col_genero]).strip().upper()
            expected = ''
            if gender_data in ['MALE', 'M', 'HOMBRE', 'H']:
                expected = 'H'
            elif gender_data in ['FEMALE', 'F', 'MUJER']:
                expected = 'M'
            if expected and curp[10] != expected:
                errors.append(f"Error Género: Esperado '{expected}', Obtenido '{curp[10]}'")
        return "; ".join(errors) if errors else None
    
    # Agregar validacion por estrutura logica 

    def _validate_rfc_row(self, row):
        col_rfc = self.col_mapping.get('RFC')
        if not col_rfc or col_rfc not in self.df.columns:
            return "Columna RFC no encontrada"
        rfc = str(row[col_rfc]).strip().upper()
        if rfc in ['NAN', '', 'NONE', 'NULL']:
            return "RFC faltante"
        # El RFC de persona moral tiene 12 caracteres (3 letras iniciales) y el
        # de persona física 13 (4 letras iniciales). Ambos llevan 6 dígitos de
        # fecha y 3 de homoclave.
        es_moral = self._es_moral_row(row)
        longitud = 12 if es_moral else 13
        n_letras = 3 if es_moral else 4
        fin_fecha = n_letras + 6
        errors = []
        if len(rfc) != longitud:
            errors.append(f"Longitud incorrecta: {len(rfc)} caracteres (esperado {longitud})")
        if len(rfc) >= n_letras and not re.match(r'^[A-Z]{%d}' % n_letras, rfc):
            errors.append(f"Primeros {n_letras} caracteres no son letras")
        if len(rfc) >= fin_fecha and not re.match(r'^[0-9]{6}$', rfc[n_letras:fin_fecha]):
            errors.append("Los 6 caracteres de la fecha no son números")
        if len(rfc) == longitud and not re.match(r'^[A-Z0-9]{3}$', rfc[fin_fecha:]):
            errors.append("Últimos 3 caracteres (homoclave) no son alfanuméricos")
        return "; ".join(errors) if errors else None

    def _validar_direccion(self, row):
        # Agregar validacion cuando la direccion viene dividida en columnas.
        col_dir = self.col_mapping.get('Dirección')
        # Caso 1: domicilio en una sola columna (tiene precedencia si está mapeada).
        if col_dir and col_dir in self.df.columns:
            valor = self._get_valor(row, 'Dirección')
            if pd.isna(valor) or valor == '':
                return "Dirección vacía"
            direc = str(valor)
            if direc.count(' ') + direc.count(',') < DIRECCION_MIN_SEPARADORES:
                return f"Dirección muy corta (menos de {DIRECCION_MIN_SEPARADORES} separadores)"
            return None
        # Caso 2: domicilio dividido en columnas. Se valida que cada parte
        # obligatoria mapeada venga llena (numero_interior es opcional) y que el
        # país, si se informa, sea reconocido.
        if any(self.col_mapping.get(c) for c in DIRECCION_PARTES):
            problemas = []
            faltantes = [campo for campo in DIRECCION_PARTES_REQUERIDAS
                         if self.col_mapping.get(campo)
                         and (lambda v: pd.isna(v) or str(v).strip() == '')(self._get_valor(row, campo))]
            if faltantes:
                problemas.append("falta " + ", ".join(faltantes))
            if self.col_mapping.get('pais'):
                v = self._get_valor(row, 'pais')
                if not (pd.isna(v) or str(v).strip() == '') and not es_pais_valido(v):
                    problemas.append(f"país '{v}' no reconocido")
            if problemas:
                return "Domicilio incompleto: " + "; ".join(problemas)
            return None
        return "Dirección vacía"

    def _validar_nivel_cuenta(self, row):
        valor = self._get_valor(row, 'Nivel_cuenta')
        if pd.isna(valor) or valor == '':
            return "Nivel de cuenta vacío"
        return None

    # ------------------------------------------------------------------
    # Validaciones entre filas
    # ------------------------------------------------------------------
    def _validar_ids_unicos(self):
        col_id = self.col_mapping.get('id_cliente')
        if col_id and col_id in self.df.columns:
            ids = self.df[col_id].astype(str).str.strip()
            duplicados = ids[ids.duplicated(keep=False)]
            if not duplicados.empty:
                base = self._obtener_columnas_base()
                cols = list(base.values()) + [col_id]
                df_dup = self.df.loc[duplicados.index, cols].copy()
                df_dup['Tipo_Error'] = 'ID duplicado'
                return df_dup
        return None

    def _validar_nombres_duplicados_con_curp(self):
        col_nombre = self.col_mapping.get('nombre')
        col_curp = self.col_mapping.get('CURP')
        if col_nombre and col_curp and col_nombre in self.df.columns and col_curp in self.df.columns:
            df_temp = self.df[[col_nombre, col_curp]].copy()
            df_temp = df_temp.dropna(subset=[col_curp])
            df_temp['nombre_norm'] = df_temp[col_nombre].astype(str).str.strip().str.lower()
            df_temp['curp'] = df_temp[col_curp].astype(str).str.strip().str.upper()
            # Excluir CURP vacíos/no válidos: si no, las personas morales (sin CURP)
            # se agruparían todas juntas y se marcarían como mismo CURP.
            df_temp = df_temp[~df_temp['curp'].isin(['', 'NAN', 'NONE', 'NULL'])]
            grupos = df_temp.groupby('curp')['nombre_norm'].nunique()
            curps_con_multiples = grupos[grupos > 1].index
            if not curps_con_multiples.empty:
                afectadas = df_temp[df_temp['curp'].isin(curps_con_multiples)].index
                base = self._obtener_columnas_base()
                cols = list(base.values()) + [col_nombre, col_curp]
                df_dup = self.df.loc[afectadas, cols].copy()
                df_dup['Tipo_Error'] = 'Mismo CURP con nombre diferente'
                return df_dup
        return None

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------
    def validar_todo(self, incluir_duplicados: bool = True) -> tuple[dict, int]:
        # incluir_duplicados=False omite la detección de duplicados (IDs y
        # nombre/CURP), que es global: al validar por lotes (SQLite) se calcula
        # sobre todo el conjunto, no lote por lote.
        self._estandarizar_fechas()
        errores_dataframes = {}
        errores_totales = 0
        current_date = pd.Timestamp(datetime.now())

        # Tipo de persona por fila (True = moral). Se usa para omitir en personas
        # morales las validaciones que solo aplican a persona física.
        es_moral = self._serie_es_moral()

        # 1. Celdas vacías en columnas críticas
        registros_con_nulos = []
        for campo in self.columnas_criticas:
            col = self.col_mapping.get(campo)
            if col and col in self.df.columns:
                nulos = self.df[self.df[col].isnull()].copy()
                # El género no aplica a personas morales: no marcar su vacío.
                if campo == 'genero' and not nulos.empty:
                    nulos = nulos[~es_moral.loc[nulos.index]]
                if not nulos.empty:
                    base = self._obtener_columnas_base()
                    cols = list(base.values()) + [col]
                    df_nulo = nulos[cols].copy()
                    if campo == 'fecha_nacimiento':
                        df_nulo['Tipo_Error'] = "Celda vacía en " + \
                            self._etiqueta_fecha_nac(df_nulo.index, es_moral)
                    else:
                        df_nulo['Tipo_Error'] = f"Celda vacía en {campo}"
                    registros_con_nulos.append(df_nulo)
        if registros_con_nulos:
            df_nulos = pd.concat(registros_con_nulos)
            errores_dataframes['Celdas Vacias'] = df_nulos
            errores_totales += len(df_nulos)

        # 2. IDs duplicados   y   3. Nombres duplicados con mismo CURP
        # (validaciones globales; se omiten en el modo por lotes)
        if incluir_duplicados:
            df_ids_dup = self._validar_ids_unicos()
            if df_ids_dup is not None:
                errores_dataframes['IDs Duplicados'] = df_ids_dup
                errores_totales += len(df_ids_dup)

            df_nombres_dup = self._validar_nombres_duplicados_con_curp()
            if df_nombres_dup is not None:
                errores_dataframes['Nombres Duplicados (CURP)'] = df_nombres_dup
                errores_totales += len(df_nombres_dup)

        # 4. Fechas futuras
        registros_futuros = []
        for campo in self.columnas_fecha:
            col = self.col_mapping.get(campo)
            # compat pandas>=3: antes era self.df[col].dtype == 'datetime64[ns]'
            if col and col in self.df.columns and pd.api.types.is_datetime64_any_dtype(self.df[col]):
                futuras = self.df[(self.df[col] > current_date) & self.df[col].notna()].copy()
                if not futuras.empty:
                    base = self._obtener_columnas_base()
                    cols = list(base.values()) + [col]
                    df_fut = futuras[cols].copy()
                    if campo == 'fecha_nacimiento':
                        etiqueta = self._etiqueta_fecha_nac(df_fut.index, es_moral)
                        df_fut['Tipo_Error'] = "Fecha futura en " + etiqueta
                        df_fut['Columna_Error'] = etiqueta
                    else:
                        df_fut['Tipo_Error'] = f"Fecha futura en {campo}"
                        df_fut['Columna_Error'] = campo
                    df_fut['Fecha_Afectada'] = df_fut[col].dt.strftime('%d/%m/%Y')
                    registros_futuros.append(df_fut)
        if registros_futuros:
            df_futuras = pd.concat(registros_futuros)
            errores_dataframes['Fechas Futuras'] = df_futuras
            errores_totales += len(df_futuras)

        # 5. Edades irrealistas y menores de 18 años
        col_nac = self.col_mapping.get('fecha_nacimiento')
        # compat pandas>=3: antes era self.df[col_nac].dtype == 'datetime64[ns]'
        if col_nac and col_nac in self.df.columns and pd.api.types.is_datetime64_any_dtype(self.df[col_nac]):
            df_temp = self.df.copy()
            df_temp['Edad'] = (current_date - df_temp[col_nac]).dt.days / 365.25
            # Los controles de edad solo aplican a persona física (en moral la
            # fecha es de constitución, sin límite de edad).
            irrealistas_idx = (((df_temp['Edad'] > 100) | (df_temp['Edad'] < 0))
                               & df_temp[col_nac].notna() & ~es_moral)
            if irrealistas_idx.any():
                base = self._obtener_columnas_base()
                cols = list(base.values()) + [col_nac]
                df_irr = self.df.loc[irrealistas_idx, cols].copy()
                df_irr['Edad'] = df_temp.loc[irrealistas_idx, 'Edad']
                df_irr['Tipo_Error'] = 'Edad irrealista'
                errores_dataframes['Edades Irrealistas'] = df_irr
                errores_totales += len(df_irr)
            menores_idx = (df_temp['Edad'] < 18) & ~es_moral
            if menores_idx.any():
                base = self._obtener_columnas_base()
                cols = list(base.values()) + [col_nac]
                df_men = self.df.loc[menores_idx, cols].copy()
                df_men['Edad'] = df_temp.loc[menores_idx, 'Edad']
                df_men['Tipo_Error'] = 'Menor de 18 años'
                errores_dataframes['Menores de 18 Años'] = df_men
                errores_totales += len(df_men)

        # 6. Teléfonos (longitud y dígitos repetidos)
        col_tel = self.col_mapping.get('Teléfono')
        if col_tel and col_tel in self.df.columns:
            df_temp = self.df.copy()
            df_temp['Telefono_Errors'] = df_temp.apply(self._validate_telefono_row, axis=1)
            invalidos_idx = df_temp['Telefono_Errors'].notna()
            if invalidos_idx.any():
                base = self._obtener_columnas_base()
                cols = list(base.values()) + [col_tel]
                df_inv = self.df.loc[invalidos_idx, cols].copy()
                df_inv['Tipo_Error'] = df_temp.loc[invalidos_idx, 'Telefono_Errors']
                errores_dataframes['Telefonos Invalidos'] = df_inv
                errores_totales += len(df_inv)

        # 7. CURP (solo persona física: las morales no tienen CURP)
        col_curp = self.col_mapping.get('CURP')
        if col_curp and col_curp in self.df.columns:
            df_temp = self.df.copy()
            df_temp['CURP_Validation_Errors'] = df_temp.apply(self._validate_curp_row, axis=1)
            curps_invalidos_idx = df_temp['CURP_Validation_Errors'].notna() & ~es_moral
            if curps_invalidos_idx.any():
                base = self._obtener_columnas_base()
                cols = list(base.values()) + [col_curp]
                df_curp = self.df.loc[curps_invalidos_idx, cols].copy()
                df_curp['Tipo_Error'] = df_temp.loc[curps_invalidos_idx, 'CURP_Validation_Errors']
                errores_dataframes['CURPs Invalidos'] = df_curp
                errores_totales += len(df_curp)

        # 8. RFC
        col_rfc = self.col_mapping.get('RFC')
        if col_rfc and col_rfc in self.df.columns:
            df_temp = self.df.copy()
            df_temp['RFC_Validation_Errors'] = df_temp.apply(self._validate_rfc_row, axis=1)
            rfcs_invalidos_idx = df_temp['RFC_Validation_Errors'].notna()
            if rfcs_invalidos_idx.any():
                base = self._obtener_columnas_base()
                cols = list(base.values()) + [col_rfc]
                df_rfc = self.df.loc[rfcs_invalidos_idx, cols].copy()
                df_rfc['Tipo_Error'] = df_temp.loc[rfcs_invalidos_idx, 'RFC_Validation_Errors']
                errores_dataframes['RFCs Invalidos'] = df_rfc
                errores_totales += len(df_rfc)

        # 9. Consistencia lugar de nacimiento
        col_entidad = self.col_mapping.get('entidad_federativa')
        col_pais = self.col_mapping.get('Pais_nacimiento')
        col_nacionalidad = self.col_mapping.get('Nacionalidad')
        if all(x is not None for x in [col_entidad, col_pais, col_nacionalidad]):
            df_temp = self.df.copy()
            df_temp['Entidad_norm'] = df_temp[col_entidad].astype(str).apply(self._normalizar_entidad)
            df_temp['Pais_es_mexico'] = df_temp[col_pais].apply(self._es_mexicano)
            df_temp['Nacionalidad_es_mexico'] = df_temp[col_nacionalidad].apply(self._es_mexicano)

            inconsistentes = df_temp[
                df_temp['Entidad_norm'].isin(ESTADOS_MEXICANOS_NORM) &
                (~df_temp['Pais_es_mexico'] | ~df_temp['Nacionalidad_es_mexico'])
            ].copy()

            if not inconsistentes.empty:
                base = self._obtener_columnas_base()
                cols = list(base.values()) + [col_entidad, col_pais, col_nacionalidad]
                df_inc = self.df.loc[inconsistentes.index, cols].copy()
                df_inc['Tipo_Error'] = 'Inconsistencia en lugar de nacimiento'
                errores_dataframes['Inconsistencias Nacimiento'] = df_inc
                errores_totales += len(df_inc)

        # 10. Otros errores (por fila)
        otros_errores = []
        for idx, row in self.df.iterrows():
            fila_num = idx + 2
            id_cliente = self._get_valor(row, 'id_cliente') if self.tiene_id else None

            def agregar(campo, error):
                otros_errores.append({
                    'fila': fila_num,
                    'id_cliente': id_cliente,
                    'campo': campo,
                    'error': error,
                    'valor': self._get_valor(row, campo)
                })

            validaciones = [
                ('id_cliente', self._validar_id_cliente),
                ('nombre', self._validar_nombre_completo),
                ('fecha_nacimiento', self._validar_fecha_nacimiento),
                ('genero', self._validar_genero),
                ('tipo de persona', self._validar_tipo_persona),
                ('estatus_cliente', self._validar_estatus_cliente),
                ('fecha_inicio_relacion', self._validar_fechas_relacion),
                ('grado_riesgo', self._validar_grado_riesgo),
                ('fecha_riesgo', self._validar_fecha_riesgo),
                ('PEP', self._validar_pep),
                ('Nacionalidad', self._validar_nacionalidad),
                ('Pais_nacimiento', self._validar_pais_nacimiento),
                ('entidad_federativa', self._validar_entidad_federativa),
                ('Actividad_generica', self._validar_actividades),
                ('Correo electronico', self._validar_correo),
                ('Dirección', self._validar_direccion),
                ('Nivel_cuenta', self._validar_nivel_cuenta)
            ]

            for campo, func in validaciones:
                err = func(row)
                if err:
                    agregar(campo, err)

        if otros_errores:
            df_otros = pd.DataFrame(otros_errores)
            errores_dataframes['Otros Errores'] = df_otros
            errores_totales += len(df_otros)

        logger.info("Validación completada: %d errores encontrados", errores_totales)
        return errores_dataframes, errores_totales
