import json
import time
import io
import streamlit as st
import streamlit.components.v1 as components
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# ==========================================
# 1. METADATOS Y CONFIGURACIÓN DE PÁGINA
# ==========================================

APP_VERSION = "v5.0 - Ultimate Soft Blue ✨"

st.set_page_config(
    page_title="Friday - Tu Tutor Virtual",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. CONFIGURACIÓN SEGURA DE LA API KEY
# ==========================================

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except KeyError:
    st.error(
        "⚠️ Falta configurar la API Key. "
        "Agrega GOOGLE_API_KEY en los Secrets de Streamlit Cloud (.streamlit/secrets.toml)."
    )
    st.stop()

# ==========================================
# 3. PROMPTS DEL SISTEMA (MODOS DE TUTORÍA)
# ==========================================

SYSTEM_PROMPTS = {
    "Tutor General": """
    Eres Friday, una tutora virtual amigable, inteligente y humana.
    - Habla de forma natural, cercana y paciente.
    - Usa ejemplos claros y sencillos.
    - Nunca reveles que eres una IA, un chatbot o un modelo de lenguaje.
    - Si no sabes algo, dilo con honestidad y ofrece una alternativa útil.
    - Responde siempre en el idioma utilizado por el usuario.
    - Explica los temas paso a paso cuando sea necesario.
    - Ayuda al usuario con tareas, programación, tecnología, matemáticas y temas académicos.
    """,
    "Experto en Programación": """
    Eres Friday en modo Code Mentor.
    - Te especializas en desarrollo de software, algoritmos y depuración de código.
    - Formatea siempre los bloques de código adecuadamente especificando el lenguaje.
    - Explica la lógica detrás de cada función o solución propuesta.
    - Ofrece mejores prácticas de programación y optimización.
    - Nunca reveles que eres una IA o modelo de lenguaje.
    """,
    "Explicación Sencilla (ELI5)": """
    Eres Friday en modo Simplificado.
    - Explica conceptos complejos como si el usuario tuviera 10 años.
    - Utiliza analogías del mundo real, metáforas y un lenguaje libre de modismos técnicos innecesarios.
    - Mantén las respuestas breves, didácticas y entretenidas.
    - Nunca reveles que eres una IA o modelo de lenguaje.
    """
}

# ==========================================
# 4. ESTILOS Y TEMA DINÁMICO (SOFT BLUE PALETTE)
# ==========================================

def load_custom_css(theme: str):
    # Definición de paletas basadas en tonos azules suaves y dinámicos
    if theme == "Oscuro (Deep Navy)":
        bg_main = "#0f172a"
        bg_sidebar = "#1e293b"
        text_color = "#f1f5f9"
        card_bg = "#334155"
        border_color = "#475569"
        accent_blue = "#38bdf8"
    elif theme == "Claro (Soft Blue)":
        bg_main = "#f0f9ff"
        bg_sidebar = "#e0f2fe"
        text_color = "#0f172a"
        card_bg = "#ffffff"
        border_color = "#bae6fd"
        accent_blue = "#0284c7"
    else:  # Predeterminado del sistema
        bg_main = "transparent"
        bg_sidebar = "transparent"
        text_color = "inherit"
        card_bg = "rgba(2, 132, 199, 0.05)"
        border_color = "#7dd3fc"
        accent_blue = "#0284c7"

    css = f"""
    <style>
        /* Estilos generales */
        .stApp {{
            background-color: {bg_main};
            color: {text_color};
        }}
        
        /* Sidebar personalizado */
        section[data-testid="stSidebar"] {{
            background-color: {bg_sidebar};
            border-right: 1px solid {border_color};
        }}

        /* Tarjetas informativas y contenedores */
        .custom-card {{
            background-color: {card_bg};
            border: 1px solid {border_color};
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            margin-bottom: 15px;
        }}

        /* Botones principales */
        .stButton button {{
            background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
            color: white;
            border-radius: 8px;
            border: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}
        .stButton button:hover {{
            background: linear-gradient(135deg, #0369a1 0%, #075985 100%);
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3);
        }}

        /* Encabezados */
        h1, h2, h3 {{
            color: {accent_blue} !important;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ==========================================
# 5. COMPONENTE DE DICTADO DE VOZ
# ==========================================

VOICE_HTML = """
<style>
  body { margin:0; font-family: sans-serif; background: transparent; }
  .wrap { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
  #mic {
    background:#0284c7; color:#fff; border:none; border-radius:999px;
    padding:8px 16px; font-size:14px; cursor:pointer; font-weight: 500;
  }
  #mic.on { background:#16a34a; animation: pulse 1.2s infinite; }
  @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(22,163,74,.6)} 70%{box-shadow:0 0 0 10px rgba(22,163,74,0)} 100%{box-shadow:0 0 0 0 rgba(22,163,74,0)} }
  #state { font-size:12px; opacity: 0.8; }
  #live { width:100%; font-size:13px; opacity: 0.7; min-height:16px; font-style:italic; }
</style>
<div class="wrap">
  <button id="mic">🎤 Dictar con voz</button>
  <span id="state">Listo</span>
  <div id="live"></div>
</div>
<script>
  const LANG = "__LANG__";
  const AUTO_SEND = __AUTO__;
  const P = window.parent;

  const SR = P.SpeechRecognition || P.webkitSpeechRecognition ||
             window.SpeechRecognition || window.webkitSpeechRecognition;

  const btn = document.getElementById("mic");
  const stateEl = document.getElementById("state");
  const liveEl = document.getElementById("live");

  function getInput() {
    return P.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
  }
  function setInput(text) {
    const ta = getInput();
    if (!ta) return;
    const setter = Object.getOwnPropertyDescriptor(P.HTMLTextAreaElement.prototype, "value").set;
    setter.call(ta, text);
    ta.dispatchEvent(new P.Event("input", { bubbles: true }));
  }
  function sendInput() {
    const send = P.document.querySelector('button[data-testid="stChatInputSubmitButton"]');
    if (send) send.click();
  }

  if (!SR) {
    btn.disabled = true;
    stateEl.textContent = "Navegador sin soporte de voz (usa Chrome/Edge).";
  } else {
    const rec = new SR();
    rec.lang = LANG;
    rec.continuous = true;
    rec.interimResults = true;

    let listening = false;
    let finalText = "";

    rec.onstart = () => {
      listening = true;
      btn.classList.add("on");
      btn.textContent = "⏹️ Detener";
      stateEl.textContent = "Escuchando...";
    };

    rec.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += t + " ";
        else interim += t;
      }
      const full = (finalText + interim).trim();
      liveEl.textContent = full ? "📝 " + full : "";
      setInput(full);
    };

    rec.onerror = (e) => { stateEl.textContent = "⚠️ " + e.error; };

    rec.onend = () => {
      listening = false;
      btn.classList.remove("on");
      btn.textContent = "🎤 Dictar con voz";
      stateEl.textContent = "Listo";
      const text = finalText.trim();
      if (AUTO_SEND && text) setTimeout(sendInput, 350);
      finalText = "";
      liveEl.textContent = "";
    };

    btn.onclick = () => {
      if (listening) { rec.stop(); }
      else { finalText = ""; setInput(""); try { rec.start(); } catch (e) {} }
    };
  }
</script>
"""

def voice_dictation(lang: str, auto_send: bool):
    html = (VOICE_HTML
            .replace("__LANG__", lang)
            .replace("__AUTO__", "true" if auto_send else "false"))
    components.html(html, height=85)

# ==========================================
# 6. PASOS DE ESTADO DINÁMICOS
# ==========================================

def get_status_steps(mode: str, prompt: str) -> list[str]:
    p = prompt.lower()
    steps = ["🧠 Leyendo y procesando tu mensaje..."]

    if mode == "Experto en Programación" or any(w in p for w in ["código", "python", "error", "bug", "función", "script"]):
        steps += ["💻 Analizando sintaxis y lógica...", "🔍 Buscando optimizaciones y buenas prácticas..."]
    elif any(w in p for w in ["calcula", "ecuación", "integral", "matemática"]):
        steps += ["🧮 Analizando planteamiento matemático...", "📐 Resolviendo paso a paso..."]
    elif mode == "Explicación Sencilla (ELI5)":
        steps += ["🎈 Creando analogía didáctica...", "✂️ Simplificando conceptos..."]
    else:
        steps += ["📚 Consultando bases de conocimiento...", "💡 Estructurando ejemplos..."]

    steps.append("✍️ Escribiendo respuesta final...")
    return steps

# ==========================================
# 7. BARRA LATERAL Y CONFIGURACIÓN (v5.0)
# ==========================================

with st.sidebar:
    st.title("🤖 Friday Config")
    st.caption(f"Versión actual: **{APP_VERSION}**")
    st.divider()

    # --- Selección de Tema ---
    st.subheader("🎨 Apariencia")
    theme_choice = st.selectbox(
        "Tema de Interfaz",
        ["Predeterminado del sistema", "Claro (Soft Blue)", "Oscuro (Deep Navy)"],
        index=0
    )
    load_custom_css(theme_choice)

    st.divider()

    # --- Parámetros del Modelo ---
    st.subheader("⚙️ Parámetros de IA")
    selected_model = st.selectbox(
        "Modelo Gemini",
        ["gemini-3.6-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        index=0
    )
    tutor_mode = st.selectbox("Modo de Tutoría", list(SYSTEM_PROMPTS.keys()), index=0)
    temperature = st.slider("Creatividad (Temperatura)", 0.0, 1.0, 0.7, 0.1)

    st.divider()

    # --- NUEVO: Cargar Historial Previo (.json) ---
    st.subheader("📥 Recuperar Chats Previos")
    uploaded_history = st.file_uploader(
        "Cargar historial JSON",
        type=["json"],
        help="Sube un archivo de exportación anterior para que Friday recuerde la conversación."
    )
    if uploaded_history is not None:
        try:
            loaded_msgs = json.load(uploaded_history)
            if isinstance(loaded_msgs, list):
                st.session_state.messages = loaded_msgs
                st.success("¡Historial recuperado con éxito!")
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")

    st.divider()

    # --- Herramientas de Voz y Estado ---
    st.subheader("🎤 Configuración de Voz")
    voice_lang_label = st.selectbox(
        "Idioma",
        ["Español (El Salvador)", "Español (España)", "Español (México)", "English (US)"],
        index=0
    )
    VOICE_LANGS = {
        "Español (El Salvador)": "es-SV",
        "Español (España)": "es-ES",
        "Español (México)": "es-MX",
        "English (US)": "en-US",
    }
    voice_lang = VOICE_LANGS[voice_lang_label]
    auto_send = st.checkbox("Enviar al terminar de dictar", value=True)
    show_steps = st.checkbox("Mostrar pasos en vivo", value=True)

    st.divider()

    # --- Acciones y Métricas ---
    st.subheader("🛠️ Acciones")
    col_clear, col_export = st.columns(2)
    with col_clear:
        if st.button("🗑️ Limpiar", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    msg_count = len(st.session_state.get("messages", []))
    st.metric("Mensajes en sesión", msg_count)

    if msg_count > 0:
        export_data = json.dumps(st.session_state.get("messages", []), indent=2, ensure_ascii=False)
        st.download_button(
            label="📥 Exportar Chat (.json)",
            data=export_data,
            file_name="historial_friday_v5.json",
            mime="application/json",
            use_container_width=True
        )

# ==========================================
# 8. INICIALIZACIÓN DEL MODELO CACHEADO
# ==========================================

@st.cache_resource
def get_llm(model_name: str, temp: float):
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=API_KEY,
        temperature=temp,
        streaming=True
    )

llm = get_llm(selected_model, temperature)

# ==========================================
# 9. ENCABEZADO Y ESTADO INICIAL
# ==========================================

st.title("🤖 Friday, tu tutora virtual")
st.caption("Versión 5.0 — Asistente inteligente con análisis de archivos, dictado por voz y temas dinámicos.")

if "messages" not in st.session_state:
    st.session_state.messages = []

if len(st.session_state.messages) == 0:
    welcome_msg = "¡Hola! Soy **Friday**, tu tutora virtual v5.0. ¿Qué tema, código o documento analizaremos hoy?"
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

# ==========================================
# 10. RENDERIZAR HISTORIAL DE MENSAJES
# ==========================================

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==========================================
# 11. NUEVO: ADJUNTAR ARCHIVOS (DOCUMENTOS / CÓDIGO)
# ==========================================

st.markdown("---")
uploaded_file = st.file_uploader(
    "📎 Adjuntar archivo para análisis (TXT, Python, JSON, CSV, PDF)",
    type=["txt", "py", "json", "csv", "md", "pdf"],
    help="Sube un archivo y escribe tu pregunta abajo para que Friday lo analice."
)

file_context_text = ""
if uploaded_file is not None:
    try:
        file_bytes = uploaded_file.read()
        if uploaded_file.name.endswith(".pdf"):
            # Lector básico de PDF en texto plano
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            extracted = [page.extract_text() for page in reader.pages if page.extract_text()]
            file_context_text = "\n".join(extracted)
        else:
            file_context_text = file_bytes.decode("utf-8", errors="ignore")
        
        st.success(f"📎 Archivo **{uploaded_file.name}** cargado correctamente. Ya puedes consultarle a Friday sobre su contenido.")
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")

# Widget de voz sobre el chat
voice_dictation(voice_lang, auto_send)

# ==========================================
# 12. ENTRADA Y PROCESAMIENTO
# ==========================================

if prompt := st.chat_input("Escribe tu duda o pregunta sobre el archivo..."):

    # Integrar contenido del archivo adjunto al prompt si existe
    final_prompt = prompt
    if file_context_text:
        final_prompt = f"[Contenido del archivo adjunto '{uploaded_file.name}']:\n{file_context_text}\n\n[Pregunta del usuario]: {prompt}"
        file_context_text = "" # Limpiar para evitar duplicados en siguientes turnos

    # 1. Guardar y renderizar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Construir historial de LangChain
    active_prompt = SYSTEM_PROMPTS[tutor_mode]
    history = [SystemMessage(content=active_prompt)]

    for message in st.session_state.messages:
        if message["role"] == "user":
            history.append(HumanMessage(content=message["content"]))
        elif message["role"] == "assistant":
            history.append(AIMessage(content=message["content"]))

    # Si hay un prompt enriquecido con archivo, lo añadimos al final del historial actual
    if uploaded_file is not None:
        history[-1] = HumanMessage(content=final_prompt)

    # 3. Generar respuesta streaming con estado visible
    with st.chat_message("assistant"):
        status_box = None
        if show_steps:
            status_box = st.status("🧠 Friday está procesando...", expanded=True)
            for step in get_status_steps(tutor_mode, prompt)[:-1]:
                status_box.update(label=step, state="running")
                status_box.write(step)
                time.sleep(0.5)

        response_placeholder = st.empty()
        full_response = ""

        try:
            if status_box:
                status_box.update(label="✍️ Escribiendo respuesta...", state="running")

            for chunk in llm.stream(history):
                text = ""
                if isinstance(chunk.content, list):
                    for part in chunk.content:
                        if isinstance(part, dict) and "text" in part:
                            text += part["text"]
                        elif isinstance(part, str):
                            text += part
                else:
                    text = str(chunk.content)

                full_response += text
                response_placeholder.markdown(full_response + "▌")

            response_placeholder.markdown(full_response)

            if status_box:
                status_box.update(label="✅ Respuesta lista", state="complete", expanded=False)

        except Exception as e:
            full_response = f"😅 Ups, ocurrió un error al generar la respuesta: `{e}`"
            if status_box:
                status_box.update(label="❌ Error en la generación", state="error", expanded=True)
            st.error(full_response)

    # 4. Guardar respuesta del asistente
    st.session_state.messages.append({"role": "assistant", "content": full_response})
