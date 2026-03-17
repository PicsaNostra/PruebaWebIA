import streamlit as st
import pandas as pd
from datetime import datetime
import io, requests
from github import Github

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Repuestos Pro", layout="wide", page_icon="🛠️")

REPO_DATOS = "PicsaNostra/DatosRepuestos" 
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_ESTADOS = "ESTADOS%20DE%20EQUIPOS.xlsx" 
ARCHIVO_CSV = "datos_gestion.csv"
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
    df_vacio = pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog', 'Ejecucion_Obra'])
    if not repo: return df_vacio
    try:
        df = pd.read_csv(io.BytesIO(repo.get_contents(ARCHIVO_CSV).decoded_content))
        if 'Ejecucion_Obra' not in df.columns: df['Ejecucion_Obra'] = False
        df['Ejecucion_Obra'] = df['Ejecucion_Obra'].fillna(False).astype(bool)
        return df
    except: return df_vacio

@st.cache_data(ttl=300)
def cargar_fallas():
    df_v = pd.DataFrame(columns=['Cod Equipo', 'COMPONENTE', 'Estado Falla', 'Falla'])
    try:
        df = pd.read_csv(URL_FALLAS)
        if not all(c in df.columns for c in ['CÓD', 'ESTADO', 'FALLA']): return df_v
        if 'COMPONENTE' not in df.columns: df['COMPONENTE'] = "SIN DATO"
        
        df['ESTADO'] = df['ESTADO'].astype(str).str.strip().str.upper()
        df = df[df['ESTADO'].isin(["PENDIENTE TRASLADO", "PENDIENTE TÉCNICO", "PENDIENTE REPUESTO", "EN REVISIÓN"])].copy()
        df.rename(columns={'CÓD': 'Cod Equipo', 'FALLA': 'Falla', 'ESTADO': 'Estado Falla'}, inplace=True)
        
        for col in ['Cod Equipo', 'Falla', 'COMPONENTE']:
            df[col] = df[col].astype(str).str.strip().str.upper() if col != 'Falla' else df[col].astype(str).str.strip()
        return df[['Cod Equipo', 'COMPONENTE', 'Estado Falla', 'Falla']]
    except: return df_v

def guardar_datos(df_m):
    repo = obtener_repo_privado()
    if not repo: return
    df_m['Fecha_Prog'] = df_m['Fecha_Prog'].astype(str).replace('NaT', '')
    csv_data = df_m[['ID_Unico', 'Estado', 'Fecha_Prog', 'Ejecucion_Obra']].drop_duplicates('ID_Unico').to_csv(index=False)
    try:
        cont = repo.get_contents(ARCHIVO_CSV)
        repo.update_file(cont.path, "Update", csv_data, cont.sha)
    except:
        repo.create_file(ARCHIVO_CSV, "Init", csv_data)
    st.cache_data.clear()
    st.rerun()

# --- 3. LÓGICA PRINCIPAL ---
st.title("🛠️ Control de Repuestos y Novedades")

with st.spinner('⏳ Sincronizando...'):
    df_pedidos = cargar_excel()
    df_est = cargar_estados()
    df_mem = cargar_memoria()
    df_fallas = cargar_fallas()

if df_pedidos is not None:
    st.success("✅ Sistema Sincronizado", icon="📡")
    try:
        # Limpieza inicial
        df_pedidos.rename(columns={df_pedidos.columns[0]: 'Cód insumo', df_pedidos.columns[1]: 'Producto', 
                                   df_pedidos.columns[6]: 'Cod Equipo', df_pedidos.columns[17]: 'Fecha_Llegada'}, inplace=True)
        for c in ['Cód insumo', 'Producto', 'Cod Equipo']: 
            df_pedidos[c] = df_pedidos[c].astype(str).str.strip().str.upper()
            
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", "ENGRASADOR", 
                   "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", "CABLE", "CINTA", "CORAZA", "LLANTA", "PINTURA"]
        
        mask = (~df_pedidos['Producto'].str.contains('|'.join(excluir), case=False, na=False)) & \
               (df_pedidos.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df_pedidos['Cod Equipo'].str.startswith('3')) & (df_pedidos['Cod Equipo'] != "A.C.PM") & \
               (pd.to_numeric(df_pedidos.iloc[:, 11], errors='coerce') > 0) & (df_pedidos['Fecha_Llegada'].notna())

        df_base = df_pedidos[mask].copy()
        df_base['ID_Unico'] = df_base['Producto'] + df_base['Cod Equipo']
        df_base['BUSQUEDA_TOTAL'] = df_base['Cód insumo'] + " " + df_base['Producto'] + " " + df_base['Cod Equipo']
        df_base['Fecha_Llegada'] = pd.to_datetime(df_base['Fecha_Llegada'], errors='coerce')
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha_Llegada']).dt.days.fillna(0).astype(int).clip(lower=0)

        # --- UBICACIONES (LIMPIEZA INTELIGENTE) ---
        if df_est is not None and not df_est.empty:
            # Quitamos espacios al inicio y final de todas las columnas y las pasamos a mayúsculas
            df_est.columns = df_est.columns.astype(str).str.strip().str.upper()
            
            # Buscamos la columna del equipo (CÓDIGO, EQUIPO, etc.) o tomamos la primera
            col_eq_est = df_est.columns[0]
            for col in df_est.columns:
                if "CÓD" in col or "COD" in col or "EQUIPO" in col:
                    col_eq_est = col
                    break
                    
            # Buscamos la columna de OBRA ASIGNACIÓN
            col_obra = df_est.columns[5] if len(df_est.columns) > 5 else df_est.columns[-1]
            for col in df_est.columns:
                if "OBRA" in col or "ASIGNAC" in col:
                    col_obra = col
                    break

            df_ubi = df_est[[col_eq_est, col_obra]].copy()
            df_ubi.columns = ['Cod Equipo', 'UBICACIÓN']
            df_ubi['Cod Equipo'] = df_ubi['Cod Equipo'].astype(str).str.strip().str.upper()
            df_ubi['UBICACIÓN'] = df_ubi['UBICACIÓN'].astype(str).str.strip()
            df_ubi = df_ubi.drop_duplicates('Cod Equipo', keep='last')
        else:
            df_ubi = pd.DataFrame(columns=['Cod Equipo', 'UBICACIÓN'])

        if 'UBICACIÓN' in df_base.columns: df_base.drop(columns=['UBICACIÓN'], inplace=True)
        if 'UBICACIÓN' in df_fallas.columns: df_fallas.drop(columns=['UBICACIÓN'], inplace=True)
        if 'COMPONENTE' in df_base.columns: df_base.drop(columns=['COMPONENTE'], inplace=True)

        df_base = pd.merge(df_base, df_ubi, on='Cod Equipo', how='left')
        df_fallas = pd.merge(df_fallas, df_ubi, on='Cod Equipo', how='left')
        
        df_comp = df_fallas[['Cod Equipo', 'COMPONENTE']].drop_duplicates('Cod Equipo', keep='last') if not df_fallas.empty else pd.DataFrame(columns=['Cod Equipo','COMPONENTE'])
        df_base = pd.merge(df_base, df_comp, on='Cod Equipo', how='left')

        df_base['UBICACIÓN'] = df_base['UBICACIÓN'].fillna('SIN DATO')
        df_base['COMPONENTE'] = df_base['COMPONENTE'].fillna('SIN DATO')
        df_fallas['UBICACIÓN'] = df_fallas['UBICACIÓN'].fillna('SIN DATO')

        # Memoria
        if not df_mem.empty:
            df_mem['ID_Unico'] = df_mem['ID_Unico'].astype(str)
            df_full = pd.merge(df_base, df_mem, on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'], df_full['Fecha_Prog'], df_full['Ejecucion_Obra'] = 'PENDIENTE', None, False

        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce') 
        df_full['Ejecucion_Obra'] = df_full['Ejecucion_Obra'].fillna(False).astype(bool)
        df_full['Prioridad'] = df_full['Días en Almacén'].apply(lambda x: "🔴 Crítico" if x > 30 else "🟢 Normal")

        # --- PANEL E INTERFAZ ---
        st.sidebar.download_button("📥 Descargar CSV", df_full.to_csv(index=False).encode('utf-8-sig'), "Repuestos.csv", "text/csv")
        txt_busq = st.sidebar.text_input("🔍 Buscador", placeholder="Ej: 1661").upper().strip()
        
        df_view, df_fview = df_full.copy(), df_fallas.copy()
        if txt_busq:
            df_view = df_view[df_view['BUSQUEDA_TOTAL'].str.contains(txt_busq, na=False) | df_view['UBICACIÓN'].str.contains(txt_busq, case=False, na=False)]
            df_fview = df_fview[df_fview.apply(lambda r: txt_busq in str(r.values).upper(), axis=1)]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🚨 Pendientes", len(df_view[df_view['Estado']=='PENDIENTE']))
        c2.metric("🛡️ Reserva", len(df_view[df_view['Estado']=='RESERVA']))
        c3.metric("✅ Completados", len(df_view[df_view['Estado']=='COMPLETADO']))
        c4.metric("📋 Novedades", len(df_fview), delta="Google Sheets", delta_color="inverse")
        
        t1, t2, t3, t4 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS", "📋 NOVEDADES"])
        cols_v = ['Prioridad', 'Cód insumo', 'Producto', 'Cod Equipo', 'UBICACIÓN', 'Días en Almacén']
        cfg = {"Sel": st.column_config.CheckboxColumn(width="small"), "Ejecucion_Obra": st.column_config.CheckboxColumn("🏗️ En Obra", width="small"),
               "Prioridad": st.column_config.TextColumn(width="small"), "Fecha_Prog": st.column_config.DateColumn("📅 Prog", format="DD/MM/YYYY")}

        with t1:
            df_p = df_view[df_view['Estado']=='PENDIENTE'].sort_values('Días en Almacén', ascending=False)
            if not df_p.empty:
                with st.expander("📊 Gráficos de Equipos Pendientes", expanded=True):
                    g1, g2 = st.columns(2)
                    g1.markdown("📍 **Equipos por Ubicación**")
                    g1.bar_chart(df_p.groupby('UBICACIÓN')['Cod Equipo'].nunique(), color="#ff4b4b")
                    g2.markdown("⚙️ **Equipos por Componente**")
                    g2.bar_chart(df_p.groupby('COMPONENTE')['Cod Equipo'].nunique(), color="#1f77b4")
                
                df_p.insert(0, "Sel", False)
                ed_p = st.data_editor(df_p[['Sel', 'Ejecucion_Obra', 'Fecha_Prog'] + cols_v], column_config=cfg, disabled=cols_v, hide_index=True)
                
                if st.button("💾 Guardar Cambios", type="primary"):
                    for i, r in ed_p.iterrows():
                        df_full.loc[df_full['ID_Unico'] == df_p.loc[i, 'ID_Unico'], ['Fecha_Prog', 'Ejecucion_Obra']] = [r['Fecha_Prog'], r['Ejecucion_Obra']]
                    guardar_datos(df_full)
                    
                sel = ed_p[ed_p['Sel']]
                if not sel.empty:
                    b1, b2 = st.columns(2)
                    ids = df_p.loc[sel.index, 'ID_Unico']
                    if b1.button("✅ COMPLETADO"): 
                        df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                        guardar_datos(df_full)
                    if b2.button("🛡️ RESERVA"):
                        df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                        guardar_datos(df_full)
            else: st.info("Todo limpio.")

        with t2:
            df_r = df_view[df_view['Estado']=='RESERVA']
            if not df_r.empty:
                df_r.insert(0, "Sel", False)
                ed_r = st.data_editor(df_r[['Sel'] + cols_v], column_config=cfg, disabled=cols_v, hide_index=True)
                sel_r = ed_r[ed_r['Sel']]
                if not sel_r.empty and st.button("🔙 PENDIENTE", key="r_to_p"):
                    df_full.loc[df_full['ID_Unico'].isin(df_r.loc[sel_r.index, 'ID_Unico']), 'Estado'] = 'PENDIENTE'
                    guardar_datos(df_full)
            else: st.info("Vacío.")

        with t3:
            df_c = df_view[df_view['Estado']=='COMPLETADO']
            if not df_c.empty:
                df_c.insert(0, "Sel", False)
                ed_c = st.data_editor(df_c[['Sel'] + cols_v], column_config=cfg, disabled=cols_v, hide_index=True)
                sel_c = ed_c[ed_c['Sel']]
                if not sel_c.empty:
                    st.warning("⚠️ Corrección")
                    b1, b2 = st.columns(2)
                    ids_c = df_c.loc[sel_c.index, 'ID_Unico']
                    if b1.button("🔙 PENDIENTE", key="c_p"): df_full.loc[df_full['ID_Unico'].isin(ids_c), 'Estado'] = 'PENDIENTE'; guardar_datos(df_full)
                    if b2.button("🛡️ RESERVA", key="c_r"): df_full.loc[df_full['ID_Unico'].isin(ids_c), 'Estado'] = 'RESERVA'; guardar_datos(df_full)
            else: st.info("Vacío.")

        with t4:
            if not df_fview.empty:
                st.dataframe(df_fview[['Cod Equipo', 'COMPONENTE', 'Falla', 'UBICACIÓN', 'Estado Falla']], hide_index=True, use_container_width=True)
            else: st.info("Vacío.")

    except Exception as e: st.error(f"❌ Error: {e}")
else: st.warning("⚠️ Sin datos.")
