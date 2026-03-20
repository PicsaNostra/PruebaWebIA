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
    """Extrae y limpia SINCO"""
    try:
        df = pd.read_excel(ruta_o_archivo, skiprows=3, usecols="A,F,H,I")
        df.columns = ["Equipo_Bruto", "Fecha vale", "km Equipo", "hr Equipo"]
    except Exception:
        try:
            df = pd.read_csv(ruta_o_archivo, sep='\t', skiprows=3, encoding='latin-1')
            df = df.iloc[:, [0, 5, 7, 8]]
            df.columns = ["Equipo_Bruto", "Fecha vale", "km Equipo", "hr Equipo"]
        except Exception:
            raise ValueError("Formato de SINCO no soportado.")

    df = df.dropna(subset=['Equipo_Bruto'])
    df['Equipo'] = df['Equipo_Bruto'].astype(str).str.split('-').str[0].str.strip()
    df['Fecha vale'] = pd.to_datetime(df['Fecha vale'], errors='coerce', dayfirst=True)
    df = df.dropna(subset=['Fecha vale'])
    df = df.sort_values(by=['Equipo', 'Fecha vale'], ascending=[True, False])
    
    df_historial = df.copy()
    df = df.drop_duplicates(subset=['Equipo'], keep='first').copy()
    
    hoy = pd.Timestamp(datetime.today().date())
    df['Días sin actualizar'] = (hoy - df['Fecha vale']).dt.days
    alertas = df[df['Días sin actualizar'] >= 3].copy()
    
    return alertas, df_historial

def analizar_datos_plantilla(ruta_o_archivo):
    """Extrae PLANTILLA (Columnas A, Q, R, S)"""
    df = pd.read_excel(ruta_o_archivo, usecols="A,Q,R,S", header=None)
    df.columns = ["Equipo_Cod", "hr_Mtto", "km_Mtto", "Fecha_Mtto"]
    
    df = df.dropna(subset=['Equipo_Cod'])
    df['Equipo'] = df['Equipo_Cod'].astype(str).str.strip()
    
    df['hr_Mtto'] = pd.to_numeric(df['hr_Mtto'], errors='coerce')
    df['km_Mtto'] = pd.to_numeric(df['km_Mtto'], errors='coerce')
    df['Fecha_Mtto'] = pd.to_datetime(df['Fecha_Mtto'], errors='coerce')
    
    df = df[df['Equipo'].str.lower() != 'equipo']
    df = df.drop_duplicates(subset=['Equipo'], keep='last')
    
    return df[['Equipo', 'hr_Mtto', 'km_Mtto', 'Fecha_Mtto']]

limpiar_archivos_viejos()

# --- 3. INTERFAZ ---
st.title("🚜 Auditoría de Mantenimiento Preventivo")
st.write("Cruce de datos de Operación (SINCO) vs. Último Mantenimiento (PLANTILLA).")
st.divider()

varados_guardados = cargar_varados()

# Carga de archivos
c1, c2 = st.columns(2)
with c1:
    st.subheader("1. Reporte SINCO")
    archivo_sinco = st.file_uploader("Subir SINCO (.xlsx)", type=["xlsx", "xls", "csv"])
    ruta_sinco = obtener_ruta_guardada("sinco")
    if archivo_sinco:
        with open(os.path.join(CARPETA_TEMP, "sinco_ultimo.xlsx"), "wb") as f:
            f.write(archivo_sinco.getbuffer())
        st.rerun()
    if ruta_sinco:
        st.success("✅ SINCO Cargado")

with c2:
    st.subheader("2. Plantilla Maestra")
    archivo_plantilla = st.file_uploader("Subir PLANTILLA (.xlsx)", type=["xlsx"])
    ruta_plantilla = obtener_ruta_guardada("plantilla")
    if archivo_plantilla:
        with open(os.path.join(CARPETA_TEMP, "plantilla_ultimo.xlsx"), "wb") as f:
            f.write(archivo_plantilla.getbuffer())
        st.rerun()
    if ruta_plantilla:
        st.success("✅ PLANTILLA Cargada")
    else:
        st.warning("⚠️ Sin PLANTILLA (Las columnas de Mtto estarán vacías)")

# Procesamiento
if ruta_sinco:
    try:
        df_alertas, df_historial = analizar_datos_sinco(ruta_sinco)
        df_maestro = df_alertas.copy()

        # Si hay plantilla, hacemos el cruce. Si no, creamos las columnas vacías a la fuerza.
        if ruta_plantilla:
            df_plan = analizar_datos_plantilla(ruta_plantilla)
            df_maestro = pd.merge(df_maestro, df_plan, on='Equipo', how='left')
        else:
            df_maestro['hr_Mtto'] = pd.NA
            df_maestro['km_Mtto'] = pd.NA
            df_maestro['Fecha_Mtto'] = pd.NaT

        st.divider()
        busqueda = st.text_input("🔍 Buscar equipo por código:")
        
        df_maestro['¿Varado?'] = df_maestro['Equipo'].isin(varados_guardados)
        if busqueda:
            df_maestro = df_maestro[df_maestro['Equipo'].str.contains(busqueda, case=False, na=False)]
        
        # ORDENAMOS EXACTAMENTE CÓMO QUEREMOS VER LAS COLUMNAS EN PANTALLA
        columnas_ordenadas = [
            "¿Varado?", "Equipo", "Fecha vale", "Días sin actualizar", 
            "hr Equipo", "hr_Mtto", "km Equipo", "km_Mtto", "Fecha_Mtto"
        ]
        
        df_criticos = df_maestro[~df_maestro['¿Varado?']][columnas_ordenadas].copy()
        df_varados = df_maestro[df_maestro['¿Varado?']][columnas_ordenadas].copy()

        t1, t2 = st.tabs(["🚨 Alertas Críticas", "🔧 Equipos en Taller"])
        
        # Configuración visual de cada columna
        config_columnas = {
            "¿Varado?": st.column_config.CheckboxColumn("🔧", help="Marcar/Desmarcar"),
            "Equipo": st.column_config.TextColumn("Código Equipo"),
            "Fecha vale": st.column_config.DateColumn("Últ. Reporte (SINCO)", format="DD/MM/YYYY"),
            "Días sin actualizar": st.column_config.NumberColumn("Días Atraso", format="%d 🔴"),
            "hr Equipo": st.column_config.NumberColumn("hr (SINCO)"),
            "hr_Mtto": st.column_config.NumberColumn("hr (PLANTILLA)", format="%d 🛠️"),
            "km Equipo": st.column_config.NumberColumn("km (SINCO)"),
            "km_Mtto": st.column_config.NumberColumn("km (PLANTILLA)", format="%d 🛠️"),
            "Fecha_Mtto": st.column_config.DateColumn("Fecha Mtto (PLANTILLA)", format="DD/MM/YYYY")
        }

        # Bloqueamos todas las columnas excepto el Checkbox de "Varado"
        columnas_bloqueadas = [col for col in columnas_ordenadas if col != "¿Varado?"]

        with t1:
            if not df_criticos.empty:
                res = st.data_editor(df_criticos, column_config=config_columnas, hide_index=True, use_container_width=True, key="edit_c", disabled=columnas_bloqueadas)
                marcados = res[res['¿Varado?']]['Equipo'].tolist()
                if marcados:
                    guardar_varados(list(set(varados_guardados + marcados)))
                    st.rerun()
            else: st.success("Sin alertas.")

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
                
                # Mostrar datos de plantilla si existen
                if ruta_plantilla:
                    df_plan = analizar_datos_plantilla(ruta_plantilla)
                    info_p = df_plan[df_plan['Equipo'] == eq_sel]
                    if not info_p.empty:
                        c_a, c_b = st.columns(2)
                        c_a.metric("Último Mtto (hr)", f"{info_p.iloc[0]['hr_Mtto']:,}" if pd.notna(info_p.iloc[0]['hr_Mtto']) else "N/A")
                        c_b.metric("Fecha Último Mtto", info_p.iloc[0]['Fecha_Mtto'].strftime('%d/%m/%Y') if pd.notna(info_p.iloc[0]['Fecha_Mtto']) else "N/A")

    except Exception as e:
        st.error(f"Error procesando datos: {e}")
