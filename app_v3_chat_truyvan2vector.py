import streamlit as st
import google.generativeai as genai
from pinecone import Pinecone
import json
import os

# Thiết lập Gemini API key
genai_api_key = "AIzaSyAfQfOJgGCRxJyDMjr9Kv5XpBGTZX_pASQ"  # Thay thế bằng API key của bạn
genai.configure(api_key=genai_api_key)

# Thiết lập Pinecone
pc = Pinecone(api_key="665d65c5-fb1f-45f9-8bf0-e3ad3d5a93bd")
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

# Hàm lưu log vào file trên server
def save_log_to_server(history, log_filename="user_questions_log.json"):
    # Ghi file vào thư mục logs (hoặc thư mục tùy chọn trên server)
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)  # Tạo thư mục nếu chưa có
    log_file_path = os.path.join(logs_dir, log_filename)

    # Ghi hoặc cập nhật log file
    with open(log_file_path, "w", encoding='utf-8') as log_file:
        json.dump(history, log_file, ensure_ascii=False, indent=4)

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
        
        # Ghi log vào file trên server
        save_log_to_server(st.session_state.history)

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
