import streamlit as st
import pandas as pd
from datetime import datetime
import io, requests
from github import Github
import altair as alt

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Repuestos Pro", layout="wide", page_icon="🛠️")

# Estilo CSS para expandir la tabla y ajustar el buscador
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

REPO_DATOS = "PicsaNostra/DatosRepuestos" 
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_ESTADOS = "ESTADOS%20DE%20EQUIPOS.xlsx" 
ARCHIVO_CSV = "datos_gestion.csv"
ARCHIVO_CSV_FALLAS = "fallas_gestion.csv" 
RAMA = "main"
URL_FALLAS = "https://docs.google.com/spreadsheets/d/1o22GZKmqCmuABGaR1nyLe2jCMBti7cWJtv38wvgH0PQ/export?format=csv&gid=0"

# --- 2. CONEXIONES ---
def obtener_token():
    if "GITHUB_TOKEN" not in st.secrets:
        st.error("❌ Falta el Token en Secrets.")
        st.stop()
    return st.secrets["GITHUB_TOKEN"]

def obtener_repo_privado():
    try:
        return Github(obtener_token()).get_repo(REPO_DATOS)
    except: return None

@st.cache_data(ttl=600)
def cargar_excel():
    url = f"https://raw.githubusercontent.com/{REPO_DATOS}/{RAMA}/{ARCHIVO_EXCEL}"
    headers = {"Authorization": f"token {obtener_token()}", "Accept": "application/vnd.github.v3.raw"}
    res = requests.get(url, headers=headers)
    return pd.read_excel(io.BytesIO(res.content), engine='openpyxl') if res.status_code == 200 else None

@st.cache_data(ttl=600)
def cargar_estados():
    url = f"https://raw.githubusercontent.com/{REPO_DATOS}/{RAMA}/{ARCHIVO_ESTADOS}"
    headers = {"Authorization": f"token {obtener_token()}", "Accept": "application/vnd.github.v3.raw"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return pd.read_excel(io.BytesIO(res.content), sheet_name="INFORMACIÓN EDITABLE", engine='openpyxl')
    return None

def cargar_memoria():
    repo = obtener_repo_privado()
    df_vacio = pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])
    if not repo: return df_vacio
    try:
        df = pd.read_csv(io.BytesIO(repo.get_contents(ARCHIVO_CSV).decoded_content))
        return df
    except: return df_vacio

def cargar_memoria_fallas():
    repo = obtener_repo_privado()
    df_vacio = pd.DataFrame(columns=['ID_Falla', 'Enviar_Tecnico'])
    if not repo: return df_vacio
    try:
        df = pd.read_csv(io.BytesIO(repo.get_contents(ARCHIVO_CSV_FALLAS).decoded_content))
        df['Enviar_Tecnico'] = df['Enviar_Tecnico'].fillna(False).astype(bool)
        return df
    except: return df_vacio

# --- Función Limpiadora de Ubicaciones ---
def limpiar_ubicacion(u):
    u_str = str(u).upper()
    if "SIBAT" in u_str: return "Equipos Sibate"
    if "0348" in u_str: return "IDU 0348 GRUPO 4"
    if "0351" in u_str: return "IDU 0351 GRUPO 7"
    return "OTRA UBICACIÓN"

@st.cache_data(ttl=300)
def cargar_fallas():
    df_v = pd.DataFrame(columns=['Cod Equipo', 'COMPONENTE', 'Estado Falla', 'Falla', 'Ubicación Equipo'])
    try:
        df = pd.read_csv(URL_FALLAS)
        # Limpiar nombres de columnas
        df.columns = df.columns.astype(str).str.strip().str.upper()
        
        # Identificar columnas básicas
        col_cod = 'CÓD' if 'CÓD' in df.columns else ('COD' if 'COD' in df.columns else None)
        
        if not col_cod or 'ESTADO' not in df.columns or 'FALLA' not in df.columns: 
            return df_v
            
        if 'COMPONENTE' not in df.columns: df['COMPONENTE'] = "SIN DATO"
        
        # EXTRAER UBICACIÓN DESDE COLUMNA E (Índice 4)
        if len(df.columns) > 4:
            df['Ubicación Equipo'] = df.iloc[:, 4].apply(limpiar_ubicacion)
        else:
            df['Ubicación Equipo'] = "SIN DATO"
        
        # Filtrar estados válidos
        df['ESTADO'] = df['ESTADO'].astype(str).str.strip().str.upper()
        df = df[df['ESTADO'].isin(["PENDIENTE TRASLADO", "PENDIENTE TÉCNICO", "PENDIENTE REPUESTO", "EN REVISIÓN"])].copy()
        
        # Renombrar y limpiar datos
        df.rename(columns={col_cod: 'Cod Equipo', 'FALLA': 'Falla', 'ESTADO': 'Estado Falla'}, inplace=True)
        for col in ['Cod Equipo', 'Falla', 'COMPONENTE']:
            df[col] = df[col].astype(str).str.strip().str.upper() if col != 'Falla' else df[col].astype(str).str.strip()
            
        return df[['Cod Equipo', 'COMPONENTE', 'Estado Falla', 'Falla', 'Ubicación Equipo']]
    except: return df_v

def guardar_datos(df_m):
    repo = obtener_repo_privado()
    if not repo: return
    df_m['Fecha_Prog'] = df_m['Fecha_Prog'].astype(str).replace('NaT', '')
    csv_data = df_m[['ID_Unico', 'Estado', 'Fecha_Prog']].drop_duplicates('ID_Unico').to_csv(index=False)
    try:
        cont = repo.get_contents(ARCHIVO_CSV)
        repo.update_file(cont.path, "Update", csv_data, cont.sha)
    except:
        repo.create_file(ARCHIVO_CSV, "Init", csv_data)
    st.cache_data.clear()
    st.rerun()

def guardar_datos_fallas(df_f):
    repo = obtener_repo_privado()
    if not repo: return
    csv_data = df_f[['ID_Falla', 'Enviar_Tecnico']].drop_duplicates('ID_Falla').to_csv(index=False)
    try:
        cont = repo.get_contents(ARCHIVO_CSV_FALLAS)
        repo.update_file(cont.path, "Update Fallas", csv_data, cont.sha)
    except:
        repo.create_file(ARCHIVO_CSV_FALLAS, "Init Fallas", csv_data)
    st.cache_data.clear()
    st.rerun()

# --- 3. LÓGICA PRINCIPAL ---
st.title("🛠️ Control de Repuestos y Novedades")

with st.spinner('⏳ Sincronizando con Google Sheet...'):
    df_pedidos = cargar_excel()
    df_est = cargar_estados()
    df_mem = cargar_memoria()
    df_mem_fallas = cargar_memoria_fallas()
    df_fallas = cargar_fallas()

if df_pedidos is not None:
    try:
        # --- PROCESAMIENTO PEDIDOS ---
        df_pedidos.rename(columns={
            df_pedidos.columns[0]: 'Cód insumo', 
            df_pedidos.columns[1]: 'Producto', 
            df_pedidos.columns[4]: 'UBICACION_PEDIDO',
            df_pedidos.columns[6]: 'Cod Equipo',
            df_pedidos.columns[8]: 'Cantidad',
            df_pedidos.columns[17]: 'Fecha_Llegada'
        }, inplace=True)
        
        for c in ['Cód insumo', 'Producto', 'Cod Equipo']: 
            df_pedidos[c] = df_pedidos[c].astype(str).str.strip().str.upper()
            
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", "ENGRASADOR", 
                   "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", "CABLE", "CINTA", "CORAZA", "LLANTA", "PINTURA"]
        
        mask = (~df_pedidos['Producto'].str.contains('|'.join(excluir), case=False, na=False)) & \
               (df_pedidos['UBICACION_PEDIDO'].astype(str).str.contains("SIBAT|0348|0351", case=False, na=False)) & \
               (~df_pedidos['Cod Equipo'].str.startswith('3')) & (df_pedidos['Cod Equipo'] != "A.C.PM") & \
               (pd.to_numeric(df_pedidos.iloc[:, 11], errors='coerce') > 0) & (df_pedidos['Fecha_Llegada'].notna())

        df_base = df_pedidos[mask].copy()
        df_base['ID_Unico'] = df_base['Producto'] + df_base['Cod Equipo']
        df_base['BUSQUEDA_TOTAL'] = df_base['Cód insumo'] + " " + df_base['Producto'] + " " + df_base['Cod Equipo']
        df_base['Fecha_Llegada'] = pd.to_datetime(df_base['Fecha_Llegada'], errors='coerce')
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha_Llegada']).dt.days.fillna(0).astype(int).clip(lower=0)
        df_base['Ubicación Equipo'] = df_base['UBICACION_PEDIDO'].apply(limpiar_ubicacion)

        # Traemos componente de fallas a repuestos
        df_comp = df_fallas[['Cod Equipo', 'COMPONENTE']].drop_duplicates('Cod Equipo', keep='last') if not df_fallas.empty else pd.DataFrame(columns=['Cod Equipo','COMPONENTE'])
        df_base = pd.merge(df_base, df_comp, on='Cod Equipo', how='left')
        df_base['COMPONENTE'] = df_base['COMPONENTE'].fillna('SIN DATO')

        if not df_mem.empty:
            df_mem['ID_Unico'] = df_mem['ID_Unico'].astype(str)
            df_full = pd.merge(df_base, df_mem, on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'], df_full['Fecha_Prog'] = 'PENDIENTE', None

        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce') 
        df_full['Prioridad'] = df_full['Días en Almacén'].apply(lambda x: "🔴 Crítico" if x > 30 else "🟢 Normal")

        # --- MEMORIA NOVEDADES ---
        if not df_fallas.empty:
            df_fallas['ID_Falla'] = df_fallas['Cod Equipo'] + " - " + df_fallas['Falla']
            if not df_mem_fallas.empty:
                df_fallas = pd.merge(df_fallas, df_mem_fallas, on='ID_Falla', how='left')
            else:
                df_fallas['Enviar_Tecnico'] = False
            df_fallas['Enviar_Tecnico'] = df_fallas['Enviar_Tecnico'].fillna(False).astype(bool)

        # --- INTERFAZ ---
        col_search, col_spacer = st.columns([1, 2])
        with col_search:
            txt_busq = st.text_input("🔍 Buscador General", placeholder="Ej: 1661").upper().strip()
        
        df_view, df_fview = df_full.copy(), df_fallas.copy()
        if txt_busq:
            df_view = df_view[df_view['BUSQUEDA_TOTAL'].str.contains(txt_busq, na=False) | df_view['Ubicación Equipo'].str.contains(txt_busq, case=False, na=False)]
            df_fview = df_fview[df_fview.apply(lambda r: txt_busq in str(r.values).upper(), axis=1)]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🚨 Pendientes", len(df_view[df_view['Estado']=='PENDIENTE']))
        m2.metric("🛡️ Reserva", len(df_view[df_view['Estado']=='RESERVA']))
        m3.metric("✅ Completados", len(df_view[df_view['Estado']=='COMPLETADO']))
        m4.metric("📋 Novedades", len(df_fview), delta="Google Sheets")
        
        t1, t2, t3, t4 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS", "📋 NOVEDADES"])
        
        cols_v = ['Prioridad', 'Cód insumo', 'Producto', 'Cod Equipo', 'Ubicación Equipo', 'Cantidad', 'Días en Almacén']
        cfg = {"Sel": st.column_config.CheckboxColumn(width="small"), 
               "Prioridad": st.column_config.TextColumn(width="small"), 
               "Fecha_Prog": st.column_config.DateColumn("📅 Prog", format="DD/MM/YYYY"),
               "Cantidad": st.column_config.NumberColumn("📦 Cant"),
               "Ubicación Equipo": st.column_config.TextColumn("📍 Ubicación Equipo", width="large")}

        with t1:
            df_p = df_view[df_view['Estado']=='PENDIENTE'].sort_values('Días en Almacén', ascending=False)
            if not df_p.empty:
                df_p.insert(0, "Sel", False)
                ed_p = st.data_editor(df_p[['Sel', 'Fecha_Prog'] + cols_v], column_config=cfg, disabled=cols_v, hide_index=True, use_container_width=True)
                if st.button("💾 Guardar Cambios", type="primary"):
                    for i, r in ed_p.iterrows():
                        df_full.loc[df_full['ID_Unico'] == df_p.loc[i, 'ID_Unico'], ['Fecha_Prog']] = [r['Fecha_Prog']]
                    guardar_datos(df_full)
                sel = ed_p[ed_p['Sel']]
                if not sel.empty:
                    b1, b2 = st.columns(2)
                    ids = df_p.loc[sel.index, 'ID_Unico']
                    if b1.button("✅ Mover a COMPLETADO"): 
                        df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                        guardar_datos(df_full)
                    if b2.button("🛡️ Mover a RESERVA"):
                        df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                        guardar_datos(df_full)
            else: st.info("Todo limpio.")

        with t4:
            if not df_fview.empty:
                filtro_ubi = st.multiselect("📍 Filtrar por Ubicación:", options=sorted(df_fview['Ubicación Equipo'].dropna().unique()))
                df_fv_f = df_fview[df_fview['Ubicación Equipo'].isin(filtro_ubi)] if filtro_ubi else df_fview
                
                with st.expander("📊 Gráficos de Novedades (Datos de Google Sheets)", expanded=True):
                    g1, g2, g3 = st.columns(3)
                    
                    # Gráfico 1: Equipos únicos por Ubicación
                    chart_ubi = alt.Chart(df_fv_f.groupby('Ubicación Equipo')['Cod Equipo'].nunique().reset_index(name='Cantidad')).mark_bar(color="#ff4b4b").encode(
                        x=alt.X('Ubicación Equipo:N', sort='-y', title='Ubicación'),
                        y=alt.Y('Cantidad:Q', title='Equipos')
                    )
                    g1.markdown("📍 **Equipos por Ubicación**")
                    g1.altair_chart(chart_ubi, use_container_width=True)
                    
                    # Gráfico 2: Equipos por Componente
                    chart_comp = alt.Chart(df_fv_f.groupby('COMPONENTE')['Cod Equipo'].nunique().reset_index(name='Cantidad')).mark_bar(color="#1f77b4").encode(
                        x=alt.X('COMPONENTE:N', sort='-y', title='Componente'),
                        y=alt.Y('Cantidad:Q', title='Equipos')
                    )
                    g2.markdown("⚙️ **Equipos por Componente**")
                    g2.altair_chart(chart_comp, use_container_width=True)

                    # Gráfico 3: Total Fallas por Ubicación
                    chart_fallas = alt.Chart(df_fv_f.groupby('Ubicación Equipo')['ID_Falla'].count().reset_index(name='Cantidad')).mark_bar(color="#2ca02c").encode(
                        x=alt.X('Ubicación Equipo:N', sort='-y', title='Ubicación'),
                        y=alt.Y('Cantidad:Q', title='Fallas')
                    )
                    g3.markdown("🚨 **Total Fallas por Ubicación**")
                    g3.altair_chart(chart_fallas, use_container_width=True)
                
                ed_f = st.data_editor(df_fv_f[['Enviar_Tecnico', 'Cod Equipo', 'COMPONENTE', 'Falla', 'Ubicación Equipo']], use_container_width=True, hide_index=True)
                if st.button("💾 Guardar Gestión Novedades"):
                    for i, r in ed_f.iterrows():
                        df_fallas.loc[df_fallas['ID_Falla'] == df_fv_f.loc[i, 'ID_Falla'], 'Enviar_Tecnico'] = r['Enviar_Tecnico']
                    guardar_datos_fallas(df_fallas)

    except Exception as e: st.error(f"❌ Error: {e}")
else: st.warning("⚠️ Sin datos.")
