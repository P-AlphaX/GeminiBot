import json
import time
import io
import streamlit as st
import streamlit.components.v1 as components
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==========================================

APP_VERSION = "v5.0 - Original Estable"

st.set_page_config(
    page_title="Friday - Tu Tutora Virtual",
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
# 3. PROMPTS DEL SISTEMA
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
# 4. COMPONENTE DE VOZ NATIVO Y SEGURO
# ==========================================

VOICE_HTML = """
<div style="display: flex; align-items: center; height: 38px;">
  <button id="mic-btn" onclick="toggleVoice()" style="background: transparent; border: 1px solid rgba(150,150,150,0.4); border-radius: 6px; padding: 6px 12px; cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: 13px; color: inherit; width: 100%; justify-content: center;">
    🎤 <span id="mic-txt">Dictar voz</span>
  </button>
</div>
<script>
  const P = window.parent;
  const SR = P.SpeechRecognition || P.webkitSpeechRecognition || window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  let active = false;

  function getTA() { 
    return P.document.querySelector('textarea[data-testid="stChatInputTextArea"]'); 
  }
  
  function setVal(t) {
    const ta = getTA();
    if (!ta) return;
    const setter = Object.getOwnPropertyDescriptor(P.HTMLTextAreaElement.prototype, "value").set;
    setter.call(ta, t);
    ta.dispatchEvent(new P.Event("input", { bubbles: true }));
  }

  function toggleVoice() {
    if (!SR) { 
      alert("Tu navegador no soporta reconocimiento de voz. Usa Google Chrome o Microsoft Edge."); 
      return; 
    }
    const btn = document.getElementById("mic-btn");
    const txt = document.getElementById("mic-txt");
    
    if (active) { 
      rec.stop(); 
      return; 
    }
    
    rec = new SR();
    rec.lang = "es-ES";
    rec.continuous = true;
    rec.interimResults = true;
    
    let base = getTA() ? getTA().value + " " : "";
    
    rec.onstart = () => { 
      active = true; 
      btn.style.borderColor = "#16A34A"; 
      btn.style.color = "#16A34A";
      txt.textContent = "Escuchando..."; 
    };
    
    rec.onresult = (e) => {
      let interim = ""; 
      let finalStr = "";
      for (let i = e.resultIndex; i < e.results.length; ++i) {
        if (e.results[i].isFinal) finalStr += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      if (finalStr) base += finalStr + " ";
      setVal((base + interim).trim());
    };
    
    rec.onend = () => { 
      active = false; 
      btn.style.borderColor = "rgba(150,150,150,0.4)"; 
      btn.style.color = "inherit";
      txt.textContent = "Dictar voz"; 
    };
    
    try { rec.start(); } catch(ex) { console.error(ex); }
  }
</script>
"""

# ==========================================
# 5. PANEL DE CONTROL (BARRA LATERAL)
# ==========================================

with st.sidebar:
    st.title("Panel de Control")
    st.caption(f"Versión: {APP_VERSION}")
    st.divider()

    st.subheader("Configuración de IA")
    selected_model = st.selectbox(
        "Modelo",
        ["gemini-3.6-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        index=0
    )
    tutor_mode = st.selectbox("Modo de Tutoría", list(SYSTEM_PROMPTS.keys()), index=0)
    temperature = st.slider("Temperatura", 0.0, 1.0, 0.7, 0.1)

    st.divider()

    st.subheader("Historial")
    uploaded_history = st.file_uploader(
        "Cargar archivo JSON previo",
        type=["json"],
        help="Recupera una sesión anterior."
    )
    if uploaded_history is not None:
        try:
            loaded_msgs = json.load(uploaded_history)
            if isinstance(loaded_msgs, list):
                st.session_state.messages = loaded_msgs
                st.success("Historial recuperado con éxito.")
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")

    st.divider()

    if st.button("Limpiar conversación", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    msg_count = len(st.session_state.get("messages", []))
    st.metric("Mensajes en sesión", msg_count)

    if msg_count > 0:
        export_data = json.dumps(st.session_state.get("messages", []), indent=2, ensure_ascii=False)
        st.download_button(
            label="Exportar Chat (JSON)",
            data=export_data,
            file_name="historial_friday.json",
            mime="application/json",
            use_container_width=True
        )

# ==========================================
# 6. INICIALIZACIÓN DEL MODELO CACHEADO
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
# 7. ENCABEZADO Y CHAT
# ==========================================

st.title("Friday, tu tutora virtual")
st.caption("Asistente académica y de programación.")

if "messages" not in st.session_state:
    st.session_state.messages = []

if len(st.session_state.messages) == 0:
    welcome_msg = "Hola. Soy Friday, tu tutora virtual. ¿En qué tema o proyecto te gustaría trabajar hoy?"
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==========================================
# 8. ZONA DE HERRAMIENTAS Y ARCHIVOS
# ==========================================

st.markdown("---")

col_file, col_voice = st.columns([3, 1])

with col_file:
    uploaded_file = st.file_uploader(
        "Adjuntar archivo de referencia",
        type=["txt", "py", "json", "csv", "md", "pdf"],
        label_visibility="collapsed"
    )

with col_voice:
    components.html(VOICE_HTML, height=40)

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
        
        st.caption(f"Archivo adjunto activo: **{uploaded_file.name}**")
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")

# ==========================================
# 9. ENTRADA DE CHAT Y PROCESAMIENTO
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
