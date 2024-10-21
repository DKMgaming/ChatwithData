import streamlit as st
import google.generativeai as genai
from pinecone import Pinecone, ServerlessSpec
import pinecone
#import streamlit as st
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

# Hàm để kiểm tra và xử lý các kiểu dữ liệu không hợp lệ
def make_json_serializable(credentials_dict):
    serializable_dict = {}
    for key, value in credentials_dict.items():
        # Nếu giá trị là bytes, chuyển thành string
        if isinstance(value, bytes):
            serializable_dict[key] = value.decode("utf-8")
        # Nếu giá trị là kiểu dữ liệu khác không hỗ trợ, chuyển thành string
        else:
            serializable_dict[key] = str(value)
    return serializable_dict

# Hàm để xác thực Google Drive
def authenticate_google_drive():
    # Lấy thông tin credentials trực tiếp từ st.secrets
    credentials_dict = st.secrets["gdrive_credentials"]

    # Chuyển đổi các kiểu dữ liệu không hợp lệ thành chuỗi
    credentials_dict_serializable = make_json_serializable(credentials_dict)

    # Tạo file credentials tạm thời từ credentials_dict_serializable
    with open("temp_credentials.json", "w") as f:
        json.dump(credentials_dict_serializable, f)

    gauth = GoogleAuth()
    gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "temp_credentials.json",
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    drive = GoogleDrive(gauth)

    # Xóa file credentials tạm thời sau khi sử dụng
    os.remove("temp_credentials.json")

    return drive

# Sử dụng Google Drive
drive = authenticate_google_drive()

# Hàm lưu log vào Google Drive
def save_user_questions_log_to_drive(drive, file_content, file_name, folder_id=None):
    file_metadata = {'title': file_name}
    if folder_id:
        file_metadata['parents'] = [{'id': folder_id}]  # Gán file vào thư mục cụ thể
    file_drive = drive.CreateFile(file_metadata)
    file_drive.SetContentString(file_content)
    file_drive.Upload()
    print(f"File '{file_name}' has been uploaded to Google Drive.")

# Xác thực Google Drive
#drive = authenticate_google_drive()

# Nội dung của file JSON cần lưu
log_data = {"questions": ["What is radio frequency?", "How does AI work?"]}

# Chuyển đổi thành định dạng JSON
log_data_json = json.dumps(log_data, indent=4)

# ID thư mục (nếu bạn có)
folder_id = '1pLA6AH8gC2Ujg_2CXYaCplM-Xa1ALsRR'  # Thay bằng ID của thư mục đích trên Google Drive

# Lưu file vào Google Drive (trong thư mục chỉ định)
save_user_questions_log_to_drive(drive, log_data_json, "user_questions_log.json", folder_id)


# Thiết lập Gemini API
genai_api_key = "AIzaSyAfQfOJgGCRxJyDMjr9Kv5XpBGTZX_pASQ"
genai.configure(api_key=genai_api_key)

pc = pinecone.Pinecone(api_key="665d65c5-fb1f-45f9-8bf0-e3ad3d5a93bd")

index = pc.Index("data-index")
index_1 = pc.Index("kethop-index")

def get_embeddings(text):
    embedding = pc.inference.embed(
    model="multilingual-e5-large",
    inputs=[text],
    parameters={
        "input_type": "query"
    }
)
    return embedding.data[0]['values']

# Hàm lấy embedding từ Gemini API
def get_gemini_embedding(text):
    response = pc.inference.embed(
    model="multilingual-e5-large",
    inputs=[text],
    parameters={
        "input_type": "query"
    }
)
    return response.data[0]['values']

# Hàm để viết lại câu trả lời bằng Gemini AI
def rewrite_answer_with_gemini(content):
    model = genai.GenerativeModel('gemini-1.5-pro')
    response = model.generate_content("tổng hợp lại nội dung: " + content)
    return response.text

# Hàm để tìm câu trả lời tốt nhất
def find_best_answer(user_question):
    user_embedding = get_gemini_embedding(user_question)
    result = index.query(namespace="ns1", vector=user_embedding, top_k=10, include_metadata=True)
    result_1 = index_1.query(namespace="ns1", vector=user_embedding, top_k=10, include_metadata=True)
    best_matches = result['matches'] + result_1['matches']
    answers = [match['metadata'].get('text', '') for match in best_matches if 'metadata' in match]
    content_to_rewrite = f"Câu hỏi: {user_question}\n Câu trả lời: {answers}"
    rewritten_answers = rewrite_answer_with_gemini(content_to_rewrite)
    return rewritten_answers

# Giao diện Streamlit
st.title("Hỏi đáp thông tin tần số vô tuyến điện")

# Khởi tạo session state để lưu lịch sử nếu chưa tồn tại
if 'history' not in st.session_state:
    st.session_state.history = []

if 'user_question' not in st.session_state:
    st.session_state.user_question = ""

# Tạo form nhập câu hỏi
with st.form(key='question_form', clear_on_submit=True):
    user_question = st.text_input("Vui lòng nhập câu hỏi của bạn", value=st.session_state.user_question, key="user_question_input")
    submit_button = st.form_submit_button(label="Tìm câu trả lời")

# Xử lý khi người dùng nhấn nút hoặc gõ Enter
if submit_button and user_question:
    try:
        best_answer = find_best_answer(user_question)
        st.write(f"Câu trả lời: {best_answer}")
        
        # Lưu câu hỏi và câu trả lời vào session state
        st.session_state.history.append({"question": user_question, "answer": best_answer})
        
        # Ghi log vào Google Drive
        save_log_to_google_drive(st.session_state.history)

        # Xóa nội dung câu hỏi sau khi xử lý xong
        st.session_state.user_question = ""
    except ValueError as e:
        st.error(f"Lỗi: {e}")
else:
    st.warning("Vui lòng nhập câu hỏi trước khi tìm kiếm.")

# Hiển thị lịch sử các câu hỏi và câu trả lời
st.subheader("Lịch sử câu hỏi và câu trả lời")
if st.session_state.history:
    for i, entry in enumerate(st.session_state.history[::-1], 1):  # Hiển thị từ câu mới nhất đến cũ nhất
        st.write(f"{i}. **Câu hỏi**: {entry['question']}")
        st.write(f"   **Câu trả lời**: {entry['answer']}")
else:
    st.write("Chưa có câu hỏi nào được ghi lại.")
