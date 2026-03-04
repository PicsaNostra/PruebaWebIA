import streamlit as st
import pandas as pd
from datetime import datetime
import os
from github import Github # Librería para conectar con la nube

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Automático", layout="wide")
st.title("🛠️ Planificador de Repuestos (Guardado Automático)")

# Nombres de archivos
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_CSV = "datos_gestion.csv"
REPO_NOMBRE = "tu_usuario/control-repuestos" # <--- CAMBIA ESTO POR TU USUARIO/REPOSITORIO

# --- CONEXIÓN CON GITHUB ---
def subir_a_github(df_nuevo):
    """Sube el archivo CSV directamente a GitHub usando el Token"""
    try:
        # 1. Conectarse usando el secreto
        token = st.secrets["GITHUB_TOKEN"]
        g = Github(token)
        
        # 2. Buscar el repositorio (Intenta detectar el nombre automáticamente si falla el manual)
        # Nota: Debes poner tu nombre de usuario y repo correctamente arriba
        try:
            repo = g.get_user().get_repo("control-repuestos") # Asegúrate que tu repo se llame así
        except:
            st.error("No encuentro el repositorio. Verifica el nombre en el código.")
            return

        # 3. Convertir DataFrame a CSV (Texto)
        content_csv = df_nuevo.to_csv(index=False)

        # 4. Intentar actualizar o crear el archivo
        try:
            # Si el archivo ya existe, lo actualizamos
            contents = repo.get_contents(ARCHIVO_CSV)
            repo.update_file(contents.path, "Actualización automática desde App", content_csv, contents.sha)
            st.toast("✅ Cambios guardados en la Nube (GitHub) exitosamente!", icon="☁️")
        except:
            # Si no existe, lo creamos
            repo.create_file(ARCHIVO_CSV, "Creación inicial automática", content_csv)
            st.toast("✅ Archivo creado en la Nube exitosamente!", icon="✨")
            
    except Exception as e:
        st.error(f"Error guardando en GitHub: {e}")

# --- FUNCIONES DE CARGA LOCAL ---
# (Usamos esto para leer rápido, pero al guardar, enviamos a la nube)
def cargar_datos():
    if os.path.exists(ARCHIVO_CSV):
        return pd.read_csv(ARCHIVO_CSV)
    return pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])

# --- APP PRINCIPAL ---
if os.path.exists(ARCHIVO_EXCEL):
    try:
        # Carga Excel
        df = pd.read_excel(ARCHIVO_EXCEL)
        df.rename(columns={df.columns[1]: 'Producto', df.columns[6]: 'Cod Equipo', df.columns[17]: 'Fecha'}, inplace=True)
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
        
        # Filtros
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", "ENGRASADOR", 
                   "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", "CABLE", "CINTA", 
                   "CORAZA", "LLANTA", "PINTURA"]
        mask = (~df['Producto'].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df['Cod Equipo'].astype(str).str.startswith('3')) & \
               (df['Cod Equipo'].astype(str) != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df['Fecha'].notna())

        df_base = df[mask].copy()
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + " (" + df_base['Cod Equipo'].astype(str) + ")"
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha']).dt.days

        # Cargar Memoria
        df_memoria = cargar_datos()
        
        # Merge
        if not df_memoria.empty:
            df_full = pd.merge(df_base, df_memoria, on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'] = 'PENDIENTE'
            df_full['Fecha_Prog'] = None

        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce')

        # --- LÓGICA DE GUARDADO CENTRALIZADA ---
        def guardar_todo(df_actualizado):
            # Guardamos localmente para velocidad inmediata
            df_actualizado.to_csv(ARCHIVO_CSV, index=False)
            # Guardamos en la nube para persistencia real
            subir_a_github(df_actualizado)

        # Tabs
        tab1, tab2, tab3 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS"])

        # COLUMNAS A MOSTRAR
        cols = ['Producto', 'Cod Equipo', df.columns[4], 'Días en Almacén']

        # --- TAB 1: PENDIENTES ---
        with tab1:
            df_p = df_full[df_full['Estado'] == 'PENDIENTE'].sort_values(['Fecha_Prog', 'Días en Almacén'], ascending=[True, False])
            
            # Editor
            edited_df = st.data_editor(
                df_p,
                column_config={
                    "Fecha_Prog": st.column_config.DateColumn("📅 F. Programación", format="DD/MM/YYYY"),
                    "Seleccionar": st.column_config.CheckboxColumn(default=False)
                },
                disabled=cols + ['ID_Unico', 'Estado'],
                hide_index=True,
                key="editor_pendientes"
            )

            # Botón Guardar Fechas
            if st.button("💾 Guardar Cambios en Nube (Automático)", type="primary"):
                # Actualizamos solo las fechas modificadas en el dataframe maestro
                df_full.update(edited_df)
                # Filtramos solo columnas clave para guardar en CSV
                df_to_save = df_full[['ID_Unico', 'Estado', 'Fecha_Prog']]
                guardar_todo(df_to_save)
                st.rerun()

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.warning("⚠️ Sube PEDIDOS.xlsx")
