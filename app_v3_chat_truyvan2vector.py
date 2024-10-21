import streamlit as st
import google.generativeai as genai
import pinecone
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

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
    # Chuyển đổi log_data thành dạng văn bản với UTF-8
    file_content = ""
    
    # Nếu log_data là danh sách, duyệt qua từng mục (câu hỏi và câu trả lời)
    if isinstance(log_data, list):
        for item in log_data:
            question = item.get("question", "")
            answer = item.get("answer", "")
            file_content += f"Câu hỏi: {question}\n"
            file_content += f"Trả lời: {answer}\n\n"
    else:
        file_content = str(log_data)

    # Tạo metadata và lưu file dưới dạng .txt
    file_metadata = {'title': file_name + ".txt"}  # Đặt phần mở rộng là .txt
    if folder_id:
        file_metadata['parents'] = [{'id': folder_id}]  # Gán file vào thư mục cụ thể

    file_drive = drive.CreateFile(file_metadata)
    
    # Lưu nội dung văn bản tiếng Việt (đã xử lý UTF-8)
    file_drive.SetContentString(file_content)
    file_drive.Upload()
    
    print(f"File '{file_name}.txt' đã được tải lên Google Drive.")
# Thiết lập Gemini API
genai_api_key = "AIzaSyAfQfOJgGCRxJyDMjr9Kv5XpBGTZX_pASQ"
genai.configure(api_key=genai_api_key)

pc = pinecone.Pinecone(api_key="665d65c5-fb1f-45f9-8bf0-e3ad3d5a93bd")

index = pc.Index("data-index")
index_1 = pc.Index("kethop-index")

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

def rewrite_answer_with_gemini(content):
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Tổng hợp lại nội dung: " + content)
    return response.text

def find_best_answer(user_question):
    user_embedding = get_gemini_embedding(user_question)
    result = index.query(namespace="ns1", vector=user_embedding, top_k=10, include_metadata=True)
    result_1 = index_1.query(namespace="ns1", vector=user_embedding, top_k=10, include_metadata=True)
    best_matches = result['matches'] + result_1['matches']
    answers = [match['metadata'].get('text', '') for match in best_matches if 'metadata' in match]
    content_to_rewrite = f"Câu hỏi: {user_question}\nCâu trả lời: {answers}"
    rewritten_answers = rewrite_answer_with_gemini(content_to_rewrite)
    return rewritten_answers

# Giao diện Streamlit
st.title("Hỏi đáp thông tin tần số vô tuyến điện")

if 'history' not in st.session_state:
    st.session_state.history = []

if 'user_question' not in st.session_state:
    st.session_state.user_question = ""

with st.form(key='question_form', clear_on_submit=True):
    user_question = st.text_input("Vui lòng nhập câu hỏi của bạn", value=st.session_state.user_question, key="user_question_input")
    submit_button = st.form_submit_button(label="Tìm câu trả lời")

if submit_button and user_question:
    try:
        best_answer = find_best_answer(user_question)
        st.write(f"Câu trả lời: {best_answer}")
        
        st.session_state.history.append({"question": user_question, "answer": best_answer})

        log_data_json = json.dumps(st.session_state.history, indent=4)
        folder_id = '1pLA6AH8gC2Ujg_2CXYaCplM-Xa1ALsRR'
        save_user_questions_log_to_drive(drive, log_data_json, "user_questions_log.json", folder_id)

        st.session_state.user_question = ""
    except ValueError as e:
        st.error(f"Lỗi: {e}")
else:
    st.warning("Vui lòng nhập câu hỏi trước khi tìm kiếm.")

st.subheader("Lịch sử câu hỏi và câu trả lời")
if st.session_state.history:
    for i, entry in enumerate(st.session_state.history[::-1], 1):
        st.write(f"{i}. **Câu hỏi**: {entry['question']}")
        st.write(f"   **Câu trả lời**: {entry['answer']}")
else:
    st.write("Chưa có câu hỏi nào được ghi lại.")
