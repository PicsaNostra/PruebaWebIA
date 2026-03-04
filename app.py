import streamlit as st
import pandas as pd
from datetime import datetime
import os

# Configuración de página
st.set_page_config(page_title="Gestor de Repuestos", layout="wide")

st.title("🛠️ Control de Repuestos - Reporte Semanal")

# --- CARGA AUTOMÁTICA DEL ARCHIVO ---
archivo_nombre = "PEDIDOS.xlsx"

# Verificar si el archivo existe en el repositorio
if os.path.exists(archivo_nombre):
    try:
        # Cargar directamente sin pedirlo al usuario
        df = pd.read_excel(archivo_nombre)
        
        # --- LÓGICA DE FECHAS Y FILTROS ---
        col_fecha = df.columns[17] # Columna R
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
        
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", 
                   "ENGRASADOR", "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", 
                   "CABLE", "CINTA", "CORAZA", "LLANTA", "PINTURA"]
        
        # Aplicar filtros
        mask = (~df.iloc[:, 1].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df.iloc[:, 6].astype(str).str.startswith('3')) & \
               (df.iloc[:, 6].astype(str) != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df[col_fecha].notna())

        df_final = df[mask].copy()
        df_final['Días en Almacén'] = (datetime.now() - df_final[col_fecha]).dt.days
        df_final = df_final.sort_values('Días en Almacén', ascending=False)
        
        # --- MOSTRAR RESULTADOS ---
        # Mostrar fecha de última actualización (basado en cuando subiste el archivo)
        fecha_mod = datetime.fromtimestamp(os.path.getmtime(archivo_nombre)).strftime('%d/%m/%Y')
        st.info(f"📅 Datos actualizados al: **{fecha_mod}**. Mostrando {len(df_final)} repuestos críticos.")

        col1, col2 = st.columns([3, 1])
        with col1:
            st.dataframe(df_final[['Producto', 'Cod equipo', 'UBICACIÓN', 'Días en Almacén']], use_container_width=True)
        with col2:
            st.metric("Más Antiguo", f"{df_final['Días en Almacén'].max()} días")
            st.metric("Promedio Espera", f"{int(df_final['Días en Almacén'].mean())} días")
            
        # Gráfico
        st.bar_chart(df_final.head(10).set_index('Producto')['Días en Almacén'])

    except Exception as e:
        st.error(f"Error leyendo el archivo: {e}")
else:
    st.error("⚠️ No se encuentra el archivo 'PEDIDOS.xlsx' en el servidor. Por favor súbelo a GitHub.")
