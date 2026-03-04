import streamlit as st
import pandas as pd
from datetime import datetime
import os

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor de Repuestos", layout="wide")
st.title("🛠️ Control de Repuestos - Reporte Semanal")

# Archivos
archivo_pedidos = "PEDIDOS.xlsx"
archivo_contingencia = "contingencias.csv"

# --- FUNCIONES DE MEMORIA (PERSISTENCIA) ---
def cargar_contingencias():
    if os.path.exists(archivo_contingencia):
        try:
            df_cont = pd.read_csv(archivo_contingencia)
            return df_cont['Identificador'].tolist()
        except:
            return []
    return []

def guardar_contingencias(lista_items):
    # Guardamos en un CSV aparte para que no se borre al cambiar el Excel semanal
    df_save = pd.DataFrame({'Identificador': lista_items})
    df_save.to_csv(archivo_contingencia, index=False)

# --- INICIO DE LA APP ---
if os.path.exists(archivo_pedidos):
    try:
        # 1. Cargar Pedidos
        df = pd.read_excel(archivo_pedidos)
        
        # Renombrar columnas clave
        df.rename(columns={
            df.columns[1]: 'Producto', 
            df.columns[6]: 'Cod Equipo', 
            df.columns[17]: 'Fecha'
        }, inplace=True)

        # 2. Limpieza de Datos
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
        
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", 
                   "ENGRASADOR", "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", 
                   "CABLE", "CINTA", "CORAZA", "LLANTA", "PINTURA"]
        
        # Filtros Base (Bogotá, Sin exclusiones, Inventario > 0)
        mask = (~df['Producto'].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df['Cod Equipo'].astype(str).str.startswith('3')) & \
               (df['Cod Equipo'].astype(str) != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df['Fecha'].notna())

        df_base = df[mask].copy()
        
        # Crear ID Único (Producto + Equipo) para identificar exactamente cuál es contingencia
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + " (" + df_base['Cod Equipo'].astype(str) + ")"
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha']).dt.days

        # --- 3. GESTIÓN DE CONTINGENCIA (MEMORIA) ---
        st.sidebar.header("🛡️ Configurar Contingencia")
        st.sidebar.info("Los items seleccionados aquí se moverán a la lista de 'Stock de Reserva' y saldrán de las alertas.")

        # Cargar lo guardado anteriormente
        contingencias_guardadas = cargar_contingencias()
        
        # Listado de todos los items disponibles hoy
        items_disponibles = sorted(df_base['ID_Unico'].unique())
        
        # Selector Multiselect (Aquí digitas y seleccionas)
        seleccion_contingencia = st.sidebar.multiselect(
            "Digita los repuestos de reserva:",
            options=items_disponibles,
            default=[x for x in contingencias_guardadas if x in items_disponibles]
        )
        
        # Guardar cambios automáticamente si el usuario modifica algo
        if set(seleccion_contingencia) != set(contingencias_guardadas):
            guardar_contingencias(seleccion_contingencia)

        # --- 4. SEPARACIÓN DE LISTAS ---
        # Lista A: Contingencia (Lo que seleccionaste)
        df_contingencia = df_base[df_base['ID_Unico'].isin(seleccion_contingencia)]
        
        # Lista B: Pendientes Reales (Todo lo que NO es contingencia)
        df_pendientes = df_base[~df_base['ID_Unico'].isin(seleccion_contingencia)]
        
        # Ordenar pendientes por antigüedad
        df_pendientes = df_pendientes.sort_values('Días en Almacén', ascending=False)

        # --- 5. VISUALIZACIÓN POR PESTAÑAS ---
        fecha_mod = datetime.fromtimestamp(os.path.getmtime(archivo_pedidos)).strftime('%d/%m/%Y')
        st.write(f"📅 **Datos del Excel cargado el:** {fecha_mod}")

        # Creamos dos pestañas
        tab1, tab2 = st.tabs(["🚨 PENDIENTES POR INSTALAR", "🛡️ STOCK DE CONTINGENCIA"])

        with tab1:
            st.markdown(f"### Items que requieren gestión ({len(df_pendientes)})")
            if df_pendientes.empty:
                st.success("¡Todo al día! No hay pendientes de instalación.")
            else:
                # Mostrar tabla limpia
                cols_ver = ['Producto', 'Cod Equipo', 'UBICACIÓN', df.columns[11], 'Días en Almacén']
                st.dataframe(df_pendientes[cols_ver], use_container_width=True)
                
                # Botón descarga SOLO pendientes
                st.download_button(
                    "📥 Descargar Lista de Pendientes",
                    df_pendientes.to_csv(index=False).encode('utf-8'),
                    "Pendientes_Instalacion.csv"
                )

        with tab2:
            st.markdown(f"### Repuestos en Stock de Reserva ({len(df_contingencia)})")
            st.info("Estos items no se consideran retrasados ya que son stock de seguridad.")
            
            if not df_contingencia.empty:
                st.dataframe(df_contingencia[['Producto', 'Cod Equipo', 'UBICACIÓN', df.columns[11]]], use_container_width=True)
                
                # Botón descarga SOLO contingencia
                st.download_button(
                    "📥 Descargar Lista de Contingencia",
                    df_contingencia.to_csv(index=False).encode('utf-8'),
                    "Stock_Contingencia.csv"
                )
            else:
                st.write("No hay repuestos marcados como contingencia.")

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.warning("⚠️ No se encuentra 'PEDIDOS.xlsx'. Súbelo a GitHub.")
