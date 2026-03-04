import streamlit as st
import pandas as pd
from datetime import datetime
import os
import urllib.parse # Para crear los links de WhatsApp y Correo
from github import Github

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Repuestos", layout="wide")
st.title("🛠️ Control de Repuestos - Gestión Total")

# --- CONSTANTES Y ARCHIVOS ---
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_CSV = "datos_gestion.csv"
REPO_NOMBRE = "TU_USUARIO/TU_REPO" # <--- ¡CAMBIA ESTO POR TU USUARIO/REPO!

# --- FUNCIÓN DE CONEXIÓN CON GITHUB ---
def subir_a_github(df_nuevo):
    """Guarda el archivo CSV de gestión en la nube (GitHub)"""
    try:
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            g = Github(token)
            try:
                # Intenta obtener el repositorio
                repo = g.get_user().get_repo(REPO_NOMBRE.split("/")[-1]) 
            except:
                st.error("Error: No encuentro el repositorio. Revisa la variable REPO_NOMBRE en el código.")
                return

            content_csv = df_nuevo.to_csv(index=False)
            
            try:
                # Intenta actualizar si existe
                contents = repo.get_contents(ARCHIVO_CSV)
                repo.update_file(contents.path, "Actualización desde App", content_csv, contents.sha)
                st.toast("✅ Cambios guardados en la Nube", icon="☁️")
            except:
                # Si no existe, lo crea
                repo.create_file(ARCHIVO_CSV, "Creación Inicial", content_csv)
                st.toast("✅ Archivo de gestión creado en Nube", icon="✨")
        else:
            st.warning("⚠️ No hay Token configurado. Los cambios solo se guardarán temporalmente en local.")
    except Exception as e:
        st.error(f"Error conectando con GitHub: {e}")

# --- CARGA DE DATOS LOCALES ---
def cargar_csv_local():
    """Lee el archivo CSV si existe en el entorno actual"""
    if os.path.exists(ARCHIVO_CSV):
        try:
            return pd.read_csv(ARCHIVO_CSV)
        except:
            return pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])
    return pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])

# --- LÓGICA PRINCIPAL ---
if os.path.exists(ARCHIVO_EXCEL):
    try:
        # 1. Cargar Excel Original
        df = pd.read_excel(ARCHIVO_EXCEL)
        
        # 2. Mapeo y Renombre de Columnas (Ajustado a tu Excel)
        col_insumo = df.columns[0]  # Columna A
        col_prod = df.columns[1]    # Columna B
        col_equipo = df.columns[6]  # Columna G
        col_fecha = df.columns[17]  # Columna R

        df.rename(columns={
            col_insumo: 'Cód insumo',
            col_prod: 'Producto',
            col_equipo: 'Cod Equipo',
            col_fecha: 'Fecha_Llegada'
        }, inplace=True)

        # Convertir fecha de llegada para cálculos
        df['Fecha_Llegada'] = pd.to_datetime(df['Fecha_Llegada'], errors='coerce')
        
        # 3. Filtros de Limpieza (Bogotá, Exclusiones, etc.)
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", "ENGRASADOR", 
                   "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", "CABLE", "CINTA", 
                   "CORAZA", "LLANTA", "PINTURA"]
        
        mask = (~df['Producto'].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df['Cod Equipo'].astype(str).str.startswith('3')) & \
               (df['Cod Equipo'].astype(str) != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df['Fecha_Llegada'].notna())

        df_base = df[mask].copy()
        
        # Crear ID Único (Producto + Equipo) para rastrear items
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + df_base['Cod Equipo'].astype(str)

        # 4. Cruzar con Memoria (CSV de Gestión)
        df_memoria = cargar_csv_local()
        
        if not df_memoria.empty:
            df_base['ID_Unico'] = df_base['ID_Unico'].astype(str)
            df_memoria['ID_Unico'] = df_memoria['ID_Unico'].astype(str)
            df_full = pd.merge(df_base, df_memoria, on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'] = 'PENDIENTE'
            df_full['Fecha_Prog'] = None

        # Rellenar vacíos y asegurar tipos de datos
        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce')

        # --- BARRA LATERAL: FILTROS Y RESPALDO ---
        st.sidebar.header("🔍 Buscador")
        
        # Filtros Multiselect
        lista_prod = sorted(df_full['Producto'].astype(str).unique())
        filtro_prod = st.sidebar.multiselect("Filtrar Producto:", lista_prod)
        
        lista_eq = sorted(df_full['Cod Equipo'].astype(str).unique())
        filtro_eq = st.sidebar.multiselect("Filtrar Equipo:", lista_eq)

        # Aplicar Filtros a la Vista
        df_view = df_full.copy()
        if filtro_prod: 
            df_view = df_view[df_view['Producto'].astype(str).isin(filtro_prod)]
        if filtro_eq: 
            df_view = df_view[df_view['Cod Equipo'].astype(str).isin(filtro_eq)]

        # Botón de Descarga Manual (Respaldo)
        st.sidebar.markdown("---")
        st.sidebar.header("📂 Respaldo")
        csv_data = df_full[['ID_Unico', 'Estado', 'Fecha_Prog']].to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("📥 Descargar Gestión (.csv)", csv_data, "datos_gestion.csv", "text/csv")

        # --- FUNCIÓN CENTRAL DE GUARDADO ---
        def guardar_cambios(df_maestro):
            """Guarda cambios en local y nube, luego recarga"""
            datos = df_maestro[['ID_Unico', 'Estado', 'Fecha_Prog']].drop_duplicates(subset=['ID_Unico'])
            datos.to_csv(ARCHIVO_CSV, index=False) # Guarda local
            subir_a_github(datos) # Guarda nube
            st.rerun()

        # --- PESTAÑAS DE GESTIÓN ---
        tab1, tab2, tab3 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS"])
        
        # Columnas visibles (Las que pediste)
        cols_view = ['Cód insumo', 'Producto', 'Cod Equipo']

        # === PESTAÑA 1: PENDIENTES ===
        with tab1:
            df_p = df_view[df_view['Estado'] == 'PENDIENTE'].copy()
            
            if df_p.empty:
                st.success("✅ No hay pendientes de instalación.")
            else:
                # --- ZONA DE NOTIFICACIÓN ---
                with st.expander("📢 Generar Notificación (WhatsApp/Correo)"):
                    st.caption("Genera un mensaje con los items listados abajo:")
                    
                    # Construir mensaje
                    mensaje_txt = "🚨 *REPORTE PENDIENTES* 🚨\n\n"
                    for _, row in df_p.iterrows():
                        f_prog = row['Fecha_Prog'].strftime('%d/%m') if pd.notnull(row['Fecha_Prog']) else "S/F"
                        mensaje_txt += f"🔧 {row['Producto']} ({row['Cod Equipo']}) - 📅 {f_prog}\n"
                    
                    col_w, col_m = st.columns(2)
                    # Link WhatsApp
                    txt_wa = urllib.parse.quote(mensaje_txt)
                    col_w.link_button("📲 WhatsApp Web", f"https://wa.me/?text={txt_wa}")
                    # Link Correo
                    asunto = urllib.parse.quote("Reporte de Repuestos Pendientes")
                    cuerpo = urllib.parse.quote(mensaje_txt)
                    col_m.link_button("📧 Abrir Correo", f"mailto:?subject={asunto}&body={cuerpo}")

                st.divider()

                # --- TABLA EDITABLE ---
                df_p.insert(0, "Seleccionar", False)
                ed_p = st.data_editor(
                    df_p[['Seleccionar', 'Fecha_Prog'] + cols_view],
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(required=True),
                        "Fecha_Prog": st.column_config.DateColumn("📅 Programación", format="DD/MM/YYYY")
                    },
                    disabled=cols_view, hide_index=True, key="ed_p"
                )
                
                # Acciones
                seleccionados = ed_p[ed_p['Seleccionar'] == True]
                
                # 1. Guardar Fechas
                if st.button("💾 Guardar Fechas"):
                    nuevas_fechas = pd.to_datetime(ed_p['Fecha_Prog'])
                    # Mapear y actualizar
                    for id_u, fecha in zip(df_p['ID_Unico'], nuevas_fechas):
                        df_full.loc[df_full['ID_Unico'] == id_u, 'Fecha_Prog'] = fecha
                    guardar_cambios(df_full)

                # 2. Mover Items
                if not seleccionados.empty:
                    st.write("---")
                    c1, c2 = st.columns(2)
                    ids = df_p.loc[seleccionados.index, 'ID_Unico'].values
                    
                    with c1:
                        if st.button("✅ MOVER A COMPLETADOS", type="primary", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                            guardar_cambios(df_full)
                    with c2:
                        if st.button("🛡️ MOVER A RESERVA", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                            guardar_cambios(df_full)

        # === PESTAÑA 2: RESERVA ===
        with tab2:
            df_r = df_view[df_view['Estado'] == 'RESERVA'].copy()
            if df_r.empty:
                st.info("No hay items en reserva.")
            else:
                df_r.insert(0, "Seleccionar", False)
                ed_r = st.data_editor(
                    df_r[['Seleccionar'] + cols_view],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn()},
                    disabled=cols_view, hide_index=True, key="ed_r"
                )
                sel_r = ed_r[ed_r['Seleccionar'] == True]
                
                if not sel_r.empty:
                    st.write("---")
                    c1, c2 = st.columns(2)
                    ids = df_r.loc[sel_r.index, 'ID_Unico'].values
                    
                    with c1:
                        if st.button("🔙 DEVOLVER A PENDIENTES", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'PENDIENTE'
                            guardar_cambios(df_full)
                    with c2:
                        if st.button("✅ YA LO USÉ (COMPLETADO)", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                            guardar_cambios(df_full)

        # === PESTAÑA 3: COMPLETADOS ===
        with tab3:
            df_c = df_view[df_view['Estado'] == 'COMPLETADO'].copy()
            if df_c.empty:
                st.info("Historial vacío.")
            else:
                df_c.insert(0, "Seleccionar", False)
                ed_c = st.data_editor(
                    df_c[['Seleccionar'] + cols_view],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn()},
                    disabled=cols_view, hide_index=True, key="ed_c"
                )
                sel_c = ed_c[ed_c['Seleccionar'] == True]
                
                if not sel_c.empty:
                    st.write("---")
                    c1, c2 = st.columns(2)
                    ids = df_c.loc[sel_c.index, 'ID_Unico'].values
                    
                    with c1:
                        if st.button("🔙 RESTAURAR A PENDIENTES", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'PENDIENTE'
                            guardar_cambios(df_full)
                    with c2:
                        if st.button("🛡️ ERA PARA RESERVA", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                            guardar_cambios(df_full)

    except Exception as e:
        st.error(f"Ocurrió un error: {e}")
else:
    st.warning("⚠️ No se encuentra el archivo 'PEDIDOS.xlsx'. Por favor súbelo a GitHub.")
