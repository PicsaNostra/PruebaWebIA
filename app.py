import streamlit as st
import pandas as pd
from datetime import datetime
import io
import urllib.parse
import requests
from github import Github

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Repuestos Pro", layout="wide", page_icon="🛠️")

# --- 2. CONSTANTES DE CONEXIÓN ---
REPO_DATOS = "PicsaNostra/DatosRepuestos" 
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_ESTADOS = "ESTADOS%20DE%20EQUIPOS.xlsx" 
ARCHIVO_CSV = "datos_gestion.csv"
RAMA = "main"

URL_FALLAS = "https://docs.google.com/spreadsheets/d/1o22GZKmqCmuABGaR1nyLe2jCMBti7cWJtv38wvgH0PQ/export?format=csv&gid=0"

# --- 3. FUNCIONES DE CONEXIÓN ---

def obtener_token():
    if "GITHUB_TOKEN" not in st.secrets:
        st.error("❌ Falta el Token en Secrets.")
        st.stop()
    return st.secrets["GITHUB_TOKEN"]

def obtener_repo_privado():
    token = obtener_token()
    g = Github(token)
    try:
        return g.get_repo(REPO_DATOS)
    except Exception as e:
        st.error(f"❌ Error conectando al repo: {e}")
        return None

@st.cache_data(ttl=600)
def cargar_excel_desde_nube():
    token = obtener_token()
    url = f"https://raw.githubusercontent.com/{REPO_DATOS}/{RAMA}/{ARCHIVO_EXCEL}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3.raw"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return pd.read_excel(io.BytesIO(response.content), engine='openpyxl')
        return None
    except:
        return None

@st.cache_data(ttl=600)
def cargar_estados_desde_nube():
    token = obtener_token()
    url = f"https://raw.githubusercontent.com/{REPO_DATOS}/{RAMA}/{ARCHIVO_ESTADOS}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3.raw"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return pd.read_excel(io.BytesIO(response.content), sheet_name="INFORMACIÓN EDITABLE", engine='openpyxl')
        return None
    except Exception as e:
        return None

def cargar_csv_desde_nube():
    repo = obtener_repo_privado()
    df_vacio = pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog', 'Ejecucion_Obra'])
    if not repo: return df_vacio
    try:
        contenido = repo.get_contents(ARCHIVO_CSV).decoded_content
        df_csv = pd.read_csv(io.BytesIO(contenido))
        if 'Ejecucion_Obra' not in df_csv.columns:
            df_csv['Ejecucion_Obra'] = False
        df_csv['Ejecucion_Obra'] = df_csv['Ejecucion_Obra'].fillna(False).astype(bool)
        return df_csv
    except:
        return df_vacio

@st.cache_data(ttl=300)
def cargar_fallas_espejo():
    df_vacio = pd.DataFrame(columns=['Cod Equipo', 'COMPONENTE', 'Estado Falla', 'Falla'])
    try:
        df_fallas = pd.read_csv(URL_FALLAS)
        
        if 'CÓD' not in df_fallas.columns or 'ESTADO' not in df_fallas.columns or 'FALLA' not in df_fallas.columns:
            return df_vacio
            
        if 'COMPONENTE' not in df_fallas.columns:
            df_fallas['COMPONENTE'] = "SIN DATO"

        estados_validos = ["PENDIENTE TRASLADO", "PENDIENTE TÉCNICO", "PENDIENTE REPUESTO", "EN REVISIÓN"]
        df_fallas['ESTADO'] = df_fallas['ESTADO'].astype(str).str.strip().str.upper()
        
        mask_estados = df_fallas['ESTADO'].isin(estados_validos)
        df_filtrado = df_fallas[mask_estados].copy()
        
        df_filtrado.rename(columns={'CÓD': 'Cod Equipo', 'FALLA': 'Falla', 'ESTADO': 'Estado Falla'}, inplace=True)
        df_filtrado['Cod Equipo'] = df_filtrado['Cod Equipo'].astype(str).str.strip().str.upper()
        df_filtrado['Falla'] = df_filtrado['Falla'].astype(str).str.strip()
        df_filtrado['COMPONENTE'] = df_filtrado['COMPONENTE'].astype(str).str.strip()
        
        return df_filtrado[['Cod Equipo', 'COMPONENTE', 'Estado Falla', 'Falla']]
    except Exception as e:
        return df_vacio

def subir_a_github(df_nuevo):
    repo = obtener_repo_privado()
    if not repo: return
    content_csv = df_nuevo.to_csv(index=False)
    try:
        contents = repo.get_contents(ARCHIVO_CSV)
        repo.update_file(contents.path, "Actualización App", content_csv, contents.sha)
        st.toast("✅ Guardado en Nube", icon="☁️")
    except:
        repo.create_file(ARCHIVO_CSV, "Creación Inicial", content_csv)
        st.toast("✅ Archivo creado", icon="✨")

# --- 4. LÓGICA PRINCIPAL ---

st.title("🛠️ Control de Repuestos y Novedades")

with st.spinner('⏳ Sincronizando inventarios, ubicaciones y diagramas...'):
    df = cargar_excel_desde_nube()
    df_estados = cargar_estados_desde_nube()
    df_memoria = cargar_csv_desde_nube()
    df_fallas_raw = cargar_fallas_espejo() 

if df is not None:
    st.success("✅ Sistema Sincronizado", icon="📡")

    try:
        col_insumo = df.columns[0]
        col_prod = df.columns[1]
        col_equipo = df.columns[6]
        col_fecha = df.columns[17]

        df.rename(columns={col_insumo: 'Cód insumo', col_prod: 'Producto', col_equipo: 'Cod Equipo', col_fecha: 'Fecha_Llegada'}, inplace=True)
        df['Fecha_Llegada'] = pd.to_datetime(df['Fecha_Llegada'], errors='coerce')
        
        df['Cód insumo'] = df['Cód insumo'].astype(str).str.strip().str.upper()
        df['Producto'] = df['Producto'].astype(str).str.strip().str.upper()
        df['Cod Equipo'] = df['Cod Equipo'].astype(str).str.strip().str.upper()

        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", "ENGRASADOR", 
                   "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", "CABLE", "CINTA", 
                   "CORAZA", "LLANTA", "PINTURA"]
        
        mask = (~df['Producto'].str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df['Cod Equipo'].str.startswith('3')) & \
               (df['Cod Equipo'] != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df['Fecha_Llegada'].notna())

        df_base = df[mask].copy()
        df_base['ID_Unico'] = df_base['Producto'] + df_base['Cod Equipo']
        df_base['BUSQUEDA_TOTAL'] = df_base['Cód insumo'] + " " + df_base['Producto'] + " " + df_base['Cod Equipo']
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha_Llegada']).dt.days.fillna(0).astype(int)
        df_base['Días en Almacén'] = df_base['Días en Almacén'].apply(lambda x: x if x > 0 else 0)

        # --- PROCESAMIENTO UBICACIONES ---
        if df_estados is not None and not df_estados.empty:
            col_eq_est = df_estados.columns[0] 
            if 'OBRA ASIGNACIÓN' in df_estados.columns:
                col_obra = 'OBRA ASIGNACIÓN'
            elif len(df_estados.columns) > 5:
                col_obra = df_estados.columns[5]
            else:
                col_obra = df_estados.columns[-1]

            df_ubicacion = df_estados[[col_eq_est, col_obra]].copy()
            df_ubicacion.rename(columns={col_eq_est: 'Cod Equipo', col_obra: 'UBICACIÓN'}, inplace=True)
            df_ubicacion['Cod Equipo'] = df_ubicacion['Cod Equipo'].astype(str).str.strip().str.upper()
            df_ubicacion['UBICACIÓN'] = df_ubicacion['UBICACIÓN'].astype(str).str.strip()
            df_ubicacion = df_ubicacion.drop_duplicates(subset=['Cod Equipo'], keep='last')
        else:
            df_ubicacion = pd.DataFrame(columns=['Cod Equipo', 'UBICACIÓN'])

        # Cruzar Repuestos con Ubicación
        df_base = pd.merge(df_base, df_ubicacion, on='Cod Equipo', how='left')
        df_base['UBICACIÓN'] = df_base['UBICACIÓN'].fillna('SIN DATO')

        # --- EXTRAER COMPONENTE PARA EL GRÁFICO ---
        if not df_fallas_raw.empty:
            df_comp = df_fallas_raw[['Cod Equipo', 'COMPONENTE']].drop_duplicates(subset=['Cod Equipo'], keep='last')
            df_base = pd.merge(df_base, df_comp, on='Cod Equipo', how='left')
        else:
            df_base['COMPONENTE'] = 'SIN DATO'
        
        df_base['COMPONENTE'] = df_base['COMPONENTE'].fillna('SIN DATO')

        # --- CRUZAR CON MEMORIA ---
        if not df_memoria.empty:
            df_base['ID_Unico'] = df_base['ID_Unico'].astype(str)
            df_memoria['ID_Unico'] = df_memoria['ID_Unico'].astype(str)
            df_full = pd.merge(df_base, df_memoria, on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'] = 'PENDIENTE'
            df_full['Fecha_Prog'] = None
            df_full['Ejecucion_Obra'] = False

        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce')
        df_full['Ejecucion_Obra'] = df_full['Ejecucion_Obra'].fillna(False).astype(bool)

        def calcular_semaforo(dias):
            return "🔴 Crítico" if dias > 30 else "🟢 Normal"
        df_full['Prioridad'] = df_full['Días en Almacén'].apply(calcular_semaforo)

        def guardar_todo(df_maestro):
            datos = df_maestro[['ID_Unico', 'Estado', 'Fecha_Prog', 'Ejecucion_Obra']].drop_duplicates(subset=['ID_Unico'])
            subir_a_github(datos)
            st.cache_data.clear()
            st.rerun()

        # --- BARRA LATERAL ---
        st.sidebar.header("🎛️ Panel de Control")
        csv_data = df_full.to_csv(index=False).encode('utf-8-sig') 
        st.sidebar.download_button("📥 Descargar Reporte Repuestos (CSV)", data=csv_data, file_name=f"Repuestos_{datetime.now().strftime('%Y-%m-%d')}.csv", mime="text/csv")
        st.sidebar.divider()
        texto_busqueda = st.sidebar.text_input("🔍 Buscador General", placeholder="Ej: 1661 o Fuga").upper().strip()
        
        # --- FILTROS ---
        df_view = df_full.copy()
        df_fallas_view = df_fallas_raw.copy()
        
        if texto_busqueda:
            mask_busqueda = df_view['BUSQUEDA_TOTAL'].str.contains(texto_busqueda, na=False) | \
                            df_view['UBICACIÓN'].str.contains(texto_busqueda, na=False, case=False)
            df_view = df_view[mask_busqueda]
            
            if not df_fallas_view.empty:
                mask_fallas = df_fallas_view['Cod Equipo'].str.contains(texto_busqueda, na=False) | \
                              df_fallas_view['Falla'].astype(str).str.upper().str.contains(texto_busqueda, na=False) | \
                              df_fallas_view['COMPONENTE'].astype(str).str.upper().str.contains(texto_busqueda, na=False) | \
                              df_fallas_view['UBICACIÓN'].astype(str).str.upper().str.contains(texto_busqueda, na=False)
                df_fallas_view = df_fallas_view[mask_fallas]

        # --- TABLERO ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🚨 Repuestos Pend.", len(df_view[df_view['Estado'] == 'PENDIENTE']))
        col2.metric("🛡️ En Reserva", len(df_view[df_view['Estado'] == 'RESERVA']))
        col3.metric("✅ Completados", len(df_view[df_view['Estado'] == 'COMPLETADO']))
        col4.metric("📋 Novedades Equipos", len(df_fallas_view), delta="Google Sheets", delta_color="inverse")
        st.divider()

        # --- PESTAÑAS ---
        tab1, tab2, tab3, tab4 = st.tabs(["🚨 PENDIENTES (Repuestos)", "🛡️ RESERVA", "✅ COMPLETADOS", "📋 NOVEDADES (Solo Consulta)"])
        
        cols_vis = ['Prioridad', 'Cód insumo', 'Producto', 'Cod Equipo', 'UBICACIÓN', 'Días en Almacén']

        # === TAB 1: PENDIENTES ===
        with tab1:
            df_p = df_view[df_view['Estado'] == 'PENDIENTE'].sort_values('Días en Almacén', ascending=False).copy()
            if df_p.empty:
                st.info("✨ Todo limpio o sin coincidencias.")
            else:
                # --- NUEVOS DIAGRAMAS ---
                with st.expander("📊 Diagramas de Equipos Pendientes", expanded=True):
                    g1, g2 = st.columns(2)
                    with g1:
                        st.markdown("📍 **Cantidad de Equipos por Ubicación**")
                        # Cuenta equipos únicos para no duplicar si tienen varios repuestos
                        grafico_ubi = df_p.groupby('UBICACIÓN')['Cod Equipo'].nunique().sort_values(ascending=False)
                        st.bar_chart(grafico_ubi, color="#ff4b4b")
                    with g2:
                        st.markdown("⚙️ **Cantidad de Equipos por Componente**")
                        grafico_comp = df_p.groupby('COMPONENTE')['Cod Equipo'].nunique().sort_values(ascending=False)
                        st.bar_chart(grafico_comp, color="#1f77b4")
                
                st.divider()

                # --- TABLA DE PENDIENTES ---
                df_p.insert(0, "Sel", False)
                ed_p = st.data_editor(
                    df_p[['Sel', 'Ejecucion_Obra', 'Fecha_Prog'] + cols_vis],
                    column_config={
                        "Sel": st.column_config.CheckboxColumn(width="small"),
                        "Ejecucion_Obra": st.column_config.CheckboxColumn("🏗️ En Obra", width="small", help="Marcar si se puede ejecutar en la obra"),
                        "Prioridad": st.column_config.TextColumn("Prioridad", width="small"),
                        "Fecha_Prog": st.column_config.DateColumn("📅 Prog", format="DD/MM/YYYY"),
                        "UBICACIÓN": st.column_config.TextColumn("Ubicación Equipo", width="medium"),
                        "Días en Almacén": st.column_config.NumberColumn("⏳ Días"),
                        "Cod Equipo": st.column_config.TextColumn("Equipo"),
                        "Cód insumo": st.column_config.TextColumn("Código")
                    },
                    disabled=cols_vis, hide_index=True, key="ed_p"
                )

                if st.button("💾 Guardar Cambios (Fechas y Obra)", type="primary", key="btn_save_dates"):
                    for idx, row in ed_p.iterrows():
                        idx_real = idx 
                        id_u = df_p.loc[idx_real]['ID_Unico']
                        df_full.loc[df_full['ID_Unico'] == id_u, 'Fecha_Prog'] = row['Fecha_Prog']
                        df_full.loc[df_full['ID_Unico'] == id_u, 'Ejecucion_Obra'] = row['Ejecucion_Obra']
                    guardar_todo(df_full)

                sel = ed_p[ed_p['Sel'] == True]
                if not sel.empty:
                    c1, c2 = st.columns(2)
                    ids = df_p.loc[sel.index, 'ID_Unico'].values
                    if c1.button("✅ Mover a COMPLETADO", key="btn_p_to_c"):
                        df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                        guardar_todo(df_full)
                    if c2.button("🛡️ Mover a RESERVA", key="btn_p_to_r"):
                        df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                        guardar_todo(df_full)

        # === TAB 2: RESERVA ===
        with tab2:
            df_r = df_view[df_view['Estado'] == 'RESERVA'].copy()
            if not df_r.empty:
                df_r.insert(0, "Sel", False)
                ed_r = st.data_editor(
                    df_r[['Sel'] + cols_vis],
                    column_config={
                        "Sel": st.column_config.CheckboxColumn(width="small"),
                        "Prioridad": st.column_config.TextColumn("Prioridad", width="small"),
                        "UBICACIÓN": st.column_config.TextColumn("Ubicación")
                    },
                    disabled=cols_vis, hide_index=True, key="ed_r"
                )
                sel_r = ed_r[ed_r['Sel'] == True]
                if not sel_r.empty and st.button("🔙 Devolver a PENDIENTE", key="btn_r_to_p"):
                    ids = df_r.loc[sel_r.index, 'ID_Unico'].values
                    df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'PENDIENTE'
                    guardar_todo(df_full)
            else:
                st.info("No hay repuestos en reserva.")

        # === TAB 3: COMPLETADOS ===
        with tab3:
            df_c = df_view[df_view['Estado'] == 'COMPLETADO'].copy()
            if not df_c.empty:
                df_c.insert(0, "Sel", False)
                ed_c = st.data_editor(
                    df_c[['Sel'] + cols_vis],
                    column_config={
                        "Sel": st.column_config.CheckboxColumn(width="small"),
                        "Prioridad": st.column_config.TextColumn("Prioridad", width="small"),
                        "UBICACIÓN": st.column_config.TextColumn("Ubicación")
                    },
                    disabled=cols_vis, hide_index=True, key="ed_c"
                )
                sel_c = ed_c[ed_c['Sel'] == True]
                if not sel_c.empty:
                    st.warning("⚠️ Zona de Corrección")
                    c1, c2 = st.columns(2)
                    ids_c = df_c.loc[sel_c.index, 'ID_Unico'].values
                    if c1.button("🔙 Devolver a PENDIENTE", key="btn_c_to_p"):
                        df_full.loc[df_full['ID_Unico'].isin(ids_c), 'Estado'] = 'PENDIENTE'
                        guardar_todo(df_full)
                    if c2.button("🛡️ Mover a RESERVA", key="btn_c_to_r"):
                        df_full.loc[df_full['ID_Unico'].isin(ids_c), 'Estado'] = 'RESERVA'
                        guardar_todo(df_full)
            else:
                st.info("No hay historial de completados.")

        # === TAB 4: NOVEDADES EQUIPOS ===
        with tab4:
            st.subheader("📋 Estado general de Novedades")
            st.write("Tip: Puedes **filtrar cualquier columna** haciendo clic en el título de la columna y seleccionando el icono de la lupa o las tres líneas (Filtro).")
            
            if df_fallas_view.empty:
                st.info("No hay fallas pendientes.")
            else:
                columnas_mostrar = ['Cod Equipo', 'COMPONENTE', 'Falla', 'UBICACIÓN', 'Estado Falla']
                
                st.dataframe(
                    df_fallas_view[columnas_mostrar],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Cod Equipo": st.column_config.TextColumn("CÓD"),
                        "COMPONENTE": st.column_config.TextColumn("Componente"),
                        "Falla": st.column_config.TextColumn("Falla Reportada"),
                        "UBICACIÓN": st.column_config.TextColumn("Ubicación actual")
                    }
                )

    except Exception as e:
        st.error(f"❌ Error procesando datos: {e}")
        st.write(e)
else:
    st.warning("⚠️ No se cargaron datos. Revisa el Excel de pedidos.")
