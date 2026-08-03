import os
import time
import urllib.parse
import base64
import io
import requests
from PIL import Image
import pandas as pd
import streamlit as st

# --- 1. CONFIGURACIÓN (BRANDING) ---
st.set_page_config(page_title="Ramozi LuzApp - Asociación 4 de Enero", page_icon="⚡", layout="centered")

# Tu clave de Google Cloud Console
API_KEY = "AQ.Ab8RN6KRORBTPy37ez_9L8oDEntYDiwJBT09u4DwmUfVtlwQUQ"

def obtener_lectura_medidor(imagen):
    """
    Motor de IA experto optimizado para la capa gratuita.
    Reduce la imagen para ahorrar cuota y sincroniza los reintentos a 60 segundos.
    """
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
            modelos_prioridad = [
                "models/gemini-2.0-flash",
                "models/gemini-1.5-flash", 
                "models/gemini-1.5-flash-latest"
            ]
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

    payload = {
        "contents": [{
            "parts": [
                {"text": instruccion},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_str}}
            ]
        }]
    }

    max_reintentos = 3
    tiempo_espera = 60 

    for intento in range(max_reintentos):
        try:
            response = requests.post(url_post, headers=headers, json=payload, timeout=40)
            
            if response.status_code == 429:
                if intento < max_reintentos - 1:
                    st.toast(f"⏳ Límite gratuito alcanzado. Recargando cuota en {tiempo_espera}s... (Intento {intento + 1}/{max_reintentos})", icon="⏳")
                    time.sleep(tiempo_espera)
                    continue 
                else:
                    st.error("🛑 Tráfico máximo alcanzado. Utiliza la opción de 'Ingreso Manual' por ahora o intenta más tarde.")
                    return None
            elif response.status_code != 200:
                st.error(f"❌ Error de Google ({response.status_code}): {response.text}")
                return None
                
            datos = response.json()
            texto_ia = datos['candidates'][0]['content']['parts'][0]['text']
            texto_limpio = texto_ia.strip().replace(" ", "").replace(",", ".")
            return float(texto_limpio)
            
        except requests.exceptions.ConnectionError:
            st.error("📡 ERROR DE RED: Revisa tu conexión a internet.")
            return None
        except ValueError:
            st.error(f"⚠️ La IA no devolvió un formato numérico claro. Respuesta capturada: '{texto_ia}'")
            return None
        except Exception as e:
            st.error(f"❌ Error inesperado: {e}")
            return None


# --- 2. CARGA DE BASE DE DATOS ---
DIRECTORIO_ACTUAL = os.path.dirname(os.path.abspath(__file__))

st.markdown("<h1 style='text-align: center; color: #1f77b4;'>⚡ Ramozi LuzApp</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 18px; color: gray;'>Administración Asociación 4 de Enero - Sede Iquitos</p>", unsafe_allow_html=True)
st.markdown("---")

archivos_en_carpeta = os.listdir(DIRECTORIO_ACTUAL)
archivo_encontrado = None

for archivo in archivos_en_carpeta:
  if archivo.lower().startswith("usuarios"):
    archivo_encontrado = os.path.join(DIRECTORIO_ACTUAL, archivo)
    break

if not archivo_encontrado:
  st.error(f"⚠️ Base de datos de usuarios no encontrada en la carpeta.")
  st.stop()

try:
  if archivo_encontrado.endswith(".xlsx") or archivo_encontrado.endswith(".xls"):
    df_usuarios = pd.read_excel(archivo_encontrado)
  else:
    df_usuarios = pd.read_csv(archivo_encontrado, encoding="utf-8")

  df_usuarios.columns = df_usuarios.columns.str.strip()
  
  if "Telefono" in df_usuarios.columns:
    df_usuarios["Telefono"] = (
        df_usuarios["Telefono"]
        .fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(" ", "")
        .str.replace("-", "")
        .str.replace("+", "")
    )
  else:
    df_usuarios["Telefono"] = ""

except Exception as e:
  st.error(f"❌ Error al leer la base de datos: {e}")
  st.stop()


# --- 3. INTERFAZ DE USUARIO (SELECCIÓN Y TARIFAS) ---
st.subheader("1. Selección de Usuario")

df_usuarios["Etiqueta"] = (
    df_usuarios["Calle"].astype(str) + " | MZ " + 
    df_usuarios["MZ"].astype(str) + " - Lote " + 
    df_usuarios["Lote"].astype(str) + " | " + 
    df_usuarios["Nombre"].astype(str)
)

opciones_usuarios = df_usuarios["Etiqueta"].dropna().tolist()
usuario_seleccionado = st.selectbox("Busca por calle, lote o propietario:", opciones_usuarios)

datos_usuario = df_usuarios[df_usuarios["Etiqueta"] == usuario_seleccionado].iloc[0]

try:
    val_lectura = datos_usuario["Lectura_Anterior"]
    if pd.isna(val_lectura) or str(val_lectura).strip() == "":
        lectura_anterior = 0.0
    else:
        lectura_anterior = float(val_lectura)
except Exception:
    lectura_anterior = 0.0

telefono_usuario = str(datos_usuario["Telefono"]).strip()

st.info(f"📍 **Ubicación:** {datos_usuario['Calle']}, MZ {datos_usuario['MZ']} - Lote {datos_usuario['Lote']}\n\n📉 **Última lectura:** `{lectura_anterior} kWh`")

col1, col2 = st.columns(2)
with col1:
  tarifa_kwh = st.number_input("Tarifa por kWh (S/.)", value=0.85, step=0.01)
with col2:
  cargo_fijo = st.number_input("Cargo Fijo (S/.)", value=2.00, step=0.50)


# --- 4. ESCÁNER DE IMAGEN Y MODO MANUAL ---
st.subheader("2. Ingreso de Lectura")

opcion_ingreso = st.radio("Método de lectura:", ("Usar Cámara", "Subir Foto", "Ingreso Manual (Sin IA)"), horizontal=True)

imagen_medidor = None
lectura_manual_ingresada = None
lectura_actual = None

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
  st.info("💡 Modo Manual Activo: Ingresa la lectura actual directamente.")
  lectura_manual_ingresada = st.number_input("Lectura Actual del Medidor (kWh):", min_value=0.0, value=float(lectura_anterior), step=0.1, format="%.1f")


# --- 5. DISPARADOR DE CÁLCULOS ---
procesar_cobro = False

if opcion_ingreso in ["Usar Cámara", "Subir Foto"] and imagen_medidor is not None:
  if st.button("🚀 Extraer Lectura con IA", type="primary"):
    with st.spinner("Analizando medidor con Inteligencia Artificial..."):
      lectura_actual = obtener_lectura_medidor(imagen_medidor)
      if lectura_actual is not None:
          procesar_cobro = True

elif opcion_ingreso == "Ingreso Manual (Sin IA)":
  if st.button("🚀 Calcular Recibo Manualmente", type="primary"):
      lectura_actual = lectura_manual_ingresada
      procesar_cobro = True


# --- 6. MOTOR FINANCIERO, WHATSAPP, EXCEL Y PDF INDIVIDUAL ---
if procesar_cobro and lectura_actual is not None:
    st.success(f"✅ Lectura actual procesada: **{lectura_actual} kWh**")

    if lectura_actual < lectura_anterior:
      st.error(
          f"🛑 **ERROR:** La lectura actual ({lectura_actual} kWh) es menor a la del mes pasado ({lectura_anterior} kWh). "
          "Verifica el número ingresado o la foto enviada."
      )
    else:
      consumo_neto = lectura_actual - lectura_anterior
      costo_consumo = consumo_neto * tarifa_kwh
      total_a_pagar = costo_consumo + cargo_fijo

      st.markdown("---")
      st.markdown("### 📊 Liquidación Oficial - Asociación 4 de Enero")
      st.write(f"- **Titular:** {datos_usuario['Nombre']}")
      st.write(f"- **Consumo Neto:** `{consumo_neto:.1f} kWh`")
      st.write(f"- **Subtotal (Energía):** `S/. {costo_consumo:.2f}`")
      st.write(f"- **Cargos Adicionales:** `S/. {cargo_fijo:.2f}`")
      st.markdown(f"## **Total a Cobrar: S/. {total_a_pagar:.2f}**")

      # --- A. BOTÓN DE WHATSAPP ---
      if not telefono_usuario or telefono_usuario == "nan":
        st.warning("⚠️ Este usuario no tiene número registrado.")
      else:
        mensaje_ws = (
            f"⚡ *ASOCIACIÓN 4 DE ENERO* - Recibo de Luz\n\n"
            f"Hola *{datos_usuario['Nombre']}*, te enviamos el detalle de tu consumo:\n"
            f"📍 *Ubicación:* {datos_usuario['Calle']}, MZ {datos_usuario['MZ']} Lote {datos_usuario['Lote']}\n"
            f"- Lectura anterior: {lectura_anterior} kWh\n"
            f"- Lectura actual: {lectura_actual} kWh\n"
            f"- Consumo neto: {consumo_neto:.1f} kWh\n\n"
            f"💰 *TOTAL A PAGAR: S/. {total_a_pagar:.2f}*\n\n"
            f"Puedes realizar el pago mediante transferencia, Yape o Plin. ¡Gracias!"
        )
        
        mensaje_codificado = urllib.parse.quote(mensaje_ws)
        enlace_whatsapp = f"https://wa.me/{telefono_usuario}?text={mensaje_codificado}"
        
        st.markdown(
            f'<a href="{enlace_whatsapp}" target="_blank"><button style="background-color:#25D366; color:white; padding:12px; border-radius:8px; width: 100%; cursor: pointer; border: none; font-weight: bold; margin-bottom: 10px;">📲 Enviar Cobro por WhatsApp</button></a>',
            unsafe_allow_html=True,
        )

      # --- B. DESCARGA DE RECIBO INDIVIDUAL EN PDF (VENTANA DE IMPRESIÓN) ---
      st.markdown("### 📄 Recibo Individual para Impresión / PDF")
      html_recibo = f"""
      <div style="border: 2px solid #333; padding: 20px; border-radius: 10px; font-family: Arial; background-color: #fff; color: #000; max-width: 400px; margin: auto;">
          <h3 style="text-align: center; margin-bottom: 5px;">ASOCIACIÓN 4 DE ENERO</h3>
          <p style="text-align: center; font-size: 12px; color: #555; margin-top: 0;">Sector 7 - Iquitos | Suministro Interno</p>
          <hr>
          <p><b>Titular:</b> {datos_usuario['Nombre']}</p>
          <p><b>Dirección:</b> {datos_usuario['Calle']} MZ {datos_usuario['MZ']} Lote {datos_usuario['Lote']}</p>
          <hr>
          <p><b>Lectura Anterior:</b> {lectura_anterior} kWh</p>
          <p><b>Lectura Actual:</b> {lectura_actual} kWh</p>
          <p><b>Consumo Neto:</b> {consumo_neto:.1f} kWh</p>
          <p><b>Tarifa kWh:</b> S/. {tarifa_kwh:.2f}</p>
          <p><b>Cargo Fijo:</b> S/. {cargo_fijo:.2f}</p>
          <hr>
          <h2 style="text-align: center; color: #d9534f;">TOTAL: S/. {total_a_pagar:.2f}</h2>
          <p style="text-align: center; font-size: 10px; margin-top: 15px;">Conserve este recibo para cualquier reclamo. ¡Gracias por su puntualidad!</p>
      </div>
      <br>
      <div style="text-align: center;">
          <button onclick="window.print()" style="background-color:#007BFF; color:white; padding:10px 20px; border:none; border-radius:5px; font-size:14px; font-weight:bold; cursor:pointer;">🖨️ Imprimir / Guardar Recibo en PDF</button>
      </div>
      """
      st.markdown(html_recibo, unsafe_allow_html=True)

      # --- C. DESCARGA DE REPORTE GENERAL EN EXCEL ---
      st.markdown("---")
      st.markdown("### 📁 Reporte General de Consumos")
      
      # Creamos un registro temporal para exportar
      df_reporte = pd.DataFrame([{
          "Calle": datos_usuario["Calle"],
          "MZ": datos_usuario["MZ"],
          "Lote": datos_usuario["Lote"],
          "Propietario": datos_usuario["Nombre"],
          "Lectura_Anterior": lectura_anterior,
          "Lectura_Actual": lectura_actual,
          "Consumo_Neto_kWh": round(consumo_neto, 1),
          "Total_Pagar_Soles": round(total_a_pagar, 2)
      }])

      # Convertimos el DataFrame a Excel en memoria
      output = io.BytesIO()
      with pd.ExcelWriter(output, engine='openpyxl') as writer:
          df_reporte.to_excel(writer, index=False, sheet_name='Liquidacion_Asociacion')
      processed_data = output.getvalue()

      st.download_button(
          label="📥 Descargar Reporte General en Excel",
          data=processed_data,
          file_name=f"Recibo_{datos_usuario['Nombre'].replace(' ', '_')}.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      )