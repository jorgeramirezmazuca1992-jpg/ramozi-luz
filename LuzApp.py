import os
import time
import urllib.parse
import base64
import io
import requests
from PIL import Image
import pandas as pd
import streamlit as st
from fpdf import FPDF
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Ramozi LuzApp - Asociación 4 de Enero", page_icon="⚡", layout="wide")

API_KEY = "AQ.Ab8RN6KRORBTPy37ez_9L8oDEntYDiwJBT09u4DwmUfVtlwQUQ"

# --- VARIABLES DE TIEMPO AUTOMÁTICAS ---
MESES_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
now = datetime.now()
mes_actual_nombre = MESES_ES[now.month - 1]
año_actual = now.year
# Truco: Si es enero (1), restamos 2 y da -1 (Diciembre en Python)
mes_anterior_nombre = MESES_ES[now.month - 2]

def obtener_lectura_medidor(imagen):
    if not API_KEY or API_KEY == "":
        st.error("❌ La API Key no está configurada.")
        return None

    tamaño_maximo = (800, 800)
    imagen.thumbnail(tamaño_maximo)
    
    buffered = io.BytesIO()
    imagen.convert("RGB").save(buffered, format="JPEG", optimize=True, quality=85)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

    model_elegido = None
    url_list = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    
    try:
        req_list = requests.get(url_list, timeout=10)
        if req_list.status_code == 200:
            modelos_disponibles = req_list.json().get("models", [])
            modelos_prioridad = ["models/gemini-2.0-flash", "models/gemini-1.5-flash", "models/gemini-1.5-flash-latest"]
            nombres_disponibles = [m.get("name") for m in modelos_disponibles if "generateContent" in m.get("supportedGenerationMethods", [])]
            for mp in modelos_prioridad:
                if mp in nombres_disponibles:
                    model_elegido = mp.replace("models/", "")
                    break
            if not model_elegido and nombres_disponibles:
                model_elegido = nombres_disponibles[0].replace("models/", "")
    except Exception:
        pass 

    if not model_elegido:
        model_elegido = "gemini-1.5-flash"

    url_post = f"https://generativelanguage.googleapis.com/v1beta/models/{model_elegido}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    instruccion = (
        "Eres un sistema de visión artificial experto en medidores eléctricos DDS-121HY. "
        "Tu ÚNICA tarea es leer el display digital LCD principal que muestra los kWh. "
        "El formato de los números es de 6 dígitos enteros seguidos de un punto decimal y un dígito más (ejemplo: 000123.4). "
        "Ignora el texto impreso en el plástico, ignora los voltajes y los Hz. "
        "Busca la pantalla LCD y extrae ese número exacto, incluyendo su decimal. "
        "Devuelve SOLAMENTE los números. Nada de letras, nada de explicaciones."
    )

    payload = {"contents": [{"parts": [{"text": instruccion}, {"inline_data": {"mime_type": "image/jpeg", "data": img_str}}]}]}

    max_reintentos = 3
    tiempo_espera = 60 

    for intento in range(max_reintentos):
        try:
            response = requests.post(url_post, headers=headers, json=payload, timeout=40)
            if response.status_code == 429:
                if intento < max_reintentos - 1:
                    st.toast(f"⏳ Límite gratuito alcanzado. Recargando en {tiempo_espera}s...", icon="⏳")
                    time.sleep(tiempo_espera)
                    continue 
                else:
                    st.error("🛑 Tráfico máximo alcanzado. Utiliza la opción de 'Ingreso Manual'.")
                    return None
            elif response.status_code != 200:
                st.error(f"❌ Error de Google ({response.status_code})")
                return None
                
            datos = response.json()
            texto_ia = datos['candidates'][0]['content']['parts'][0]['text']
            return float(texto_ia.strip().replace(" ", "").replace(",", "."))
            
        except requests.exceptions.ConnectionError:
            st.error("📡 ERROR DE RED: Revisa tu conexión a internet.")
            return None
        except Exception:
            st.error("⚠️ Error de lectura de IA.")
            return None

# --- 2. CARGA Y MEMORIAS ---
DIRECTORIO_ACTUAL = os.path.dirname(os.path.abspath(__file__))

def cargar_datos_iniciales():
    archivos_en_carpeta = os.listdir(DIRECTORIO_ACTUAL)
    archivo_encontrado = next((os.path.join(DIRECTORIO_ACTUAL, f) for f in archivos_en_carpeta if f.lower().startswith("usuarios")), None)
            
    if not archivo_encontrado:
        st.error("⚠️ Base de datos de usuarios no encontrada.")
        st.stop()
        
    try:
        if archivo_encontrado.endswith((".xlsx", ".xls")):
            df = pd.read_excel(archivo_encontrado)
        else:
            df = pd.read_csv(archivo_encontrado, encoding="utf-8")
            
        df.columns = df.columns.str.strip()
        if "Telefono" in df.columns:
            df["Telefono"] = df["Telefono"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.replace(" ", "").str.replace("-", "").str.replace("+", "")
        else:
            df["Telefono"] = ""
            
        if "Lectura_Nueva" not in df.columns: df["Lectura_Nueva"] = 0.0
        if "Consumo_Neto" not in df.columns: df["Consumo_Neto"] = 0.0
        if "Total_Pagar" not in df.columns: df["Total_Pagar"] = 0.0
            
        return df
    except Exception as e:
        st.error(f"❌ Error al leer la base de datos: {e}")
        st.stop()

if "df_usuarios" not in st.session_state:
    st.session_state.df_usuarios = cargar_datos_iniciales()
if "procesados_hoy" not in st.session_state:
    st.session_state.procesados_hoy = [] 
if "recaudacion" not in st.session_state:
    st.session_state.recaudacion = {} 

# --- BARRA LATERAL (DASHBOARD Y DOBLE DESCARGA HISTÓRICA) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/6009/6009864.png", width=100)
    st.markdown("### 💾 Guardar Trabajo")
    st.warning("⚠️ Recuerda descargar tus archivos al finalizar el día.")
    
    output_reporte = io.BytesIO()
    with pd.ExcelWriter(output_reporte, engine='openpyxl') as writer:
        st.session_state.df_usuarios.to_excel(writer, index=False, sheet_name='Reporte_Auditoria')
    
    st.download_button(
        label="📊 1. Descargar Reporte del Mes",
        data=output_reporte.getvalue(),
        file_name="Reporte_Historial_Mes.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
    df_proximo = st.session_state.df_usuarios.copy()
    mask = df_proximo['Nombre'].isin(st.session_state.procesados_hoy)
    
    col_historial = f"Historial_{mes_actual_nombre}_{año_actual}"
    
    df_proximo.loc[mask, col_historial] = df_proximo.loc[mask, 'Lectura_Nueva']
    df_proximo.loc[mask, 'Lectura_Anterior'] = df_proximo.loc[mask, 'Lectura_Nueva']
    
    output_db = io.BytesIO()
    with pd.ExcelWriter(output_db, engine='openpyxl') as writer:
        cols_base = [c for c in df_proximo.columns if c not in ["Lectura_Nueva", "Consumo_Neto", "Total_Pagar", "Etiqueta"]]
        df_proximo[cols_base].to_excel(writer, index=False, sheet_name='Usuarios')
        
    st.download_button(
        label="💾 2. Descargar BD (Próximo Mes)",
        data=output_db.getvalue(),
        file_name="usuarios.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
    st.markdown("---")
    st.markdown("### 💰 Panel de Recaudación")
    total_recaudado = sum(st.session_state.recaudacion.values())
    st.metric(label="Total Facturado Hoy", value=f"S/. {total_recaudado:.2f}")
    
    total_usuarios = len(st.session_state.df_usuarios)
    leidos = len(st.session_state.procesados_hoy)
    st.progress(leidos / total_usuarios if total_usuarios > 0 else 0)
    st.caption(f"📊 Medidores leídos: **{leidos} de {total_usuarios}**")


# --- 3. INTERFAZ PRINCIPAL ---
st.markdown("<h1 style='text-align: center; color: #1f77b4;'>⚡ Ramozi LuzApp</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 18px; color: gray;'>Administración Asociación 4 de Enero</p>", unsafe_allow_html=True)
st.markdown("---")

st.subheader("1. Selección de Usuario")

st.session_state.df_usuarios["Etiqueta"] = (
    st.session_state.df_usuarios["Calle"].astype(str) + " | MZ " + 
    st.session_state.df_usuarios["MZ"].astype(str) + " - Lote " + 
    st.session_state.df_usuarios["Lote"].astype(str) + " | " + 
    st.session_state.df_usuarios["Nombre"].astype(str)
)

filtro_usuarios = st.radio("Filtro de búsqueda:", ("Solo Pendientes", "Todos los Usuarios"), horizontal=True)

if filtro_usuarios == "Solo Pendientes":
    df_filtrado = st.session_state.df_usuarios[~st.session_state.df_usuarios["Nombre"].isin(st.session_state.procesados_hoy)].copy()
    if df_filtrado.empty:
        st.success("🎉 ¡Felicidades! Has terminado de leer todos los medidores de la asociación.")
        st.stop()
else:
    df_filtrado = st.session_state.df_usuarios.copy()

opciones_usuarios = df_filtrado["Etiqueta"].dropna().tolist()
usuario_seleccionado = st.selectbox("Busca por calle, lote o propietario:", opciones_usuarios)

idx_usuario = st.session_state.df_usuarios[st.session_state.df_usuarios["Etiqueta"] == usuario_seleccionado].index[0]
datos_usuario = st.session_state.df_usuarios.loc[idx_usuario]
nombre_actual = datos_usuario['Nombre']

try:
    lectura_anterior = float(datos_usuario["Lectura_Anterior"]) if pd.notna(datos_usuario["Lectura_Anterior"]) else 0.0
except:
    lectura_anterior = 0.0

if nombre_actual in st.session_state.procesados_hoy:
    st.success("✅ **¡Este medidor ya fue leído y facturado en esta sesión!**")

# Modificación aquí para agregar el mes a la interfaz
st.info(f"📍 **Ubicación:** {datos_usuario['Calle']}, MZ {datos_usuario['MZ']} - Lote {datos_usuario['Lote']}\n\n📉 **Lectura Registrada Anterior ({mes_anterior_nombre}):** `{lectura_anterior} kWh`")

col1, col2 = st.columns(2)
with col1:
  tarifa_kwh = st.number_input("Tarifa por kWh (S/.)", value=0.85, step=0.01)
with col2:
  cargo_fijo = st.number_input("Cargo Fijo (S/.)", value=2.00, step=0.50)

if nombre_actual in st.session_state.procesados_hoy:
    st.warning("Detectamos que actualizaste este medidor recientemente. ¿Hubo un error?")
    if st.button("↩️ Deshacer y Borrar Lectura Actual", type="secondary"):
        st.session_state.df_usuarios.at[idx_usuario, 'Lectura_Nueva'] = 0.0
        st.session_state.df_usuarios.at[idx_usuario, 'Consumo_Neto'] = 0.0
        st.session_state.df_usuarios.at[idx_usuario, 'Total_Pagar'] = 0.0
        
        st.session_state.procesados_hoy.remove(nombre_actual)
        if nombre_actual in st.session_state.recaudacion:
            del st.session_state.recaudacion[nombre_actual] 
        st.rerun()

st.markdown("---")
st.subheader("2. Ingreso de Nueva Lectura")
opcion_ingreso = st.radio("Método de lectura:", ("Usar Cámara", "Subir Foto", "Ingreso Manual (Sin IA)"), horizontal=True)

imagen_medidor = None
lectura_manual_ingresada = None
lectura_actual = None
procesar_cobro = False

if opcion_ingreso == "Usar Cámara":
  imagen_capturada = st.camera_input("Toma la foto de la pantalla LCD")
  if imagen_capturada:
    imagen_medidor = Image.open(imagen_capturada)
elif opcion_ingreso == "Subir Foto":
  imagen_subida = st.file_uploader("Sube foto del medidor", type=["jpg", "jpeg", "png"])
  if imagen_subida:
    imagen_medidor = Image.open(imagen_subida)
    st.image(imagen_medidor, use_column_width=True)
else:
  # Modificación aquí para el ingreso manual
  lectura_manual_ingresada = st.number_input(f"Lectura Actual del Medidor - {mes_actual_nombre} (kWh):", min_value=0.0, value=float(lectura_anterior), step=0.1, format="%.1f")

if opcion_ingreso in ["Usar Cámara", "Subir Foto"] and imagen_medidor is not None:
  if st.button("🚀 Extraer y Calcular", type="primary"):
    with st.spinner("Analizando medidor..."):
      lectura_actual = obtener_lectura_medidor(imagen_medidor)
      if lectura_actual is not None: procesar_cobro = True
elif opcion_ingreso == "Ingreso Manual (Sin IA)":
  if st.button("🚀 Calcular Recibo Manualmente", type="primary"):
      lectura_actual = lectura_manual_ingresada
      procesar_cobro = True

# --- 5. MOTOR FINANCIERO Y RENDERING ---
if procesar_cobro and lectura_actual is not None:
    if lectura_actual < lectura_anterior:
      st.error(f"🛑 **ERROR:** La lectura nueva ({lectura_actual}) es menor a la anterior ({lectura_anterior}).")
    else:
      consumo_neto = lectura_actual - lectura_anterior
      costo_consumo = consumo_neto * tarifa_kwh
      total_a_pagar = costo_consumo + cargo_fijo

      st.session_state.df_usuarios.at[idx_usuario, 'Lectura_Nueva'] = lectura_actual
      st.session_state.df_usuarios.at[idx_usuario, 'Consumo_Neto'] = consumo_neto
      st.session_state.df_usuarios.at[idx_usuario, 'Total_Pagar'] = total_a_pagar
      
      if nombre_actual not in st.session_state.procesados_hoy:
          st.session_state.procesados_hoy.append(nombre_actual)
      
      st.session_state.recaudacion[nombre_actual] = total_a_pagar

      st.success("✅ **Lectura guardada temporalmente. ¡El Panel de Recaudación se ha actualizado!**")
      st.markdown("### 📊 Liquidación Oficial")
      st.write(f"- **Consumo Neto:** `{consumo_neto:.1f} kWh`")
      st.markdown(f"## **Total a Cobrar: S/. {total_a_pagar:.2f}**")

      # A. WHATSAPP (Añadiendo los meses)
      telefono_usuario = str(datos_usuario["Telefono"]).strip()
      if telefono_usuario and telefono_usuario != "nan":
        mensaje_ws = f"⚡ *ASOCIACIÓN 4 DE ENERO* - Recibo de Luz\nHola *{nombre_actual}*, te enviamos el detalle de tu consumo:\n📍 *Ubicación:* {datos_usuario['Calle']}, MZ {datos_usuario['MZ']} Lote {datos_usuario['Lote']}\n- Lectura anterior ({mes_anterior_nombre}): {lectura_anterior} kWh\n- Lectura actual ({mes_actual_nombre}): {lectura_actual} kWh\n- Consumo neto: {consumo_neto:.1f} kWh\n\n💰 *TOTAL A PAGAR: S/. {total_a_pagar:.2f}*\n\nPuedes realizar el pago mediante transferencia, Yape o Plin. ¡Gracias!"
        enlace_whatsapp = f"https://wa.me/{telefono_usuario}?text={urllib.parse.quote(mensaje_ws)}"
        st.markdown(f'<a href="{enlace_whatsapp}" target="_blank"><button style="background-color:#25D366; color:white; padding:12px; border-radius:8px; width: 100%; cursor: pointer; border: none; font-weight: bold; margin-bottom: 10px;">📲 Enviar Cobro por WhatsApp</button></a>', unsafe_allow_html=True)

      # B. PDF (Añadiendo los meses en la tabla)
      pdf = FPDF()
      pdf.add_page()
      pdf.set_font("Arial", "B", 18); pdf.set_text_color(0, 51, 102) 
      pdf.cell(190, 10, txt="ASOCIACION 4 DE ENERO", ln=True, align='C')
      pdf.set_font("Arial", "", 10); pdf.set_text_color(100, 100, 100) 
      pdf.cell(190, 5, txt="Sector 7 - Iquitos | Suministro Interno", ln=True, align='C')
      pdf.ln(5); pdf.set_draw_color(200, 200, 200); pdf.line(10, 30, 200, 30); pdf.ln(5)
      
      pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", "B", 11)
      pdf.cell(30, 8, txt="Titular:", border=0)
      pdf.set_font("Arial", "", 11); pdf.cell(160, 8, txt=str(nombre_actual).upper(), border=0, ln=True)
      
      pdf.set_font("Arial", "B", 11); pdf.cell(30, 8, txt="Direccion:", border=0)
      pdf.set_font("Arial", "", 11); pdf.multi_cell(160, 8, txt=f"{datos_usuario['Calle']} MZ {datos_usuario['MZ']} Lote {datos_usuario['Lote']}".upper(), border=0)
      pdf.ln(5)
      
      pdf.set_fill_color(240, 240, 240); pdf.set_draw_color(150, 150, 150); pdf.set_font("Arial", "B", 11)
      pdf.cell(140, 8, txt=" Descripcion del Consumo", border=1, fill=True)
      pdf.cell(50, 8, txt=" Importe", border=1, fill=True, align='R', ln=True)
      
      pdf.set_font("Arial", "", 11)
      pdf.cell(140, 8, txt=f" Lectura Anterior ({mes_anterior_nombre}): {lectura_anterior} kWh", border='LR'); pdf.cell(50, 8, txt="", border='LR', align='R', ln=True)
      pdf.cell(140, 8, txt=f" Lectura Actual ({mes_actual_nombre}): {lectura_actual} kWh", border='LR'); pdf.cell(50, 8, txt="", border='LR', align='R', ln=True)
      pdf.cell(140, 8, txt=f" Consumo Neto: {consumo_neto:.1f} kWh", border='LR'); pdf.cell(50, 8, txt="", border='LR', align='R', ln=True)
      pdf.cell(140, 8, txt=f" Cargo por Energia (S/. {tarifa_kwh:.2f})", border='LR'); pdf.cell(50, 8, txt=f"S/. {costo_consumo:.2f} ", border='LR', align='R', ln=True)
      pdf.cell(140, 8, txt=f" Cargo Fijo", border='LR'); pdf.cell(50, 8, txt=f"S/. {cargo_fijo:.2f} ", border='LR', align='R', ln=True)
      pdf.cell(140, 2, txt="", border='LRB'); pdf.cell(50, 2, txt="", border='LRB', ln=True); pdf.ln(8)
      
      pdf.set_fill_color(230, 240, 255); pdf.set_draw_color(0, 51, 102); pdf.set_line_width(0.6) 
      pdf.set_font("Arial", "B", 14); pdf.cell(90, 14, txt="", border=0) 
      pdf.set_text_color(0, 51, 102); pdf.cell(50, 14, txt="TOTAL A PAGAR:", border='LTB', align='R', fill=True)
      pdf.set_font("Arial", "B", 16); pdf.set_text_color(204, 0, 0) 
      pdf.cell(50, 14, txt=f"S/. {total_a_pagar:.2f}", border='RTB', align='C', fill=True, ln=True)
      
      pdf.set_line_width(0.2); pdf.set_text_color(120, 120, 120); pdf.ln(12)
      pdf.set_font("Arial", "I", 9); pdf.cell(190, 10, txt="Conserve este recibo para cualquier reclamo. ¡Gracias por su puntualidad!", ln=True, align='C')
      
      st.download_button(label="📥 Descargar Recibo (PDF Oficial)", data=pdf.output(dest='S').encode('latin-1', 'replace'), file_name=f"Recibo_{str(nombre_actual).replace(' ', '_')}.pdf", mime="application/pdf")