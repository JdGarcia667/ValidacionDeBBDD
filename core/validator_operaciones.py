import pandas as pd
import numpy as np
import re
from core.conversor import ConversorMoneda

class ValidatorOperaciones:
    def __init__(self, df, mapeo, config, update_callback=None):
        """
        df: DataFrame con las operaciones
        mapeo: dict {campo_requerido: nombre_columna_real}
        config: dict con configuración de validación (moneda, agrupación, filtros, archivos de conversión)
        update_callback: función opcional para actualizar la interfaz (mensaje)
        """
        self.df = df.copy()
        self.mapeo = mapeo
        self.config = config
        self.update_callback = update_callback
        self.errores_dataframes = {}

    def _limpiar_numero_vectorizado(self, serie):
        """Limpia y convierte a número una serie de pandas de forma vectorizada."""
        serie_str = serie.astype(str)
        limpia = serie_str.str.replace(r'[^0-9.-]', '', regex=True)
        return pd.to_numeric(limpia, errors='coerce')

    def validar_todo(self):
        if self.update_callback:
            self.update_callback("Validando columnas...")

        # 1. Obtener columnas del mapeo
        col_id_cuenta = self.mapeo.get('id_cuenta')
        col_tipo_op = self.mapeo.get('tipo_operacion')
        col_fecha = self.mapeo.get('fecha_operacion')
        col_monto = self.mapeo.get('monto')
        col_instrumento = self.mapeo.get('instrumento_monetario')
        col_id_cliente = self.mapeo.get('id_cliente')
        col_id_operacion = self.mapeo.get('id_operacion')
        col_nivel = self.mapeo.get('nivel_cuenta')

        # Validar columnas obligatorias
        obligatorias = [col_id_cuenta, col_tipo_op, col_fecha, col_monto]
        if any(c is None for c in obligatorias):
            faltantes = [k for k, v in zip(['id_cuenta', 'tipo_operacion', 'fecha_operacion', 'monto'], obligatorias) if v is None]
            raise ValueError(f"Faltan columnas obligatorias en el mapeo: {faltantes}")

        if self.update_callback:
            self.update_callback("Convirtiendo fechas...")

        # 2. Convertir fechas (formato día/mes/año)
        self.df[col_fecha] = pd.to_datetime(self.df[col_fecha], errors='coerce', dayfirst=True)
        self.df = self.df.dropna(subset=[col_fecha])
        self.df['mes'] = self.df[col_fecha].dt.to_period('M')

        if self.update_callback:
            self.update_callback("Limpiando montos...")

        # 3. Limpiar montos y crear columna numérica
        self.df['monto_limpio'] = self._limpiar_numero_vectorizado(self.df[col_monto])
        self.df = self.df.dropna(subset=['monto_limpio'])

        if self.df.empty:
            return {}, 0

        # 4. Conversión de moneda
        moneda = self.config.get('moneda', 'MONEDA NACIONAL')
        col_monto_analisis = 'monto_limpio'

        if moneda != 'MONEDA NACIONAL':
            if self.update_callback:
                self.update_callback(f"Preparando conversión a {moneda}...")

            conversor = ConversorMoneda(self.df, col_fecha, 'monto_limpio')
            try:
                if moneda in ['UDIS', 'TODAS'] and self.config.get('archivo_udis'):
                    conversor.cargar_tasas_udis(self.config['archivo_udis'], self.config['mapeo_udis'])
                if moneda in ['DOLARES', 'TODAS'] and self.config.get('archivo_tc'):
                    conversor.cargar_tipo_cambio(self.config['archivo_tc'], self.config['mapeo_tc'])

                self.df = conversor.aplicar_conversion(moneda)
                col_monto_analisis = 'monto_convertido'
                self.df = self.df.dropna(subset=[col_monto_analisis])

                if self.df.empty:
                    if self.update_callback:
                        self.update_callback("No se pudo realizar la conversión (datos insuficientes)")
                    return {}, 0

            except Exception as e:
                if self.update_callback:
                    self.update_callback(f"Error en conversión: {str(e)[:100]}")
                return {}, 0

        else:
            self.df['monto_convertido'] = self.df['monto_limpio']
            col_monto_analisis = 'monto_convertido'

        # 5. Agrupación según configuración
        if self.update_callback:
            self.update_callback("Agrupando operaciones...")

        agrupacion = self.config.get('agrupacion', 'por_instrumento')
        if agrupacion == 'por_instrumento' and col_instrumento:
            group_cols = [col_id_cuenta, col_tipo_op, 'mes', col_instrumento]
        else:
            group_cols = [col_id_cuenta, col_tipo_op, 'mes']

        grouped = self.df.groupby(group_cols).agg(
            total_monto=(col_monto_analisis, 'sum'),
            cantidad_operaciones=(col_monto_analisis, 'count'),
            monto_pesos=('monto_limpio', 'sum')
        ).reset_index()

        # Agregar id_cliente si existe
        if col_id_cliente and col_id_cliente in self.df.columns:
            clientes_por_cuenta = self.df.groupby(col_id_cuenta)[col_id_cliente].first().to_dict()
            grouped['id_cliente'] = grouped[col_id_cuenta].map(clientes_por_cuenta)

        # 6. Aplicar filtros de monto
        filtros = self.config.get('filtros', [])
        if not filtros:
            return {}, 0

        if self.update_callback:
            self.update_callback("Aplicando filtros...")

        hallazgos = []
        for _, row in grouped.iterrows():
            monto = row['total_monto']
            for operador, limite in filtros:
                cumple = False
                if operador == '>' and monto > limite:
                    cumple = True
                elif operador == '<' and monto < limite:
                    cumple = True
                elif operador == '>=' and monto >= limite:
                    cumple = True
                elif operador == '<=' and monto <= limite:
                    cumple = True
                if cumple:
                    registro = row.to_dict()
                    registro['Tipo_Error'] = f"Monto {monto:.2f} {operador} {limite}"
                    hallazgos.append(registro)
                    break  # Evita duplicados por múltiples filtros

        if hallazgos:
            df_hallazgos = pd.DataFrame(hallazgos)
            # Redondear columnas numéricas
            for col in ['total_monto', 'monto_pesos']:
                if col in df_hallazgos.columns:
                    df_hallazgos[col] = df_hallazgos[col].round(2)
            self.errores_dataframes['Operaciones con excesos'] = df_hallazgos
            total_errores = len(df_hallazgos)
        else:
            total_errores = 0

        if self.update_callback:
            self.update_callback(f"Validación completada. {total_errores} hallazgos encontrados.")

        return self.errores_dataframes, total_errores