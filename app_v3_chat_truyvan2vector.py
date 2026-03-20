import streamlit as st
import time
import google.generativeai as genai
import pinecone
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import pyttsx3

# Hàm để kiểm tra và xử lý các kiểu dữ liệu không hợp lệ
def make_json_serializable(credentials_dict):
    serializable_dict = {}
    for key, value in credentials_dict.items():
        if isinstance(value, bytes):
            serializable_dict[key] = value.decode("utf-8")
        else:
            serializable_dict[key] = str(value)
    return serializable_dict

# Hàm để xác thực Google Drive
def authenticate_google_drive():
    credentials_dict = st.secrets["gdrive_credentials"]
    credentials_dict_serializable = make_json_serializable(credentials_dict)

    with open("temp_credentials.json", "w") as f:
        json.dump(credentials_dict_serializable, f)

    gauth = GoogleAuth()
    gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "temp_credentials.json",
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    drive = GoogleDrive(gauth)
    os.remove("temp_credentials.json")

    return drive

# Sử dụng Google Drive
drive = authenticate_google_drive()

def save_user_questions_log_to_drive(drive, log_data, file_name, folder_id=None):
    file_content = ""

    if isinstance(log_data, list):
        for item in log_data:
            question = item.get("question", "")
            answer = item.get("answer", "")
            file_content += f"Câu hỏi: {question}\n"
            file_content += f"Trả lời: {answer}\n\n"
    else:
        file_content = str(log_data)

    file_metadata = {'title': file_name + ".txt"}
    if folder_id:
        file_metadata['parents'] = [{'id': folder_id}]

    file_drive = drive.CreateFile(file_metadata)
    file_drive.SetContentString(file_content.encode('utf-8').decode('utf-8'))
    file_drive.Upload()
    
    print(f"File '{file_name}.txt' đã được tải lên Google Drive.")

# Thiết lập Gemini API
genai_api_key = "AIzaSyAfQfOJgGCRxJyDMjr9Kv5XpBGTZX_pASQ"
genai.configure(api_key=genai_api_key)

# Danh sách API key của Gemini
gemini_models = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    
]

current_model_index = 0

def set_next_gemini_model():
    global current_model_index
    current_model_index += 1
    if current_model_index >= len(gemini_models):
        st.error("Tất cả các model đã hết giới hạn token hoặc không hợp lệ.")
        return False
    else:
        return True

pc = pinecone.Pinecone(api_key="665d65c5-fb1f-45f9-8bf0-e3ad3d5a93bd")
index = pc.Index("pdf-chunks")
index_1 = pc.Index("pdf-chunks")
index_2 = pc.Index("pdf-chunks")

def get_gemini_embedding(text):
    response = pc.inference.embed(
        model="multilingual-e5-large",
        inputs=[text],
        parameters={
            "input_type": "query"
        }
    )
    return response.data[0]['values']

def rewrite_answer_with_gemini(content):
    global current_model_index
    try:
        model_name = gemini_models[current_model_index]
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Bạn là Trợ lý về tần số vô tuyến điện hãy cho câu trả lời tối ưu nhất" + content)
        return response.text
    except Exception as e:
        if set_next_gemini_model():
            return rewrite_answer_with_gemini(content)
        else:
            return "Không thể lấy câu trả lời do tất cả các model đã hết giới hạn token."

def find_best_answer(user_question):
    user_embedding = get_gemini_embedding(user_question)
    result = index.query(namespace="ns1", vector=user_embedding, top_k=5, include_metadata=True)
    result_1 = index_1.query(namespace="ns1", vector=user_embedding, top_k=5, include_metadata=True)
    result_2 = index_2.query(namespace="ns1", vector=user_embedding, top_k=5, include_metadata=True)
    best_matches = result['matches'] + result_1['matches'] + result_2['matches']
    answers = [match['metadata'].get('text', '') for match in best_matches if 'metadata' in match]
    content_to_rewrite = f"Câu hỏi: {user_question}\nCâu trả lời: {answers}"
    rewritten_answers = rewrite_answer_with_gemini(content_to_rewrite)
    return rewritten_answers

# Giao diện Streamlit
st.markdown("<h1 style='text-align: center;'>Hỏi đáp về tần số vô tuyến điện</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 12px; color: grey;'>@copyright Ngo Minh Tri</p>", unsafe_allow_html=True)

if 'history' not in st.session_state:
    st.session_state.history = []

def typing_effect(text, container, speed=0.01):
    displayed_text = ""
    for char in text:
        displayed_text += char
        container.markdown(f"<p style='text-align: left;'>{displayed_text}</p>", unsafe_allow_html=True)
        time.sleep(speed)
def speak_text(text):
    engine = pyttsx3.init()
    engine.setProperty("rate", 150)  # Điều chỉnh tốc độ đọc
    engine.say(text)
    engine.runAndWait()

with st.form(key='question_form', clear_on_submit=True):
    user_question = st.text_input("💬 Bạn: ", key="user_question_input")
    submit_button = st.form_submit_button(label="Gửi câu hỏi")

if submit_button and user_question:
    try:
        best_answer = find_best_answer(user_question)
        st.session_state.history.append({"question": user_question, "answer": best_answer})
        folder_id = '1pLA6AH8gC2Ujg_2CXYaCplM-Xa1ALsRR'
        save_user_questions_log_to_drive(drive, st.session_state.history, "user_questions_log.txt", folder_id)
        container = st.empty()
        #st.markdown("<strong>Trợ lý vui vẻ:</strong>", unsafe_allow_html=True)
        typing_effect(best_answer, container)
        # Thêm nút đọc câu trả lời
        if st.button("🔊 Đọc câu trả lời"):
            speak_text(best_answer)
    except ValueError as e:
        st.error(f"Lỗi: {e}")
else:
    st.warning("Vui lòng nhập câu hỏi trước khi tìm kiếm.")

st.subheader("📜 Lịch sử hội thoại")
if st.session_state.history:
    for i, entry in enumerate(st.session_state.history[::-1], 1):
        st.markdown(f"<div style='border: 1px solid #f0f0f0; padding: 10px; margin-bottom: 5px;'><strong>Bạn:</strong> {entry['question']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='border: 1px solid #f0f0f0; padding: 10px; background-color: #f9f9f9;'><strong>Trợ lý vui vẻ:</strong> {entry['answer']}</div>", unsafe_allow_html=True)
else:
    st.write("Chưa có câu hỏi nào được ghi lại.")

