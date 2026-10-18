import json
import time
import io
import base64
import sqlite3
import hashlib
import uuid
import streamlit as st
import streamlit.components.v1 as components
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==========================================

APP_VERSION = "v6.0 - Full-Stack Advanced Edition"

st.set_page_config(
    page_title="Friday - Tu Tutora Virtual",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. BASE DE DATOS AVANZADA (CRUD, STATS, FILES)
# ==========================================

def init_db():
    conn = sqlite3.connect("friday_v6.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chats (chat_id TEXT PRIMARY KEY, username TEXT NOT NULL, title TEXT NOT NULL, messages TEXT NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shared_links (link_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_stats (username TEXT, tokens INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_files (file_id TEXT PRIMARY KEY, username TEXT, filename TEXT, file_type TEXT, uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def hash_pass(p: str): return hashlib.sha256(p.encode()).hexdigest()

def register_user(u, p):
    try:
        conn = sqlite3.connect("friday_v6.db")
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (u, hash_pass(p)))
        conn.commit(); conn.close(); return True
    except: return False

def auth_user(u, p):
    conn = sqlite3.connect("friday_v6.db")
    res = conn.execute("SELECT password FROM users WHERE username = ?", (u,)).fetchone()
    conn.close()
    return res and res[0] == hash_pass(p)

def save_chat(chat_id, user, title, msgs):
    conn = sqlite3.connect("friday_v6.db")
    safe_msgs = []
    for m in msgs:
        if isinstance(m.get("content"), list):
            text = "".join([p.get("text", "") for p in m["content"] if isinstance(p, dict) and "text" in p])
            safe_msgs.append({"role": m["role"], "content": text if text else "[Contenido Multimedia Analizado]"})
        else: safe_msgs.append(m)
    conn.execute('''INSERT INTO chats (chat_id, username, title, messages, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(chat_id) DO UPDATE SET messages=excluded.messages, title=excluded.title, updated_at=CURRENT_TIMESTAMP''', 
                 (chat_id, user, title, json.dumps(safe_msgs, ensure_ascii=False)))
    conn.commit(); conn.close()

def get_chats(user):
    conn = sqlite3.connect("friday_v6.db")
    chats = conn.execute("SELECT chat_id, title FROM chats WHERE username = ? ORDER BY updated_at DESC", (user,)).fetchall()
    conn.close(); return chats

def load_chat(chat_id):
    conn = sqlite3.connect("friday_v6.db")
    res = conn.execute("SELECT messages FROM chats WHERE chat_id = ?", (chat_id,)).fetchone()
    conn.close(); return json.loads(res[0]) if res else []

def delete_chat(chat_id):
    conn = sqlite3.connect("friday_v6.db")
    conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
    conn.commit(); conn.close()

def rename_chat(chat_id, new_title):
    conn = sqlite3.connect("friday_v6.db")
    conn.execute("UPDATE chats SET title = ? WHERE chat_id = ?", (new_title, chat_id))
    conn.commit(); conn.close()

def log_usage(user, tokens):
    conn = sqlite3.connect("friday_v6.db")
    conn.execute("INSERT INTO user_stats (username, tokens) VALUES (?, ?)", (user, tokens))
    conn.commit(); conn.close()

def get_usage(user, period="all"):
    conn = sqlite3.connect("friday_v6.db")
    query = "SELECT SUM(tokens) FROM user_stats WHERE username = ?"
    if period == "week": query += " AND date >= date('now', '-7 days')"
    elif period == "month": query += " AND date >= date('now', '-1 month')"
    res = conn.execute(query, (user,)).fetchone()[0]
    conn.close(); return res if res else 0

def save_file_record(user, filename, ftype):
    conn = sqlite3.connect("friday_v6.db")
    conn.execute("INSERT INTO user_files (file_id, username, filename, file_type) VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), user, filename, ftype))
    conn.commit(); conn.close()

def get_user_files(user):
    conn = sqlite3.connect("friday_v6.db")
    files = conn.execute("SELECT filename, file_type, uploaded_at FROM user_files WHERE username = ? ORDER BY uploaded_at DESC", (user,)).fetchall()
    conn.close(); return files

def generate_share_link(chat_id):
    link_id = str(uuid.uuid4())[:8]
    conn = sqlite3.connect("friday_v6.db")
    conn.execute("INSERT INTO shared_links (link_id, chat_id) VALUES (?, ?)", (link_id, chat_id))
    conn.commit(); conn.close()
    return link_id

def import_shared_link(link_id, new_user):
    conn = sqlite3.connect("friday_v6.db")
    chat_id = conn.execute("SELECT chat_id FROM shared_links WHERE link_id = ?", (link_id,)).fetchone()
    if chat_id:
        msgs = load_chat(chat_id[0])
        new_chat_id = str(time.time())
        save_chat(new_chat_id, new_user, f"Importado: {link_id}", msgs)
        conn.close(); return new_chat_id
    conn.close(); return None

# ==========================================
# 3. API KEY Y LLM
# ==========================================
try: API_KEY = st.secrets["GOOGLE_API_KEY"]
except: st.error("Falta API Key en secrets."); st.stop()

@st.cache_resource
def get_llm(model, temp): return ChatGoogleGenerativeAI(model=model, google_api_key=API_KEY, temperature=temp, streaming=True)

# ==========================================
# 4. CSS FLUIDO Y ADAPTATIVO
# ==========================================

st.markdown("""
<style>
    .stChatMessage {
        animation: fadeIn 0.3s ease-in-out forwards;
        opacity: 0;
        transform: translateY(10px);
    }
    @keyframes fadeIn {
        to { opacity: 1; transform: translateY(0); }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 5. GESTIÓN DE SESIÓN Y LOGIN
# ==========================================

if "user" not in st.session_state: st.session_state.user = None
if "current_chat_id" not in st.session_state: st.session_state.current_chat_id = str(time.time())
if "messages" not in st.session_state: st.session_state.messages = []
if "view" not in st.session_state: st.session_state.view = "chat"

if st.session_state.user is None:
    st.title("🤖 Friday, tu tutora virtual")
    st.caption("v6.0 - Inicia sesión para acceder a tu ecosistema inteligente.")
    t1, t2 = st.tabs(["Iniciar Sesión", "Registrarse"])
    with t1:
        u = st.text_input("Usuario", key="l_u")
        p = st.text_input("Contraseña", type="password", key="l_p")
        if st.button("Entrar", use_container_width=True):
            if auth_user(u, p): st.session_state.user = u; st.rerun()
            else: st.error("Credenciales incorrectas.")
    with t2:
        nu = st.text_input("Nuevo Usuario", key="r_u")
        np = st.text_input("Nueva Contraseña", type="password", key="r_p")
        if st.button("Crear Cuenta", use_container_width=True):
            if register_user(nu, np): st.success("Cuenta creada. Inicia sesión.")
            else: st.warning("Usuario ocupado.")
    st.stop()

# ==========================================
# 6. PROMPTS DEL SISTEMA
# ==========================================
SYS_PROMPT = """
Eres Friday (v6.0), una tutora virtual inteligente, empática y avanzada.
REGLAS:
1. Responde de forma clara, profesional y estructurada.
2. Si te piden GENERAR UNA IMAGEN, responde estrictamente con este formato Markdown:
   ![Imagen Generada](https://image.pollinations.ai/prompt/{descripcion_en_ingles_detallada})
3. Si el usuario comparte un enlace web o de video, realiza un resumen analítico del contenido probable o contexto.
4. Puedes leer documentos y archivos subidos para resumirlos y explicarlos paso a paso.
"""

# ==========================================
# 7. MENÚ LATERAL (CRUD, CONFIGURACIÓN Y NAVEGACIÓN)
# ==========================================

with st.sidebar:
    st.title("Friday Ecosystem")
    st.caption(f"Usuario: **{st.session_state.user}**")
    
    col_nav1, col_nav2 = st.columns(2)
    if col_nav1.button("💬 Chat", use_container_width=True): st.session_state.view = "chat"; st.rerun()
    if col_nav2.button("⚙️ Ajustes", use_container_width=True): st.session_state.view = "ajustes"; st.rerun()

    st.divider()

    if st.session_state.view == "chat":
        st.subheader("Conversaciones (CRUD)")
        if st.button("➕ Nuevo Chat", use_container_width=True):
            st.session_state.current_chat_id = str(time.time()); st.session_state.messages = []; st.rerun()
        
        with st.expander("🔗 Compartir / Importar"):
            if st.button("Generar Link del Chat"):
                link = generate_share_link(st.session_state.current_chat_id)
                st.success(f"Código: **{link}**")
            
            import_code = st.text_input("Pegar código de acceso")
            if st.button("Importar por Link"):
                new_id = import_shared_link(import_code, st.session_state.user)
                if new_id: st.session_state.current_chat_id = new_id; st.session_state.messages = load_chat(new_id); st.rerun()
                else: st.error("Código inválido.")

            up_json = st.file_uploader("Importar JSON", type=["json"])
            if up_json:
                msgs = json.load(up_json)
                new_id = str(time.time())
                save_chat(new_id, st.session_state.user, "Importado JSON", msgs)
                st.session_state.current_chat_id = new_id
                st.session_state.messages = msgs
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        
        for c_id, title in get_chats(st.session_state.user):
            c1, c2, c3 = st.columns([6, 2, 2])
            if c1.button(f"{title[:15]}...", key=f"load_{c_id}"):
                st.session_state.current_chat_id = c_id; st.session_state.messages = load_chat(c_id); st.rerun()
            if c2.button("✏️", key=f"rn_{c_id}"): st.session_state[f"edit_{c_id}"] = True
            if c3.button("🗑️", key=f"del_{c_id}"): delete_chat(c_id); st.rerun()
            
            if st.session_state.get(f"edit_{c_id}"):
                new_t = st.text_input("Nuevo nombre:", key=f"inp_{c_id}")
                if st.button("Guardar", key=f"sv_{c_id}"):
                    rename_chat(c_id, new_t); st.session_state[f"edit_{c_id}"] = False; st.rerun()

    st.divider()

    # --- SELECTOR DE MODELOS RECUPERADO ---
    st.subheader("Parámetros de IA")
    selected_model = st.selectbox(
        "Modelo Gemini",
        ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-1.5-pro", "gemini-1.5-pro-latest"],
        index=0
    )
    temperature = st.slider("Creatividad (Temperatura)", 0.0, 1.0, 0.7, 0.1)

    st.divider()

    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state.user = None; st.session_state.messages = []; st.rerun()

# ==========================================
# 8. VISTA DE AJUSTES (ESTADÍSTICAS Y ARCHIVOS)
# ==========================================

if st.session_state.view == "ajustes":
    st.header("⚙️ Ajustes y Estadísticas")
    
    st.subheader("Estado de la Cuenta")
    periodo = st.selectbox("Filtrar uso por:", ["Última semana", "Último mes", "Todo el tiempo"])
    p_map = {"Última semana": "week", "Último mes": "month", "Todo el tiempo": "all"}
    
    tokens = get_usage(st.session_state.user, p_map[periodo])
    MAX_TOKENS = 500000 
    pct = min(tokens / MAX_TOKENS, 1.0)
    
    st.metric("Tokens/Caracteres procesados", f"{tokens:,}")
    st.progress(pct, text=f"Uso de cuota disponible ({int(pct*100)}%)")

    st.divider()
    st.subheader("🗄️ Bóveda de Archivos")
    st.caption("Historial de archivos e imágenes compartidas con Friday.")
    files = get_user_files(st.session_state.user)
    if not files: st.info("No hay archivos registrados todavía.")
    for fn, ft, dt in files:
        st.markdown(f"- **{fn}** (`{ft}`) - *{dt}*")
    st.stop()

# ==========================================
# 9. VISTA DEL CHAT PRINCIPAL
# ==========================================

st.title("🤖 Friday, Tu Asistente Virtual")
st.caption("Versión 6.0 — Ecosistema Inteligente con Multimodalidad, Bóveda y CRUD.")

llm = get_llm(selected_model, temperature)

if not st.session_state.messages:
    st.session_state.messages.append({"role": "assistant", "content": f"Hola, {st.session_state.user}. Soy **Friday**. ¿Qué Necesitas?"})

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]): st.markdown(msg["content"])

st.markdown("---")
c_file, c_voice = st.columns([4, 1])

with c_file:
    up_file = st.file_uploader("Adjuntar archivo o imagen", type=["png", "jpg", "jpeg", "webp", "pdf", "txt", "py", "csv", "mp3", "mp4"], label_visibility="collapsed")

with c_voice:
    components.html("""
    <div style="display:flex;height:38px;"><button id="m" onclick="run()" style="width:100%;border-radius:8px;border:1px solid #0284c7;background:transparent;color:inherit;cursor:pointer;">Dictar voz</button></div>
    <script>
      const sr=window.parent.SpeechRecognition||window.parent.webkitSpeechRecognition;
      function run(){
        if(!sr)return alert('Sin soporte de voz');
        let r=new sr(); r.lang='es-ES'; r.start();
        r.onresult=(e)=>{
          const inp=window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
          const set=Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype,"value").set;
          set.call(inp, e.results[0][0].transcript); inp.dispatchEvent(new window.parent.Event("input",{bubbles:true}));
        };
      }
    </script>
    """, height=45)

file_ctx, file_type, file_name = None, None, None

if up_file:
    file_name = up_file.name
    ext = file_name.split('.')[-1].lower()
    file_bytes = up_file.read()
    save_file_record(st.session_state.user, file_name, ext)
    
    if ext in ['png', 'jpg', 'jpeg', 'webp']:
        file_ctx = f"data:image/{ext};base64,{base64.b64encode(file_bytes).decode()}"
        file_type = "image"
        st.image(file_bytes, caption=file_name, width=200)
    elif ext == 'pdf':
        import pypdf
        file_ctx = "\n".join([p.extract_text() for p in pypdf.PdfReader(io.BytesIO(file_bytes)).pages if p.extract_text()])
        file_type = "text"
        st.caption(f"📄 PDF cargado: {file_name}")
    else:
        file_ctx = file_bytes.decode('utf-8', errors='ignore')
        file_type = "text"
        st.caption(f"📝 Archivo cargado: {file_name}")

if prompt := st.chat_input("Escribe tu consulta o pide una imagen..."):
    log_usage(st.session_state.user, len(prompt) + (len(file_ctx) if file_ctx else 0))

    display_p = f"{prompt}\n\n*[Adjunto: {file_name}]*" if file_name else prompt
    st.session_state.messages.append({"role": "user", "content": display_p})
    with st.chat_message("user"): st.markdown(display_p)

    history = [SystemMessage(content=SYS_PROMPT)]
    for msg in st.session_state.messages[:-1]:
        history.append(HumanMessage(content=msg["content"]) if msg["role"] == "user" else AIMessage(content=msg["content"]))

    if file_type == "image":
        history.append(HumanMessage(content=[{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": file_ctx}}]))
    elif file_type == "text":
        history.append(HumanMessage(content=f"[Contexto Archivo]:\n{file_ctx}\n\n[Consulta]: {prompt}"))
    else:
        history.append(HumanMessage(content=prompt))

    with st.chat_message("assistant"):
        resp_box = st.empty()
        full_r = ""
        try:
            for chunk in llm.stream(history):
                text = ""
                if isinstance(chunk.content, list):
                    text = "".join([p.get("text", "") for p in chunk.content if isinstance(p, dict)])
                else: text = str(chunk.content)
                full_r += text
                resp_box.markdown(full_r + "▌")
            resp_box.markdown(full_r)
        except Exception as e:
            full_r = f"Ocurrió un error: {e}"
            st.error(full_r)

    st.session_state.messages.append({"role": "assistant", "content": full_r})
    save_chat(st.session_state.current_chat_id, st.session_state.user, prompt[:25], st.session_state.messages)
