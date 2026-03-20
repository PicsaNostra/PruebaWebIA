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

# --- MEMORIA DE DATOS ---
def cargar_varados():
    if os.path.exists(ARCHIVO_VARADOS):
        return pd.read_csv(ARCHIVO_VARADOS)['Equipo'].tolist()
    return []

def guardar_varados(lista_equipos):
    df_var = pd.DataFrame({'Equipo': lista_equipos})
    df_var.to_csv(ARCHIVO_VARADOS, index=False)

# --- 2. LÓGICA DE PROCESAMIENTO ---
def limpiar_archivos_viejos():
    archivos = glob.glob(os.path.join(CARPETA_TEMP, "*_ultimo.*"))
    tiempo_actual = time.time()
    for ruta in archivos:
        if os.path.exists(ruta):
            if (tiempo_actual - os.path.getmtime(ruta)) > 86400:
                os.remove(ruta)

def analizar_datos_sinco(ruta_o_archivo):
    """Extrae y limpia SINCO (Encabezados en fila 4 / A4)"""
    try:
        df = pd.read_excel(ruta_o_archivo, skiprows=3, usecols="A,F,H,I")
        df.columns = ["Equipo_Bruto", "Fecha vale", "km Equipo", "hr Equipo"]
    except Exception:
        # Fallback para archivos planos/CSV
        try:
            df = pd.read_csv(ruta_o_archivo, sep='\t', skiprows=3, encoding='latin-1')
            df = df.iloc[:, [0, 5, 7, 8]]
            df.columns = ["Equipo_Bruto", "Fecha vale", "km Equipo", "hr Equipo"]
        except Exception:
            raise ValueError("Formato de SINCO no soportado.")

    df = df.dropna(subset=['Equipo_Bruto'])
    # Separar código antes del "-"
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
    """Extrae PLANTILLA (Columnas A, Q, R, S) manejando vacíos e inconsistencias"""
    # Leemos sin encabezado definido para no perder datos si hay filas vacías al inicio
    df = pd.read_excel(ruta_o_archivo, usecols="A,Q,R,S", header=None)
    df.columns = ["Equipo_Cod", "hr_Mtto", "km_Mtto", "Fecha_Mtto"]
    
    # 1. ELIMINAR FILAS VACÍAS: Si la columna A está vacía, no hay equipo
    df = df.dropna(subset=['Equipo_Cod'])
    
    # 2. LIMPIEZA DE CÓDIGO: Convertir a texto y quitar espacios
    df['Equipo'] = df['Equipo_Cod'].astype(str).str.strip()
    
    # 3. MANEJO DE INCONSISTENCIAS: Convertir a números y fechas forzadamente
    df['hr_Mtto'] = pd.to_numeric(df['hr_Mtto'], errors='coerce')
    df['km_Mtto'] = pd.to_numeric(df['km_Mtto'], errors='coerce')
    df['Fecha_Mtto'] = pd.to_datetime(df['Fecha_Mtto'], errors='coerce')
    
    # 4. Quitar posibles filas de encabezado que se colaron (si el código es "Equipo")
    df = df[df['Equipo'].str.lower() != 'equipo']
    
    # 5. Si hay duplicados en la plantilla, nos quedamos con el último registro
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

with c2:
    st.subheader("2. Plantilla Maestra")
    archivo_plantilla = st.file_uploader("Subir PLANTILLA (.xlsx)", type=["xlsx"])
    ruta_plantilla = obtener_ruta_guardada("plantilla")
    if archivo_plantilla:
        with open(os.path.join(CARPETA_TEMP, "plantilla_ultimo.xlsx"), "wb") as f:
            f.write(archivo_plantilla.getbuffer())
        st.rerun()

# Procesamiento
if ruta_sinco:
    try:
        df_alertas, df_historial = analizar_datos_sinco(ruta_sinco)
        df_maestro = df_alertas

        if ruta_plantilla:
            df_plan = analizar_datos_plantilla(ruta_plantilla)
            # CRUCE DE DATOS
            df_maestro = pd.merge(df_alertas, df_plan, on='Equipo', how='left')
        
        # Filtros y Visualización
        st.divider()
        busqueda = st.text_input("🔍 Buscar equipo por código:")
        
        df_maestro['¿Varado?'] = df_maestro['Equipo'].isin(varados_guardados)
        if busqueda:
            df_maestro = df_maestro[df_maestro['Equipo'].str.contains(busqueda, case=False, na=False)]
        
        df_criticos = df_maestro[~df_maestro['¿Varado?']].copy()
        df_varados = df_maestro[df_maestro['¿Varado?']].copy()

        t1, t2 = st.tabs(["🚨 Alertas Críticas", "🔧 Equipos en Taller"])
        
        # Configuración de columnas para mostrar en las tablas
        config_columnas = {
            "¿Varado?": st.column_config.CheckboxColumn("🔧"),
            "Equipo": "Código",
            "Fecha vale": st.column_config.DateColumn("Últ. Reporte"),
            "hr Equipo": "hr Actual",
            "hr_Mtto": st.column_config.NumberColumn("hr Últ. Mtto", format="%d"),
            "Fecha_Mtto": st.column_config.DateColumn("Fecha Últ. Mtto"),
            "Días sin actualizar": st.column_config.NumberColumn("Días Atraso", format="%d 🔴")
        }

        with t1:
            if not df_criticos.empty:
                res = st.data_editor(df_criticos, column_config=config_columnas, hide_index=True, use_container_width=True, key="edit_c", disabled=["Equipo", "Fecha vale", "hr Equipo", "hr_Mtto", "Fecha_Mtto", "Días sin actualizar"])
                marcados = res[res['¿Varado?']]['Equipo'].tolist()
                if marcados:
                    guardar_varados(list(set(varados_guardados + marcados)))
                    st.rerun()
            else: st.success("Sin alertas.")

        with t2:
            if not df_varados.empty:
                res_v = st.data_editor(df_varados, column_config=config_columnas, hide_index=True, use_container_width=True, key="edit_v", disabled=["Equipo", "Fecha vale", "hr Equipo", "hr_Mtto", "Fecha_Mtto", "Días sin actualizar"])
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
                    info_p = df_plan[df_plan['Equipo'] == eq_sel]
                    if not info_p.empty:
                        c_a, c_b = st.columns(2)
                        c_a.metric("Último Mtto (hr)", f"{info_p.iloc[0]['hr_Mtto']:,}")
                        c_b.metric("Fecha Último Mtto", info_p.iloc[0]['Fecha_Mtto'].strftime('%d/%m/%Y') if pd.notna(info_p.iloc[0]['Fecha_Mtto']) else "N/A")

    except Exception as e:
        st.error(f"Error procesando datos: {e}")
