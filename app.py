import streamlit as st
import pandas as pd
from datetime import datetime
import os
from github import Github

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Repuestos", layout="wide")
st.title("🛠️ Control de Repuestos - Gestión Total")

# Nombres de archivos
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_CSV = "datos_gestion.csv"
REPO_NOMBRE = "TU_USUARIO/TU_REPO" # <--- ¡PON TU USUARIO/REPO AQUÍ!

# --- CONEXIÓN GITHUB ---
def subir_a_github(df_nuevo):
    try:
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            g = Github(token)
            try:
                repo = g.get_user().get_repo(REPO_NOMBRE.split("/")[-1]) 
            except:
                st.error("Error: Revisa el nombre del repositorio.")
                return

            content_csv = df_nuevo.to_csv(index=False)
            try:
                contents = repo.get_contents(ARCHIVO_CSV)
                repo.update_file(contents.path, "Update App", content_csv, contents.sha)
                st.toast("✅ Guardado en Nube", icon="☁️")
            except:
                repo.create_file(ARCHIVO_CSV, "Init App", content_csv)
                st.toast("✅ Creado en Nube", icon="✨")
        else:
            st.warning("⚠️ Sin Token. Guardado Local.")
    except Exception as e:
        st.error(f"Error GitHub: {e}")

# --- CARGA DATOS ---
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
        
        # Mapeo Columnas
        col_insumo = df.columns[0]
        col_prod = df.columns[1]
        col_equipo = df.columns[6]
        col_fecha = df.columns[17]

        df.rename(columns={col_insumo: 'Cód insumo', col_prod: 'Producto', col_equipo: 'Cod Equipo', col_fecha: 'Fecha_Llegada'}, inplace=True)
        df['Fecha_Llegada'] = pd.to_datetime(df['Fecha_Llegada'], errors='coerce')
        
        # 2. Filtros Limpieza
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

        # 3. Cruzar Memoria
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
        df_full['Fecha_Prog'] = pd.to_datetime(df_full['Fecha_Prog'], errors='coerce')

        # --- FILTROS LATERALES ---
        st.sidebar.header("🔍 Buscador")
        lista_prod = sorted(df_full['Producto'].astype(str).unique())
        filtro_prod = st.sidebar.multiselect("Producto:", lista_prod)
        lista_eq = sorted(df_full['Cod Equipo'].astype(str).unique())
        filtro_eq = st.sidebar.multiselect("Equipo:", lista_eq)

        df_view = df_full.copy()
        if filtro_prod: df_view = df_view[df_view['Producto'].astype(str).isin(filtro_prod)]
        if filtro_eq: df_view = df_view[df_view['Cod Equipo'].astype(str).isin(filtro_eq)]

        # Botón Descarga
        st.sidebar.markdown("---")
        csv_data = df_full[['ID_Unico', 'Estado', 'Fecha_Prog']].to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("📥 Bajar Copia Seguridad", csv_data, "datos_gestion.csv", "text/csv")

        # Función Guardar Central
        def guardar_cambios(df_maestro):
            datos = df_maestro[['ID_Unico', 'Estado', 'Fecha_Prog']].drop_duplicates(subset=['ID_Unico'])
            datos.to_csv(ARCHIVO_CSV, index=False)
            subir_a_github(datos)
            st.rerun()

        # --- TABS ---
        tab1, tab2, tab3 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS"])
        cols_view = ['Cód insumo', 'Producto', 'Cod Equipo']

        # 1. PENDIENTES
        with tab1:
            df_p = df_view[df_view['Estado'] == 'PENDIENTE'].copy()
            if not df_p.empty:
                df_p.insert(0, "Seleccionar", False)
                ed_p = st.data_editor(
                    df_p[['Seleccionar', 'Fecha_Prog'] + cols_view],
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(required=True),
                        "Fecha_Prog": st.column_config.DateColumn("📅 Programación", format="DD/MM/YYYY")
                    },
                    disabled=cols_view, hide_index=True, key="ed_p"
                )
                
                # Guardar Fecha
                if st.button("💾 Guardar Fechas"):
                    nuevas_fechas = pd.to_datetime(ed_p['Fecha_Prog'])
                    for id_u, fecha in zip(df_p['ID_Unico'], nuevas_fechas):
                        df_full.loc[df_full['ID_Unico'] == id_u, 'Fecha_Prog'] = fecha
                    guardar_cambios(df_full)

                # Mover
                sel_p = ed_p[ed_p['Seleccionar'] == True]
                if not sel_p.empty:
                    st.write("---")
                    c1, c2 = st.columns(2)
                    ids = df_p.loc[sel_p.index, 'ID_Unico'].values
                    with c1:
                        if st.button("✅ ENVIAR A COMPLETADOS", type="primary", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                            guardar_cambios(df_full)
                    with c2:
                        if st.button("🛡️ ENVIAR A RESERVA", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                            guardar_cambios(df_full)
            else:
                st.success("Sin pendientes.")

        # 2. RESERVA (Ahora con doble movilidad)
        with tab2:
            df_r = df_view[df_view['Estado'] == 'RESERVA'].copy()
            if not df_r.empty:
                df_r.insert(0, "Seleccionar", False)
                ed_r = st.data_editor(
                    df_r[['Seleccionar'] + cols_view],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn()},
                    disabled=cols_view, hide_index=True, key="ed_r"
                )
                sel_r = ed_r[ed_r['Seleccionar'] == True]
                if not sel_r.empty:
                    st.write("---")
                    c1, c2 = st.columns(2)
                    ids = df_r.loc[sel_r.index, 'ID_Unico'].values
                    
                    with c1:
                        if st.button("🔙 DEVOLVER A PENDIENTES", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'PENDIENTE'
                            guardar_cambios(df_full)
                    with c2:
                        # NUEVO BOTÓN: De Reserva directo a Completado
                        if st.button("✅ YA LO USÉ (COMPLETADO)", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                            guardar_cambios(df_full)
            else:
                st.info("Nada en reserva.")

        # 3. COMPLETADOS (Ahora con doble movilidad)
        with tab3:
            df_c = df_view[df_view['Estado'] == 'COMPLETADO'].copy()
            if not df_c.empty:
                df_c.insert(0, "Seleccionar", False)
                ed_c = st.data_editor(
                    df_c[['Seleccionar'] + cols_view],
                    column_config={"Seleccionar": st.column_config.CheckboxColumn()},
                    disabled=cols_view, hide_index=True, key="ed_c"
                )
                sel_c = ed_c[ed_c['Seleccionar'] == True]
                if not sel_c.empty:
                    st.write("---")
                    c1, c2 = st.columns(2)
                    ids = df_c.loc[sel_c.index, 'ID_Unico'].values
                    
                    with c1:
                        if st.button("🔙 RESTAURAR A PENDIENTES", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'PENDIENTE'
                            guardar_cambios(df_full)
                    with c2:
                        # NUEVO BOTÓN: De Completado a Reserva (Corrección de error)
                        if st.button("🛡️ ERA PARA RESERVA", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                            guardar_cambios(df_full)
            else:
                st.info("Historial vacío.")

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.warning("⚠️ Carga PEDIDOS.xlsx")
