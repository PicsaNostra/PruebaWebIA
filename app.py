import streamlit as st
import pandas as pd
from datetime import datetime
import os

# Configuración de la página
st.set_page_config(page_title="Gestor de Repuestos", layout="wide")
st.title("🛠️ Control de Repuestos - Reporte Semanal")

archivo_nombre = "PEDIDOS.xlsx"

if os.path.exists(archivo_nombre):
    try:
        df = pd.read_excel(archivo_nombre)
        
        # --- 1. ESTANDARIZACIÓN DE NOMBRES ---
        # Renombramos la Columna G (índice 6) a "Cod Equipo" para que sea uniforme
        # Renombramos la Columna R (índice 17) a "Fecha"
        df.rename(columns={df.columns[6]: 'Cod Equipo', df.columns[17]: 'Fecha'}, inplace=True)

        # --- 2. PROCESAMIENTO ---
        # Convertir fecha
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
        
        # Lista de exclusión
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", 
                   "ENGRASADOR", "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", 
                   "CABLE", "CINTA", "CORAZA", "LLANTA", "PINTURA"]
        
        # Filtros (Usando el nuevo nombre "Cod Equipo")
        # Columna B es índice 1 (Producto) y E es índice 4 (Ubicación) - Las usamos por índice para seguridad
        mask = (~df.iloc[:, 1].astype(str).str.contains('|'.join(excluir), case=False, na=False)) & \
               (df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)) & \
               (~df['Cod Equipo'].astype(str).str.startswith('3')) & \
               (df['Cod Equipo'].astype(str) != "A.C.PM") & \
               (pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0) & \
               (df['Fecha'].notna())

        df_base = df[mask].copy()
        
        # Calcular Días
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha']).dt.days
        df_base = df_base.sort_values('Días en Almacén', ascending=False)
        
        # --- 3. MENÚ LATERAL INTERACTIVO ---
        st.sidebar.header("🔍 Filtros")
        
        # Obtener lista única de equipos (quitando vacíos)
        lista_equipos = sorted(df_base['Cod Equipo'].dropna().astype(str).unique())
        
        # El multiselect usa la lista limpia
        equipos_seleccionados = st.sidebar.multiselect(
            "Filtrar por Cod Equipo:",
            options=lista_equipos,
            default=lista_equipos
        )
        
        # Aplicar el filtro del usuario
        if equipos_seleccionados:
            df_final = df_base[df_base['Cod Equipo'].astype(str).isin(equipos_seleccionados)]
        else:
            df_final = df_base
        
        # --- 4. MOSTRAR RESULTADOS ---
        # Fecha de actualización del archivo
        fecha_mod = datetime.fromtimestamp(os.path.getmtime(archivo_nombre)).strftime('%d/%m/%Y')
        st.markdown(f"**Actualizado al:** {fecha_mod} | **Items:** {len(df_final)}")

        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("📋 Listado Detallado")
            # Mostramos las columnas clave incluyendo "Cod Equipo"
            cols_mostrar = [df.columns[1], 'Cod Equipo', df.columns[4], df.columns[11], 'Días en Almacén']
            st.dataframe(df_final[cols_mostrar], use_container_width=True)
            
        with col2:
            st.subheader("📊 Estadísticas")
            if not df_final.empty:
                st.metric("Más Antiguo", f"{df_final['Días en Almacén'].max()} días")
                st.metric("Promedio", f"{int(df_final['Días en Almacén'].mean())} días")
                st.markdown("---")
                st.bar_chart(df_final.head(5).set_index(df.columns[1])['Días en Almacén'])

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.warning("⚠️ Sube el archivo 'PEDIDOS.xlsx' a GitHub.")
