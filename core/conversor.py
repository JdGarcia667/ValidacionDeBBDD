import pandas as pd
import re

class ConversorMoneda:
    def __init__(self, df_operaciones, col_fecha, col_monto):
        self.df = df_operaciones.copy()
        self.col_fecha = col_fecha
        self.col_monto = col_monto
        self.df_udis = None
        self.df_tipo_cambio = None
        self.col_udi_fecha = None
        self.col_udi_valor = None
        self.col_tc_fecha = None
        self.col_tc_valor = None

    def _limpiar_serie_numerica(self, serie):
        serie_str = serie.astype(str)
        limpia = serie_str.str.replace(r'[^0-9.-]', '', regex=True)
        return pd.to_numeric(limpia, errors='coerce')

    def cargar_tasas_udis(self, archivo, mapeo):
        self.df_udis = pd.read_excel(archivo)
        self.col_udi_fecha = mapeo['fecha']
        self.col_udi_valor = mapeo['valor']
        self.df_udis[self.col_udi_fecha] = pd.to_datetime(self.df_udis[self.col_udi_fecha], errors='coerce', dayfirst=True)
        self.df_udis[self.col_udi_valor] = self._limpiar_serie_numerica(self.df_udis[self.col_udi_valor])
        self.df_udis = self.df_udis.dropna(subset=[self.col_udi_fecha, self.col_udi_valor])
        self.df_udis = self.df_udis.sort_values(self.col_udi_fecha)
        self.df_udis.set_index(self.col_udi_fecha, inplace=True)

    def cargar_tipo_cambio(self, archivo, mapeo):
        self.df_tipo_cambio = pd.read_excel(archivo)
        self.col_tc_fecha = mapeo['fecha']
        self.col_tc_valor = mapeo['valor']
        self.df_tipo_cambio[self.col_tc_fecha] = pd.to_datetime(self.df_tipo_cambio[self.col_tc_fecha], errors='coerce', dayfirst=True)
        self.df_tipo_cambio[self.col_tc_valor] = self._limpiar_serie_numerica(self.df_tipo_cambio[self.col_tc_valor])
        self.df_tipo_cambio = self.df_tipo_cambio.dropna(subset=[self.col_tc_fecha, self.col_tc_valor])
        self.df_tipo_cambio = self.df_tipo_cambio.sort_values(self.col_tc_fecha)
        self.df_tipo_cambio.set_index(self.col_tc_fecha, inplace=True)

    def aplicar_conversion(self, moneda_destino):
        """
        Usa merge asof (fecha más cercana) en lugar de apply para gran velocidad.
        """
        # Normalizar fechas en operaciones
        self.df['_fecha_norm'] = pd.to_datetime(self.df[self.col_fecha]).dt.normalize()
        self.df['_monto_limpio'] = self._limpiar_serie_numerica(self.df[self.col_monto])
        self.df = self.df.dropna(subset=['_monto_limpio'])

        if moneda_destino == 'UDIS':
            if self.df_udis is None or self.df_udis.empty:
                raise ValueError("No se cargaron datos de UDIS")
            # Reindex para merge asof
            df_tasas = self.df_udis.reset_index().rename(columns={self.col_udi_fecha: 'fecha', self.col_udi_valor: 'tasa'})
            # Merge asof: para cada operación, toma la tasa de la fecha más cercana anterior o igual
            self.df = pd.merge_asof(
                self.df.sort_values('_fecha_norm'),
                df_tasas.sort_values('fecha'),
                left_on='_fecha_norm',
                right_on='fecha',
                direction='backward'  # tasa del día o anterior
            )
            self.df['monto_convertido'] = self.df['_monto_limpio'] / self.df['tasa']
            self.df = self.df.drop(columns=['fecha', 'tasa', '_fecha_norm', '_monto_limpio'])

        elif moneda_destino == 'DOLARES':
            if self.df_tipo_cambio is None or self.df_tipo_cambio.empty:
                raise ValueError("No se cargaron datos de tipo de cambio")
            df_tc = self.df_tipo_cambio.reset_index().rename(columns={self.col_tc_fecha: 'fecha', self.col_tc_valor: 'tc'})
            self.df = pd.merge_asof(
                self.df.sort_values('_fecha_norm'),
                df_tc.sort_values('fecha'),
                left_on='_fecha_norm',
                right_on='fecha',
                direction='backward'
            )
            self.df['monto_convertido'] = self.df['_monto_limpio'] * self.df['tc']
            self.df = self.df.drop(columns=['fecha', 'tc', '_fecha_norm', '_monto_limpio'])

        else:  # MONEDA NACIONAL
            self.df['monto_convertido'] = self.df['_monto_limpio']
            self.df = self.df.drop(columns=['_fecha_norm', '_monto_limpio'])

        return self.df