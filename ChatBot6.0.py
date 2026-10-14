import json
import time
import io
import base64
import sqlite3
import hashlib
import streamlit as st
import streamlit.components.v1 as components
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y BASE DE DATOS
# ==========================================

APP_VERSION = "v6.0 - Multimodal Full-Stack"

st.set_page_config(
    page_title="Friday - Tu Tutora Virtual",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="expanded"
)

def init_db():
    conn = sqlite3.connect("friday_database.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            chat_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            title TEXT NOT NULL,
            messages TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (username) REFERENCES users (username)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    try:
        conn = sqlite3.connect("friday_database.db")
        c = conn.cursor()
        c.execute("INSERT INTO users VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def authenticate_user(username, password):
    conn = sqlite3.connect("friday_database.db")
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    if result and result[0] == hash_password(password):
        return True
    return False

def save_chat_to_db(chat_id, username, title, messages):
    conn = sqlite3.connect("friday_database.db")
    c = conn.cursor()
    
    # Limpiar o serializar mensajes complejos (como imágenes binarias en el historial) para JSON
    safe_messages = []
    for msg in messages:
        if isinstance(msg.get("content"), list):
            # Filtrar solo texto para guardar de forma ligera en SQLite
            text_content = "".join([part.get("text", "") for part in msg["content"] if isinstance(part, dict) and "text" in part])
            safe_messages.append({"role": msg["role"], "content": text_content if text_content else "[Archivo multimedia analizado]"})
        else:
            safe_messages.append(msg)

    messages_json = json.dumps(safe_messages, ensure_ascii=False)
    c.execute('''
        INSERT INTO chats (chat_id, username, title, messages)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET messages=excluded.messages, title=excluded.title
    ''', (chat_id, username, title, messages_json))
    conn.commit()
    conn.close()

def get_user_chats(username):
    conn = sqlite3.connect("friday_database.db")
    c = conn.cursor()
    c.execute("SELECT chat_id, title FROM chats WHERE username = ? ORDER BY created_at DESC", (username,))
    chats = c.fetchall()
    conn.close()
    return chats

def load_chat_from_db(chat_id):
    conn = sqlite3.connect("friday_database.db")
    c = conn.cursor()
    c.execute("SELECT messages FROM chats WHERE chat_id = ?", (chat_id,))
    result = c.fetchone()
    conn.close()
    if result:
        return json.loads(result[0])
    return []

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
# 3. GESTIÓN DE SESIÓN Y LOGIN
# ==========================================

if "user" not in st.session_state:
    st.session_state.user = None
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = str(time.time())
if "messages" not in st.session_state:
    st.session_state.messages = []

if st.session_state.user is None:
    st.title("🤖 Friday, tu tutora virtual")
    st.caption("Inicia sesión o regístrate para acceder a tus tutores y chats guardados.")
    
    tab_login, tab_register = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    with tab_login:
        u = st.text_input("Usuario", key="login_u")
        p = st.text_input("Contraseña", type="password", key="login_p")
        if st.button("Entrar", use_container_width=True):
            if authenticate_user(u, p):
                st.session_state.user = u
                st.success(f"Bienvenido de nuevo, {u}.")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")

    with tab_register:
        new_u = st.text_input("Nuevo Usuario", key="reg_u")
        new_p = st.text_input("Nueva Contraseña", type="password", key="reg_p")
        if st.button("Crear Cuenta", use_container_width=True):
            if new_u and new_p:
                if register_user(new_u, new_p):
                    st.success("Cuenta creada exitosamente. Ya puedes iniciar sesión.")
                else:
                    st.warning("El nombre de usuario ya está ocupado.")
            else:
                st.warning("Completa todos los campos.")
    st.stop()

# ==========================================
# 4. PROMPTS DEL SISTEMA
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
    - Utiliza analogías del mundo real, metáforas y un lenguaje libre de tecnicismos innecesarios.
    - Mantén las respuestas breves, didácticas y ordenadas.
    - Nunca reveles que eres una IA o modelo de lenguaje.
    """
}

# ==========================================
# 5. ESTILOS CSS CON DEGRADADOS (AISLADO DEL SISTEMA OPERATIVO)
# ==========================================

def load_custom_css(theme: str):
    if theme == "Oscuro (Deep Navy)":
        bg_gradient = "linear-gradient(180deg, #0f172a 0%, #020617 100%)"
        bg_sidebar = "linear-gradient(180deg, #1e293b 0%, #0f172a 100%)"
        text_color = "#f8fafc"
        border_color = "#334155"
        accent_blue = "#38bdf8"
        chat_bg = "#020617"
    elif theme == "Claro (Soft Blue)":
        bg_gradient = "linear-gradient(180deg, #e0f2fe 0%, #ffffff 100%)"
        bg_sidebar = "linear-gradient(180deg, #bae6fd 0%, #e0f2fe 100%)"
        text_color = "#0f172a"
        border_color = "#93c5fd"
        accent_blue = "#0284c7"
        chat_bg = "#ffffff"
    else:  # Predeterminado del sistema
        bg_gradient = "transparent"
        bg_sidebar = "transparent"
        text_color = "inherit"
        border_color = "#cbd5e1"
        accent_blue = "#0284c7"
        chat_bg = "transparent"

    css = f"""
    <style>
        /* Forzar anulación del esquema de color del sistema operativo para evitar bugs cruzados */
        @media (prefers-color-scheme: dark), (prefers-color-scheme: light) {{
            .stApp {{
                background: {bg_gradient} !important;
                color: {text_color} !important;
            }}
            section[data-testid="stSidebar"] {{
                background: {bg_sidebar} !important;
                border-right: 1px solid {border_color} !important;
            }}
        }}

        p, span, label, h1, h2, h3, h4, h5, h6, div[data-testid="stMarkdownContainer"] {{
            color: {text_color} !important;
        }}

        div[data-testid="stChatInput"] {{
            background-color: {chat_bg} !important;
            border: 1px solid {border_color} !important;
            border-radius: 12px !important;
        }}
        
        div[data-testid="stChatInput"] textarea {{
            color: {text_color} !important;
        }}

        .stButton button {{
            background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important;
            color: white !important;
            border-radius: 8px !important;
            border: none !important;
            font-weight: 500 !important;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ==========================================
# 6. COMPONENTE WEB DE VOZ
# ==========================================

VOICE_HTML = """
<style>
  body { margin:0; font-family: sans-serif; background: transparent; }
  .wrap { display:flex; align-items:center; gap:8px; height: 38px; }
  #mic {
    background:#0284c7; color:#fff; border:none; border-radius:6px;
    padding:8px 12px; font-size:13px; cursor:pointer; font-weight: 500; width: 100%;
  }
  #mic.on { background:#16a34a; }
</style>
<div class="wrap">
  <button id="mic">Dictar por voz</button>
</div>
<script>
  const LANG = "__LANG__";
  const P = window.parent;
  const SR = P.SpeechRecognition || P.webkitSpeechRecognition || window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = document.getElementById("mic");

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

  if (SR) {
    const rec = new SR();
    rec.lang = LANG;
    rec.continuous = true;
    rec.interimResults = true;
    let listening = false;
    let finalText = "";

    rec.onstart = () => {
      listening = true;
      btn.classList.add("on");
      btn.textContent = "Detener voz";
    };

    rec.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += t + " ";
        else interim += t;
      }
      setInput((finalText + interim).trim());
    };

    rec.onend = () => {
      listening = false;
      btn.classList.remove("on");
      btn.textContent = "Dictar por voz";
      finalText = "";
    };

    btn.onclick = () => {
      if (listening) { rec.stop(); }
      else { finalText = ""; setInput(""); try { rec.start(); } catch (e) {} }
    };
  }
</script>
"""

def voice_dictation(lang: str):
    html = VOICE_HTML.replace("__LANG__", lang)
    components.html(html, height=45, allow="microphone")

# ==========================================
# 7. BARRA LATERAL Y NAVEGACIÓN
# ==========================================

with st.sidebar:
    st.title("Friday Config")
    st.caption(f"Usuario activo: {st.session_state.user}")
    
    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state.user = None
        st.session_state.messages = []
        st.rerun()

    st.divider()

    st.subheader("Apariencia")
    theme_choice = st.selectbox(
        "Tema de Interfaz",
        ["Predeterminado del sistema", "Claro (Soft Blue)", "Oscuro (Deep Navy)"],
        index=0
    )
    load_custom_css(theme_choice)

    st.divider()

    st.subheader("Mis Conversaciones")
    if st.button("Nueva Conversación", use_container_width=True):
        st.session_state.current_chat_id = str(time.time())
        st.session_state.messages = []
        st.rerun()

    user_chats = get_user_chats(st.session_state.user)
    if user_chats:
        chat_options = {title: chat_id for chat_id, title in user_chats}
        selected_chat_title = st.selectbox("Historial de Chats", list(chat_options.keys()))
        if st.button("Cargar Chat Seleccionado", use_container_width=True):
            st.session_state.current_chat_id = chat_options[selected_chat_title]
            st.session_state.messages = load_chat_from_db(st.session_state.current_chat_id)
            st.rerun()

    st.divider()

    st.subheader("Parámetros de IA")
    selected_model = st.selectbox(
        "Modelo Gemini",
        ["gemini-3.6-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        index=0
    )
    tutor_mode = st.selectbox("Modo de Tutoría", list(SYSTEM_PROMPTS.keys()), index=0)
    temperature = st.slider("Creatividad (Temperatura)", 0.0, 1.0, 0.7, 0.1)

    st.divider()

    st.subheader("Configuración de Voz")
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
# 9. ENCABEZADO Y RENDERIZADO DE MENSAJES
# ==========================================

st.title("🤖 Friday, tu tutora virtual")
st.caption("Versión 6.0 — Asistente avanzada con soporte multimodal (imágenes y archivos), base de datos y temas dinámicos.")

if len(st.session_state.messages) == 0:
    welcome_msg = f"Hola, {st.session_state.user}. Soy **Friday**, tu tutora virtual. ¿Qué tema, código o imagen analizaremos hoy?"
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==========================================
# 10. HERRAMIENTAS INFERIORES Y ARCHIVOS (MULTIMODAL)
# ==========================================

st.markdown("---")
col_file, col_voice_widget = st.columns([3, 1])

# Permitir todo tipo de archivos y especialmente imágenes (png, jpg, jpeg, webp) además de documentos
with col_file:
    uploaded_file = st.file_uploader(
        "Adjuntar archivo o imagen (Imágenes, PDF, TXT, Python, JSON, CSV)",
        type=["png", "jpg", "jpeg", "webp", "txt", "py", "json", "csv", "md", "pdf"],
        label_visibility="collapsed"
    )

with col_voice_widget:
    voice_dictation(voice_lang)

file_context_data = None
file_type = None
file_name = None

if uploaded_file is not None:
    file_name = uploaded_file.name
    file_extension = file_name.split(".")[-1].lower()
    
    image_extensions = ["png", "jpg", "jpeg", "webp"]
    
    if file_extension in image_extensions:
        file_bytes = uploaded_file.read()
        encoded_img = base64.b64encode(file_bytes).decode("utf-8")
        mime_subtype = "jpeg" if file_extension == "jpg" else file_extension
        file_context_data = f"data:image/{mime_subtype};base64,{encoded_img}"
        file_type = "image"
        st.image(file_bytes, caption=f"Imagen adjunta: {file_name}", width=250)
    else:
        try:
            file_bytes = uploaded_file.read()
            if file_extension == "pdf":
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                extracted = [page.extract_text() for page in reader.pages if page.extract_text()]
                file_context_data = "\n".join(extracted)
            else:
                file_context_data = file_bytes.decode("utf-8", errors="ignore")
            file_type = "text"
            st.caption(f"Archivo de texto adjunto activo: **{file_name}**")
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")

# ==========================================
# 11. ENTRADA Y PROCESAMIENTO MULTIMODAL
# ==========================================

if prompt := st.chat_input("Escribe tu duda o pregunta..."):

    # Construir mensaje de usuario y adjuntos para LangChain / Gemini
    user_display_content = prompt
    if file_name:
        user_display_content += f"\n\n[Archivo adjunto: {file_name}]"

    st.session_state.messages.append({"role": "user", "content": user_display_content})
    with st.chat_message("user"):
        st.markdown(user_display_content)

    active_prompt = SYSTEM_PROMPTS[tutor_mode]
    history = [SystemMessage(content=active_prompt)]

    for message in st.session_state.messages[:-1]:
        if message["role"] == "user":
            history.append(HumanMessage(content=message["content"]))
        elif message["role"] == "assistant":
            history.append(AIMessage(content=message["content"]))

    # Adjuntar el último mensaje con soporte multimodal si hay archivo o imagen
    if file_type == "image":
        human_content = [
            {"type": "text", "text": prompt if prompt else "Analiza esta imagen."},
            {"type": "image_url", "image_url": {"url": file_context_data}}
        ]
        history.append(HumanMessage(content=human_content))
    elif file_type == "text":
        enriched_prompt = f"[Contenido del archivo '{file_name}']: \n{file_context_data}\n\n[Pregunta]: {prompt}"
        history.append(HumanMessage(content=enriched_prompt))
    else:
        history.append(HumanMessage(content=prompt))

    # Limpiar referencias de archivo tras enviar
    file_context_data = None
    file_type = None
    file_name = None

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
            full_response = f"Ocurrió un error al generar la respuesta: `{e}`"
            st.error(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})

    # Guardar conversación en SQLite
    first_user_msg = prompt[:30] if len(prompt) > 30 else prompt
    save_chat_to_db(
        st.session_state.current_chat_id,
        st.session_state.user,
        f"Chat: {first_user_msg}",
        st.session_state.messages
    )
