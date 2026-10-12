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

APP_VERSION = "v6.1 - Clean Professional UI"

st.set_page_config(
    page_title="Friday - Tutor Virtual",
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
        "Falta configurar la API Key. "
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
    - Explica conceptos complejos de forma clara y accesible.
    - Utiliza analogías del mundo real y un lenguaje libre de tecnicismos innecesarios.
    - Mantén las respuestas breves, didácticas y ordenadas.
    - Nunca reveles que eres una IA o modelo de lenguaje.
    """
}

# ==========================================
# 4. INYECCIÓN CORRECTA DE CSS Y TEMA
# ==========================================

def load_custom_css(theme: str):
    if theme == "Oscuro (Deep Navy)":
        bg_main = "#0F172A"
        bg_sidebar = "#1E293B"
        text_color = "#F1F5F9"
        border_color = "#334155"
        accent_blue = "#38BDF8"
    elif theme == "Claro (Soft Blue)":
        bg_main = "#F8FAFC"
        bg_sidebar = "#F1F5F9"
        text_color = "#1E293B"
        border_color = "#CBD5E1"
        accent_blue = "#0284C7"
    else:  # Predeterminado del sistema
        bg_main = "transparent"
        bg_sidebar = "transparent"
        text_color = "inherit"
        border_color = "#CBD5E1"
        accent_blue = "#0284C7"

    css_code = f"""<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700&display=swap');

    html, body, [class*="st-"], input, textarea, button {{
        font-family: 'Montserrat', sans-serif !important;
    }}
    .stApp {{
        background-color: {bg_main};
        color: {text_color};
    }}
    section[data-testid="stSidebar"] {{
        background-color: {bg_sidebar};
        border-right: 1px solid {border_color};
    }}
    p, span, label, .stMarkdown, .stText, div[data-testid="stMarkdownContainer"] {{
        color: {text_color} !important;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {accent_blue} !important;
        font-weight: 600 !important;
    }}
    .stButton button {{
        background-color: {accent_blue};
        color: white;
        border-radius: 6px;
        border: none;
        font-weight: 500;
        transition: background 0.2s;
    }}
    .stButton button:hover {{
        background-color: #0369A1;
    }}
    /* Ocultar margen superior del file uploader para compacitar la barra */
    div[data-testid="stFileUploader"] {{
        padding-top: 0px;
        padding-bottom: 0px;
    }}
    </style>"""

    # Uso directo de st.html para inyección segura de CSS sin escapado de texto
    if hasattr(st, "html"):
        st.html(css_code)
    else:
        st.markdown(css_code, unsafe_allow_html=True)

# ==========================================
# 5. COMPONENTE DE DICTADO POR VOZ CORREGIDO
# ==========================================

VOICE_TOOLBAR_HTML = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500&display=swap');
  body { margin:0; padding:0; background: transparent; font-family: 'Montserrat', sans-serif; }
  .voice-container {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 2px;
    margin-bottom: 2px;
  }
  .voice-btn {
    background: transparent;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 14px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 500;
    color: #0284C7;
    transition: all 0.2s;
  }
  .voice-btn:hover {
    background-color: rgba(2, 132, 199, 0.08);
    border-color: #0284C7;
  }
  .voice-btn.active {
    background-color: #16A34A;
    color: white;
    border-color: #16A34A;
  }
  .voice-status {
    font-size: 12px;
    opacity: 0.8;
    font-style: italic;
    color: #64748B;
  }
  svg { width: 14px; height: 14px; fill: currentColor; }
</style>
<div class="voice-container">
  <button id="mic-btn" class="voice-btn" onclick="toggleDictation()" title="Dictar mensaje por voz">
    <svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.91-3c-.49 0-.9.36-.98.85C16.52 14.2 14.47 16 12 16s-4.52-1.8-4.93-4.15c-.08-.49-.49-.85-.98-.85-.61 0-1.09.54-1 1.14.49 3 2.89 5.35 5.91 5.78V20h2v-3.08c3.02-.43 5.42-2.78 5.91-5.78.1-.6-.39-1.14-1-1.14z"/></svg>
    <span id="mic-text">Dictar por voz</span>
  </button>
  <span id="mic-status" class="voice-status"></span>
</div>
<script>
  const P = window.parent;
  const SR = P.SpeechRecognition || P.webkitSpeechRecognition || window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isListening = false;

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

  function toggleDictation() {
    if (!SR) {
      alert("El navegador no soporta reconocimiento de voz. Utilice Google Chrome o Microsoft Edge.");
      return;
    }
    const btn = document.getElementById("mic-btn");
    const txt = document.getElementById("mic-text");
    const status = document.getElementById("mic-status");

    if (isListening) {
      recognition.stop();
      return;
    }

    recognition = new SR();
    recognition.lang = "es-ES";
    recognition.continuous = true;
    recognition.interimResults = true;

    let accumulated = getInput() ? getInput().value + " " : "";

    recognition.onstart = () => {
      isListening = true;
      btn.classList.add("active");
      txt.textContent = "Detener voz";
      status.textContent = "Escuchando...";
    };

    recognition.onresult = (event) => {
      let interim = "";
      let finalChunk = "";
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalChunk += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      if (finalChunk) {
        accumulated += finalChunk + " ";
      }
      setInput((accumulated + interim).trim());
    };

    recognition.onerror = (e) => {
      status.textContent = "Error: " + e.error;
    };

    recognition.onend = () => {
      isListening = false;
      btn.classList.remove("active");
      txt.textContent = "Dictar por voz";
      status.textContent = "";
    };

    try {
      recognition.start();
    } catch(err) {
      console.error(err);
    }
  }
</script>
"""

def voice_toolbar():
    components.html(VOICE_TOOLBAR_HTML, height=42)

# ==========================================
# 6. CONFIGURACIÓN DE LA BARRA LATERAL
# ==========================================

with st.sidebar:
    st.title("Panel de Control")
    st.caption(f"Versión: {APP_VERSION}")
    st.divider()

    # --- Tema ---
    st.subheader("Apariencia")
    theme_choice = st.selectbox(
        "Tema de interfaz",
        ["Predeterminado del sistema", "Claro (Soft Blue)", "Oscuro (Deep Navy)"],
        index=0
    )
    load_custom_css(theme_choice)

    st.divider()

    # --- Parámetros de Modelo ---
    st.subheader("Configuración de IA")
    selected_model = st.selectbox(
        "Modelo",
        ["gemini-3.6-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        index=0
    )
    tutor_mode = st.selectbox("Modo de Tutoría", list(SYSTEM_PROMPTS.keys()), index=0)
    temperature = st.slider("Temperatura", 0.0, 1.0, 0.7, 0.1)

    st.divider()

    # --- Cargar Historial Previo ---
    st.subheader("Historial de Conversación")
    uploaded_history = st.file_uploader(
        "Cargar archivo JSON previo",
        type=["json"],
        help="Sube un archivo de exportación anterior para recuperar la sesión."
    )
    if uploaded_history is not None:
        try:
            loaded_msgs = json.load(uploaded_history)
            if isinstance(loaded_msgs, list):
                st.session_state.messages = loaded_msgs
                st.success("Historial recuperado exitosamente.")
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")

    st.divider()

    # --- Acciones ---
    col_clear, col_export = st.columns(2)
    with col_clear:
        if st.button("Limpiar", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    msg_count = len(st.session_state.get("messages", []))
    st.metric("Mensajes", msg_count)

    if msg_count > 0:
        export_data = json.dumps(st.session_state.get("messages", []), indent=2, ensure_ascii=False)
        st.download_button(
            label="Exportar JSON",
            data=export_data,
            file_name="historial_friday.json",
            mime="application/json",
            use_container_width=True
        )

# ==========================================
# 7. INICIALIZACIÓN DEL MODELO CACHEADO
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
# 8. ENCABEZADO Y ESTADO INICIAL
# ==========================================

st.title("Friday, tu tutora virtual")
st.caption("Asistente académica y de programación.")

if "messages" not in st.session_state:
    st.session_state.messages = []

if len(st.session_state.messages) == 0:
    welcome_msg = "Hola. Soy Friday, tu tutora virtual. ¿En qué tema o proyecto te gustaría trabajar hoy?"
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

# ==========================================
# 9. RENDERIZAR HISTORIAL DE MENSAJES
# ==========================================

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==========================================
# 10. HERRAMIENTAS ADJUNTAS COMPACTAS
# ==========================================

st.markdown("---")

col_file, col_voice = st.columns([2, 1])

with col_file:
    uploaded_file = st.file_uploader(
        "Adjuntar archivo (TXT, Python, JSON, CSV, PDF)",
        type=["txt", "py", "json", "csv", "md", "pdf"],
        label_visibility="collapsed"
    )

with col_voice:
    voice_toolbar()

file_context_text = ""
if uploaded_file is not None:
    try:
        file_bytes = uploaded_file.read()
        if uploaded_file.name.endswith(".pdf"):
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            extracted = [page.extract_text() for page in reader.pages if page.extract_text()]
            file_context_text = "\n".join(extracted)
        else:
            file_context_text = file_bytes.decode("utf-8", errors="ignore")
        
        st.caption(f"📎 Archivo adjunto: **{uploaded_file.name}**")
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")

# ==========================================
# 11. ENTRADA Y PROCESAMIENTO
# ==========================================

if prompt := st.chat_input("Escribe tu consulta aquí..."):

    final_prompt = prompt
    if file_context_text:
        final_prompt = f"[Contenido del archivo adjunto '{uploaded_file.name}']:\n{file_context_text}\n\n[Consulta]: {prompt}"
        file_context_text = ""

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    active_prompt = SYSTEM_PROMPTS[tutor_mode]
    history = [SystemMessage(content=active_prompt)]

    for message in st.session_state.messages:
        if message["role"] == "user":
            history.append(HumanMessage(content=message["content"]))
        elif message["role"] == "assistant":
            history.append(AIMessage(content=message["content"]))

    if uploaded_file is not None:
        history[-1] = HumanMessage(content=final_prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""

        try:
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

        except Exception as e:
            full_response = f"Ocurrió un inconveniente al generar la respuesta: `{e}`"
            st.error(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})
