import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# ==========================================
# 1. CONFIGURACIÓN SEGURA DE LA API KEY
# ==========================================

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "Falta configurar la API Key. "
        "Crea el archivo .streamlit/secrets.toml "
        "con GOOGLE_API_KEY."
    )
    st.stop()

# ==========================================
# 2. CONFIGURACIÓN DEL MODELO
# ==========================================

@st.cache_resource
def get_llm():
    return ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    google_api_key=API_KEY,
    temperature=0.7,
    streaming=True,
    )

llm = get_llm()

# ==========================================
# 3. PROMPT DEL SISTEMA
# ==========================================

SYSTEM_PROMPT = """Eres Friday, un tutor virtual amigable, inteligente y humano.

Reglas:
- Habla de forma natural y cercana, como un amigo que sabe mucho.
- Usa ejemplos claros y sencillos para explicar.
- Nunca reveles que eres una IA, un chatbot o un modelo de lenguaje.
- Si no sabes algo, dilo con honestidad y ofrece ayuda alternativa.
- Responde siempre en el idioma del usuario.
"""

# ==========================================
# 4. INTERFAZ DE USUARIO
# ==========================================

st.set_page_config(
    page_title="Friday - Tu Tutor Virtual",
    page_icon="🤖"
)

st.title("🤖 Friday, tu tutora virtual")

# ==========================================
# 5. BARRA LATERAL
# ==========================================

with st.sidebar:
    st.header("Opciones")

    if st.button("🗑️ Reiniciar conversación"):
        st.session_state.messages = []
        st.rerun()

    st.caption("Friday v2.0 - Mejorada")

# ==========================================
# 6. INICIALIZAR HISTORIAL
# ==========================================

if "messages" not in st.session_state:
    st.session_state.messages = []

# ==========================================
# 7. MOSTRAR HISTORIAL
# ==========================================

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==========================================
# 8. LÓGICA DEL CHAT
# ==========================================

if prompt := st.chat_input("Escribe tu mensaje..."):

    # Mostrar mensaje del usuario
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    # Construir historial para LangChain
    history = [
        SystemMessage(content=SYSTEM_PROMPT)
    ]

    for msg in st.session_state.messages:

        if msg["role"] == "user":
            history.append(
                HumanMessage(content=msg["content"])
            )

        else:
            history.append(
                AIMessage(content=msg["content"])
            )

    # Generar respuesta
    with st.chat_message("assistant"):

        try:
            response_placeholder = st.empty()
            full_response = ""

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

                response_placeholder.markdown(
                    full_response + "▌"
                )

            response_placeholder.markdown(
                full_response
            )

        except Exception as e:

            full_response = (
                f"😅 Ups, tuve un problema: `{e}`. "
                "¿Intentamos de nuevo?"
            )

            st.error(full_response)

    # Guardar respuesta
    st.session_state.messages.append({
        "role": "assistant",
        "content": full_response
    })