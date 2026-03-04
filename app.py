import streamlit as st
import pandas as pd
from datetime import datetime
import os

# Configuración de la página
st.set_page_config(page_title="Gestor de Repuestos", layout="wide")

st.title("🛠️ Control de Repuestos - Reporte Semanal")

# Nombre del archivo que subiste a GitHub
archivo_nombre = "PEDIDOS.xlsx"

if os.path.exists(archivo_nombre):
    try:
        # 1. Cargar el archivo automáticamente
        df = pd.read_excel(archivo_nombre)
        
        # --- PROCESAMIENTO PREVIO (Filtros Duros) ---
        # Convertir fecha (Columna R - índice 17)
        col_fecha = df.columns[17]
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
        
        # Lista de palabras a excluir
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", 
                   "ENGRASADOR", "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", 
                   "CABLE", "CINTA", "CORAZA", "LLANTA", "PINTURA"]
        
        # Aplicar máscaras de limpieza (Bogotá, Inventario > 0, etc.)
        mask = (~df.iloc[:, 1].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df.iloc[:, 6].astype(str).str.startswith('3')) & \
               (df.iloc[:, 6].astype(str) != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df[col_fecha].notna())

        # Dataframe base limpio
        df_base = df[mask].copy()
        df_base['Días en Almacén'] = (datetime.now() - df_base[col_fecha]).dt.days
        df_base = df_base.sort_values('Días en Almacén', ascending=False)
        
        # --- FILTROS INTERACTIVOS (WEB) ---
        # Creamos una barra lateral para los filtros
        st.sidebar.header("🔍 Filtros Dinámicos")
        
        # 1. Obtener lista única de equipos disponibles en la data limpia
        lista_equipos = sorted(df_base['Cod equipo'].astype(str).unique())
        
        # 2. Crear el selector múltiple
        equipos_seleccionados = st.sidebar.multiselect(
            "Seleccionar Equipo(s):",
            options=lista_equipos,
            default=lista_equipos # Por defecto mostramos todos
        )
        
        # 3. Filtrar la data según lo que el usuario elija en la web
        df_final = df_base[df_base['Cod equipo'].astype(str).isin(equipos_seleccionados)]
        
        # --- MOSTRAR RESULTADOS ---
        # Fecha de actualización del archivo
        fecha_mod = datetime.fromtimestamp(os.path.getmtime(archivo_nombre)).strftime('%d/%m/%Y')
        st.markdown(f"**Datos actualizados al:** {fecha_mod} | **Mostrando:** {len(df_final)} repuestos")

        # Métricas
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Items", len(df_final))
        if not df_final.empty:
            col2.metric("Más Antiguo", f"{df_final['Días en Almacén'].max()} días")
            col3.metric("Promedio Espera", f"{int(df_final['Días en Almacén'].mean())} días")

        # Tabla Principal
        st.subheader("📋 Detalle de Repuestos")
        st.dataframe(
            df_final[['Producto', 'Cod equipo', 'UBICACIÓN', 'Cantidad en inventario', 'Días en Almacén']],
            use_container_width=True
        )

        # Gráfico
        if not df_final.empty:
            st.subheader("🚨 Top 10 Más Críticos (Selección actual)")
            st.bar_chart(df_final.head(10).set_index('Producto')['Días en Almacén'])
            
    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")
else:
    st.error("⚠️ No se encuentra el archivo 'PEDIDOS.xlsx' en GitHub. Por favor súbelo.")
