import streamlit as st
import pandas as pd
from datetime import datetime
import os
import time
import glob

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Auditoría de Mantenimiento", page_icon="🚜", layout="wide")

CARPETA_TEMP = "temp_datos"
if not os.path.exists(CARPETA_TEMP):
    os.makedirs(CARPETA_TEMP)

ARCHIVO_VARADOS = os.path.join(CARPETA_TEMP, "equipos_varados.csv")

def obtener_ruta_guardada(prefijo):
    archivos = glob.glob(os.path.join(CARPETA_TEMP, f"{prefijo}_ultimo.*"))
    return archivos[0] if archivos else None

def cargar_varados():
    if os.path.exists(ARCHIVO_VARADOS):
        return pd.read_csv(ARCHIVO_VARADOS)['Equipo'].tolist()
    return []

def guardar_varados(lista_equipos):
    df_var = pd.DataFrame({'Equipo': lista_equipos})
    df_var.to_csv(ARCHIVO_VARADOS, index=False)

def limpiar_archivos_viejos():
    archivos = glob.glob(os.path.join(CARPETA_TEMP, "*_ultimo.*"))
    tiempo_actual = time.time()
    for ruta in archivos:
        if os.path.exists(ruta):
            if (tiempo_actual - os.path.getmtime(ruta)) > 86400:
                os.remove(ruta)

# --- 2. LÓGICA DE PROCESAMIENTO ---
def analizar_datos_sinco(ruta_o_archivo):
    """Extrae y limpia SINCO exactamente como se pidió al inicio"""
    try:
        df = pd.read_excel(ruta_o_archivo, skiprows=3, usecols="A,F,H,I")
        df.columns = ["Equipo", "Fecha vale", "km Equipo", "hr Equipo"]
    except Exception:
        try:
            df = pd.read_csv(ruta_o_archivo, sep='\t', skiprows=3, encoding='latin-1')
            df = df.iloc[:, [0, 5, 7, 8]]
            df.columns = ["Equipo", "Fecha vale", "km Equipo", "hr Equipo"]
        except Exception:
            raise ValueError("Formato de SINCO no soportado.")

    df = df.dropna(subset=['Equipo'])
    df['Fecha vale'] = pd.to_datetime(df['Fecha vale'], errors='coerce', dayfirst=True)
    df = df.dropna(subset=['Fecha vale'])
    
    # CRUCE INVISIBLE: Creamos una columna temporal solo para cruzar con la plantilla
    df['Codigo_Match'] = df['Equipo'].astype(str).str.split('-').str[0].str.strip()
    
    df = df.sort_values(by=['Equipo', 'Fecha vale'], ascending=[True, False])
    
    df_historial = df.copy()
    df = df.drop_duplicates(subset=['Equipo'], keep='first').copy()
    
    hoy = pd.Timestamp(datetime.today().date())
    df['Días sin actualizar'] = (hoy - df['Fecha vale']).dt.days
    alertas = df[df['Días sin actualizar'] >= 3].copy()
    
    return alertas, df_historial

def analizar_datos_plantilla(ruta_o_archivo):
    """Extrae PLANTILLA a prueba de fallos y sin crasheos"""
    df_full = pd.read_excel(ruta_o_archivo, header=None)
    
    # Rellena columnas vacías si la tabla es muy corta
    while df_full.shape[1] <= 18:
        df_full[df_full.shape[1]] = pd.NA
        
    df = df_full.iloc[:, [0, 16, 17, 18]].copy()
    df.columns = ["Codigo_Match", "hr_Mtto", "km_Mtto", "Fecha_Mtto"]
    
    df = df.dropna(subset=['Codigo_Match'])
    df['Codigo_Match'] = df['Codigo_Match'].astype(str).str.strip()
    
    df['hr_Mtto'] = pd.to_numeric(df['hr_Mtto'], errors='coerce')
    df['km_Mtto'] = pd.to_numeric(df['km_Mtto'], errors='coerce')
    df['Fecha_Mtto'] = pd.to_datetime(df['Fecha_Mtto'], errors='coerce')
    
    df.loc[df['Fecha_Mtto'].dt.year <= 1970, 'Fecha_Mtto'] = pd.NaT
    df = df[~df['Codigo_Match'].str.lower().isin(['equipo', 'codigo', 'código'])]
    
    df = df.sort_values(by=['Codigo_Match', 'Fecha_Mtto'], ascending=[True, False])
    df = df.drop_duplicates(subset=['Codigo_Match'], keep='first')
    
    return df[['Codigo_Match', 'hr_Mtto', 'km_Mtto', 'Fecha_Mtto']]

limpiar_archivos_viejos()

# --- 3. INTERFAZ ---
varados_guardados = cargar_varados()

# ==========================================
# SECCIÓN 1: PLANTILLA (BARRA LATERAL)
# ==========================================
st.sidebar.title("⚙️ Base de Datos Maestra")
st.sidebar.info("Sube aquí el archivo PLANTILLA. Se quedará guardado temporalmente para cruzarlo con tus reportes diarios.")

# El parámetro "key" separa esta subida de la del centro
archivo_plantilla = st.sidebar.file_uploader("📥 Subir PLANTILLA (.xlsx)", type=["xlsx"], key="up_plantilla")
if archivo_plantilla:
    with open(os.path.join(CARPETA_TEMP, "plantilla_ultimo.xlsx"), "wb") as f:
        f.write(archivo_plantilla.getbuffer())
    st.sidebar.success("✅ Archivo PLANTILLA guardado.")

ruta_plantilla = obtener_ruta_guardada("plantilla")
if ruta_plantilla:
    st.sidebar.success("📂 PLANTILLA activa en memoria")
else:
    st.sidebar.warning("⚠️ Faltan datos de Mantenimiento")


# ==========================================
# SECCIÓN 2: SINCO (PANTALLA PRINCIPAL)
# ==========================================
st.title("🚜 Auditoría de Mantenimiento Preventivo")
st.write("Sube tu reporte diario de operación para detectar equipos atrasados y comparar con el taller.")
st.divider()

# El parámetro "key" asegura que no choque con la plantilla
archivo_sinco = st.file_uploader("📥 Subir reporte diario SINCO (.xlsx)", type=["xlsx", "xls", "csv"], key="up_sinco")
if archivo_sinco:
    if "SINCOPAVIMENTOSCOL_NUEVA_InforLSVZ" not in archivo_sinco.name:
        st.warning(f"⚠️ Atención: El archivo se llama '{archivo_sinco.name}'. Asegúrate de usar el reporte oficial.")
    with open(os.path.join(CARPETA_TEMP, "sinco_ultimo.xlsx"), "wb") as f:
        f.write(archivo_sinco.getbuffer())

ruta_sinco = obtener_ruta_guardada("sinco")

# --- 4. PROCESAMIENTO PRINCIPAL ---
if ruta_sinco:
    try:
        df_alertas, df_historial = analizar_datos_sinco(ruta_sinco)
        df_maestro = df_alertas.copy()

        # Cruce de datos seguro
        if ruta_plantilla:
            try:
                df_plan = analizar_datos_plantilla(ruta_plantilla)
                df_maestro = pd.merge(df_maestro, df_plan, on='Codigo_Match', how='left')
            except Exception as e:
                st.error(f"⚠️ Hubo un problema técnico al leer la plantilla: {e}")
                df_maestro['hr_Mtto'] = pd.NA
                df_maestro['km_Mtto'] = pd.NA
                df_maestro['Fecha_Mtto'] = pd.NaT
        else:
            df_maestro['hr_Mtto'] = pd.NA
            df_maestro['km_Mtto'] = pd.NA
            df_maestro['Fecha_Mtto'] = pd.NaT

        st.divider()
        busqueda = st.text_input("🔍 Buscar equipo (Escribe parte del nombre o código):")
        
        df_maestro['¿Varado?'] = df_maestro['Equipo'].isin(varados_guardados)
        if busqueda:
            df_maestro = df_maestro[df_maestro['Equipo'].str.contains(busqueda, case=False, na=False)]
        
        columnas_ordenadas = [
            "¿Varado?", "Equipo", "Fecha vale", "Días sin actualizar", 
            "hr Equipo", "hr_Mtto", "km Equipo", "km_Mtto", "Fecha_Mtto"
        ]
        
        df_criticos = df_maestro[~df_maestro['¿Varado?']][columnas_ordenadas].copy()
        df_varados = df_maestro[df_maestro['¿Varado?']][columnas_ordenadas].copy()

        t1, t2 = st.tabs(["🚨 Alertas Críticas", "🔧 Equipos en Taller"])
        
        config_columnas = {
            "¿Varado?": st.column_config.CheckboxColumn("🔧", help="Marcar/Desmarcar"),
            "Equipo": st.column_config.TextColumn("Equipo (SINCO)"),
            "Fecha vale": st.column_config.DateColumn("Últ. Reporte (SINCO)", format="DD/MM/YYYY"),
            "Días sin actualizar": st.column_config.NumberColumn("Días Atraso", format="%d 🔴"),
            "hr Equipo": st.column_config.NumberColumn("hr (SINCO)"),
            "hr_Mtto": st.column_config.NumberColumn("hr (PLANTILLA)", format="%d 🛠️"),
            "km Equipo": st.column_config.NumberColumn("km (SINCO)"),
            "km_Mtto": st.column_config.NumberColumn("km (PLANTILLA)", format="%d 🛠️"),
            "Fecha_Mtto": st.column_config.DateColumn("Fecha Mtto (PLANTILLA)", format="DD/MM/YYYY")
        }

        columnas_bloqueadas = [col for col in columnas_ordenadas if col != "¿Varado?"]

        with t1:
            if not df_criticos.empty:
                res = st.data_editor(df_criticos, column_config=config_columnas, hide_index=True, use_container_width=True, key="edit_c", disabled=columnas_bloqueadas)
                marcados = res[res['¿Varado?']]['Equipo'].tolist()
                if marcados:
                    guardar_varados(list(set(varados_guardados + marcados)))
                    st.rerun()
            else: st.success("✅ Sin alertas activas.")

        with t2:
            if not df_varados.empty:
                res_v = st.data_editor(df_varados, column_config=config_columnas, hide_index=True, use_container_width=True, key="edit_v", disabled=columnas_bloqueadas)
                desmarcados = res_v[~res_v['¿Varado?']]['Equipo'].tolist()
                if desmarcados:
                    nueva_lista = [e for e in varados_guardados if e not in desmarcados]
                    guardar_varados(nueva_lista)
                    st.rerun()
            else: st.info("Taller vacío.")

        # Gráfica de Picos
        st.divider()
        st.subheader("📈 Análisis de Picos de Horas")
        eq_sel = st.selectbox("Seleccionar equipo para ver historial:", ["(Seleccionar)"] + sorted(df_historial['Equipo'].unique().tolist()))
        
        if eq_sel != "(Seleccionar)":
            hist = df_historial[df_historial['Equipo'] == eq_sel].sort_values('Fecha vale')
            if len(hist) >= 2:
                hist['Pico Horas'] = hist['hr Equipo'].diff()
                st.bar_chart(hist.dropna(subset=['Pico Horas']).set_index('Fecha vale')['Pico Horas'])
                
                if ruta_plantilla:
                    try:
                        df_plan = analizar_datos_plantilla(ruta_plantilla)
                        cod_match = eq_sel.split('-')[0].strip()
                        info_p = df_plan[df_plan['Codigo_Match'] == cod_match]
                        
                        if not info_p.empty:
                            c_a, c_b = st.columns(2)
                            c_a.metric("Último Mtto (hr)", f"{info_p.iloc[0]['hr_Mtto']:,}" if pd.notna(info_p.iloc[0]['hr_Mtto']) else "N/A")
                            c_b.metric("Fecha Último Mtto", info_p.iloc[0]['Fecha_Mtto'].strftime('%d/%m/%Y') if pd.notna(info_p.iloc[0]['Fecha_Mtto']) else "N/A")
                    except: pass
            else:
                st.warning("No hay suficientes datos históricos para este equipo.")

    except Exception as e:
        st.error(f"❌ Error crítico procesando los datos: {e}")
else:
    st.info("💡 Por favor, sube el reporte diario SINCO en el recuadro de arriba para comenzar.")
