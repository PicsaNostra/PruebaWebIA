import streamlit as st
import pandas as pd
from datetime import datetime
import io, requests
from github import Github
import altair as alt

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Repuestos Pro", layout="wide", page_icon="🛠️")

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

def cargar_memoria(archivo):
    repo = obtener_repo_privado()
    if not repo: return pd.DataFrame()
    try:
        df = pd.read_csv(io.BytesIO(repo.get_contents(archivo).decoded_content))
        return df
    except: return pd.DataFrame()

# --- FUNCIONES DE LIMPIEZA SEPARADAS ---

# 1. Limpieza Estricta (SOLO PARA REPUESTOS)
def limpiar_ubicacion_repuestos(u):
    u_str = str(u).upper()
    if "SIBAT" in u_str: return "Equipos Sibate"
    if "0348" in u_str: return "IDU 0348 GRUPO 4"
    if "0351" in u_str: return "IDU 0351 GRUPO 7"
    return "OTRA UBICACIÓN"

# 2. Limpieza Amplia (SOLO PARA NOVEDADES - GOOGLE SHEETS)
def limpiar_ubicacion_novedades(u):
    u_s = str(u).upper().strip()
    if not u_s or u_s == "NAN": return "SIN DATO"
    
    if "0348" in u_s: return "IDU 0348 GR 4"
    if "0351" in u_s: return "IDU 0351 GR 7"
    if "SIBATE" in u_s or "SIBATÉ" in u_s: return "SIBATE"
    if "SONSO" in u_s: return "PLANTA SONSO"
    if "CUADRILLA 4" in u_s: return "CUADRILLA 4"
    if "OFICINA" in u_s: return "OFICINA PRINCIPAL"
    if "MALLA VIAL" in u_s: return "MALLA VIAL DEL VALLE"
    if "MATERIALES" in u_s: return "MATERIALES DE SOACHA"
    if "TRANSM" in u_s: return "TRANSM SOACHA"
    if "GUAYURIBA" in u_s: return "GUAYURIBA"
    if "TALLER" in u_s: return "TALLER EXTERNO"
    if "CHICORAL" in u_s: return "CHICORAL"
    if "LABORATORIO" in u_s: return "LABORATORIO"
    if "SEGURIDAD" in u_s: return "SEGURIDAD VIAL"
    if "LOGISTICA" in u_s or "LOGÍSTICA" in u_s: return "LOGISTICA"
    return u_s

@st.cache_data(ttl=300)
def cargar_fallas_gsheet():
    try:
        df = pd.read_csv(URL_FALLAS)
        df.columns = df.columns.astype(str).str.strip().str.upper()
        col_cod = 'CÓD' if 'CÓD' in df.columns else ('COD' if 'COD' in df.columns else df.columns[0])
        
        # --- LECTURA CORREGIDA A LA COLUMNA Q (ÍNDICE 16) ---
        if len(df.columns) > 16:
            df['Ubicación Equipo'] = df.iloc[:, 16].apply(limpiar_ubicacion_novedades)
        else:
            df['Ubicación Equipo'] = "SIN DATO"
            
        estados_v = ["PENDIENTE TRASLADO", "PENDIENTE TÉCNICO", "PENDIENTE REPUESTO", "EN REVISIÓN"]
        df = df[df['ESTADO'].astype(str).str.upper().isin(estados_v)].copy()
        
        df.rename(columns={col_cod: 'Cod Equipo', 'FALLA': 'Falla', 'ESTADO': 'Estado Falla'}, inplace=True)
        if 'COMPONENTE' not in df.columns: df['COMPONENTE'] = "SIN DATO"
        
        return df[['Cod Equipo', 'COMPONENTE', 'Estado Falla', 'Falla', 'Ubicación Equipo']]
    except: return pd.DataFrame()

def guardar_en_github(archivo, df_datos):
    repo = obtener_repo_privado()
    if not repo: return
    if 'Fecha_Prog' in df_datos.columns:
        df_datos['Fecha_Prog'] = df_datos['Fecha_Prog'].astype(str).replace(['NaT', 'None', 'nan'], '')
    
    csv_data = df_datos.to_csv(index=False)
    try:
        cont = repo.get_contents(archivo)
        repo.update_file(cont.path, "Update", csv_data, cont.sha)
    except:
        repo.create_file(archivo, "Init", csv_data)
    st.cache_data.clear()
    st.rerun()

# --- 3. PROCESAMIENTO ---
st.title("🛠️ Control de Repuestos y Novedades")

with st.spinner('⏳ Actualizando bases de datos...'):
    df_pedidos = cargar_excel()
    df_mem_rep = cargar_memoria(ARCHIVO_CSV)
    df_mem_fal = cargar_memoria(ARCHIVO_CSV_FALLAS)
    df_fallas_raw = cargar_fallas_gsheet()

if df_pedidos is not None:
    try:
        # --- PROCESAR PEDIDOS (REPUESTOS) ---
        df_pedidos.rename(columns={
            df_pedidos.columns[0]: 'Cód insumo', df_pedidos.columns[1]: 'Producto', 
            df_pedidos.columns[4]: 'UBI_PED', df_pedidos.columns[6]: 'Cod Equipo',
            df_pedidos.columns[8]: 'Cantidad', df_pedidos.columns[17]: 'Fecha_Llegada'
        }, inplace=True)
        
        df_pedidos['Cantidad'] = pd.to_numeric(df_pedidos['Cantidad'], errors='coerce').fillna(0)
        
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", "ENGRASADOR", 
                   "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", "CABLE", "CINTA", "CORAZA", "LLANTA", "PINTURA"]
        
        mask = (~df_pedidos['Producto'].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df_pedidos['UBI_PED'].astype(str).str.contains("SIBAT|0348|0351", case=False, na=False)) & \
               (~df_pedidos['Cod Equipo'].astype(str).str.startswith('3')) & (df_pedidos['Cod Equipo'] != "A.C.PM") & \
               (df_pedidos['Cantidad'] > 0) & (df_pedidos['Fecha_Llegada'].notna())

        df_base = df_pedidos[mask].copy()
        
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + df_base['Cod Equipo'].astype(str)
        df_base['Ubicación Equipo'] = df_base['UBI_PED'].apply(limpiar_ubicacion_repuestos)
        df_base['Días en Almacén'] = (datetime.now() - pd.to_datetime(df_base['Fecha_Llegada'], errors='coerce')).dt.days.fillna(0).astype(int).clip(lower=0)
        df_base['BUSQUEDA_TOTAL'] = df_base['Cód insumo'].astype(str) + " " + df_base['Producto'].astype(str) + " " + df_base['Cod Equipo'].astype(str)

        if not df_mem_rep.empty:
            df_mem_rep['ID_Unico'] = df_mem_rep['ID_Unico'].astype(str)
            df_full = pd.merge(df_base, df_mem_rep[['ID_Unico', 'Estado', 'Fecha_Prog']], on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'], df_full['Fecha_Prog'] = 'PENDIENTE', None

        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce')
        df_full['Fecha_Prog'] = df_full['Fecha_Prog'].apply(lambda x: x.date() if pd.notnull(x) else None)
        df_full['Prioridad'] = df_full['Días en Almacén'].apply(lambda x: "🔴 Crítico" if x > 30 else "🟢 Normal")

        # --- PROCESAR NOVEDADES ---
        if not df_fallas_raw.empty:
            df_fallas_raw['ID_Falla'] = df_fallas_raw['Cod Equipo'].astype(str) + " - " + df_fallas_raw['Falla'].astype(str)
            if not df_mem_fal.empty:
                df_fallas_full = pd.merge(df_fallas_raw, df_mem_fal, on='ID_Falla', how='left')
            else:
                df_fallas_full = df_fallas_raw.copy()
                df_fallas_full['Enviar_Tecnico'] = False
            df_fallas_full['Enviar_Tecnico'] = df_fallas_full['Enviar_Tecnico'].fillna(False).astype(bool)
        else:
            df_fallas_full = pd.DataFrame()

        # --- BUSCADOR ---
        col_search, col_spacer = st.columns([1, 2])
        with col_search:
            txt_busq = st.text_input("🔍 Buscador General (Filtra equipos o repuestos)", placeholder="Ej: 1661, Chicoral, Filtro").upper().strip()
        
        df_v, df_fv = df_full.copy(), df_fallas_full.copy()
        if txt_busq:
            pat = '|'.join([t.strip() for t in txt_busq.replace(',', '|').split('|') if t.strip()])
            df_v = df_v[df_v['BUSQUEDA_TOTAL'].str.contains(pat, na=False) | df_v['Ubicación Equipo'].str.contains(pat, na=False)]
            if not df_fv.empty:
                df_fv = df_fv[df_fv.astype(str).apply(lambda x: x.str.contains(pat, case=False)).any(axis=1)]

        # --- MÉTRICAS ---
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🚨 Pendientes", len(df_v[df_v['Estado']=='PENDIENTE']))
        m2.metric("🛡️ Reserva", len(df_view[df_view['Estado']=='RESERVA']) if 'df_view' in locals() else len(df_v[df_v['Estado']=='RESERVA']))
        m3.metric("✅ Completados", len(df_v[df_v['Estado']=='COMPLETADO']))
        m4.metric("📋 Novedades", len(df_fv))

        # --- TABS ---
        t1, t2, t3, t4 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS", "📋 NOVEDADES"])
        
        cols_v = ['Prioridad', 'Cód insumo', 'Producto', 'Cod Equipo', 'Ubicación Equipo', 'Cantidad', 'Días en Almacén']
        cfg = {"Sel": st.column_config.CheckboxColumn(width="small"), 
               "Prioridad": st.column_config.TextColumn(width="small"), 
               "Fecha_Prog": st.column_config.DateColumn("📅 Prog", format="DD/MM/YYYY"),
               "Cantidad": st.column_config.NumberColumn("📦 Cant", format="%d"),
               "Ubicación Equipo": st.column_config.TextColumn("📍 Ubicación Equipo", width="medium")}

        # 1. PENDIENTES
        with t1:
            df_p = df_v[df_v['Estado']=='PENDIENTE'].sort_values('Días en Almacén', ascending=False)
            if not df_p.empty:
                df_p.insert(0, "Sel", False)
                ed_p = st.data_editor(df_p[['Sel', 'Fecha_Prog'] + cols_v], column_config=cfg, disabled=cols_v, hide_index=True, use_container_width=True)
                
                if st.button("💾 Guardar Fechas"):
                    for i, r in ed_p.iterrows():
                        df_full.loc[df_full['ID_Unico']==df_p.loc[i, 'ID_Unico'], 'Fecha_Prog'] = r['Fecha_Prog']
                    guardar_en_github(ARCHIVO_CSV, df_full[['ID_Unico', 'Estado', 'Fecha_Prog']])
                
                sel = ed_p[ed_p['Sel']]
                if not sel.empty:
                    c1, c2 = st.columns(2)
                    ids = df_p.loc[sel.index, 'ID_Unico']
                    if c1.button("✅ COMPLETADO"): df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'; guardar_en_github(ARCHIVO_CSV, df_full[['ID_Unico', 'Estado', 'Fecha_Prog']])
                    if c2.button("🛡️ RESERVA"): df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'; guardar_en_github(ARCHIVO_CSV, df_full[['ID_Unico', 'Estado', 'Fecha_Prog']])
            else: st.info("Todo limpio.")

        # 2. RESERVA
        with t2:
            df_r = df_v[df_v['Estado']=='RESERVA']
            if not df_r.empty:
                df_r.insert(0, "Sel", False)
                ed_r = st.data_editor(df_r[['Sel', 'Fecha_Prog'] + cols_v], column_config=cfg, disabled=cols_v, hide_index=True, use_container_width=True)
                
                if st.button("💾 Guardar Fechas (Reserva)"):
                    for i, r in ed_r.iterrows():
                        df_full.loc[df_full['ID_Unico']==df_r.loc[i, 'ID_Unico'], 'Fecha_Prog'] = r['Fecha_Prog']
                    guardar_en_github(ARCHIVO_CSV, df_full[['ID_Unico', 'Estado', 'Fecha_Prog']])

                sel_r = ed_r[ed_r['Sel']]
                if not sel_r.empty and st.button("🔙 Regresar a PENDIENTE"):
                    df_full.loc[df_full['ID_Unico'].isin(df_r.loc[sel_r.index, 'ID_Unico']), 'Estado'] = 'PENDIENTE'
                    guardar_en_github(ARCHIVO_CSV, df_full[['ID_Unico', 'Estado', 'Fecha_Prog']])
            else: st.info("No hay repuestos en reserva.")

        # 3. COMPLETADOS
        with t3:
            df_c = df_v[df_v['Estado']=='COMPLETADO']
            if not df_c.empty:
                df_c.insert(0, "Sel", False)
                ed_c = st.data_editor(df_c[['Sel', 'Fecha_Prog'] + cols_v], column_config=cfg, disabled=cols_v, hide_index=True, use_container_width=True)
                sel_c = ed_c[ed_c['Sel']]
                if not sel_c.empty:
                    b1, b2 = st.columns(2)
                    ids_c = df_c.loc[sel_c.index, 'ID_Unico']
                    if b1.button("🔙 Devolver a PENDIENTE"): 
                        df_full.loc[df_full['ID_Unico'].isin(ids_c), 'Estado'] = 'PENDIENTE'
                        guardar_en_github(ARCHIVO_CSV, df_full[['ID_Unico', 'Estado', 'Fecha_Prog']])
            else: st.info("No hay repuestos completados.")

        # 4. NOVEDADES
        with t4:
            if not df_fv.empty:
                filtro_u = st.multiselect("📍 Filtrar por Obra:", options=sorted(df_fv['Ubicación Equipo'].unique()))
                df_final_f = df_fv[df_fv['Ubicación Equipo'].isin(filtro_u)] if filtro_u else df_fv
                
                with st.expander("📊 Gráficos de Novedades", expanded=True):
                    g1, g2, g3 = st.columns(3)
                    g1.markdown("**Equipos por Ubicación**")
                    g1.altair_chart(alt.Chart(df_final_f).mark_bar(color="#ff4b4b").encode(x=alt.X('Ubicación Equipo:N', sort='-y'), y='distinct(Cod Equipo)'), use_container_width=True)
                    g2.markdown("**Equipos por Componente**")
                    g2.altair_chart(alt.Chart(df_final_f).mark_bar(color="#1f77b4").encode(x=alt.X('COMPONENTE:N', sort='-y'), y='distinct(Cod Equipo)'), use_container_width=True)
                    g3.markdown("**Total Fallas por Obra**")
                    g3.altair_chart(alt.Chart(df_final_f).mark_bar(color="#2ca02c").encode(x=alt.X('Ubicación Equipo:N', sort='-y'), y='count()'), use_container_width=True)

                ed_f = st.data_editor(df_final_f[['Enviar_Tecnico', 'Cod Equipo', 'COMPONENTE', 'Falla', 'Ubicación Equipo']], 
                                      column_config={"Enviar_Tecnico": st.column_config.CheckboxColumn("👷 Obra", width="medium")}, use_container_width=True, hide_index=True)
                
                if st.button("💾 Guardar Gestión Novedades"):
                    for i, r in ed_f.iterrows(): 
                        df_fallas_full.loc[df_fallas_full['ID_Falla']==df_final_f.loc[i, 'ID_Falla'], 'Enviar_Tecnico'] = r['Enviar_Tecnico']
                    guardar_en_github(ARCHIVO_CSV_FALLAS, df_fallas_full[['ID_Falla', 'Enviar_Tecnico']])
            else: st.info("No hay novedades reportadas.")

    except Exception as e: st.error(f"❌ Error: {e}")
else: st.warning("⚠️ Sin datos.")
