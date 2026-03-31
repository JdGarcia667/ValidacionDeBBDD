import pandas as pd

class ReportGenerator:
    @staticmethod
    def generar_reporte(errores_dataframes, df_original, mapeo, archivo_salida, columnas_adicionales=None):
        """
        errores_dataframes: dict {categoria: DataFrame con errores}
        df_original: DataFrame original (para la muestra y para extraer columnas adicionales)
        mapeo: dict con la asignación de columnas (campo -> nombre real)
        archivo_salida: ruta donde guardar el Excel
        columnas_adicionales: lista de nombres de columnas del df_original a agregar en cada hoja de errores
        """
        if columnas_adicionales is None:
            columnas_adicionales = []

        # Validar que las columnas adicionales existan en el DataFrame original
        columnas_adicionales = [c for c in columnas_adicionales if c in df_original.columns]

        # Construir un diccionario rápido de índices a valores adicionales
        idx_to_extra = {}
        if columnas_adicionales:
            for idx, row in df_original.iterrows():
                idx_to_extra[idx] = {col: row[col] for col in columnas_adicionales}

        if not errores_dataframes:
            with pd.ExcelWriter(archivo_salida, engine='xlsxwriter') as writer:
                pd.DataFrame({"Mensaje": ["No se encontraron errores"]}).to_excel(
                    writer, sheet_name="Sin_errores", index=False
                )
            return archivo_salida

        with pd.ExcelWriter(archivo_salida, engine='xlsxwriter') as writer:
            # Hoja de mapeo
            mapeo_df = pd.DataFrame(list(mapeo.items()), columns=["Campo requerido", "Columna asignada"])
            mapeo_df.to_excel(writer, sheet_name="Mapeo", index=False)

            # Hoja de datos originales (muestra)
            df_original.head(100).to_excel(writer, sheet_name="Datos (muestra)", index=False)

            for tipo, df_error in errores_dataframes.items():
                sheet_name = tipo[:31].replace(':', '_').replace('?', '_').replace('/', '_')

                # Agregar columnas adicionales si existen
                if idx_to_extra and not df_error.empty:
                    for col_adic in columnas_adicionales:
                        valores = []
                        for idx in df_error.index:
                            # Nota: df_error puede tener un índice que no coincide con el original
                            # si se ha realizado alguna transformación. Por eso, primero intentamos
                            # con el índice original, pero si no, usamos None.
                            if idx in idx_to_extra:
                                valores.append(idx_to_extra[idx].get(col_adic, None))
                            else:
                                valores.append(None)
                        df_error[col_adic] = valores

                # Asegurar que las columnas base tengan nombres legibles (puede que ya estén)
                # Si el DataFrame ya tiene las columnas con nombres de campo, no hacemos nada.
                df_error.to_excel(writer, sheet_name=sheet_name, index=False)

        return archivo_salida