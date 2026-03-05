import streamlit as st
import pandas as pd
from datetime import datetime
import os
import urllib.parse
from github import Github

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Repuestos", layout="wide")
st.title("🛠️ Control de Repuestos - Gestión Total")

# --- CONSTANTES Y ARCHIVOS ---
ARCHIVO_EXCEL = "PEDIDOS.xlsx"
ARCHIVO_CSV = "datos_gestion.csv"

# ¡OJO! Asegúrate de que este sea tu usuario y repositorio exacto
REPO_NOMBRE = "PicsaNostra/PruebaWebIA" 

# --- FUNCIÓN CONEXIÓN GITHUB (SEGURA) ---
def subir_a_github(df_nuevo):
    """Guarda el archivo CSV de gestión en la nube (GitHub) usando el Token secreto"""
    try:
        # Aquí el código busca la llave en la caja fuerte de Streamlit
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            g = Github(token)
            
            try:
                # Intenta conectarse al repositorio
                repo = g.get_user().get_repo(REPO_NOMBRE.split("/")[-1]) 
            except:
                st.error(f"Error: No encuentro el repositorio '{REPO_NOMBRE}'. Verifica que esté bien escrito.")
                return

            # Convierte los datos a formato CSV
            content_csv = df_nuevo.to_csv(index=False)
            
            try:
                # Si el archivo ya existe, lo actualiza
                contents = repo.get_contents(ARCHIVO_CSV)
                repo.update_file(contents.path, "Actualización desde App", content_csv, contents.sha)
                st.toast("✅ Cambios guardados en la Nube exitosamente", icon="☁️")
            except:
                # Si no existe, lo crea por primera vez
                repo.create_file(ARCHIVO_CSV, "Creación Inicial", content_csv)
                st.toast("✅ Archivo de memoria creado en Nube", icon="✨")
        else:
            st.warning("⚠️ No has configurado el Token en Secrets. Los cambios NO se guardarán.")
    except Exception as e:
        st.error(f"Error conectando con GitHub: {e}")

# --- CARGA LOCAL (LECTURA RÁPIDA) ---
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
        
        # 2. Renombrar Columnas (Adaptado a tu formato)
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
        
        # Crear ID Único y Calcular Días
        df_base['ID_Unico'] = df_base['Producto'].astype(str) + df_base['Cod Equipo'].astype(str)
        
        # Calculamos días transcurridos (si es negativo o nulo, ponemos 0)
        df_base['Días en Almacén'] = (datetime.now() - df_base['Fecha_Llegada']).dt.days.fillna(0).astype(int)
        df_base['Días en Almacén'] = df_base['Días en Almacén'].apply(lambda x: x if x > 0 else 0)

        # 4. Cruzar con Memoria (Lo que guardamos ayer)
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

        # --- BARRA LATERAL (FILTROS) ---
        st.sidebar.header("🔍 Buscador")
        lista_prod = sorted(df_full['Producto'].astype(str).unique())
        filtro_prod = st.sidebar.multiselect("Filtrar Producto:", lista_prod)
        lista_eq = sorted(df_full['Cod Equipo'].astype(str).unique())
        filtro_eq = st.sidebar.multiselect("Filtrar Equipo:", lista_eq)

        # Aplicar Filtros
        df_view = df_full.copy()
        if filtro_prod: df_view = df_view[df_view['Producto'].astype(str).isin(filtro_prod)]
        if filtro_eq: df_view = df_view[df_view['Cod Equipo'].astype(str).isin(filtro_eq)]

        # Botón de Respaldo Manual
        st.sidebar.markdown("---")
        st.sidebar.header("📂 Respaldo")
        csv_data = df_full[['ID_Unico', 'Estado', 'Fecha_Prog']].to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("📥 Descargar Copia (.csv)", csv_data, "datos_gestion.csv", "text/csv")

        # --- FUNCIÓN CENTRAL DE GUARDADO ---
        def guardar_cambios(df_maestro):
            # Guardamos solo las columnas clave para no hacer pesado el archivo
            datos = df_maestro[['ID_Unico', 'Estado', 'Fecha_Prog']].drop_duplicates(subset=['ID_Unico'])
            datos.to_csv(ARCHIVO_CSV, index=False) # Guarda localmente
            subir_a_github(datos) # Sube a la nube
            st.rerun() # Recarga la página para ver cambios

        # --- PESTAÑAS DE GESTIÓN ---
        tab1, tab2, tab3 = st.tabs(["🚨 PENDIENTES", "🛡️ RESERVA", "✅ COMPLETADOS"])
        
        # Columnas que se mostrarán en las tablas
        cols_view = ['Cód insumo', 'Producto', 'Cod Equipo', 'Días en Almacén']

        # === TAB 1: PENDIENTES ===
        with tab1:
            # Ordenamos por antigüedad (los más viejos arriba)
            df_p = df_view[df_view['Estado'] == 'PENDIENTE'].sort_values('Días en Almacén', ascending=False).copy()
            
            if df_p.empty:
                st.success("✅ ¡Todo al día! No hay pendientes.")
            else:
                # --- NOTIFICACIÓN SEMÁFORO (CORREO Y WHATSAPP) ---
                with st.expander("📢 Enviar Alerta de Seguimiento", expanded=True):
                    total = len(df_p)
                    max_dias = int(df_p['Días en Almacén'].max()) if not df_p.empty else 0
                    
                    if max_dias > 30: emoji = "🔴 URGENTE"
                    elif max_dias > 15: emoji = "🟠 ATENCIÓN"
                    else: emoji = "🟢 SEGUIMIENTO"

                    LINK_APP = "https://pruebawebia.streamlit.app" # <--- Tu link real

                    cuerpo_msg = (
                        f"*{emoji}: REPORTE DE GESTIÓN*\n\n"
                        f"⚠️ Pendientes: *{total}*\n"
                        f"⏳ Antigüedad Máx: *{max_dias} días*\n\n"
                        f"👉 *Gestionar aquí:* \n{LINK_APP}"
                    )
                    
                    st.info(f"Vista previa:\n{cuerpo_msg}")
                    c_wa, c_mail = st.columns(2)
                    
                    # WhatsApp
                    txt_wa = urllib.parse.quote(cuerpo_msg)
                    c_wa.link_button("📲 Enviar WhatsApp", f"https://api.whatsapp.com/send?text={txt_wa}")
                    
                    # Correo (Simplificado para evitar errores)
                    asunto = urllib.parse.quote(f"Seguimiento: {total} Pendientes")
                    body = urllib.parse.quote(cuerpo_msg)
                    c_mail.link_button("📧 Enviar Correo", f"mailto:?subject={asunto}&body={body}")

                st.divider()

                # --- TABLA EDITABLE ---
                df_p.insert(0, "Seleccionar", False)
                ed_p = st.data_editor(
                    df_p[['Seleccionar', 'Fecha_Prog'] + cols_view],
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(required=True),
                        "Fecha_Prog": st.column_config.DateColumn("📅 Programación", format="DD/MM/YYYY"),
                        "Días en Almacén": st.column_config.NumberColumn("⏳ Días", format="%d días")
                    },
                    disabled=cols_view, hide_index=True, key="ed_p"
                )
                
                seleccionados = ed_p[ed_p['Seleccionar'] == True]
                
                # BOTÓN 1: Guardar Fechas
                if st.button("💾 Guardar Fechas"):
                    nuevas_fechas = pd.to_datetime(ed_p['Fecha_Prog'])
                    for id_u, fecha in zip(df_p['ID_Unico'], nuevas_fechas):
                        df_full.loc[df_full['ID_Unico'] == id_u, 'Fecha_Prog'] = fecha
                    guardar_cambios(df_full)

                # BOTONES 2 y 3: Mover Items
                if not seleccionados.empty:
                    st.write("---")
                    c1, c2 = st.columns(2)
                    ids = df_p.loc[seleccionados.index, 'ID_Unico'].values
                    
                    with c1:
                        if st.button("✅ MOVER A COMPLETADOS", type="primary", use_container_width=True):
                            df_full.loc[df_full['ID_Unico'].isin(ids), 'Estado'] = 'COMPLETADO'
                            guardar_cambios(df_full)
                    with c2:
                        if st.button("🛡️ MOVER A RESERVA", use_container_width=True):
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
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(),
                        "Días en Almacén": st.column_config.NumberColumn("⏳ Días", format="%d días")
                    },
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
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(),
                        "Días en Almacén": st.column_config.NumberColumn("⏳ Días", format="%d días")
                    },
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
