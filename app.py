import streamlit as st
import pandas as pd
from datetime import datetime
import io
import urllib.parse
from github import Github

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Repuestos", layout="wide")

# --- 2. CONSTANTES DE CONEXIÓN (LA CAJA FUERTE) ---
# Nombre EXACTO de tu repositorio privado (Usuario/Repositorio)
REPO_DATOS = "PicsaNostra/DatosRepuestos" 

# Nombres exactos de los archivos en la Caja Fuerte
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_CSV = "datos_gestion.csv"

# --- 3. FUNCIONES DE CONEXIÓN ---

def obtener_repo_privado():
    """Se conecta a GitHub y busca la Caja Fuerte"""
    # Verificamos si existe el token en los secretos
    if "GITHUB_TOKEN" not in st.secrets:
        st.error("❌ ERROR CRÍTICO: No has configurado el GITHUB_TOKEN en los Secrets de Streamlit.")
        st.stop()
    
    token = st.secrets["GITHUB_TOKEN"]
    g = Github(token)
    
    try:
        # Intentamos conectar con el repositorio privado
        return g.get_repo(REPO_DATOS)
    except Exception as e:
        st.error(f"❌ ERROR DE CONEXIÓN: No encuentro el repositorio '{REPO_DATOS}'.")
        st.warning("POSIBLES CAUSAS:\n1. El nombre del repo está mal escrito.\n2. Tu Token no tiene marcado el permiso 'repo' (Full control of private repositories).")
        st.stop()
        return None

@st.cache_data(ttl=600)
def cargar_excel_desde_nube():
    """Descarga el Excel privado y lo convierte para Pandas"""
    repo = obtener_repo_privado()
    if not repo: return None

    try:
        # Descargamos el contenido del archivo
        contenido = repo.get_contents(ARCHIVO_EXCEL).decoded_content
        return pd.read_excel(io.BytesIO(contenido))
    except Exception as e:
        st.error(f"⚠️ No pude leer el archivo Excel '{ARCHIVO_EXCEL}': {e}")
        return None

def cargar_csv_desde_nube():
    """Descarga la memoria (CSV) del repositorio privado"""
    repo = obtener_repo_privado()
    # Estructura vacía por defecto si falla la carga
    df_vacio = pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])

    if not repo: return df_vacio

    try:
        contenido = repo.get_contents(ARCHIVO_CSV).decoded_content
        return pd.read_csv(io.BytesIO(contenido))
    except:
        # Si entra aquí, es que el archivo CSV aún no existe (es la primera vez)
        return df_vacio

def subir_a_github(df_nuevo):
    """Guarda los cambios en la Caja Fuerte"""
    repo = obtener_repo_privado()
    if not repo: return

    # Convertimos el DataFrame a CSV (texto)
    content_csv = df_nuevo.to_csv(index=False)
    
    try:
        # Intentamos actualizar el archivo existente
        contents = repo.get_contents(ARCHIVO_CSV)
        repo.update_file(contents.path, "Actualización desde App Pública", content_csv, contents.sha)
        st.toast("✅ Datos guardados en la Caja Fuerte", icon="🔐")
    except:
        # Si no existe, lo creamos de cero
        repo.create_file(ARCHIVO_CSV, "Creación Inicial", content_csv)
        st.toast("✅ Archivo creado en la Caja Fuerte", icon="✨")

# --- 4. LÓGICA PRINCIPAL Y UI ---

st.title("🛠️ Control de Repuestos - Gestión")

# Carga de datos
with st.spinner('⏳ Conectando con la Caja Fuerte...'):
    df = cargar_excel_desde_nube()
    df_memoria = cargar_csv_desde_nube()

if df is not None:
    try:
        # --- PROCESAMIENTO (TU LÓGICA DE NEGOCIO) ---
        # Renombrar columnas clave
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

        # Limpieza de fechas
        df['Fecha_Llegada'] = pd.to_datetime(df['Fecha_Llegada'], errors='coerce')
        
        # Filtros automáticos (Excluir tornillos, etc.)
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", "ENGRASADOR", 
                   "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", "CABLE", "CINTA", 
                   "CORAZA", "LLANTA", "PINTURA"]
        
        # Aplicar filtros
        mask = (~df['Producto'].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df['Cod Equipo'].astype(str).str.startswith('3')) & \
               (df['Cod Equipo'].astype(str) != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df['Fecha_Llegada'].notna())

        df_base = df[mask].copy()
        
        # Crear ID Único para cruzar datos
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + df_base['Cod Equipo'].astype(str)
        
        # Calcular días
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha_Llegada']).dt.days.fillna(0).astype(int)
        df_base['Días en Almacén'] = df_base['Días en Almacén'].apply(lambda x: x if x > 0 else 0)

        # Cruzar con la memoria (CSV)
        if not df_memoria.empty:
            df_base['ID_Unico'] = df_base['ID_Unico'].astype(str)
            df_memoria['ID_Unico'] = df_memoria['ID_Unico'].astype(str)
            df_full = pd.merge(df_base, df_memoria, on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'] = 'PENDIENTE' # Valor por defecto
            df_full['Fecha_Prog'] = None

        # Rellenar vacíos
        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce')

        # --- FUNCIÓN INTERNA PARA GUARDAR ---
        def guardar_cambios_global(df_maestro):
            datos_a_guardar = df_maestro[['ID_Unico', 'Estado', 'Fecha_Prog']].drop_duplicates(subset=['ID_Unico'])
            subir_a_github(datos_a_guardar)
            st.cache_data.clear()
            st.rerun()

        # --- INTERFAZ VISUAL ---
        st.sidebar.header("🔍 Filtros")
        lista_prod = sorted(df_full['Producto'].astype(str).unique())
        filtro_prod = st.sidebar.multiselect("Filtrar por Producto:", lista_prod)
        
        df_view = df_full.copy()
        if filtro_prod:
            df_view = df_view[df_view['Producto'].astype(str).isin(filtro_prod)]

        # Pestañas
        tab1, tab2, tab3 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS"])
        cols_visuales = ['Cód insumo', 'Producto', 'Cod Equipo', 'Días en Almacén']

        # === PESTAÑA 1: PENDIENTES ===
        with tab1:
            df_p = df_view[df_view['Estado'] == 'PENDIENTE'].sort_values('Días en Almacén', ascending=False).copy()
            
            if df_p.empty:
                st.success("✅ ¡No hay pendientes!")
            else:
                # Botón WhatsApp
                with st.expander("📲 Enviar Reporte WhatsApp"):
                    total = len(df_p)
                    mensaje = f"⚠️ Reporte: Hay {total} repuestos pendientes en almacén."
                    link_wa = f"https://api.whatsapp.com/send?text={urllib.parse.quote(mensaje)}"
                    st.link_button("Enviar WhatsApp", link_wa)

                # Tabla editable
                df_p.insert(0, "Seleccionar", False)
                edited_p = st.data_editor(
                    df_p[['Seleccionar', 'Fecha_Prog'] + cols_visuales],
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(required=True),
                        "Fecha_Prog": st.column_config.DateColumn("📅 Programación", format="DD/MM/YYYY"),
                        "Días en Almacén": st.column_config.NumberColumn("⏳ Días")
                    },
                    disabled=cols_visuales,
                    hide_index=True,
                    key="editor_pendientes"
                )

                # Botón de Guardar Fechas
                if st.button("💾 Guardar Cambios (Fechas)", key="btn_save_p"):
                    # Actualizar fechas en el maestro
                    for idx, row in edited_p.iterrows():
                        id_u = df_p.iloc[idx]['ID_Unico'] # Recuperar ID original
                        nueva_fecha = row['Fecha_Prog']
                        df_full.loc[df_full['ID_Unico'] == id_u, 'Fecha_Prog'] = nueva_fecha
                    guardar_cambios_global(df_full)

                # Acciones de Movimiento
                seleccionados = edited_p[edited_p['Seleccionar'] == True]
                if not seleccionados.empty:
                    st.divider()
                    st.write("Con los seleccionados:")
                    col1, col2 = st.columns(2)
                    
                    # Recuperar IDs reales de los seleccionados
                    # Usamos el índice del editor para buscar en el dataframe original filtrado
                    ids_seleccionados = df_p.iloc[seleccionados.index]['ID_Unico'].values

                    if col1.button("✅ Mover a COMPLETADO"):
                        df_full.loc[df_full['ID_Unico'].isin(ids_seleccionados), 'Estado'] = 'COMPLETADO'
                        guardar_cambios_global(df_full)
                    
                    if col2.button("🛡️ Mover a RESERVA"):
                        df_full.loc[df_full['ID_Unico'].isin(ids_seleccionados), 'Estado'] = 'RESERVA'
                        guardar_cambios_global(df_full)

        # === PESTAÑA 2: RESERVA ===
        with tab2:
            df_r = df_view[df_view['Estado'] == 'RESERVA'].copy()
            if df_r.empty:
                st.info("No hay repuestos en reserva.")
            else:
                df_r.insert(0, "Seleccionar", False)
                edited_r = st.data_editor(
                    df_r[['Seleccionar'] + cols_visuales],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn(required=True)},
                    disabled=cols_visuales, hide_index=True, key="editor_reserva"
                )
                
                sel_r = edited_r[edited_r['Seleccionar'] == True]
                if not sel_r.empty:
                    st.divider()
                    ids_sel_r = df_r.iloc[sel_r.index]['ID_Unico'].values
                    if st.button("🔙 Devolver a PENDIENTE"):
                        df_full.loc[df_full['ID_Unico'].isin(ids_sel_r), 'Estado'] = 'PENDIENTE'
                        guardar_cambios_global(df_full)

        # === PESTAÑA 3: COMPLETADOS ===
        with tab3:
            df_c = df_view[df_view['Estado'] == 'COMPLETADO'].copy()
            st.dataframe(df_c[cols_visuales], hide_index=True)

    except Exception as e:
        st.error(f"❌ Ocurrió un error al procesar los datos: {e}")
        st.write("Detalles técnicos para soporte:", e)

else:
    st.warning("⚠️ No se pudieron cargar los datos. Revisa la conexión con GitHub.")
