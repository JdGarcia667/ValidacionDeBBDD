import pandas as pd
import xml.etree.ElementTree as ET
import os

class FileReader:
    """Lee archivos de diferentes formatos y devuelve un DataFrame con los datos."""
    
    @staticmethod
    def read(file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.xlsx', '.xls']:
            return pd.read_excel(file_path, dtype=str)  # leer todo como texto para evitar inferencias
        elif ext == '.csv':
            return pd.read_csv(file_path, dtype=str, encoding='utf-8')
        elif ext == '.xml':
            return FileReader._read_xml(file_path)
        else:
            raise ValueError(f"Formato no soportado: {ext}")

    @staticmethod
    def _read_xml(file_path):
        # Ejemplo simple: asume que los datos están en elementos <row> con atributos o subelementos
        tree = ET.parse(file_path)
        root = tree.getroot()
        rows = []
        for elem in root.findall('.//row'):  # ajusta según la estructura de tu XML
            row_data = {}
            for child in elem:
                row_data[child.tag] = child.text
            rows.append(row_data)
        return pd.DataFrame(rows)