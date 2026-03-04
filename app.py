import streamlit as st
import pandas as pd
from datetime import datetime

# Configuración de la página
st.set_page_config(page_title="Gestor de Repuestos", layout="wide")

st.title("🛠️ Control de Repuestos e Instalaciones")
st.markdown("Sube el archivo **PEDIDOS** para detectar repuestos críticos en Bogotá.")

# Carga de archivo
archivo_subido = st.file_uploader("Arrastra tu archivo Excel aquí", type=["xlsx"])

if archivo_subido:
    try:
        df = pd.read_excel(archivo_subido)

        # --- LÓGICA DE FILTROS ---
        # 1. Definir columnas clave (ajusta los índices si tu Excel cambia)
        # Columna R (Fecha) es índice 17. Columna B (Producto) es 1.
        col_fecha = df.columns[17]
        
        # Convertir fecha
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')

        # Lista de exclusión
        excluir = ["SOLDADURA", "REMACHES", "SILICONA", "TORNILLO", "TUERCA", "GRASA", 
                   "ENGRASADOR", "FILTRO", "ABRAZADERA", "PALETA", "AMARRE", "ARANDELA", 
                   "CABLE", "CINTA", "CORAZA", "LLANTA", "PINTURA"]
        
        # Aplicar máscaras (Filtros)
        # B: Producto no prohibido
        mask_prod = ~df.iloc[:, 1].astype(str).str.contains('|'.join(excluir), case=False, na=False)
        # E: Bogotá
        mask_bog = df.iloc[:, 4].astype(str).str.contains("Bogotá", case=False, na=False)
        # G: Código equipo
        mask_equ = (~df.iloc[:, 6].astype(str).str.startswith('3')) & (df.iloc[:, 6].astype(str) != "A.C.PM")
        # L: Inventario > 0
        mask_inv = pd.to_numeric(df.iloc[:, 11], errors='coerce') > 0
        # R: Fecha válida
        mask_fec = df[col_fecha].notna()

        # Unir filtros
        df_final = df[mask_prod & mask_bog & mask_equ & mask_inv & mask_fec].copy()
        
        # Calcular días
        df_final['Días en Almacén'] = (datetime.now() - df_final[col_fecha]).dt.days
        
        # Ordenar por urgencia
        df_final = df_final.sort_values('Días en Almacén', ascending=False)

        # --- MOSTRAR RESULTADOS ---
        st.success(f"✅ Se encontraron {len(df_final)} repuestos para programar.")

        # Métricas rápidas
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Items", len(df_final))
        if not df_final.empty:
            col2.metric("Más Antiguo", f"{df_final['Días en Almacén'].max()} días")
            col3.metric("Promedio Espera", f"{int(df_final['Días en Almacén'].mean())} días")

        # Tabla interactiva
        st.subheader("📋 Detalle de Repuestos")
        st.dataframe(
            df_final[['Producto', 'Cod equipo', 'UBICACIÓN', 'Cantidad en inventario', 'Días en Almacén']],
            use_container_width=True
        )

        # Gráfico
        if not df_final.empty:
            st.subheader("🚨 Top 10 Más Críticos")
            st.bar_chart(df_final.head(10).set_index('Producto')['Días en Almacén'])

        # Botón de descarga
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
        st.download_button(
            label="📥 Descargar Reporte Filtrado (Excel)",
            data=df_final.to_csv(index=False).encode('utf-8'),
            file_name=f'Reporte_Instalaciones_{fecha_hoy}.csv',
            mime='text/csv',
        )

    except Exception as e:
        st.error(f"Hubo un error al procesar el archivo: {e}")
else:
    st.info("Esperando archivo... Por favor sube el Excel.")
