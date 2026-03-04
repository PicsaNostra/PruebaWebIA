import streamlit as st
import pandas as pd
from datetime import datetime
import os
import urllib.parse # Necesario para codificar los enlaces de whatsapp y correo
from github import Github

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Repuestos", layout="wide")
st.title("🛠️ Control de Repuestos - Gestión Total")

# --- CONSTANTES Y ARCHIVOS ---
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_CSV = "datos_gestion.csv"
REPO_NOMBRE = "TU_USUARIO/TU_REPO" # <--- ¡IMPORTANTE: CAMBIA ESTO POR TU USUARIO/REPO!

# --- FUNCIÓN CONEXIÓN GITHUB ---
def subir_a_github(df_nuevo):
    """Guarda el archivo CSV de gestión en la nube (GitHub)"""
    try:
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            g = Github(token)
            try:
                repo = g.get_user().get_repo(REPO_NOMBRE.split("/")[-1]) 
            except:
                st.error("Error: No encuentro el repositorio. Revisa la variable REPO_NOMBRE.")
                return

            content_csv = df_nuevo.to_csv(index=False)
            
            try:
                contents = repo.get_contents(ARCHIVO_CSV)
                repo.update_file(contents.path, "Actualización desde App", content_csv, contents.sha)
                st.toast("✅ Cambios guardados en la Nube", icon="☁️")
            except:
                repo.create_file(ARCHIVO_CSV, "Creación Inicial", content_csv)
                st.toast("✅ Archivo de gestión creado en Nube", icon="✨")
        else:
            st.warning("⚠️ No hay Token configurado. Los cambios solo se guardarán en local.")
    except Exception as e:
        st.error(f"Error conectando con GitHub: {e}")

# --- CARGA LOCAL ---
def cargar_csv_local():
    if os.path.exists(ARCHIVO_CSV):
        try:
            return pd.read_csv(ARCHIVO_CSV)
        except:
            return pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])
    return pd.DataFrame(columns=['ID_Unico', 'Estado', 'Fecha_Prog'])

# --- LÓGICA PRINCIPAL ---
if os.path.exists(ARCHIVO_EXCEL):
    try:
        # 1. Cargar Excel
        df = pd.read_excel(ARCHIVO_EXCEL)
        
        # 2. Renombrar Columnas (Ajustado a tu estructura)
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
        
        # 3. Limpieza y Filtros
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
        
        # Crear ID y Calcular Días
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + df_base['Cod Equipo'].astype(str)
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha_Llegada']).dt.days

        # 4. Cruzar con Memoria
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

        # --- BARRA LATERAL ---
        st.sidebar.header("🔍 Buscador")
        
        # Filtros
        lista_prod = sorted(df_full['Producto'].astype(str).unique())
        filtro_prod = st.sidebar.multiselect("Filtrar Producto:", lista_prod)
        lista_eq = sorted(df_full['Cod Equipo'].astype(str).unique())
        filtro_eq = st.sidebar.multiselect("Filtrar Equipo:", lista_eq)

        # Aplicar Filtros
        df_view = df_full.copy()
        if filtro_prod: df_view = df_view[df_view['Producto'].astype(str).isin(filtro_prod)]
        if filtro_eq: df_view = df_view[df_view['Cod Equipo'].astype(str).isin(filtro_eq)]

        # Respaldo
        st.sidebar.markdown("---")
        st.sidebar.header("📂 Respaldo")
        csv_data = df_full[['ID_Unico', 'Estado', 'Fecha_Prog']].to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("📥 Descargar Gestión (.csv)", csv_data, "datos_gestion.csv", "text/csv")

        # Función Guardar
        def guardar_cambios(df_maestro):
            datos = df_maestro[['ID_Unico', 'Estado', 'Fecha_Prog']].drop_duplicates(subset=['ID_Unico'])
            datos.to_csv(ARCHIVO_CSV, index=False)
            subir_a_github(datos)
            st.rerun()

        # --- PESTAÑAS ---
        tab1, tab2, tab3 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS"])
        cols_view = ['Cód insumo', 'Producto', 'Cod Equipo']

        # === TAB 1: PENDIENTES ===
        with tab1:
            df_p = df_view[df_view['Estado'] == 'PENDIENTE'].copy()
            
            if df_p.empty:
                st.success("✅ ¡Todo al día! No hay pendientes.")
            else:
                # --- NOTIFICACIÓN TIPO SEMÁFORO (CORREGIDA) ---
                with st.expander("📢 Enviar Alerta de Seguimiento", expanded=True):
                    
                    # 1. Datos Clave
                    total = len(df_p)
                    # Calculamos antigüedad máxima (si hay datos)
                    if 'Días en Almacén' in df_p.columns and not df_p.empty:
                        max_dias = int(df_p['Días en Almacén'].max())
                    else:
                        max_dias = 0
                    
                    # 2. Lógica del Semáforo
                    if max_dias > 30:
                        emoji = "🔴 URGENTE"
                    elif max_dias > 15:
                        emoji = "🟠 ATENCIÓN"
                    else:
                        emoji = "🟢 SEGUIMIENTO"

                    # 3. URL DE LA APP (¡PON TU LINK AQUÍ!)
                    LINK_APP = "https://pruebawebia-sfayt38cvkueqghbajqrm7.streamlit.app/" 

                    # 4. Mensaje Corto y Directo
                    asunto_msg = f"Reporte Repuestos: {total} Pendientes"
                    cuerpo_msg = (
                        f"*{emoji}: REPORTE DE GESTIÓN*\n\n"
                        f"⚠️ Pendientes por instalar: *{total}*\n"
                        f"⏳ Antigüedad máxima: *{max_dias} días*\n\n"
                        f"👉 *Ingresa aquí para gestionar:* \n{LINK_APP}"
                    )
                    
                    st.info(f"Vista previa:\n\n{cuerpo_msg}")
                    
                    c_wa, c_mail = st.columns(2)
                    
                    # WhatsApp (API Segura)
                    txt_wa = urllib.parse.quote(cuerpo_msg)
                    link_wa = f"https://api.whatsapp.com/send?text={txt_wa}"
                    c_wa.link_button("📲 Enviar Alerta (WhatsApp)", link_wa)
                    
                    # Correo (FIXED: Codificación correcta para evitar errores)
                    subject_encoded = urllib.parse.quote(asunto_msg)
                    body_encoded = urllib.parse.quote(cuerpo_msg)
                    link_mail = f"mailto:?subject={subject_encoded}&body={body_encoded}"
                    
                    c_mail.link_button("📧 Enviar Alerta (Correo)", link_mail, help="Abre tu aplicación de correo predeterminada.")
                    
                    st.caption("Nota: Si el botón de correo no abre, asegúrate de tener Outlook o Correo configurado en tu PC.")

                st.divider()

                # --- TABLA Y EDICIÓN ---
                df_p.insert(0, "Seleccionar", False)
                ed_p = st.data_editor(
                    df_p[['Seleccionar', 'Fecha_Prog'] + cols_view],
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(required=True),
                        "Fecha_Prog": st.column_config.DateColumn("📅 Programación", format="DD/MM/YYYY")
                    },
                    disabled=cols_view, hide_index=True, key="ed_p"
                )
                
                seleccionados = ed_p[ed_p['Seleccionar'] == True]
                
                # Botón Guardar Fechas
                if st.button("💾 Guardar Fechas"):
                    nuevas_fechas = pd.to_datetime(ed_p['Fecha_Prog'])
                    for id_u, fecha in zip(df_p['ID_Unico'], nuevas_fechas):
                        df_full.loc[df_full['ID_Unico'] == id_u, 'Fecha_Prog'] = fecha
                    guardar_cambios(df_full)

                # Botones Mover
                if not seleccionados.empty:
                    st.write("---")
                    c1, c2 = st.columns(2)
                    ids = df_p.loc[seleccionados.index, 'ID_Unico'].values
                    
                    with c1:
                        if st.button("✅ ENVIAR A COMPLETADOS", type="primary", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                            guardar_cambios(df_full)
                    with c2:
                        if st.button("🛡️ ENVIAR A RESERVA", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                            guardar_cambios(df_full)

        # === TAB 2: RESERVA ===
        with tab2:
            df_r = df_view[df_view['Estado'] == 'RESERVA'].copy()
            if df_r.empty:
                st.info("Nada en reserva.")
            else:
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
                        if st.button("✅ YA LO USÉ (COMPLETADO)", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                            guardar_cambios(df_full)

        # === TAB 3: COMPLETADOS ===
        with tab3:
            df_c = df_view[df_view['Estado'] == 'COMPLETADO'].copy()
            if df_c.empty:
                st.info("Historial vacío.")
            else:
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
                        if st.button("🛡️ ERA PARA RESERVA", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'RESERVA'
                            guardar_cambios(df_full)

    except Exception as e:
        st.error(f"Ocurrió un error: {e}")
else:
    st.warning("⚠️ No se encuentra el archivo 'PEDIDOS.xlsx'.")
