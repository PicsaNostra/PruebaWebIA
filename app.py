import streamlit as st
import pandas as pd
from datetime import datetime
import os

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor de Repuestos", layout="wide")
st.title("🛠️ Control de Repuestos - Gestión Interactiva")

# Archivos
archivo_pedidos = "PEDIDOS.xlsx"
archivo_contingencia = "contingencias.csv"

# --- FUNCIONES DE MEMORIA ---
def cargar_contingencias():
    if os.path.exists(archivo_contingencia):
        try:
            return pd.read_csv(archivo_contingencia)['Identificador'].tolist()
        except:
            return []
    return []

def guardar_contingencias(lista_items):
    pd.DataFrame({'Identificador': list(set(lista_items))}).to_csv(archivo_contingencia, index=False)

# --- INICIO DE LA APP ---
if os.path.exists(archivo_pedidos):
    try:
        # 1. Cargar y Limpiar
        df = pd.read_excel(archivo_pedidos)
        
        # Renombrar columnas clave (Indices fijos)
        df.rename(columns={
            df.columns[1]: 'Producto', 
            df.columns[6]: 'Cod Equipo', 
            df.columns[17]: 'Fecha'
        }, inplace=True)

        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
        
        # Filtros Duros
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", 
                   "ENGRASADOR", "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", 
                   "CABLE", "CINTA", "CORAZA", "LLANTA", "PINTURA"]
        
        mask = (~df['Producto'].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df['Cod Equipo'].astype(str).str.startswith('3')) & \
               (df['Cod Equipo'].astype(str) != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df['Fecha'].notna())

        df_base = df[mask].copy()
        
        # Crear ID Único
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + " (" + df_base['Cod Equipo'].astype(str) + ")"
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha']).dt.days

        # Cargar memoria de contingencia
        lista_contingencia = cargar_contingencias()

        # --- BARRA LATERAL (FILTROS DE VISUALIZACIÓN) ---
        st.sidebar.header("🔍 Filtros de Búsqueda")
        
        # Buscador
        texto_busqueda = st.sidebar.text_input("Buscar (Producto/Equipo):", "")
        
        # Filtro Equipo
        equipos_unicos = sorted(df_base['Cod Equipo'].astype(str).unique())
        filtro_equipo = st.sidebar.multiselect("Filtrar por Equipo:", options=equipos_unicos)

        # Aplicar Filtros Visuales
        df_view = df_base.copy()
        if texto_busqueda:
            term = texto_busqueda.lower()
            df_view = df_view[
                df_view['Producto'].astype(str).str.lower().str.contains(term) | 
                df_view['Cod Equipo'].astype(str).str.lower().str.contains(term)
            ]
        if filtro_equipo:
            df_view = df_view[df_view['Cod Equipo'].astype(str).isin(filtro_equipo)]

        # Separar en dos DataFrames
        df_pendientes = df_view[~df_view['ID_Unico'].isin(lista_contingencia)].copy()
        df_reserva = df_view[df_view['ID_Unico'].isin(lista_contingencia)].copy()

        # Columnas a mostrar
        cols_mostrar = ['Producto', 'Cod Equipo', df.columns[4], 'Días en Almacén']

        # --- INTERFAZ PRINCIPAL ---
        fecha_mod = datetime.fromtimestamp(os.path.getmtime(archivo_pedidos)).strftime('%d/%m/%Y')
        st.write(f"📅 **Datos actualizados al:** {fecha_mod}")

        tab1, tab2 = st.tabs([f"🚨 PENDIENTES ({len(df_pendientes)})", f"🛡️ RESERVA / CONTINGENCIA ({len(df_reserva)})"])

        # --- PESTAÑA 1: PENDIENTES ---
        with tab1:
            st.info("Selecciona los items que quieras enviar a reserva y presiona el botón.")
            
            # Preparamos dataframe para edición (añadimos columna checkbox)
            df_p_edit = df_pendientes.copy()
            df_p_edit.insert(0, "Seleccionar", False) # Columna de checks al inicio
            
            # Editor interactivo
            editor_pendientes = st.data_editor(
                df_p_edit[['Seleccionar'] + cols_mostrar],
                column_config={"Seleccionar": st.column_config.CheckboxColumn("Mover?", help="Marca para mover a reserva", default=False)},
                disabled=cols_mostrar, # Bloqueamos edición de datos, solo permitimos el check
                hide_index=True,
                key="editor_pendientes"
            )

            # Detectar seleccionados
            seleccionados_p = editor_pendientes[editor_pendientes['Seleccionar'] == True]
            
            if not seleccionados_p.empty:
                ids_a_mover = df_pendientes.loc[seleccionados_p.index, 'ID_Unico'].tolist()
                st.write(f"Has seleccionado {len(ids_a_mover)} items.")
                
                if st.button("🛡️ Mover a Contingencia", type="primary"):
                    nueva_lista = lista_contingencia + ids_a_mover
                    guardar_contingencias(nueva_lista)
                    st.success("Items movidos a reserva exitosamente.")
                    st.rerun()

        # --- PESTAÑA 2: RESERVA ---
        with tab2:
            st.warning("Selecciona los items que quieras devolver a pendientes (Instalación).")
            
            if df_reserva.empty:
                st.write("No hay items en reserva.")
            else:
                # Preparamos dataframe para edición
                df_r_edit = df_reserva.copy()
                df_r_edit.insert(0, "Seleccionar", False)
                
                # Editor interactivo
                editor_reserva = st.data_editor(
                    df_r_edit[['Seleccionar'] + cols_mostrar],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn("Devolver?", help="Marca para devolver a pendientes", default=False)},
                    disabled=cols_mostrar,
                    hide_index=True,
                    key="editor_reserva"
                )

                # Detectar seleccionados
                seleccionados_r = editor_reserva[editor_reserva['Seleccionar'] == True]
                
                if not seleccionados_r.empty:
                    ids_a_devolver = df_reserva.loc[seleccionados_r.index, 'ID_Unico'].tolist()
                    st.write(f"Has seleccionado {len(ids_a_devolver)} items.")
                    
                    if st.button("🚨 Devolver a Pendientes"):
                        # Filtramos para quitar los seleccionados
                        lista_actualizada = [x for x in lista_contingencia if x not in ids_a_devolver]
                        guardar_contingencias(lista_actualizada)
                        st.success("Items devueltos a pendientes exitosamente.")
                        st.rerun()

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.warning("⚠️ No se encuentra el archivo 'PEDIDOS.xlsx'.")
