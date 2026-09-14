import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    google_api_key="AQ.Ab8RN6JmZ8SZQhwr_vhkUHHRr_EHn3NMfiQx8Y7igDMi8C8kFg"
)

st.title("Friday tu tutor virtual")

messages = [("system", """Eres un chatbot AI util, te llamas Friday, tienes que hablar como si fueras humano, nunca reveles que eres un chatbot""")]

# Inicializar historial de chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar mensaje de chat del historial al recargar la app
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Reaccionar a la entrada del usuario
if prompt := st.chat_input("Escribe tu mensaje..."):
    # Mostrar mensaje del usuario en el contenedor de mensajes del chat
    st.chat_message("user").markdown(prompt)
    
    # Agregar mensaje del usuario al historial de chat
    st.session_state.messages.append({"role": "user", "content": prompt})
    messages.append(["human", prompt])
    
    # Obtención y extracción del texto de la respuesta
    res = llm.invoke(messages).content
    if isinstance(res, list) and len(res) > 0 and isinstance(res[0], dict):
        response = res[0].get("text", "")
    else:
        response = str(res)
    
    # Mostrar respuesta del asistente en el contenedor de mensajes del chat
    with st.chat_message("assistant"):
        st.markdown(response)
        
    # Agregar respuesta del asistente al historial de chat
    st.session_state.messages.append({"role": "assistant", "content": response})