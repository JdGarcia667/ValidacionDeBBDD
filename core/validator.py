import pandas as pd
import re
from datetime import datetime, date

class Validator:
    def __init__(self, df, mapeo, tipo_persona_default=None):
        self.df = df
        self.mapeo = mapeo
        self.tipo_persona_default = tipo_persona_default

        # Normalización de nombres de columnas reales del DataFrame
        self.real_columns = {self._normalizar_columna(c): c for c in self.df.columns}
        self.col_mapping = {}
        for campo, col_mapeada in self.mapeo.items():
            if col_mapeada:
                col_norm = self._normalizar_columna(col_mapeada)
                if col_norm in self.real_columns:
                    self.col_mapping[campo] = self.real_columns[col_norm]
                else:
                    self.col_mapping[campo] = None
            else:
                self.col_mapping[campo] = None

        self.col_id = self.col_mapping.get('id_cliente')
        self.tiene_id = self.col_id is not None

        # Columnas críticas (para celdas vacías)
        self.columnas_criticas = [
            'id_cliente', 'nombre', 'fecha_nacimiento', 'fecha_inicio_relacion',
            'Dirección', 'genero', 'Actividad_especifica', 'Correo electronico'
        ]

        # Columnas de fecha para estandarización y validación de fechas futuras
        self.columnas_fecha = [
            'fecha_nacimiento', 'fecha_inicio_relacion', 'fecha_termino_relacion', 'fecha_riesgo'
        ]

    # --------------------------------------------------------------
    # Métodos auxiliares (normalización, acceso a valores)
    # --------------------------------------------------------------
    def _normalizar_columna(self, nombre):
        if not isinstance(nombre, str):
            return ""
        nombre = nombre.lower().strip()
        nombre = re.sub(r'[áàäâ]', 'a', nombre)
        nombre = re.sub(r'[éèëê]', 'e', nombre)
        nombre = re.sub(r'[íìïî]', 'i', nombre)
        nombre = re.sub(r'[óòöô]', 'o', nombre)
        nombre = re.sub(r'[úùüû]', 'u', nombre)
        nombre = re.sub(r'[^a-z0-9\s]', '', nombre)
        nombre = re.sub(r'\s+', ' ', nombre)
        return nombre

    def _get_valor(self, row, campo):
        col = self.col_mapping.get(campo)
        if col and col in self.df.columns:
            return row[col]
        return None

    # --------------------------------------------------------------
    # Conversión de fechas (formato día-mes-año)
    # --------------------------------------------------------------
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
                    if año > 50:
                        año += 1900
                    else:
                        año += 2000
                if 1 <= mes <= 12 and 1 <= dia <= 31 and 1900 <= año <= 2100:
                    return pd.Timestamp(year=año, month=mes, day=dia)
        except:
            pass
        return pd.NaT

    def _estandarizar_fechas(self):
        for campo in self.columnas_fecha:
            col = self.col_mapping.get(campo)
            if col and col in self.df.columns:
                self.df[col] = self.df[col].apply(self._convertir_fecha_dia_mes)

    # --------------------------------------------------------------
    # Funciones de validación específicas (basadas en tu script de Colab)
    # --------------------------------------------------------------
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
        # Validar género
        col_genero = self.col_mapping.get('genero')
        if col_genero and col_genero in self.df.columns:
            gender_data = str(row[col_genero]).strip().upper()
            expected = ''
            if gender_data in ['MALE', 'M', 'HOMBRE', 'H']:
                expected = 'H'
            elif gender_data in ['FEMALE', 'F', 'MUJER', 'M']:
                expected = 'M'
            if expected and curp[10] != expected:
                errors.append(f"Error Género: Esperado '{expected}', Obtenido '{curp[10]}'")
        return "; ".join(errors) if errors else None

    def _validate_rfc_row(self, row):
        col_rfc = self.col_mapping.get('RFC')
        if not col_rfc or col_rfc not in self.df.columns:
            return "Columna RFC no encontrada"
        rfc = str(row[col_rfc]).strip().upper()
        if rfc in ['NAN', '', 'NONE', 'NULL']:
            return "RFC faltante"
        errors = []
        if len(rfc) != 13:
            errors.append(f"Longitud incorrecta: {len(rfc)} caracteres")
        if len(rfc) >= 4 and not re.match(r'^[A-Z]{4}', rfc):
            errors.append("Primeros 4 caracteres no son letras")
        if len(rfc) >= 10 and not re.match(r'^[0-9]{6}', rfc[4:10]):
            errors.append("Caracteres del 5 al 10 no son números")
        if len(rfc) == 13 and not re.match(r'^[A-Z0-9]{3}$', rfc[10:]):
            errors.append("Últimos 3 caracteres no son alfanuméricos")
        return "; ".join(errors) if errors else None

    # --------------------------------------------------------------
    # Validaciones originales (que ya estaban)
    # --------------------------------------------------------------
    def _validar_nombre_completo(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'nombre')
        if pd.isna(valor) or valor == '':
            return "Nombre vacío"
        if valor.count(' ') < 1:
            return "Nombre incompleto (debe tener al menos un espacio)"
        return None

    def _validar_fecha_nacimiento_edad(self, row, fila, id_cliente):
        col = self.col_mapping.get('fecha_nacimiento')
        if not col or col not in self.df.columns:
            return None
        valor = row[col]
        if pd.isna(valor) or valor == '':
            return "Fecha de nacimiento vacía"
        try:
            fecha = pd.to_datetime(valor, errors='coerce')
            if pd.isna(fecha):
                return "Fecha inválida"
            hoy = date.today()
            edad = hoy.year - fecha.year - ((hoy.month, hoy.day) < (fecha.month, fecha.day))
            if edad < 18:
                return f"Edad {edad} años menor a 18"
            elif edad > 120:
                return f"Edad {edad} años mayor a 120"
        except:
            return "Fecha no procesable"
        return None

    def _validar_genero(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'genero')
        if pd.isna(valor) or valor == '':
            return "Género vacío"
        return None

    def _validar_tipo_persona(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'tipo de persona')
        if valor is None and self.tipo_persona_default:
            return None
        if pd.isna(valor) or valor == '':
            return "Tipo de persona vacío"
        return None

    def _validar_estatus_cliente(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'estatus_cliente')
        if pd.isna(valor) or valor == '':
            return "Estatus vacío"
        return None

    def _validar_fechas_relacion(self, row, fila, id_cliente):
        fecha_inicio = self._get_valor(row, 'fecha_inicio_relacion')
        fecha_termino = self._get_valor(row, 'fecha_termino_relacion')
        estatus = self._get_valor(row, 'estatus_cliente')

        if pd.isna(fecha_inicio) or fecha_inicio == '':
            return "Fecha inicio relación vacía"
        try:
            f_ini = pd.to_datetime(fecha_inicio, errors='coerce')
            if pd.isna(f_ini):
                return "Fecha inicio inválida"
        except:
            return "Fecha inicio inválida"

        if not (pd.isna(fecha_termino) or fecha_termino == ''):
            try:
                f_ter = pd.to_datetime(fecha_termino, errors='coerce')
                if pd.isna(f_ter):
                    return "Fecha término inválida"
                if f_ter < f_ini:
                    return "Fecha término anterior a fecha inicio"
            except:
                return "Fecha término inválida"

        if estatus and isinstance(estatus, str) and 'activo' in estatus.lower():
            if not (pd.isna(fecha_termino) or fecha_termino == ''):
                return "Cliente activo con fecha de término"
        return None

    def _validar_grado_riesgo(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'grado_riesgo')
        if pd.isna(valor) or valor == '':
            return "Grado de riesgo vacío"
        return None

    def _validar_fecha_riesgo(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'fecha_riesgo')
        if pd.isna(valor) or valor == '':
            return "Fecha de riesgo vacía"
        try:
            if pd.isna(pd.to_datetime(valor, errors='coerce')):
                return "Fecha de riesgo inválida"
        except:
            return "Fecha de riesgo inválida"
        return None

    def _validar_pep(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'PEP')
        if pd.isna(valor) or valor == '':
            return "PEP vacío"
        return None

    def _validar_nacionalidad(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'Nacionalidad')
        if pd.isna(valor) or valor == '':
            return "Nacionalidad vacía"
        return None

    def _validar_pais_nacimiento(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'Pais_nacimiento')
        if pd.isna(valor) or valor == '':
            return "País de nacimiento vacío"
        return None

    def _validar_entidad_federativa(self, row, fila, id_cliente):
        entidad = self._get_valor(row, 'entidad_federativa')
        pais = self._get_valor(row, 'Pais_nacimiento')
        if pd.isna(entidad) or entidad == '':
            return "Entidad federativa vacía"
        if pais and 'méxico' in str(pais).lower():
            estados_mexicanos = [
                'AGUASCALIENTES', 'BAJA CALIFORNIA', 'BAJA CALIFORNIA SUR', 'CAMPECHE', 'COAHUILA',
                'COLIMA', 'CHIAPAS', 'CHIHUAHUA', 'CIUDAD DE MÉXICO', 'DURANGO', 'GUANAJUATO',
                'GUERRERO', 'HIDALGO', 'JALISCO', 'MÉXICO', 'MICHOACÁN', 'MORELOS', 'NAYARIT',
                'NUEVO LEÓN', 'OAXACA', 'PUEBLA', 'QUERÉTARO', 'QUINTANA ROO', 'SAN LUIS POTOSÍ',
                'SINALOA', 'SONORA', 'TABASCO', 'TAMAULIPAS', 'TLAXCALA', 'VERACRUZ', 'YUCATÁN', 'ZACATECAS', 'CDMX'
            ]
            if str(entidad).upper() not in estados_mexicanos:
                return f"Entidad '{entidad}' no válida para México"
        return None

    def _validar_actividades(self, row, fila, id_cliente):
        act_gen = self._get_valor(row, 'Actividad_generica')
        act_esp = self._get_valor(row, 'Actividad_especifica')
        if (pd.isna(act_gen) or act_gen == '') and (pd.isna(act_esp) or act_esp == ''):
            return "Ambas actividades vacías"
        return None

    def _validar_telefono(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'Teléfono')
        if pd.isna(valor) or valor == '':
            return "Teléfono vacío"
        telefono_limpio = re.sub(r'\D', '', str(valor))
        if len(telefono_limpio) < 10:
            return f"Teléfono con {len(telefono_limpio)} dígitos, mínimo 10"
        if re.search(r'(\d)\1{4}', telefono_limpio):
            return "Teléfono con 5 dígitos consecutivos repetidos"
        return None

    def _validar_correo(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'Correo electronico')
        if pd.isna(valor) or valor == '':
            return "Correo vacío"
        if '@' not in str(valor):
            return "Correo sin @"
        return None

    def _validar_curp(self, row, fila, id_cliente):
        # Usa la función de Colab (ya incluye género y formato)
        return self._validate_curp_row(row)

    def _validar_rfc(self, row, fila, id_cliente):
        # Usa la función de Colab (solo formato básico; luego podemos ampliar con tipo persona)
        # Pero también incorporamos la lógica de tipo de persona si se desea.
        rfc_error = self._validate_rfc_row(row)
        if rfc_error:
            return rfc_error
        # Validación adicional por tipo de persona (física/moral) si existe la columna
        tipo_persona = self._get_valor(row, 'tipo de persona')
        if pd.isna(tipo_persona) or tipo_persona == '':
            tipo_persona = self.tipo_persona_default
        if tipo_persona:
            rfc = str(self._get_valor(row, 'RFC')).strip().upper()
            if 'física' in tipo_persona.lower() and len(rfc) != 13:
                return "RFC física debe tener 13 caracteres"
            elif 'moral' in tipo_persona.lower() and len(rfc) != 12:
                return "RFC moral debe tener 12 caracteres"
        return None

    def _validar_direccion(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'Dirección')
        if pd.isna(valor) or valor == '':
            return "Dirección vacía"
        direc = str(valor)
        if direc.count(' ') + direc.count(',') < 5:
            return "Dirección muy corta (menos de 5 separadores)"
        return None

    def _validar_nivel_cuenta(self, row, fila, id_cliente):
        valor = self._get_valor(row, 'Nivel_cuenta')
        if pd.isna(valor) or valor == '':
            return "Nivel de cuenta vacío"
        return None

    # --------------------------------------------------------------
    # Validaciones entre filas
    # --------------------------------------------------------------
    def _validar_ids_unicos(self):
        col_id = self.col_mapping.get('id_cliente')
        if col_id and col_id in self.df.columns:
            ids = self.df[col_id].astype(str).str.strip()
            duplicados = ids[ids.duplicated(keep=False)]
            if not duplicados.empty:
                df_dup = self.df.loc[duplicados.index].copy()
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
            grupos = df_temp.groupby('curp')['nombre_norm'].nunique()
            curps_con_multiples = grupos[grupos > 1].index
            if not curps_con_multiples.empty:
                df_dup = df_temp[df_temp['curp'].isin(curps_con_multiples)].copy()
                df_dup['Tipo_Error'] = 'Mismo CURP con nombre diferente'
                return df_dup
        return None

    # --------------------------------------------------------------
    # Método principal que integra todas las validaciones
    # --------------------------------------------------------------
    def validar_todo(self):
        """Ejecuta todas las validaciones y retorna un diccionario con DataFrames de errores."""
        self._estandarizar_fechas()
        errores_dataframes = {}
        errores_totales = 0
        current_date = pd.Timestamp(datetime.now())

        # 1. Celdas vacías en columnas críticas (versión original, usando las columnas mapeadas)
        registros_con_nulos = []
        for campo in self.columnas_criticas:
            col = self.col_mapping.get(campo)
            if col and col in self.df.columns:
                nulos = self.df[self.df[col].isnull()].copy()
                if not nulos.empty:
                    nulos['Tipo_Error'] = f"Celda vacía en {campo}"
                    registros_con_nulos.append(nulos)
        if registros_con_nulos:
            df_nulos = pd.concat(registros_con_nulos)
            errores_dataframes['Celdas Vacias'] = df_nulos
            errores_totales += len(df_nulos)

        # 2. IDs duplicados
        df_ids_dup = self._validar_ids_unicos()
        if df_ids_dup is not None:
            errores_dataframes['IDs Duplicados'] = df_ids_dup
            errores_totales += len(df_ids_dup)

        # 3. Nombres duplicados con mismo CURP
        df_nombres_dup = self._validar_nombres_duplicados_con_curp()
        if df_nombres_dup is not None:
            errores_dataframes['Nombres Duplicados (CURP)'] = df_nombres_dup
            errores_totales += len(df_nombres_dup)

        # 4. Fechas futuras (Colab style)
        registros_futuros = []
        for campo in self.columnas_fecha:
            col = self.col_mapping.get(campo)
            if col and col in self.df.columns and self.df[col].dtype == 'datetime64[ns]':
                futuras = self.df[(self.df[col] > current_date) & self.df[col].notna()].copy()
                if not futuras.empty:
                    futuras['Tipo_Error'] = f"Fecha futura en {campo}"
                    futuras['Columna_Error'] = campo
                    futuras['Fecha_Afectada'] = futuras[col].dt.strftime('%d/%m/%Y')
                    registros_futuros.append(futuras)
        if registros_futuros:
            df_futuras = pd.concat(registros_futuros)
            errores_dataframes['Fechas Futuras'] = df_futuras
            errores_totales += len(df_futuras)

        # 5. Edades irrealistas y menores de 18 años (Colab style)
        col_nac = self.col_mapping.get('fecha_nacimiento')
        if col_nac and col_nac in self.df.columns and self.df[col_nac].dtype == 'datetime64[ns]':
            df_temp = self.df.copy()
            df_temp['Edad'] = (current_date - df_temp[col_nac]).dt.days / 365.25
            irrealistas = df_temp[((df_temp['Edad'] > 100) | (df_temp['Edad'] < 0)) & df_temp[col_nac].notna()].copy()
            if not irrealistas.empty:
                irrealistas['Tipo_Error'] = 'Edad irrealista'
                errores_dataframes['Edades Irrealistas'] = irrealistas
                errores_totales += len(irrealistas)
            menores = df_temp[df_temp['Edad'] < 18].copy()
            if not menores.empty:
                menores['Tipo_Error'] = 'Menor de 18 años'
                errores_dataframes['Menores de 18 Años'] = menores
                errores_totales += len(menores)

        # 6. Teléfonos (10 dígitos) - Colab style
        col_tel = self.col_mapping.get('Teléfono')
        if col_tel and col_tel in self.df.columns:
            df_temp = self.df.copy()
            df_temp['Telefono_cleaned'] = df_temp[col_tel].astype(str).str.replace(r'[^0-9]', '', regex=True)
            invalidos = df_temp[
                (df_temp['Telefono_cleaned'].str.len() != 10) &
                (df_temp['Telefono_cleaned'] != '') &
                (df_temp['Telefono_cleaned'] != 'nan')
            ].copy()
            if not invalidos.empty:
                invalidos['Tipo_Error'] = 'Longitud de teléfono incorrecta'
                errores_dataframes['Telefonos Invalidos'] = invalidos
                errores_totales += len(invalidos)

        # 7. CURP - Colab style (ya incluye género)
        col_curp = self.col_mapping.get('CURP')
        if col_curp and col_curp in self.df.columns:
            df_temp = self.df.copy()
            df_temp['CURP_Validation_Errors'] = df_temp.apply(self._validate_curp_row, axis=1)
            curps_invalidos = df_temp[df_temp['CURP_Validation_Errors'].notna()].copy()
            if not curps_invalidos.empty:
                curps_invalidos['Tipo_Error'] = curps_invalidos['CURP_Validation_Errors']
                errores_dataframes['CURPs Invalidos'] = curps_invalidos
                errores_totales += len(curps_invalidos)

        # 8. RFC - Colab style (con opción de validación por tipo de persona)
        col_rfc = self.col_mapping.get('RFC')
        if col_rfc and col_rfc in self.df.columns:
            df_temp = self.df.copy()
            df_temp['RFC_Validation_Errors'] = df_temp.apply(self._validate_rfc_row, axis=1)  # Usa la función que solo recibe la fila
            rfcs_invalidos = df_temp[df_temp['RFC_Validation_Errors'].notna()].copy()
            if not rfcs_invalidos.empty:
               rfcs_invalidos['Tipo_Error'] = rfcs_invalidos['RFC_Validation_Errors']
               errores_dataframes['RFCs Invalidos'] = rfcs_invalidos
               errores_totales += len(rfcs_invalidos)

        # 9. Consistencia lugar de nacimiento (entidad vs país) - Colab style
        col_entidad = self.col_mapping.get('entidad_federativa')
        col_pais = self.col_mapping.get('Pais_nacimiento')
        col_nacionalidad = self.col_mapping.get('Nacionalidad')
        if all(x is not None for x in [col_entidad, col_pais, col_nacionalidad]):
            estados_mexicanos = [
                'AGUASCALIENTES', 'BAJA CALIFORNIA', 'BAJA CALIFORNIA SUR', 'CAMPECHE', 'COAHUILA',
                'COLIMA', 'CHIAPAS', 'CHIHUAHUA', 'CIUDAD DE MÉXICO', 'DURANGO', 'GUANAJUATO',
                'GUERRERO', 'HIDALGO', 'JALISCO', 'MÉXICO', 'MICHOACÁN', 'MORELOS', 'NAYARIT',
                'NUEVO LEÓN', 'OAXACA', 'PUEBLA', 'QUERÉTARO', 'QUINTANA ROO', 'SAN LUIS POTOSÍ',
                'SINALOA', 'SONORA', 'TABASCO', 'TAMAULIPAS', 'TLAXCALA', 'VERACRUZ', 'YUCATÁN', 'ZACATECAS'
            ]
            df_temp = self.df.copy()
            df_temp['Entidad_norm'] = df_temp[col_entidad].astype(str).str.upper().str.strip()
            inconsistentes = df_temp[
                df_temp['Entidad_norm'].isin(estados_mexicanos) &
                (
                    (df_temp[col_pais].astype(str).str.upper().str.strip() != 'MÉXICO') |
                    (df_temp[col_nacionalidad].astype(str).str.upper().str.strip() != 'MEXICO')
                )
            ].copy()
            if not inconsistentes.empty:
                inconsistentes['Tipo_Error'] = 'Inconsistencia en lugar de nacimiento'
                errores_dataframes['Inconsistencias Nacimiento'] = inconsistentes
                errores_totales += len(inconsistentes)

        # 10. Validaciones por fila de los campos restantes (las que no están en los grupos anteriores)
        # Recorremos cada fila y aplicamos las validaciones que devuelven errores individuales.
        # Agruparemos los errores en un DataFrame por tipo (ej: "Nombre incompleto", "Género vacío", etc.)
        # Para mantener la estructura de hojas, podemos juntar todos estos en una hoja "Otros Errores".
        otros_errores = []
        for idx, row in self.df.iterrows():
            fila_num = idx + 2
            id_cliente = self._get_valor(row, 'id_cliente') if self.tiene_id else None

            # Función auxiliar para agregar error
            def agregar(campo, error):
                otros_errores.append({
                    'fila': fila_num,
                    'id_cliente': id_cliente,
                    'campo': campo,
                    'error': error,
                    'valor': self._get_valor(row, campo)
                })

            # Validación de nombre completo
            err = self._validar_nombre_completo(row, fila_num, id_cliente)
            if err:
                agregar('nombre', err)

            # Fecha de nacimiento (edad) - ya la tenemos en las hojas de edades, pero también la incluimos aquí si queremos
            # (podríamos omitirla porque ya está cubierta, pero la dejamos por si acaso)
            err = self._validar_fecha_nacimiento_edad(row, fila_num, id_cliente)
            if err:
                agregar('fecha_nacimiento', err)

            # Género
            err = self._validar_genero(row, fila_num, id_cliente)
            if err:
                agregar('genero', err)

            # Tipo de persona
            err = self._validar_tipo_persona(row, fila_num, id_cliente)
            if err:
                agregar('tipo de persona', err)

            # Estatus cliente
            err = self._validar_estatus_cliente(row, fila_num, id_cliente)
            if err:
                agregar('estatus_cliente', err)

            # Fechas relación
            err = self._validar_fechas_relacion(row, fila_num, id_cliente)
            if err:
                agregar('fecha_inicio_relacion', err)

            # Grado riesgo
            err = self._validar_grado_riesgo(row, fila_num, id_cliente)
            if err:
                agregar('grado_riesgo', err)

            # Fecha riesgo
            err = self._validar_fecha_riesgo(row, fila_num, id_cliente)
            if err:
                agregar('fecha_riesgo', err)

            # PEP
            err = self._validar_pep(row, fila_num, id_cliente)
            if err:
                agregar('PEP', err)

            # Nacionalidad
            err = self._validar_nacionalidad(row, fila_num, id_cliente)
            if err:
                agregar('Nacionalidad', err)

            # País nacimiento
            err = self._validar_pais_nacimiento(row, fila_num, id_cliente)
            if err:
                agregar('Pais_nacimiento', err)

            # Entidad federativa
            err = self._validar_entidad_federativa(row, fila_num, id_cliente)
            if err:
                agregar('entidad_federativa', err)

            # Actividades
            err = self._validar_actividades(row, fila_num, id_cliente)
            if err:
                agregar('Actividad_generica', err)

            # Teléfono (ya lo tenemos en hoja separada, pero incluimos también aquí? podemos omitir)
            # err = self._validar_telefono(row, fila_num, id_cliente)
            # if err:
            #     agregar('Teléfono', err)

            # Correo
            err = self._validar_correo(row, fila_num, id_cliente)
            if err:
                agregar('Correo electronico', err)

            # CURP (ya en hoja separada)
            # RFC (ya en hoja separada)
            # Dirección
            err = self._validar_direccion(row, fila_num, id_cliente)
            if err:
                agregar('Dirección', err)

            # Nivel cuenta
            err = self._validar_nivel_cuenta(row, fila_num, id_cliente)
            if err:
                agregar('Nivel_cuenta', err)

        if otros_errores:
            df_otros = pd.DataFrame(otros_errores)
            errores_dataframes['Otros Errores'] = df_otros
            errores_totales += len(df_otros)

        return errores_dataframes, errores_totales