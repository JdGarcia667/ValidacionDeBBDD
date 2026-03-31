import pandas as pd

class ReportGenerator:
    @staticmethod
    def generar_reporte(errores_dataframes, df_original, mapeo, archivo_salida):
        """
        errores_dataframes: dict {categoria: DataFrame con errores}
        df_original: DataFrame original (para la muestra)
        mapeo: dict con la asignación de columnas (campo -> nombre real)
        archivo_salida: ruta donde guardar el Excel
        """
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

            # Para cada categoría de error, escribir una hoja
            for tipo, df_error in errores_dataframes.items():
                sheet_name = tipo[:31]  # Excel limita a 31 caracteres
                # Limpiar el nombre de la hoja (caracteres no permitidos)
                sheet_name = sheet_name.replace(':', '_').replace('?', '_').replace('/', '_')
                df_error.to_excel(writer, sheet_name=sheet_name, index=False)

        return archivo_salida