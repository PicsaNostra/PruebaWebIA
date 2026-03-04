import streamlit as st
import pandas as pd
from datetime import datetime
import os
from github import Github

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Repuestos", layout="wide")
st.title("🛠️ Control de Repuestos - Simplificado")

# Nombres de archivos
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_CSV = "datos_gestion.csv"
REPO_NOMBRE = "TU_USUARIO/TU_REPO" # <--- ¡RECUERDA PONER TU USUARIO/REPO AQUÍ!

# --- CONEXIÓN CON GITHUB (Para guardar automático) ---
def subir_a_github(df_nuevo):
    """Sube el archivo CSV a GitHub"""
    try:
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            g = Github(token)
            # Intentar obtener repo, si falla usa el nombre manual
            try:
                repo = g.get_user().get_repo(REPO_NOMBRE.split("/")[-1]) 
            except:
                st.error("Revisa el nombre del repositorio en el código.")
                return

            content_csv = df_nuevo.to_csv(index=False)
            
            try:
                contents = repo.get_contents(ARCHIVO_CSV)
                repo.update_file(contents.path, "Update desde App", content_csv, contents.sha)
                st.toast("✅ Guardado en Nube", icon="☁️")
            except:
                repo.create_file(ARCHIVO_CSV, "Init App", content_csv)
                st.toast("✅ Archivo Creado en Nube", icon="✨")
        else:
            st.warning("No hay Token configurado en Secrets. Solo se guardará localmente.")
            
    except Exception as e:
        st.error(f"Error GitHub: {e}")

# --- CARGA DE DATOS ---
def cargar_csv_local():
    if os.path.exists(ARCHIVO_CSV):
        return pd.read_csv(ARCHIVO_CSV)
    return pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])

# --- APP PRINCIPAL ---
if os.path.exists(ARCHIVO_EXCEL):
    try:
        # 1. Cargar Excel
        df = pd.read_excel(ARCHIVO_EXCEL)
        
        # --- DEFINICIÓN DE COLUMNAS (AQUÍ ESTÁ EL CAMBIO) ---
        # Asumimos: Col A(0)=Insumo, Col B(1)=Producto, Col G(6)=Equipo, Col R(17)=Fecha
        col_insumo = df.columns[0]  # Cód insumo
        col_prod = df.columns[1]    # Producto
        col_equipo = df.columns[6]  # Cod Equipo
        col_fecha = df.columns[17]  # Fecha llegada

        # Renombrar para trabajar fácil
        df.rename(columns={
            col_insumo: 'Cód insumo',
            col_prod: 'Producto',
            col_equipo: 'Cod Equipo',
            col_fecha: 'Fecha_Llegada'
        }, inplace=True)

        df['Fecha_Llegada'] = pd.to_datetime(df['Fecha_Llegada'], errors='coerce')
        
        # 2. Filtros de Limpieza (Bogotá, Exclusiones, etc)
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", "ENGRASADOR", 
                   "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", "CABLE", "CINTA", 
                   "CORAZA", "LLANTA", "PINTURA"]
        
        # Usamos índices para filtrar seguro: Col 4 es Ubicación
        mask = (~df['Producto'].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df['Cod Equipo'].astype(str).str.startswith('3')) & \
               (df['Cod Equipo'].astype(str) != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df['Fecha_Llegada'].notna())

        df_base = df[mask].copy()
        
        # Crear ID Único para rastrear
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + df_base['Cod Equipo'].astype(str)

        # 3. Cruzar con Memoria (CSV)
        df_memoria = cargar_csv_local()
        
        if not df_memoria.empty:
            # Convertimos a string para evitar errores de cruce
            df_base['ID_Unico'] = df_base['ID_Unico'].astype(str)
            df_memoria['ID_Unico'] = df_memoria['ID_Unico'].astype(str)
            
            df_full = pd.merge(df_base, df_memoria, on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'] = 'PENDIENTE'
            df_full['Fecha_Prog'] = None

        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')

        # --- FILTROS VISUALES ---
        st.sidebar.header("🔍 Buscar")
        texto = st.sidebar.text_input("Escribe aquí:", "").lower()
        
        if texto:
            df_full = df_full[
                df_full['Producto'].astype(str).str.lower().str.contains(texto) | 
                df_full['Cod Equipo'].astype(str).str.lower().str.contains(texto) |
                df_full['Cód insumo'].astype(str).str.lower().str.contains(texto)
            ]

        # --- FUNCIÓN PARA GUARDAR ---
        def guardar_cambios_csv_y_nube(df_maestro):
            # Guardar solo las columnas necesarias en el CSV
            datos_a_guardar = df_maestro[['ID_Unico', 'Estado', 'Fecha_Prog']].drop_duplicates(subset=['ID_Unico'])
            datos_a_guardar.to_csv(ARCHIVO_CSV, index=False)
            subir_a_github(datos_a_guardar)
            st.rerun()

        # --- INTERFAZ (PESTAÑAS) ---
        tab1, tab2, tab3 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS"])

        # COLUMNAS EXACTAS QUE PEDISTE (Más Fecha Prog que es necesaria para editar)
        cols_visuales = ['Cód insumo', 'Producto', 'Cod Equipo']

        # === PESTAÑA 1: PENDIENTES ===
        with tab1:
            df_p = df_full[df_full['Estado'] == 'PENDIENTE'].copy()
            
            if df_p.empty:
                st.success("No hay pendientes.")
            else:
                # Preparamos tabla editable
                df_p.insert(0, "Seleccionar", False)
                
                edited_p = st.data_editor(
                    df_p[['Seleccionar', 'Fecha_Prog'] + cols_visuales], # Solo mostramos lo que pediste
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(required=True),
                        "Fecha_Prog": st.column_config.DateColumn("📅 Programación", format="DD/MM/YYYY")
                    },
                    disabled=cols_visuales, # No dejar editar nombres, solo fecha y check
                    hide_index=True,
                    key="editor_p"
                )

                # BOTONES DE ACCIÓN
                seleccionados = edited_p[edited_p['Seleccionar'] == True]
                
                # 1. Guardar Fechas (Si cambian)
                if st.button("💾 Guardar Fechas"):
                    # Actualizar fechas en el maestro usando el índice
                    df_full.loc[df_p.index, 'Fecha_Prog'] = edited_p['Fecha_Prog']
                    guardar_cambios_csv_y_nube(df_full)

                # 2. Mover Items
                if not seleccionados.empty:
                    st.write("---")
                    col_btn1, col_btn2 = st.columns(2)
                    ids_sel = df_p.loc[seleccionados.index, 'ID_Unico'].values
                    
                    with col_btn1:
                        if st.button("✅ MOVER A COMPLETADOS", type="primary", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids_sel), 'Estado'] = 'COMPLETADO'
                            guardar_cambios_csv_y_nube(df_full)
                    
                    with col_btn2:
                        if st.button("🛡️ MOVER A RESERVA", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids_sel), 'Estado'] = 'RESERVA'
                            guardar_cambios_csv_y_nube(df_full)

        # === PESTAÑA 2: RESERVA ===
        with tab2:
            df_r = df_full[df_full['Estado'] == 'RESERVA'].copy()
            if df_r.empty:
                st.info("Nada en reserva.")
            else:
                df_r.insert(0, "Seleccionar", False)
                edited_r = st.data_editor(
                    df_r[['Seleccionar'] + cols_visuales],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn()},
                    disabled=cols_visuales,
                    hide_index=True,
                    key="editor_r"
                )
                
                sel_r = edited_r[edited_r['Seleccionar'] == True]
                if not sel_r.empty:
                    if st.button("🔙 Devolver a Pendientes"):
                        ids_sel = df_r.loc[sel_r.index, 'ID_Unico'].values
                        df_full.loc[df_full['ID_Unico'].isin(ids_sel), 'Estado'] = 'PENDIENTE'
                        guardar_cambios_csv_y_nube(df_full)

        # === PESTAÑA 3: COMPLETADOS ===
        with tab3:
            df_c = df_full[df_full['Estado'] == 'COMPLETADO'].copy()
            if df_c.empty:
                st.info("Historial vacío.")
            else:
                df_c.insert(0, "Seleccionar", False)
                edited_c = st.data_editor(
                    df_c[['Seleccionar'] + cols_visuales],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn()},
                    disabled=cols_visuales,
                    hide_index=True,
                    key="editor_c"
                )
                
                sel_c = edited_c[edited_c['Seleccionar'] == True]
                if not sel_c.empty:
                    if st.button("Restaurar a Pendientes"):
                        ids_sel = df_c.loc[sel_c.index, 'ID_Unico'].values
                        df_full.loc[df_full['ID_Unico'].isin(ids_sel), 'Estado'] = 'PENDIENTE'
                        guardar_cambios_csv_y_nube(df_full)

    except Exception as e:
        st.error(f"Error cargando archivo: {e}")
else:
    st.warning("⚠️ No se encuentra 'PEDIDOS.xlsx'")
