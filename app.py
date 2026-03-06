import streamlit as st
import pandas as pd
from datetime import datetime
import io
import urllib.parse
import requests  # <--- NUEVA LIBRERÍA NECESARIA
from github import Github

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Repuestos", layout="wide")

# --- 2. CONSTANTES DE CONEXIÓN ---
# Nombre EXACTO de tu repositorio privado (Usuario/Repositorio)
REPO_DATOS = "PicsaNostra/DatosRepuestos" 

# Nombres de archivos
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_CSV = "datos_gestion.csv"
RAMA = "main" # <--- Cambia a 'master' si tu repo es antiguo, pero suele ser 'main'

# --- 3. FUNCIONES DE CONEXIÓN ---

def obtener_token():
    """Recupera y valida el token"""
    if "GITHUB_TOKEN" not in st.secrets:
        st.error("❌ Falta el Token en Secrets.")
        st.stop()
    return st.secrets["GITHUB_TOKEN"]

def obtener_repo_privado():
    """Conexión para guardar el CSV (archivos pequeños)"""
    token = obtener_token()
    g = Github(token)
    try:
        return g.get_repo(REPO_DATOS)
    except Exception as e:
        st.error(f"❌ No encuentro el repositorio '{REPO_DATOS}': {e}")
        return None

@st.cache_data(ttl=600)
def cargar_excel_desde_nube():
    """
    MÉTODO 'RAW' PARA ARCHIVOS GRANDES (>1MB)
    Usa requests para descargar el binario directo.
    """
    token = obtener_token()
    
    # Construimos la URL del archivo crudo (Raw)
    # Estructura: https://raw.githubusercontent.com/USUARIO/REPO/RAMA/ARCHIVO
    url = f"https://raw.githubusercontent.com/{REPO_DATOS}/{RAMA}/{ARCHIVO_EXCEL}"
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw"
    }
    
    try:
        # Hacemos la petición directa
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            # Éxito: Leemos el contenido binario
            return pd.read_excel(io.BytesIO(response.content), engine='openpyxl')
        elif response.status_code == 404:
            st.error(f"❌ Archivo no encontrado (404). Verifica que '{ARCHIVO_EXCEL}' esté en la rama '{RAMA}'.")
            return None
        else:
            st.error(f"❌ Error descargando Excel: Código {response.status_code}")
            return None
            
    except Exception as e:
        st.error(f"⚠️ Error crítico descargando Excel: {e}")
        return None

def cargar_csv_desde_nube():
    """Descarga la memoria (CSV) usando el método estándar (es liviano)"""
    repo = obtener_repo_privado()
    df_vacio = pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])

    if not repo: return df_vacio

    try:
        contenido = repo.get_contents(ARCHIVO_CSV).decoded_content
        return pd.read_csv(io.BytesIO(contenido))
    except:
        return df_vacio

def subir_a_github(df_nuevo):
    """Guarda los cambios del CSV en la Caja Fuerte"""
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

st.title("🛠️ Control de Repuestos - Gestión")

# Carga de datos
with st.spinner('⏳ Descargando archivo grande (esto puede tardar unos segundos)...'):
    df = cargar_excel_desde_nube()
    df_memoria = cargar_csv_desde_nube()

if df is not None:
    try:
        # --- PROCESAMIENTO ---
        col_insumo = df.columns[0]
        col_prod = df.columns[1]
        col_equipo = df.columns[6]
        col_fecha = df.columns[17]

        df.rename(columns={
            col_insumo: 'Cód insumo',
            col_prod: 'Producto',
            col_equipo: 'Cod Equipo',
            col_fecha: 'Fecha_Llegada'
        }, inplace=True)

        df['Fecha_Llegada'] = pd.to_datetime(df['Fecha_Llegada'], errors='coerce')
        
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
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + df_base['Cod Equipo'].astype(str)
        
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha_Llegada']).dt.days.fillna(0).astype(int)
        df_base['Días en Almacén'] = df_base['Días en Almacén'].apply(lambda x: x if x > 0 else 0)

        # Cruzar con memoria
        if not df_memoria.empty:
            df_base['ID_Unico'] = df_base['ID_Unico'].astype(str)
            df_memoria['ID_Unico'] = df_memoria['ID_Unico'].astype(str)
            df_full = pd.merge(df_base, df_memoria, on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'] = 'PENDIENTE'
            df_full['Fecha_Prog'] = None

        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce')

        # Función Guardar Global
        def guardar_todo(df_maestro):
            datos = df_maestro[['ID_Unico', 'Estado', 'Fecha_Prog']].drop_duplicates(subset=['ID_Unico'])
            subir_a_github(datos)
            st.cache_data.clear()
            st.rerun()

        # --- INTERFAZ ---
        st.sidebar.header("🔍 Filtros")
        lista_prod = sorted(df_full['Producto'].astype(str).unique())
        filtro_prod = st.sidebar.multiselect("Producto:", lista_prod)
        
        df_view = df_full.copy()
        if filtro_prod: df_view = df_view[df_view['Producto'].astype(str).isin(filtro_prod)]

        tab1, tab2, tab3 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS"])
        cols_vis = ['Cód insumo', 'Producto', 'Cod Equipo', 'Días en Almacén']

        # TAB 1
        with tab1:
            df_p = df_view[df_view['Estado'] == 'PENDIENTE'].sort_values('Días en Almacén', ascending=False).copy()
            if df_p.empty:
                st.success("✅ Todo limpio")
            else:
                with st.expander("📲 WhatsApp"):
                    txt = urllib.parse.quote(f"⚠️ {len(df_p)} pendientes.")
                    st.link_button("Enviar", f"https://api.whatsapp.com/send?text={txt}")

                df_p.insert(0, "Sel", False)
                ed_p = st.data_editor(
                    df_p[['Sel', 'Fecha_Prog'] + cols_vis],
                    column_config={
                        "Sel": st.column_config.CheckboxColumn(width="small"),
                        "Fecha_Prog": st.column_config.DateColumn("📅 Prog", format="DD/MM/YYYY"),
                        "Días en Almacén": st.column_config.NumberColumn("⏳ Días")
                    },
                    disabled=cols_vis, hide_index=True, key="ed_p"
                )

                if st.button("💾 Guardar Fechas"):
                    for idx, row in ed_p.iterrows():
                        id_u = df_p.iloc[idx]['ID_Unico']
                        df_full.loc[df_full['ID_Unico'] == id_u, 'Fecha_Prog'] = row['Fecha_Prog']
                    guardar_todo(df_full)

                sel = ed_p[ed_p['Sel'] == True]
                if not sel.empty:
                    st.divider()
                    c1, c2 = st.columns(2)
                    ids = df_p.iloc[sel.index]['ID_Unico'].values
                    if c1.button("✅ A Completado"):
                        df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                        guardar_todo(df_full)
                    if c2.button("🛡️ A Reserva"):
                        df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                        guardar_todo(df_full)

        # TAB 2
        with tab2:
            df_r = df_view[df_view['Estado'] == 'RESERVA'].copy()
            if df_r.empty:
                st.info("Vacío")
            else:
                df_r.insert(0, "Sel", False)
                ed_r = st.data_editor(
                    df_r[['Sel'] + cols_vis],
                    column_config={"Sel": st.column_config.CheckboxColumn(width="small")},
                    disabled=cols_vis, hide_index=True, key="ed_r"
                )
                sel_r = ed_r[ed_r['Sel'] == True]
                if not sel_r.empty and st.button("🔙 Devolver a Pendiente"):
                    ids = df_r.iloc[sel_r.index]['ID_Unico'].values
                    df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'PENDIENTE'
                    guardar_todo(df_full)

        # TAB 3
        with tab3:
            st.dataframe(df_view[df_view['Estado'] == 'COMPLETADO'][cols_vis], hide_index=True)

    except Exception as e:
        st.error(f"❌ Error procesando datos: {e}")

else:
    st.warning("⚠️ No se cargaron datos.")
