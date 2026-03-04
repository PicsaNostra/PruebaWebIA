import streamlit as st
import pandas as pd
from datetime import datetime
import os
from github import Github

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Repuestos", layout="wide")
st.title("🛠️ Control de Repuestos - Simplificado")

# Nombres de archivos
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_CSV = "datos_gestion.csv"
REPO_NOMBRE = "TU_USUARIO/TU_REPO" # <--- ¡IMPORTANTE: PON TU USUARIO/REPO AQUÍ!

# --- CONEXIÓN CON GITHUB ---
def subir_a_github(df_nuevo):
    """Sube el archivo CSV a GitHub"""
    try:
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            g = Github(token)
            try:
                repo = g.get_user().get_repo(REPO_NOMBRE.split("/")[-1]) 
            except:
                st.error("No se encontró el repositorio. Revisa el nombre en el código.")
                return

            content_csv = df_nuevo.to_csv(index=False)
            
            try:
                contents = repo.get_contents(ARCHIVO_CSV)
                repo.update_file(contents.path, "Update desde App", content_csv, contents.sha)
                st.toast("✅ Guardado en Nube", icon="☁️")
            except:
                repo.create_file(ARCHIVO_CSV, "Init App", content_csv)
                st.toast("✅ Archivo Creado en Nube", icon="✨")
        else:
            st.warning("⚠️ No hay Token configurado. Se guardará solo localmente.")
            
    except Exception as e:
        st.error(f"Error GitHub: {e}")

# --- CARGA DE DATOS ---
def cargar_csv_local():
    if os.path.exists(ARCHIVO_CSV):
        try:
            return pd.read_csv(ARCHIVO_CSV)
        except:
            return pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])
    return pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])

# --- APP PRINCIPAL ---
if os.path.exists(ARCHIVO_EXCEL):
    try:
        # 1. Cargar Excel
        df = pd.read_excel(ARCHIVO_EXCEL)
        
        # Mapeo de columnas
        col_insumo = df.columns[0]  # A
        col_prod = df.columns[1]    # B
        col_equipo = df.columns[6]  # G
        col_fecha = df.columns[17]  # R

        df.rename(columns={
            col_insumo: 'Cód insumo',
            col_prod: 'Producto',
            col_equipo: 'Cod Equipo',
            col_fecha: 'Fecha_Llegada'
        }, inplace=True)

        df['Fecha_Llegada'] = pd.to_datetime(df['Fecha_Llegada'], errors='coerce')
        
        # 2. Filtros de Limpieza
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

        # 3. Cruzar con Memoria
        df_memoria = cargar_csv_local()
        
        if not df_memoria.empty:
            df_base['ID_Unico'] = df_base['ID_Unico'].astype(str)
            df_memoria['ID_Unico'] = df_memoria['ID_Unico'].astype(str)
            df_full = pd.merge(df_base, df_memoria, on='ID_Unico', how='left')
        else:
            df_full = df_base.copy()
            df_full['Estado'] = 'PENDIENTE'
            df_full['Fecha_Prog'] = None

        df_full['Estado'] = df_full['Estado'].fillna('PENDIENTE')
        # Corrección de Fechas para evitar error de edición
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce')

        # --- BARRA LATERAL: FILTROS Y DESCARGA ---
        st.sidebar.header("🔍 Filtros")
        
        # 1. Buscador de Lista de PRODUCTOS
        lista_productos = sorted(df_full['Producto'].dropna().astype(str).unique())
        filtro_producto = st.sidebar.multiselect(
            "Filtrar por Producto:",
            options=lista_productos,
            placeholder="Escribe o selecciona..."
        )

        # 2. Buscador de EQUIPOS (Opcional, útil tener ambos)
        lista_equipos = sorted(df_full['Cod Equipo'].dropna().astype(str).unique())
        filtro_equipo = st.sidebar.multiselect(
            "Filtrar por Equipo:",
            options=lista_equipos
        )

        # Aplicar Filtros
        df_view = df_full.copy()
        
        if filtro_producto:
            df_view = df_view[df_view['Producto'].astype(str).isin(filtro_producto)]
            
        if filtro_equipo:
            df_view = df_view[df_view['Cod Equipo'].astype(str).isin(filtro_equipo)]

        # --- SECCIÓN DE DESCARGA ---
        st.sidebar.markdown("---")
        st.sidebar.header("📂 Respaldo")
        
        # Guardamos el estado actual en memoria a un CSV temporal para descargar
        csv_actual = df_full[['ID_Unico', 'Estado', 'Fecha_Prog']].to_csv(index=False).encode('utf-8')
        
        st.sidebar.download_button(
            label="📥 Descargar Gestión (.csv)",
            data=csv_actual,
            file_name="datos_gestion.csv",
            mime="text/csv",
            help="Descarga el archivo con las fechas y estados actuales."
        )

        # --- FUNCIÓN DE GUARDADO ---
        def guardar_cambios_central(df_maestro):
            datos_a_guardar = df_maestro[['ID_Unico', 'Estado', 'Fecha_Prog']].drop_duplicates(subset=['ID_Unico'])
            datos_a_guardar.to_csv(ARCHIVO_CSV, index=False)
            subir_a_github(datos_a_guardar)
            st.rerun()

        # --- PESTAÑAS PRINCIPALES ---
        tab1, tab2, tab3 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS"])
        cols_visuales = ['Cód insumo', 'Producto', 'Cod Equipo']

        # === TAB 1: PENDIENTES ===
        with tab1:
            df_p = df_view[df_view['Estado'] == 'PENDIENTE'].copy()
            
            if df_p.empty:
                st.success("No hay pendientes con los filtros actuales.")
            else:
                df_p.insert(0, "Seleccionar", False)
                
                edited_p = st.data_editor(
                    df_p[['Seleccionar', 'Fecha_Prog'] + cols_visuales],
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(required=True),
                        "Fecha_Prog": st.column_config.DateColumn("📅 Programación", format="DD/MM/YYYY")
                    },
                    disabled=cols_visuales,
                    hide_index=True,
                    key="editor_p"
                )

                seleccionados = edited_p[edited_p['Seleccionar'] == True]
                
                # Botón Guardar Fechas
                if st.button("💾 Guardar Fechas"):
                    fechas_nuevas = pd.to_datetime(edited_p['Fecha_Prog'])
                    # Usamos ID_Unico para mapear las fechas correctamente al dataframe maestro
                    # Creamos un diccionario ID -> Fecha nueva
                    mapa_fechas = dict(zip(df_p['ID_Unico'], dates_new := fechas_nuevas))
                    # Actualizamos solo donde coincida el ID
                    for id_u, fecha in zip(df_p['ID_Unico'], fechas_nuevas):
                        df_full.loc[df_full['ID_Unico'] == id_u, 'Fecha_Prog'] = fecha
                    
                    guardar_cambios_central(df_full)

                # Botones Mover
                if not seleccionados.empty:
                    st.write("---")
                    c1, c2 = st.columns(2)
                    ids_sel = df_p.loc[seleccionados.index, 'ID_Unico'].values
                    
                    with c1:
                        if st.button("✅ MOVER A COMPLETADOS", type="primary", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids_sel), 'Estado'] = 'COMPLETADO'
                            guardar_cambios_central(df_full)
                    with c2:
                        if st.button("🛡️ MOVER A RESERVA", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids_sel), 'Estado'] = 'RESERVA'
                            guardar_cambios_central(df_full)

        # === TAB 2: RESERVA ===
        with tab2:
            df_r = df_view[df_view['Estado'] == 'RESERVA'].copy()
            if df_r.empty:
                st.info("Nada en reserva.")
            else:
                df_r.insert(0, "Seleccionar", False)
                edited_r = st.data_editor(
                    df_r[['Seleccionar'] + cols_visuales],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn()},
                    disabled=cols_visuales,
                    hide_index=True,
                    key="editor_r"
                )
                sel_r = edited_r[edited_r['Seleccionar'] == True]
                if not sel_r.empty and st.button("🔙 Devolver a Pendientes"):
                    ids = df_r.loc[sel_r.index, 'ID_Unico'].values
                    df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'PENDIENTE'
                    guardar_cambios_central(df_full)

        # === TAB 3: COMPLETADOS ===
        with tab3:
            df_c = df_view[df_view['Estado'] == 'COMPLETADO'].copy()
            if df_c.empty:
                st.info("Historial vacío.")
            else:
                df_c.insert(0, "Seleccionar", False)
                edited_c = st.data_editor(
                    df_c[['Seleccionar'] + cols_visuales],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn()},
                    disabled=cols_visuales,
                    hide_index=True,
                    key="editor_c"
                )
                sel_c = edited_c[edited_c['Seleccionar'] == True]
                if not sel_c.empty and st.button("Restaurar a Pendientes"):
                    ids = df_c.loc[sel_c.index, 'ID_Unico'].values
                    df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'PENDIENTE'
                    guardar_cambios_central(df_full)

    except Exception as e:
        st.error(f"Error cargando archivo: {e}")
else:
    st.warning("⚠️ No se encuentra 'PEDIDOS.xlsx'. Súbelo a GitHub.")
